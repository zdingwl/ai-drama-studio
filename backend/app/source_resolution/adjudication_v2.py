"""Validated P9 manual-adjudication adapter.

Manual merge/split/reassign operations are versioned Source edits. The base module implements the
operation transforms and Artifact publication. This adapter adds the invariant pass required before
publication: entity membership is recomputed from authoritative bindings, P5/P6/P8 references are
revalidated, and Speaker->Character links must point at the CURRENT Character revision.
"""

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.skills.models import ArtifactType
from app.source_resolution import adjudication as _base
from app.source_resolution.models import SourceResolutionRevision
from app.source_resolution.schemas import (
    CharacterResolutionContent,
    ManualResolutionCommand,
    PropResolutionContent,
    ResolutionStatus,
    SceneResolutionContent,
    SourceResolutionKind,
    SpeakerResolutionContent,
)
from app.source_resolution.service import P9Inputs, _current_artifact, _shot_fact_map, _utterance_map


def _resolved_binding(status: ResolutionStatus, value: str | None, *, label: str) -> None:
    if status in {ResolutionStatus.RESOLVED, ResolutionStatus.MANUAL_CONFIRMED} and value is None:
        raise AppError("P9_MANUAL_BINDING_INVALID", f"{label} 已确认/已归一状态必须绑定 stable identity", status_code=422)
    if status in {ResolutionStatus.UNKNOWN, ResolutionStatus.UNRESOLVED} and value is not None:
        raise AppError("P9_MANUAL_BINDING_INVALID", f"{label} UNKNOWN/UNRESOLVED 不得绑定 stable identity", status_code=422)


def _speaker_candidate_map(inputs: P9Inputs) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for episode in inputs.facts_content.episodes:
        for shot in episode.shots:
            for binding in shot.dialogue:
                if binding.speaker is not None:
                    result.setdefault(binding.utterance_id, set()).add(binding.speaker.id)
    return result


def _speaker_shot_ids(inputs: P9Inputs, utterance_ids: set[str]) -> list[str]:
    values: set[str] = set()
    for episode in inputs.facts_content.episodes:
        for shot in episode.shots:
            if any(binding.utterance_id in utterance_ids for binding in shot.dialogue):
                values.add(shot.shot_anchor_id)
    return sorted(values)


def _normalize_characters(content: CharacterResolutionContent, inputs: P9Inputs) -> CharacterResolutionContent:
    shot_map = _shot_fact_map(inputs)
    entity_ids = {item.character_id for item in content.entities}
    for item in content.observations:
        pair = shot_map.get(item.shot_anchor_id)
        if pair is None or item.source_candidate_id not in {value.id for value in pair[1].bindings.characters}:
            raise AppError("P9_MANUAL_CHARACTER_REFERENCE_INVALID", "Character observation 不再属于 CURRENT P8", status_code=409)
        _resolved_binding(item.resolution_status, item.character_id, label="Character observation")
        if item.character_id is not None and item.character_id not in entity_ids:
            raise AppError("P9_MANUAL_ENTITY_NOT_FOUND", "Character observation 绑定了不存在的 stable identity", status_code=422)

    normalized = []
    for entity in content.entities:
        members = [item for item in content.observations if item.character_id == entity.character_id]
        if not members:
            continue
        shot_ids = sorted({item.shot_anchor_id for item in members})
        normalized.append(
            entity.model_copy(
                update={
                    "source_candidate_ids": sorted({item.source_candidate_id for item in members}),
                    "shot_anchor_ids": shot_ids,
                    "episode_ids": sorted({shot_map[shot_id][0] for shot_id in shot_ids}),
                }
            )
        )
    return content.model_copy(update={"entities": normalized})


def _normalize_speakers(content: SpeakerResolutionContent, inputs: P9Inputs, db: Session, project_id: str) -> SpeakerResolutionContent:
    utterance_map = _utterance_map(inputs)
    entity_ids = {item.speaker_id for item in content.entities}
    for item in content.attributions:
        pair = utterance_map.get(item.utterance_id)
        if pair is None:
            raise AppError("P9_MANUAL_SPEAKER_REFERENCE_INVALID", "Speaker attribution 不再属于 CURRENT P6", status_code=409)
        episode_id, utterance = pair
        if (
            item.episode_id != episode_id
            or item.utterance_number != utterance.utterance_number
            or item.start_us != utterance.start_us
            or item.end_us != utterance.end_us
            or item.text != utterance.text
        ):
            raise AppError("P9_P6_CANONICAL_MISMATCH", "Speaker attribution 不得修改 CURRENT P6 canonical text/time", status_code=409)
        _resolved_binding(item.resolution_status, item.speaker_id, label="Speaker attribution")
        if item.speaker_id is not None and item.speaker_id not in entity_ids:
            raise AppError("P9_MANUAL_ENTITY_NOT_FOUND", "Speaker attribution 绑定了不存在的 stable identity", status_code=422)

    current_characters = _current_artifact(db, project_id, ArtifactType.SOURCE_CHARACTERS)
    if current_characters is None:
        raise AppError("SOURCE_CHARACTERS_REQUIRED", "Speaker 人工裁决需要 CURRENT SOURCE_CHARACTERS", status_code=409)
    row = db.scalar(select(SourceResolutionRevision).where(SourceResolutionRevision.artifact_id == current_characters.id))
    if row is None:
        raise AppError("SOURCE_RESOLUTION_CONTENT_MISSING", "CURRENT SOURCE_CHARACTERS 缺少正式 revision 内容", status_code=500)
    characters = CharacterResolutionContent.model_validate(row.content_json)
    valid_character_ids = {item.character_id for item in characters.entities}
    invalid_links = sorted({item.character_id for item in content.entities if item.character_id is not None and item.character_id not in valid_character_ids})
    if invalid_links:
        raise AppError(
            "P9_SPEAKER_CHARACTER_LINK_STALE",
            "Speaker->Character 仍引用旧 Character identity；请显式重新裁决或重新运行 P9",
            status_code=409,
            details={"character_ids": invalid_links},
        )

    candidate_map = _speaker_candidate_map(inputs)
    normalized = []
    for entity in content.entities:
        members = [item for item in content.attributions if item.speaker_id == entity.speaker_id]
        if not members:
            continue
        utterance_ids = {item.utterance_id for item in members}
        candidate_ids = sorted({value for utterance_id in utterance_ids for value in candidate_map.get(utterance_id, set())})
        normalized.append(
            entity.model_copy(
                update={
                    "utterance_ids": sorted(utterance_ids),
                    "episode_ids": sorted({item.episode_id for item in members}),
                    "shot_anchor_ids": _speaker_shot_ids(inputs, utterance_ids),
                    "source_candidate_ids": candidate_ids,
                    "source_candidate_character_ids": candidate_ids,
                }
            )
        )
    return content.model_copy(update={"entities": normalized})


