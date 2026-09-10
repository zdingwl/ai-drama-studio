from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, invalidate_current_artifact_type
from app.core.errors import AppError
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill
from app.source_resolution.models import SourceResolutionRevision
from app.source_resolution.providers import P9_SCHEMA_VERSION, P9_SOURCE_TRUTH_CONTRACT
from app.source_resolution.schemas import (
    CharacterEntity,
    CharacterResolutionContent,
    ManualAdjudicationProvenance,
    ManualResolutionCommand,
    ManualResolutionOperation,
    PropEntity,
    PropResolutionContent,
    ResolutionStatus,
    SceneEntity,
    SceneResolutionContent,
    SourceResolutionKind,
    SourceResolutionProvenance,
    SpeakerEntity,
    SpeakerResolutionContent,
)
from app.source_resolution.service import (
    _KIND_ARTIFACT,
    _KIND_LABEL,
    _KIND_SKILL,
    _current_artifact,
    _latest_artifact,
    _load_inputs,
    _sha,
)


MANUAL_ADJUDICATION_CONTRACT = "p9-manual-adjudication-v1"


def _row(db: Session, artifact: ArtifactNode) -> SourceResolutionRevision:
    row = db.scalar(select(SourceResolutionRevision).where(SourceResolutionRevision.artifact_id == artifact.id))
    if row is None:
        raise AppError("SOURCE_RESOLUTION_CONTENT_MISSING", "P9 Artifact 缺少正式 revision 内容", status_code=500)
    return row


def _content(kind: SourceResolutionKind, row: SourceResolutionRevision):
    if kind == SourceResolutionKind.CHARACTER:
        return CharacterResolutionContent.model_validate(row.content_json)
    if kind == SourceResolutionKind.SPEAKER:
        return SpeakerResolutionContent.model_validate(row.content_json)
    if kind == SourceResolutionKind.SCENE:
        return SceneResolutionContent.model_validate(row.content_json)
    return PropResolutionContent.model_validate(row.content_json)


def _base_artifact(db: Session, project_id: str, kind: SourceResolutionKind, expected_revision: int) -> ArtifactNode:
    artifact_type = _KIND_ARTIFACT[kind]
    current = _current_artifact(db, project_id, artifact_type)
    if current is not None:
        base = current
    elif kind == SourceResolutionKind.SPEAKER:
        # A manual Character revision intentionally stales its downstream Speaker Artifact.
        # Permit an explicit Speaker adjudication to recover from that state, but only from
        # the latest historical revision and only after CURRENT P5/P6/P7/P8 are revalidated.
        base = _latest_artifact(db, project_id, artifact_type)
        if base is None:
            raise AppError("SOURCE_SPEAKERS_REQUIRED", "尚无可人工裁决的 SOURCE_SPEAKERS", status_code=409)
    else:
        raise AppError("SOURCE_RESOLUTION_CURRENT_REQUIRED", "人工裁决需要当前 P9 Artifact", status_code=409)
    if base.revision != expected_revision:
        raise AppError(
            "SOURCE_RESOLUTION_REVISION_CONFLICT",
            "P9 人工裁决 revision 已变化，请刷新后重试",
            status_code=409,
            details={"expected_revision": expected_revision, "actual_revision": base.revision},
        )
    return base


def _entity_map(content) -> dict[str, object]:
    result = {item.entity_id: item for item in content.entities}
    if len(result) != len(content.entities):
        raise AppError("P9_ENTITY_ID_DUPLICATED", "P9 stable entity id 重复", status_code=500)
    return result


def _require_entities(content, entity_ids: list[str]) -> dict[str, object]:
    entities = _entity_map(content)
    missing = sorted(set(entity_ids) - set(entities))
    if missing:
        raise AppError("P9_MANUAL_ENTITY_NOT_FOUND", "人工裁决引用了不存在的 stable entity", status_code=422, details={"entity_ids": missing})
    return entities


def _manual_id(kind: SourceResolutionKind, base: ArtifactNode, command: ManualResolutionCommand, refs: list[str], suffix: str = "") -> str:
    prefix = {
        SourceResolutionKind.CHARACTER: "chr",
        SourceResolutionKind.SPEAKER: "spk",
        SourceResolutionKind.SCENE: "scn",
        SourceResolutionKind.PROP: "prop",
    }[kind]
    digest = _sha(
        {
            "contract": MANUAL_ADJUDICATION_CONTRACT,
            "base_artifact_id": base.id,
            "base_fingerprint": base.input_fingerprint,
            "operation": command.operation.value,
            "refs": sorted(refs),
            "reason": command.reason,
            "suffix": suffix,
        }
    )[:20]
    return f"p9-{prefix}-manual-{digest}"


