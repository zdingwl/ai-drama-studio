from sqlalchemy.orm import Session

from app.shot_breakdown.service_v2 import get_shot_breakdown
from app.source_analysis.schemas import (
    SourceAnalysisState,
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
                        text=attribution.text if attribution is not None else dialogue.text,
                        delivery=_status_value(dialogue.delivery),
                    )
                )

            current_scene.shots.append(
                SourceScriptShot(
                    shot_anchor_id=fact.shot_anchor_id,
                    shot_number=fact.shot_number,
                    start_us=fact.start_us,
                    end_us=fact.end_us,
                    duration_us=fact.duration_us,
                    visual_description=fact.visual_description,
                    shot_size=fact.camera_language.shot_size,
                    composition=fact.camera_language.composition,
                    angle_or_type=fact.camera_language.angle_or_type,
                    movement=fact.camera_language.movement,
                    focal_length_dof=fact.camera_language.focal_length_dof,
                    dialogues=shot_dialogues,
                )
            )
            current_scene.end_us = fact.end_us
            names = set(current_scene.character_names)
            names.update(characters_by_shot.get(fact.shot_anchor_id, set()))
            names.update(item.speaker_name for item in shot_dialogues if item.speaker_name != "未知说话人")
            current_scene.character_names = sorted(names)

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
    )
