import re

from sqlalchemy.orm import Session

from app.shot_breakdown.service_v2 import get_shot_breakdown
from app.source_analysis.schemas import (
    SourceAssetShotRef,
    SourceAnalysisState,
    SourceCharacterAssetCard,
    SourcePropAssetCard,
    SourceSceneAssetCard,
    SourceScriptDialogue,
    SourceScriptEntity,
    SourceScriptRead,
    SourceScriptScene,
    SourceScriptShot,
)
from app.source_analysis.service import get_source_analysis_status
from app.source_resolution.service_v2 import get_source_resolution


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _scene_name(scene_id: str | None, scene_names: dict[str, str]) -> str:
    if scene_id is None:
        return "未识别场景"
    return scene_names.get(scene_id, "未命名场景")


_DESCRIPTION_PARTS = re.compile(r"(?<=[。！？!?；;])\s*")
_CAMERA_METADATA_PREFIX = re.compile(
    r"^(?:景别|构图|镜头(?:语言|类型|角度|运动)?|机位|运镜|焦距|景深)\s*[:：]"
)


def _action_summary(
    visual_description: str,
    *,
    visible_character_names: set[str],
    camera_values: tuple[str, ...],
) -> str:
    """Conservatively reduce camera-only prose without inventing action.

    Character-bearing clauses are safe presentation candidates because P9 already
    binds those characters to this exact Shot. If the rule cannot isolate a
    useful clause, the accepted P8 description is preserved verbatim (apart from
    whitespace normalization).
    """

    normalized = " ".join(visual_description.split())
    if not normalized:
        return normalized
    parts = [part.strip() for part in _DESCRIPTION_PARTS.split(normalized) if part.strip()]
    camera_tokens = {" ".join(value.split()).rstrip("。！？!?；;，,") for value in camera_values if value.strip()}

    def camera_only(part: str) -> bool:
        plain = part.rstrip("。！？!?；;，,").strip()
        return bool(_CAMERA_METADATA_PREFIX.match(plain)) or plain in camera_tokens

    character_actions = [
        part
        for part in parts
        if not camera_only(part) and any(name and name in part for name in visible_character_names)
    ]
    if character_actions:
        return "".join(character_actions[:2])

    non_camera = [part for part in parts if not camera_only(part)]
    if non_camera and len(non_camera) < len(parts):
        return "".join(non_camera)
    return normalized


def _source_facts(entity: object) -> list[str]:
    facts: list[str] = []
    facts.extend(str(item).strip() for item in getattr(entity, "notes", []) if str(item).strip())
    facts.extend(
        str(ref.note).strip()
        for ref in getattr(entity, "evidence_refs", [])
        if getattr(ref, "note", None) and str(ref.note).strip()
    )
    return list(dict.fromkeys(facts))


def _related_shots(entity: object, shot_refs: dict[str, SourceAssetShotRef]) -> list[SourceAssetShotRef]:
    return sorted(
        (shot_refs[shot_id] for shot_id in getattr(entity, "shot_anchor_ids", []) if shot_id in shot_refs),
        key=lambda item: (item.episode_order, item.shot_number),
    )


def _shot_ranges(shots: list[SourceAssetShotRef], *, multi_episode: bool) -> list[str]:
    if not shots:
        return []
    ranges: list[str] = []
    start = previous = shots[0]
    for item in shots[1:]:
        contiguous = item.episode_id == previous.episode_id and item.shot_number == previous.shot_number + 1
        if not contiguous:
            prefix = f"第{start.episode_order}集 " if multi_episode else ""
            suffix = f"#{start.shot_number:03d}" if start.shot_number == previous.shot_number else f"#{start.shot_number:03d}–#{previous.shot_number:03d}"
            ranges.append(prefix + suffix)
            start = item
        previous = item
    prefix = f"第{start.episode_order}集 " if multi_episode else ""
    suffix = f"#{start.shot_number:03d}" if start.shot_number == previous.shot_number else f"#{start.shot_number:03d}–#{previous.shot_number:03d}"
    ranges.append(prefix + suffix)
    return ranges