def _confirm(content, command: ManualResolutionCommand):
    if not command.entity_ids:
        raise AppError("P9_MANUAL_ENTITY_REQUIRED", "CONFIRM 至少需要一个 entity_id", status_code=422)
    _require_entities(content, command.entity_ids)
    selected = set(command.entity_ids)
    entities = []
    for item in content.entities:
        if item.entity_id not in selected:
            entities.append(item)
            continue
        update = {"resolution_status": ResolutionStatus.MANUAL_CONFIRMED}
        if command.display_name is not None:
            if len(selected) != 1:
                raise AppError("P9_MANUAL_DISPLAY_NAME_AMBIGUOUS", "一次只能为一个 entity 修改 display_name", status_code=422)
            update["display_name"] = command.display_name
        entities.append(item.model_copy(update=update))
    return content.model_copy(update={"entities": entities})


def _merge(kind: SourceResolutionKind, content, base: ArtifactNode, command: ManualResolutionCommand):
    if len(set(command.entity_ids)) < 2:
        raise AppError("P9_MANUAL_MERGE_REQUIRES_MULTIPLE", "MERGE 至少需要两个不同 entity_id", status_code=422)
    entities = _require_entities(content, command.entity_ids)
    selected = [entities[value] for value in command.entity_ids]
    new_id = _manual_id(kind, base, command, command.entity_ids)
    display_name = command.display_name or selected[0].display_name
    aliases = sorted({alias for item in selected for alias in ([item.display_name] + item.aliases)} - {display_name})
    evidence = []
    seen_evidence: set[tuple[str, str, str | None, str | None]] = set()
    for item in selected:
        for ref in item.evidence_refs:
            key = (ref.ref_type, ref.ref_id, ref.shot_anchor_id, ref.utterance_id)
            if key not in seen_evidence:
                evidence.append(ref)
                seen_evidence.add(key)
    common = dict(
        entity_id=new_id,
        display_name=display_name,
        aliases=aliases,
        source_candidate_ids=sorted({value for item in selected for value in item.source_candidate_ids}),
        episode_ids=sorted({value for item in selected for value in item.episode_ids}),
        shot_anchor_ids=sorted({value for item in selected for value in item.shot_anchor_ids}),
        evidence_refs=evidence,
        confidence=max(item.confidence for item in selected),
        resolution_status=ResolutionStatus.MANUAL_CONFIRMED,
        notes=sorted({value for item in selected for value in item.notes} | {command.reason}),
    )
    if kind == SourceResolutionKind.CHARACTER:
        merged = CharacterEntity(character_id=new_id, **common)
        observations = [
            item.model_copy(update={"character_id": new_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED})
            if item.character_id in entities else item
            for item in content.observations
        ]
        updates = {"observations": observations}
    elif kind == SourceResolutionKind.SPEAKER:
        character_ids = {item.character_id for item in selected}
        character_id = next(iter(character_ids)) if len(character_ids) == 1 else None
        merged = SpeakerEntity(
            speaker_id=new_id,
            character_id=character_id,
            utterance_ids=sorted({value for item in selected for value in item.utterance_ids}),
            source_candidate_character_ids=sorted({value for item in selected for value in item.source_candidate_character_ids}),
            **common,
        )
        attributions = [
            item.model_copy(update={"speaker_id": new_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED})
            if item.speaker_id in entities else item
            for item in content.attributions
        ]
        updates = {"attributions": attributions}
    elif kind == SourceResolutionKind.SCENE:
        merged = SceneEntity(scene_id=new_id, disambiguation_notes=[command.reason], **common)
        assignments = [
            item.model_copy(update={"scene_id": new_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED})
            if item.scene_id in entities else item
            for item in content.assignments
        ]
        updates = {"assignments": assignments}
    else:
        merged = PropEntity(prop_id=new_id, instance_notes=[command.reason], **common)
        observations = [
            item.model_copy(update={"prop_id": new_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED})
            if item.prop_id in entities else item
            for item in content.observations
        ]
        updates = {"observations": observations}
    remaining = [item for item in content.entities if item.entity_id not in entities]
    updates["entities"] = remaining + [merged]
    return content.model_copy(update=updates)