def _normalize_scenes(content: SceneResolutionContent, inputs: P9Inputs) -> SceneResolutionContent:
    shot_map = _shot_fact_map(inputs)
    entity_ids = {item.scene_id for item in content.entities}
    for item in content.assignments:
        pair = shot_map.get(item.shot_anchor_id)
        if pair is None:
            raise AppError("P9_MANUAL_SCENE_REFERENCE_INVALID", "Scene assignment 不再属于 CURRENT P5/P8", status_code=409)
        episode_id, shot = pair
        if (
            item.episode_id != episode_id
            or item.shot_number != shot.shot_number
            or item.start_us != shot.start_us
            or item.end_us != shot.end_us
            or set(item.source_candidate_ids) != {value.id for value in shot.bindings.scenes}
        ):
            raise AppError("P9_P5_TIME_AUTHORITY_VIOLATION", "Scene assignment 不得修改 CURRENT P5/P8 Shot 事实", status_code=409)
        _resolved_binding(item.resolution_status, item.scene_id, label="Scene assignment")
        if item.scene_id is not None and item.scene_id not in entity_ids:
            raise AppError("P9_MANUAL_ENTITY_NOT_FOUND", "Scene assignment 绑定了不存在的 stable identity", status_code=422)

    normalized = []
    for entity in content.entities:
        members = [item for item in content.assignments if item.scene_id == entity.scene_id]
        if not members:
            continue
        shot_ids = sorted({item.shot_anchor_id for item in members})
        normalized.append(
            entity.model_copy(
                update={
                    "source_candidate_ids": sorted({value for item in members for value in item.source_candidate_ids}),
                    "shot_anchor_ids": shot_ids,
                    "episode_ids": sorted({item.episode_id for item in members}),
                }
            )
        )
    return content.model_copy(update={"entities": normalized})


def _normalize_props(content: PropResolutionContent, inputs: P9Inputs) -> PropResolutionContent:
    shot_map = _shot_fact_map(inputs)
    entity_ids = {item.prop_id for item in content.entities}
    for item in content.observations:
        pair = shot_map.get(item.shot_anchor_id)
        if pair is None or item.source_candidate_id not in {value.id for value in pair[1].bindings.props}:
            raise AppError("P9_MANUAL_PROP_REFERENCE_INVALID", "Prop observation 不再属于 CURRENT P8", status_code=409)
        _resolved_binding(item.resolution_status, item.prop_id, label="Prop observation")
        if item.prop_id is not None and item.prop_id not in entity_ids:
            raise AppError("P9_MANUAL_ENTITY_NOT_FOUND", "Prop observation 绑定了不存在的 stable identity", status_code=422)

    normalized = []
    for entity in content.entities:
        members = [item for item in content.observations if item.prop_id == entity.prop_id]
        if not members:
            continue
        shot_ids = sorted({item.shot_anchor_id for item in members})
        normalized.append(
            entity.model_copy(
                update={
                    "source_candidate_ids": sorted({item.source_candidate_id for item in members}),
                    "shot_anchor_ids": shot_ids,
                    "episode_ids": sorted({shot_map[shot_id][0] for shot_id in shot_ids}),
                }
            )
        )
    return content.model_copy(update={"entities": normalized})


def _normalize(db: Session, project_id: str, kind: SourceResolutionKind, content, inputs: P9Inputs):
    if kind == SourceResolutionKind.CHARACTER:
        return _normalize_characters(CharacterResolutionContent.model_validate(content), inputs)
    if kind == SourceResolutionKind.SPEAKER:
        return _normalize_speakers(SpeakerResolutionContent.model_validate(content), inputs, db, project_id)
    if kind == SourceResolutionKind.SCENE:
        return _normalize_scenes(SceneResolutionContent.model_validate(content), inputs)
    return _normalize_props(PropResolutionContent.model_validate(content), inputs)


def adjudicate_source_resolution(
    db: Session,
    *,
    project_id: str,
    kind: SourceResolutionKind,
    command: ManualResolutionCommand,
) -> ArtifactNode:
    inputs = _base._load_inputs(db, project_id)
    base = _base._base_artifact(db, project_id, kind, command.expected_revision)
    row = _base._row(db, base)
    content = _base._content(kind, row)
    updated = _base._apply(db, project_id, kind, deepcopy(content), base, command)
    normalized = _normalize(db, project_id, kind, updated, inputs)
    return _base._publish_manual(
        db,
        project_id=project_id,
        kind=kind,
        base=base,
        content=normalized,
        command=command,
    )