def get_source_script(db: Session, project_id: str) -> SourceScriptRead:
    """Compose a deterministic, user-readable script from accepted Source Facts.

    This is a view, not a new model inference. Scene runs are split both when the
    resolved scene changes and at every Episode boundary so independent episodes
    can never be silently merged into one screenplay scene.
    """

    status = get_source_analysis_status(db, project_id)
    if status.state != SourceAnalysisState.READY:
        return SourceScriptRead(project_id=project_id, state=status.state, title="原片剧本")

    breakdown = get_shot_breakdown(db, project_id)
    resolution = get_source_resolution(db, project_id)
    if (
        _status_value(breakdown.status) != "CURRENT"
        or breakdown.content is None
        or resolution.characters.content is None
        or resolution.speakers.content is None
        or resolution.scenes.content is None
        or resolution.props.content is None
    ):
        return SourceScriptRead(
            project_id=project_id,
            state=SourceAnalysisState.NEEDS_REFRESH,
            title="原片剧本",
        )

    scene_names = {item.scene_id: item.display_name for item in resolution.scenes.content.entities}
    assignment_by_shot = {item.shot_anchor_id: item for item in resolution.scenes.content.assignments}
    character_names = {item.character_id: item.display_name for item in resolution.characters.content.entities}
    speaker_names = {item.speaker_id: item.display_name for item in resolution.speakers.content.entities}
    speaker_character_names = {
        item.speaker_id: character_names.get(item.character_id or "") or item.display_name
        for item in resolution.speakers.content.entities
    }
    attribution_by_utterance = {
        item.utterance_id: item
        for item in resolution.speakers.content.attributions
    }
    characters_by_shot: dict[str, set[str]] = {}
    for character in resolution.characters.content.entities:
        for shot_id in character.shot_anchor_ids:
            characters_by_shot.setdefault(shot_id, set()).add(character.display_name)

    shot_refs: dict[str, SourceAssetShotRef] = {}
    for episode_index, episode in enumerate(breakdown.content.episodes, 1):
        episode_order = int(getattr(episode, "episode_order", episode_index))
        for fact in episode.shots:
            base_url = (
                f"/api/v3/projects/{project_id}/episodes/{episode.episode_id}/shot-boundary/"
                f"shots/{fact.shot_anchor_id}"
            )
            shot_refs[fact.shot_anchor_id] = SourceAssetShotRef(
                episode_id=episode.episode_id,
                episode_order=episode_order,
                shot_anchor_id=fact.shot_anchor_id,
                shot_number=fact.shot_number,
                thumbnail_url=f"{base_url}/thumbnail",
                reference_clip_url=f"{base_url}/reference-clip",
            )

    scenes: list[SourceScriptScene] = []
    seen_utterances: set[str] = set()
    scene_number = 0
    previous_episode_id: str | None = None

    for episode in breakdown.content.episodes:
        episode_changed = previous_episode_id is not None and previous_episode_id != episode.episode_id
        previous_episode_id = episode.episode_id
        first_shot_in_episode = True

        for fact in episode.shots:
            assignment = assignment_by_shot.get(fact.shot_anchor_id)
            scene_id = assignment.scene_id if assignment is not None else None
            must_start_scene = (
                not scenes
                or first_shot_in_episode and episode_changed
                or scenes[-1].scene_id != scene_id
            )
            if must_start_scene:
                scene_number += 1
                scenes.append(
                    SourceScriptScene(
                        scene_number=scene_number,
                        episode_id=episode.episode_id,
                        scene_id=scene_id,
                        scene_name=_scene_name(scene_id, scene_names),
                        start_us=fact.start_us,
                        end_us=fact.end_us,
                        character_names=[],
                        shots=[],
                    )
                )
            first_shot_in_episode = False
            current_scene = scenes[-1]
            visible_names = characters_by_shot.get(fact.shot_anchor_id, set())

            shot_dialogues: list[SourceScriptDialogue] = []
            for dialogue in fact.dialogue:
                if dialogue.utterance_id in seen_utterances:
                    continue
                seen_utterances.add(dialogue.utterance_id)
                attribution = attribution_by_utterance.get(dialogue.utterance_id)
                speaker_id = attribution.speaker_id if attribution is not None else None
                speaker_name = (
                    speaker_character_names.get(speaker_id or "")
                    or speaker_names.get(speaker_id or "")
                    or "未知说话人"
                )
                shot_dialogues.append(
                    SourceScriptDialogue(
                        utterance_id=dialogue.utterance_id,
                        utterance_number=dialogue.utterance_number,
                        start_us=dialogue.utterance_start_us,
                        end_us=dialogue.utterance_end_us,
                        speaker_id=speaker_id,
                        speaker_name=speaker_name,
                        text=dialogue.text,
                        delivery=_status_value(dialogue.delivery),
                    )
                )

            current_scene.shots.append(
                SourceScriptShot(
                    episode_id=episode.episode_id,
                    shot_anchor_id=fact.shot_anchor_id,
                    shot_number=fact.shot_number,
                    start_us=fact.start_us,
                    end_us=fact.end_us,
                    duration_us=fact.duration_us,
                    action_summary=_action_summary(
                        fact.visual_description,
                        visible_character_names=visible_names,
                        camera_values=(
                            fact.camera_language.shot_size,
                            fact.camera_language.composition,
                            fact.camera_language.angle_or_type,
                            fact.camera_language.movement,
                            fact.camera_language.focal_length_dof,
                        ),
                    ),
                    visual_description=fact.visual_description,
                    shot_size=fact.camera_language.shot_size,
                    composition=fact.camera_language.composition,
                    angle_or_type=fact.camera_language.angle_or_type,
                    movement=fact.camera_language.movement,
                    focal_length_dof=fact.camera_language.focal_length_dof,
                    thumbnail_url=shot_refs[fact.shot_anchor_id].thumbnail_url,
                    reference_clip_url=shot_refs[fact.shot_anchor_id].reference_clip_url,
                    dialogues=shot_dialogues,
                )
            )
            current_scene.end_us = fact.end_us
            names = set(current_scene.character_names)
            names.update(visible_names)
            current_scene.character_names = sorted(names)

    character_assets: list[SourceCharacterAssetCard] = []
    for entity in resolution.characters.content.entities:
        related = _related_shots(entity, shot_refs)
        dialogue_ids = {
            utterance_id
            for speaker in resolution.speakers.content.entities
            if speaker.character_id == entity.character_id
            for utterance_id in getattr(speaker, "utterance_ids", [])
        }
        character_assets.append(
            SourceCharacterAssetCard(
                id=entity.character_id,
                name=entity.display_name,
                related_shots=related,
                dialogue_count=len(dialogue_ids),
                source_facts=_source_facts(entity),
                representative_frame=related[0] if related else None,
            )
        )

    multi_episode = len(breakdown.content.episodes) > 1
    scene_assets: list[SourceSceneAssetCard] = []
    for entity in resolution.scenes.content.entities:
        related = _related_shots(entity, shot_refs)
        scene_assets.append(
            SourceSceneAssetCard(
                id=entity.scene_id,
                name=entity.display_name,
                shot_ranges=_shot_ranges(related, multi_episode=multi_episode),
                related_shots=related,
                source_facts=_source_facts(entity),
                representative_frame=related[0] if related else None,
            )
        )

    prop_assets: list[SourcePropAssetCard] = []
    for entity in resolution.props.content.entities:
        related = _related_shots(entity, shot_refs)
        prop_assets.append(
            SourcePropAssetCard(
                id=entity.prop_id,
                name=entity.display_name,
                related_shots=related,
                source_facts=_source_facts(entity),
                representative_frame=related[0] if related else None,
            )
        )

    return SourceScriptRead(
        project_id=project_id,
        state=SourceAnalysisState.READY,
        title=breakdown.content.title or "原片剧本",
        scenes=scenes,
        characters=[
            SourceScriptEntity(id=item.character_id, name=item.display_name)
            for item in resolution.characters.content.entities
        ],
        props=[
            SourceScriptEntity(id=item.prop_id, name=item.display_name)
            for item in resolution.props.content.entities
        ],
        character_assets=character_assets,
        scene_assets=scene_assets,
        prop_assets=prop_assets,
    )