def _reference_members(kind: SourceResolutionKind, content, entity_id: str) -> list[str]:
    if kind == SourceResolutionKind.CHARACTER:
        return [f"{item.shot_anchor_id}:{item.source_candidate_id}" for item in content.observations if item.character_id == entity_id]
    if kind == SourceResolutionKind.SPEAKER:
        return [item.utterance_id for item in content.attributions if item.speaker_id == entity_id]
    if kind == SourceResolutionKind.SCENE:
        return [item.shot_anchor_id for item in content.assignments if item.scene_id == entity_id]
    return [f"{item.shot_anchor_id}:{item.source_candidate_id}" for item in content.observations if item.prop_id == entity_id]


def _split(kind: SourceResolutionKind, content, base: ArtifactNode, command: ManualResolutionCommand):
    if len(command.entity_ids) != 1 or len(command.split_groups) < 2:
        raise AppError("P9_MANUAL_SPLIT_INVALID", "SPLIT 需要一个 entity_id 和至少两个 split_groups", status_code=422)
    entity_id = command.entity_ids[0]
    source = _require_entities(content, [entity_id])[entity_id]
    expected = set(_reference_members(kind, content, entity_id))
    flattened = [value for group in command.split_groups for value in group]
    if len(flattened) != len(set(flattened)) or set(flattened) != expected:
        raise AppError("P9_MANUAL_SPLIT_PARTITION_INVALID", "split_groups 必须无重叠且完整覆盖该 entity 的所有绑定", status_code=422)
    new_entities = []
    ref_to_id: dict[str, str] = {}
    for index, group in enumerate(command.split_groups, 1):
        new_id = _manual_id(kind, base, command, group, suffix=str(index))
        ref_to_id.update({value: new_id for value in group})
        display_name = command.display_name or source.display_name
        common = source.model_dump()
        common.update(
            entity_id=new_id,
            display_name=f"{display_name} {index}" if len(command.split_groups) > 1 else display_name,
            resolution_status=ResolutionStatus.MANUAL_CONFIRMED,
            notes=sorted(set(source.notes + [command.reason])),
        )
        if kind == SourceResolutionKind.CHARACTER:
            common["character_id"] = new_id
            new_entities.append(CharacterEntity.model_validate(common))
        elif kind == SourceResolutionKind.SPEAKER:
            common["speaker_id"] = new_id
            common["utterance_ids"] = list(group)
            new_entities.append(SpeakerEntity.model_validate(common))
        elif kind == SourceResolutionKind.SCENE:
            common["scene_id"] = new_id
            common["disambiguation_notes"] = list(dict.fromkeys(source.disambiguation_notes + [command.reason]))
            new_entities.append(SceneEntity.model_validate(common))
        else:
            common["prop_id"] = new_id
            common["instance_notes"] = list(dict.fromkeys(source.instance_notes + [command.reason]))
            new_entities.append(PropEntity.model_validate(common))
    remaining = [item for item in content.entities if item.entity_id != entity_id]
    if kind == SourceResolutionKind.CHARACTER:
        observations = []
        for item in content.observations:
            ref = f"{item.shot_anchor_id}:{item.source_candidate_id}"
            observations.append(item.model_copy(update={"character_id": ref_to_id[ref], "resolution_status": ResolutionStatus.MANUAL_CONFIRMED}) if item.character_id == entity_id else item)
        return content.model_copy(update={"entities": remaining + new_entities, "observations": observations})
    if kind == SourceResolutionKind.SPEAKER:
        attributions = [item.model_copy(update={"speaker_id": ref_to_id[item.utterance_id], "resolution_status": ResolutionStatus.MANUAL_CONFIRMED}) if item.speaker_id == entity_id else item for item in content.attributions]
        return content.model_copy(update={"entities": remaining + new_entities, "attributions": attributions})
    if kind == SourceResolutionKind.SCENE:
        assignments = [item.model_copy(update={"scene_id": ref_to_id[item.shot_anchor_id], "resolution_status": ResolutionStatus.MANUAL_CONFIRMED}) if item.scene_id == entity_id else item for item in content.assignments]
        return content.model_copy(update={"entities": remaining + new_entities, "assignments": assignments})
    observations = []
    for item in content.observations:
        ref = f"{item.shot_anchor_id}:{item.source_candidate_id}"
        observations.append(item.model_copy(update={"prop_id": ref_to_id[ref], "resolution_status": ResolutionStatus.MANUAL_CONFIRMED}) if item.prop_id == entity_id else item)
    return content.model_copy(update={"entities": remaining + new_entities, "observations": observations})


def _mark_unknown(kind: SourceResolutionKind, content, command: ManualResolutionCommand):
    refs = set(command.reference_ids)
    if not refs:
        raise AppError("P9_MANUAL_REFERENCE_REQUIRED", "MARK_UNKNOWN 需要 reference_ids", status_code=422)
    known = set()
    if kind == SourceResolutionKind.CHARACTER:
        rows = []
        for item in content.observations:
            ref = f"{item.shot_anchor_id}:{item.source_candidate_id}"
            known.add(ref)
            rows.append(item.model_copy(update={"character_id": None, "resolution_status": ResolutionStatus.UNKNOWN, "reason": command.reason}) if ref in refs else item)
        content = content.model_copy(update={"observations": rows})
    elif kind == SourceResolutionKind.SPEAKER:
        known = {item.utterance_id for item in content.attributions}
        content = content.model_copy(update={"attributions": [item.model_copy(update={"speaker_id": None, "resolution_status": ResolutionStatus.UNKNOWN, "reason": command.reason}) if item.utterance_id in refs else item for item in content.attributions]})
    elif kind == SourceResolutionKind.SCENE:
        known = {item.shot_anchor_id for item in content.assignments}
        content = content.model_copy(update={"assignments": [item.model_copy(update={"scene_id": None, "resolution_status": ResolutionStatus.UNKNOWN, "reason": command.reason}) if item.shot_anchor_id in refs else item for item in content.assignments]})
    else:
        rows = []
        for item in content.observations:
            ref = f"{item.shot_anchor_id}:{item.source_candidate_id}"
            known.add(ref)
            rows.append(item.model_copy(update={"prop_id": None, "resolution_status": ResolutionStatus.UNKNOWN, "reason": command.reason}) if ref in refs else item)
        content = content.model_copy(update={"observations": rows})
    missing = sorted(refs - known)
    if missing:
        raise AppError("P9_MANUAL_REFERENCE_NOT_FOUND", "人工裁决引用了不存在的 binding/observation", status_code=422, details={"reference_ids": missing})
    return _drop_unreferenced(kind, content)


def _reassign(db: Session, project_id: str, kind: SourceResolutionKind, content, command: ManualResolutionCommand):
    if kind == SourceResolutionKind.SPEAKER and not command.reference_ids:
        if not command.entity_ids:
            raise AppError("P9_MANUAL_ENTITY_REQUIRED", "Speaker→Character REASSIGN 需要 entity_ids", status_code=422)
        _require_entities(content, command.entity_ids)
        if command.character_id is not None:
            current_characters = _current_artifact(db, project_id, ArtifactType.SOURCE_CHARACTERS)
            if current_characters is None:
                raise AppError("SOURCE_CHARACTERS_REQUIRED", "Speaker→Character 裁决需要 CURRENT SOURCE_CHARACTERS", status_code=409)
            char_row = _row(db, current_characters)
            chars = CharacterResolutionContent.model_validate(char_row.content_json)
            if command.character_id not in {item.character_id for item in chars.entities}:
                raise AppError("P9_MANUAL_CHARACTER_NOT_FOUND", "目标 Character identity 不存在", status_code=422)
        selected = set(command.entity_ids)
        return content.model_copy(update={"entities": [item.model_copy(update={"character_id": command.character_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED, "notes": list(dict.fromkeys(item.notes + [command.reason]))}) if item.entity_id in selected else item for item in content.entities]})

    if command.target_entity_id is None or not command.reference_ids:
        raise AppError("P9_MANUAL_REASSIGN_INVALID", "REASSIGN 需要 target_entity_id 与 reference_ids", status_code=422)
    _require_entities(content, [command.target_entity_id])
    refs = set(command.reference_ids)
    known = set()
    if kind == SourceResolutionKind.CHARACTER:
        rows = []
        for item in content.observations:
            ref = f"{item.shot_anchor_id}:{item.source_candidate_id}"
            known.add(ref)
            rows.append(item.model_copy(update={"character_id": command.target_entity_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED, "reason": command.reason}) if ref in refs else item)
        content = content.model_copy(update={"observations": rows})
    elif kind == SourceResolutionKind.SPEAKER:
        known = {item.utterance_id for item in content.attributions}
        content = content.model_copy(update={"attributions": [item.model_copy(update={"speaker_id": command.target_entity_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED, "reason": command.reason}) if item.utterance_id in refs else item for item in content.attributions]})
    elif kind == SourceResolutionKind.SCENE:
        known = {item.shot_anchor_id for item in content.assignments}
        content = content.model_copy(update={"assignments": [item.model_copy(update={"scene_id": command.target_entity_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED, "reason": command.reason}) if item.shot_anchor_id in refs else item for item in content.assignments]})
    else:
        rows = []
        for item in content.observations:
            ref = f"{item.shot_anchor_id}:{item.source_candidate_id}"
            known.add(ref)
            rows.append(item.model_copy(update={"prop_id": command.target_entity_id, "resolution_status": ResolutionStatus.MANUAL_CONFIRMED, "reason": command.reason}) if ref in refs else item)
        content = content.model_copy(update={"observations": rows})
    missing = sorted(refs - known)
    if missing:
        raise AppError("P9_MANUAL_REFERENCE_NOT_FOUND", "人工裁决引用了不存在的 binding/observation", status_code=422, details={"reference_ids": missing})
    return _drop_unreferenced(kind, content)


def _drop_unreferenced(kind: SourceResolutionKind, content):
    if kind == SourceResolutionKind.CHARACTER:
        used = {item.character_id for item in content.observations if item.character_id}
    elif kind == SourceResolutionKind.SPEAKER:
        used = {item.speaker_id for item in content.attributions if item.speaker_id}
    elif kind == SourceResolutionKind.SCENE:
        used = {item.scene_id for item in content.assignments if item.scene_id}
    else:
        used = {item.prop_id for item in content.observations if item.prop_id}
    return content.model_copy(update={"entities": [item for item in content.entities if item.entity_id in used]})


def _apply(db: Session, project_id: str, kind: SourceResolutionKind, content, base: ArtifactNode, command: ManualResolutionCommand):
    if command.operation == ManualResolutionOperation.CONFIRM:
        return _confirm(content, command)
    if command.operation == ManualResolutionOperation.MERGE:
        return _merge(kind, content, base, command)
    if command.operation == ManualResolutionOperation.SPLIT:
        return _split(kind, content, base, command)
    if command.operation == ManualResolutionOperation.MARK_UNKNOWN:
        return _mark_unknown(kind, content, command)
    if command.operation == ManualResolutionOperation.REASSIGN:
        return _reassign(db, project_id, kind, content, command)
    raise AppError("P9_MANUAL_OPERATION_UNSUPPORTED", "不支持的 P9 人工裁决操作", status_code=422)


def _publish_manual(
    db: Session,
    *,
    project_id: str,
    kind: SourceResolutionKind,
    base: ArtifactNode,
    content,
    command: ManualResolutionCommand,
) -> ArtifactNode:
    inputs = _load_inputs(db, project_id)
    base_row = _row(db, base)
    old_provenance = SourceResolutionProvenance.model_validate(base_row.provenance_json)
    skill = get_professional_skill(_KIND_SKILL[kind])
    current_characters = _current_artifact(db, project_id, ArtifactType.SOURCE_CHARACTERS) if kind == SourceResolutionKind.SPEAKER else None
    if kind == SourceResolutionKind.SPEAKER and current_characters is None:
        raise AppError("SOURCE_CHARACTERS_REQUIRED", "Speaker 人工裁决需要 CURRENT SOURCE_CHARACTERS", status_code=409)
    fingerprint = _sha(
        {
            "contract": MANUAL_ADJUDICATION_CONTRACT,
            "kind": kind.value,
            "base_artifact_id": base.id,
            "base_fingerprint": base.input_fingerprint,
            "upstream": {
                "source_video": [inputs.source.id, inputs.source.input_fingerprint],
                "source_bible": [inputs.bible.id, inputs.bible.input_fingerprint],
                "source_shot_facts": [inputs.facts.id, inputs.facts.input_fingerprint],
                "shot_anchors": [inputs.shots.id, inputs.shots.input_fingerprint],
                "source_dialogue": [inputs.dialogue.id, inputs.dialogue.input_fingerprint] if kind == SourceResolutionKind.SPEAKER else None,
                "source_characters": [current_characters.id, current_characters.input_fingerprint] if current_characters is not None else None,
            },
            "command": command.model_dump(mode="json"),
        }
    )
    artifact = create_artifact(
        db,
        project_id=project_id,
        artifact_type=_KIND_ARTIFACT[kind],
        namespace=ArtifactNamespace.SOURCE,
        label=_KIND_LABEL[kind],
        input_fingerprint=fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        metadata_json={
            "schema_version": P9_SCHEMA_VERSION,
            "resolution_kind": kind.value,
            "manual_adjudication": True,
            "manual_operation": command.operation.value,
            "source_video_artifact_id": inputs.source.id,
            "source_bible_artifact_id": inputs.bible.id,
            "source_shot_facts_artifact_id": inputs.facts.id,
            "shot_anchors_artifact_id": inputs.shots.id,
            "source_dialogue_artifact_id": inputs.dialogue.id if kind == SourceResolutionKind.SPEAKER else None,
            "source_characters_artifact_id": current_characters.id if current_characters is not None else None,
            "entity_count": len(content.entities),
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P9_SOURCE_TRUTH_CONTRACT,
            "document_title": _KIND_LABEL[kind],
        },
    )
    provenance = old_provenance.model_copy(
        update={
            "source_video_artifact_id": inputs.source.id,
            "source_video_fingerprint": inputs.source.input_fingerprint,
            "source_bible_artifact_id": inputs.bible.id,
            "source_bible_fingerprint": inputs.bible.input_fingerprint,
            "source_shot_facts_artifact_id": inputs.facts.id,
            "source_shot_facts_fingerprint": inputs.facts.input_fingerprint,
            "shot_anchors_artifact_id": inputs.shots.id,
            "shot_anchors_fingerprint": inputs.shots.input_fingerprint,
            "source_dialogue_artifact_id": inputs.dialogue.id if kind == SourceResolutionKind.SPEAKER else None,
            "source_dialogue_fingerprint": inputs.dialogue.input_fingerprint if kind == SourceResolutionKind.SPEAKER else None,
            "source_characters_artifact_id": current_characters.id if current_characters is not None else None,
            "source_characters_fingerprint": current_characters.input_fingerprint if current_characters is not None else None,
            "generated_by_task_id": None,
            "supersedes_artifact_id": base.id,
            "adjudication": ManualAdjudicationProvenance(operation=command.operation, reason=command.reason),
        }
    )
    row = SourceResolutionRevision(
        project_id=project_id,
        artifact_id=artifact.id,
        resolution_kind=kind.value,
        source_video_artifact_id=inputs.source.id,
        source_bible_artifact_id=inputs.bible.id,
        source_shot_facts_artifact_id=inputs.facts.id,
        shot_anchors_artifact_id=inputs.shots.id,
        source_dialogue_artifact_id=inputs.dialogue.id if kind == SourceResolutionKind.SPEAKER else None,
        generated_by_task_id=None,
        schema_version=P9_SCHEMA_VERSION,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
    )
    try:
        db.add(row)
        db.commit()
        for upstream_id, relation in (
            (inputs.source.id, ArtifactRelationType.DERIVED_FROM),
            (inputs.bible.id, ArtifactRelationType.USES),
            (inputs.facts.id, ArtifactRelationType.DERIVED_FROM),
            (inputs.shots.id, ArtifactRelationType.DERIVED_FROM),
        ):
            create_artifact_relation(db, project_id=project_id, source_node_id=upstream_id, target_node_id=artifact.id, relation_type=relation)
        if kind == SourceResolutionKind.SPEAKER:
            create_artifact_relation(db, project_id=project_id, source_node_id=inputs.dialogue.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM)
            assert current_characters is not None
            create_artifact_relation(db, project_id=project_id, source_node_id=current_characters.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES)
        create_artifact_relation(db, project_id=project_id, source_node_id=artifact.id, target_node_id=base.id, relation_type=ArtifactRelationType.SUPERSEDES)
    except Exception:
        invalidate_current_artifact_type(db, project_id=project_id, artifact_type=_KIND_ARTIFACT[kind])
        raise
    return artifact


def adjudicate_source_resolution(
    db: Session,
    *,
    project_id: str,
    kind: SourceResolutionKind,
    command: ManualResolutionCommand,
) -> ArtifactNode:
    # Revalidate P5/P6/P7/P8 before reading or publishing any manual P9 revision.
    _load_inputs(db, project_id)
    base = _base_artifact(db, project_id, kind, command.expected_revision)
    row = _row(db, base)
    content = _content(kind, row)
    updated = _apply(db, project_id, kind, deepcopy(content), base, command)
    return _publish_manual(db, project_id=project_id, kind=kind, base=base, content=updated, command=command)
