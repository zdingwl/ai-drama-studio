import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact_relation, invalidate_current_artifact_type
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import SOURCE_BIBLE_PROJECT_TYPES
from app.projects.service import get_project
from app.shot_breakdown.models import SourceShotFactsRevision
from app.shot_breakdown.schemas import ShotBreakdownProvenance, SourceShotFactsContent
from app.shot_breakdown.service import (
    EpisodeContext,
    _current_artifact,
    _episode_contexts,
    _required_bible,
    _required_dialogue,
    _required_shots,
    _required_source,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.source_resolution.models import SourceResolutionRevision
from app.source_resolution.providers import (
    P9_PROMPT_VERSION,
    P9_SCHEMA_VERSION,
    P9_SKILL_IDS,
    P9_SOURCE_TRUTH_CONTRACT,
    ProjectResolutionInput,
    ResolutionEpisodeVideo,
    SourceResolutionProvider,
    build_source_resolution_provider,
)
from app.source_resolution.schemas import (
    CharacterEntity,
    CharacterObservation,
    CharacterResolutionContent,
    CharacterResolutionRead,
    CharacterResolutionSemantic,
    EntityGroupSemantic,
    EvidenceRef,
    PropEntity,
    PropObservation,
    PropResolutionContent,
    PropResolutionRead,
    PropResolutionSemantic,
    ResolutionEpisodeInputProvenance,
    ResolutionProviderJobProvenance,
    ResolutionStatus,
    SceneAssignment,
    SceneEntity,
    SceneResolutionContent,
    SceneResolutionRead,
    SceneResolutionSemantic,
    SourceResolutionKind,
    SourceResolutionProvenance,
    SourceResolutionRead,
    SourceResolutionResultStatus,
    SourceResolutionRevisionSummary,
    SpeakerAttribution,
    SpeakerEntity,
    SpeakerResolutionContent,
    SpeakerResolutionRead,
    SpeakerResolutionSemantic,
)
from app.sources.storage import resolve_source_asset_path
from app.understanding.schemas import SourceBibleContent
from app.workflow.models import ProviderJob, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    publish_validated_task_artifact,
)
from app.workflow.worker import TaskExecutionContext


P9_TASK_TYPE = "P9_SOURCE_RESOLUTION"

_KIND_ARTIFACT = {
    SourceResolutionKind.CHARACTER: ArtifactType.SOURCE_CHARACTERS,
    SourceResolutionKind.SPEAKER: ArtifactType.SOURCE_SPEAKERS,
    SourceResolutionKind.SCENE: ArtifactType.SOURCE_SCENES,
    SourceResolutionKind.PROP: ArtifactType.SOURCE_PROPS,
}
_KIND_SKILL = {
    SourceResolutionKind.CHARACTER: "character-resolution",
    SourceResolutionKind.SPEAKER: "speaker-attribution",
    SourceResolutionKind.SCENE: "scene-resolution",
    SourceResolutionKind.PROP: "prop-resolution",
}
_KIND_CAPABILITY = {
    SourceResolutionKind.CHARACTER: Capability.IDENTITY_RESOLUTION,
    SourceResolutionKind.SPEAKER: Capability.IDENTITY_RESOLUTION,
    SourceResolutionKind.SCENE: Capability.SCENE_RESOLUTION,
    SourceResolutionKind.PROP: Capability.PROP_RESOLUTION,
}
_KIND_LABEL = {
    SourceResolutionKind.CHARACTER: "人物最终归一",
    SourceResolutionKind.SPEAKER: "说话人最终归因",
    SourceResolutionKind.SCENE: "场景最终归一",
    SourceResolutionKind.PROP: "关键道具最终归一",
}


@dataclass(frozen=True)
class P9Inputs:
    source: ArtifactNode
    dialogue: ArtifactNode
    bible: ArtifactNode
    bible_content: SourceBibleContent
    shots: ArtifactNode
    facts: ArtifactNode
    facts_content: SourceShotFactsContent
    contexts: tuple[EpisodeContext, ...]


@dataclass(frozen=True)
class P9ExecutionResult:
    characters: CharacterResolutionContent
    speakers: SpeakerResolutionContent
    scenes: SceneResolutionContent
    props: PropResolutionContent
    provider_jobs: dict[SourceResolutionKind, tuple[ResolutionProviderJobProvenance, ...]]
    provider_profiles: dict[SourceResolutionKind, dict]


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value)
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )


def _required_facts(
    db: Session,
    *,
    project_id: str,
    source: ArtifactNode,
    dialogue: ArtifactNode,
    bible: ArtifactNode,
    shots: ArtifactNode,
    contexts: list[EpisodeContext],
) -> tuple[ArtifactNode, SourceShotFactsContent]:
    facts = _current_artifact(db, project_id, ArtifactType.SOURCE_SHOT_FACTS)
    if facts is None:
        raise AppError("SOURCE_SHOT_FACTS_REQUIRED", "P9 需要 CURRENT P8 SOURCE_SHOT_FACTS", status_code=409)
    row = db.scalar(select(SourceShotFactsRevision).where(SourceShotFactsRevision.artifact_id == facts.id))
    if row is None:
        raise AppError("SOURCE_SHOT_FACTS_CONTENT_MISSING", "CURRENT SOURCE_SHOT_FACTS 缺少正式 revision 内容", status_code=500)
    content = SourceShotFactsContent.model_validate(row.content_json)
    provenance = ShotBreakdownProvenance.model_validate(row.provenance_json)
    if (
        provenance.source_video_artifact_id != source.id
        or provenance.source_video_fingerprint != source.input_fingerprint
        or provenance.source_bible_artifact_id != bible.id
        or provenance.source_bible_fingerprint != bible.input_fingerprint
        or provenance.shot_anchors_artifact_id != shots.id
        or provenance.shot_anchors_fingerprint != shots.input_fingerprint
        or provenance.source_dialogue_artifact_id != dialogue.id
        or provenance.source_dialogue_fingerprint != dialogue.input_fingerprint
    ):
        raise AppError("SOURCE_SHOT_FACTS_STALE", "CURRENT SOURCE_SHOT_FACTS provenance 与当前 P5/P6/P7 不一致", status_code=409)

    by_episode = {item.episode_id: item for item in content.episodes}
    if len(by_episode) != len(content.episodes) or set(by_episode) != {item.episode.id for item in contexts}:
        raise AppError("SOURCE_SHOT_FACTS_EPISODE_SET_INVALID", "P8 Episode 集合与当前完整原片不一致", status_code=409)

    for context in contexts:
        episode = by_episode[context.episode.id]
        if len(episode.shots) != len(context.shot_anchors):
            raise AppError("SOURCE_SHOT_FACTS_SHOT_SET_INVALID", "P8 Shot 集合与 CURRENT P5 不一致", status_code=409)
        p8_by_number = {item.shot_number: item for item in episode.shots}
        if len(p8_by_number) != len(episode.shots):
            raise AppError("SOURCE_SHOT_FACTS_SHOT_SET_INVALID", "P8 Shot 编号重复", status_code=409)
        utterance_by_id = {item.id: item for item in context.dialogue}
        for anchor in context.shot_anchors:
            fact = p8_by_number.get(anchor.shot_number)
            if fact is None or (
                fact.shot_anchor_id != anchor.id
                or fact.start_us != anchor.start_us
                or fact.end_us != anchor.end_us
                or fact.duration_us != anchor.duration_us
            ):
                raise AppError("P9_P5_TIME_AUTHORITY_VIOLATION", "P8 Shot 与 CURRENT P5 权威时间不一致", status_code=409)
            for binding in fact.dialogue:
                utterance = utterance_by_id.get(binding.utterance_id)
                if utterance is None or (
                    binding.utterance_number != utterance.utterance_number
                    or binding.utterance_start_us != utterance.start_us
                    or binding.utterance_end_us != utterance.end_us
                    or binding.text != utterance.text
                    or binding.language != utterance.language
                ):
                    raise AppError("P9_P6_CANONICAL_MISMATCH", "P8 dialogue 与 CURRENT P6 canonical Evidence 不一致", status_code=409)
    return facts, content


def _load_inputs(db: Session, project_id: str) -> P9Inputs:
    project = get_project(db, project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError("SOURCE_RESOLUTION_NOT_ALLOWED", "当前项目类型不执行 P9 最终归一", status_code=422)
    source = _required_source(db, project_id)
    dialogue = _required_dialogue(db, project_id, source)
    bible, bible_content, _ = _required_bible(db, project_id, source, dialogue)
    shots = _required_shots(db, project_id, source)
    contexts = _episode_contexts(
        db,
        project_id=project_id,
        source=source,
        dialogue_artifact=dialogue,
        shots_artifact=shots,
        bible_content=bible_content,
    )
    facts, facts_content = _required_facts(
        db,
        project_id=project_id,
        source=source,
        dialogue=dialogue,
        bible=bible,
        shots=shots,
        contexts=contexts,
    )
    return P9Inputs(
        source=source,
        dialogue=dialogue,
        bible=bible,
        bible_content=bible_content,
        shots=shots,
        facts=facts,
        facts_content=facts_content,
        contexts=tuple(contexts),
    )


def _provider_for_project(project) -> SourceResolutionProvider:
    return build_source_resolution_provider(get_settings(), project.source_understanding_provider)


def _previous_snapshot(db: Session, project_id: str) -> dict[str, list[str] | None]:
    result: dict[str, list[str] | None] = {}
    for kind, artifact_type in _KIND_ARTIFACT.items():
        previous = _latest_artifact(db, project_id, artifact_type)
        result[kind.value] = [previous.id, previous.input_fingerprint] if previous is not None else None
    return result


def _fingerprint_inputs(db: Session, inputs: P9Inputs, provider: SourceResolutionProvider) -> str:
    skill_profiles = {skill_id: provider.profile(skill_id) for skill_id in P9_SKILL_IDS}
    return _sha(
        {
            "task": P9_TASK_TYPE,
            "prompt_version": P9_PROMPT_VERSION,
            "schema_version": P9_SCHEMA_VERSION,
            "source_truth_contract": P9_SOURCE_TRUTH_CONTRACT,
            "skills": {
                skill_id: [get_professional_skill(skill_id).id, get_professional_skill(skill_id).version]
                for skill_id in P9_SKILL_IDS
            },
            "profiles": skill_profiles,
            "source_video": [inputs.source.id, inputs.source.input_fingerprint],
            "source_bible": [inputs.bible.id, inputs.bible.input_fingerprint],
            "source_shot_facts": [inputs.facts.id, inputs.facts.input_fingerprint],
            "shot_anchors": [inputs.shots.id, inputs.shots.input_fingerprint],
            "source_dialogue": [inputs.dialogue.id, inputs.dialogue.input_fingerprint],
            "previous": _previous_snapshot(db, inputs.source.project_id),
            "episodes": [
                {
                    "episode_id": item.episode.id,
                    "source_asset_sha256": item.asset.sha256,
                    "shot_boundary_set_id": item.shot_boundary.id,
                    "shot_boundary_fingerprint": item.shot_boundary.input_fingerprint,
                    "source_evidence_set_id": item.evidence_set.id,
                    "source_evidence_fingerprint": item.evidence_set.input_fingerprint,
                    "shots": [
                        [shot.id, shot.shot_number, shot.start_us, shot.end_us, shot.duration_us]
                        for shot in item.shot_anchors
                    ],
                    "dialogue": [
                        [u.id, u.utterance_number, u.start_us, u.end_us, u.text, u.language]
                        for u in item.dialogue
                    ],
                    "visual_text": [[v.id, v.start_us, v.end_us, v.text] for v in item.visual_text],
                }
                for item in inputs.contexts
            ],
        }
    )


def create_source_resolution_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    _assert_p9_storage_ready(db)
    inputs = _load_inputs(db, project_id)
    project = get_project(db, project_id)
    provider = _provider_for_project(project)
    fingerprint = _fingerprint_inputs(db, inputs, provider)
    return create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P9_TASK_TYPE,
            task_name="Speaker / Character / Scene / Prop 最终归一",
            input_fingerprint=fingerprint,
            input_artifact_ids=[
                inputs.source.id,
                inputs.bible.id,
                inputs.facts.id,
                inputs.shots.id,
                inputs.dialogue.id,
            ],
            max_attempts=3,
        ),
    )


def _assert_p9_storage_ready(db: Session) -> None:
    if not inspect(db.get_bind()).has_table(SourceResolutionRevision.__tablename__):
        raise AppError(
            "P9_DATABASE_MIGRATION_REQUIRED",
            "P9 数据库迁移尚未应用，请先执行 alembic upgrade head",
            status_code=503,
        )


def _assert_task_snapshot(db: Session, task: TaskWorkerRead | Task, inputs: P9Inputs, provider: SourceResolutionProvider) -> None:
    expected_ids = {inputs.source.id, inputs.bible.id, inputs.facts.id, inputs.shots.id, inputs.dialogue.id}
    if set(task.input_artifact_ids_json) != expected_ids:
        raise AppError("STALE_ARTIFACT_INPUT", "P9 输入 Artifact 已变化，请重新创建任务", status_code=409)
    if task.input_fingerprint != _fingerprint_inputs(db, inputs, provider):
        raise AppError("STALE_ARTIFACT_INPUT", "P9 输入 fingerprint、Professional Skill 或 Provider profile 已变化", status_code=409)


def _episode_fact_map(inputs: P9Inputs) -> dict[str, Any]:
    return {episode.episode_id: episode for episode in inputs.facts_content.episodes}


def _shot_fact_map(inputs: P9Inputs) -> dict[str, tuple[str, Any]]:
    result: dict[str, tuple[str, Any]] = {}
    for episode in inputs.facts_content.episodes:
        for shot in episode.shots:
            if shot.shot_anchor_id in result:
                raise AppError("P9_SHOT_ANCHOR_DUPLICATED", "P8 shot_anchor_id 重复", status_code=409)
            result[shot.shot_anchor_id] = (episode.episode_id, shot)
    return result


def _utterance_map(inputs: P9Inputs) -> dict[str, tuple[str, Any]]:
    result: dict[str, tuple[str, Any]] = {}
    for context in inputs.contexts:
        for utterance in context.dialogue:
            if utterance.id in result:
                raise AppError("P9_UTTERANCE_ID_DUPLICATED", "P6 canonical utterance id 重复", status_code=409)
            result[utterance.id] = (context.episode.id, utterance)
    return result


def _known_ref_ids(inputs: P9Inputs) -> set[str]:
    values = {item.episode.id for item in inputs.contexts}
    for context in inputs.contexts:
        values.update(item.id for item in context.shot_anchors)
        values.update(item.id for item in context.dialogue)
        values.update(item.id for item in context.visual_text)
        values.add(context.shot_boundary.id)
        values.add(context.evidence_set.id)
        values.update(item.character_id for item in context.source_bible_episode.characters)
        values.update(item.scene_id for item in context.source_bible_episode.scenes)
        values.update(item.prop_id for item in context.source_bible_episode.key_props)
    for episode in inputs.facts_content.episodes:
        for shot in episode.shots:
            values.update(shot.visual_text_evidence_ids)
    return values


def _validate_evidence_refs(refs: list[EvidenceRef], inputs: P9Inputs) -> None:
    known = _known_ref_ids(inputs)
    episode_ids = {item.episode.id for item in inputs.contexts}
    shot_ids = set(_shot_fact_map(inputs))
    utterance_ids = set(_utterance_map(inputs))
    for ref in refs:
        if ref.ref_id not in known:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 Provider 引用了不存在的 Source evidence/candidate id", status_code=422, details={"ref_id": ref.ref_id})
        if ref.episode_id is not None and ref.episode_id not in episode_ids:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 evidence episode_id 无效", status_code=422)
        if ref.shot_anchor_id is not None and ref.shot_anchor_id not in shot_ids:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 evidence shot_anchor_id 无效", status_code=422)
        if ref.utterance_id is not None and ref.utterance_id not in utterance_ids:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 evidence utterance_id 无效", status_code=422)


def _groups(groups: list[EntityGroupSemantic], inputs: P9Inputs) -> dict[str, EntityGroupSemantic]:
    by_key = {item.group_key: item for item in groups}
    if len(by_key) != len(groups):
        raise AppError("P9_GROUP_KEY_DUPLICATED", "P9 Provider group_key 重复", status_code=422)
    for group in groups:
        if group.resolution_status != ResolutionStatus.RESOLVED:
            raise AppError("P9_GROUP_STATUS_INVALID", "Provider stable group 必须是 RESOLVED；未决结果不得伪造 stable identity", status_code=422)
        if not group.evidence_refs:
            raise AppError("P9_GROUP_EVIDENCE_REQUIRED", "Provider stable group 必须提供可追溯 evidence_refs", status_code=422)
        _validate_evidence_refs(group.evidence_refs, inputs)
    return by_key


def _binding(group_key: str | None, status: ResolutionStatus, groups: dict[str, EntityGroupSemantic]) -> EntityGroupSemantic | None:
    if status == ResolutionStatus.MANUAL_CONFIRMED:
        raise AppError("P9_PROVIDER_MANUAL_STATUS_INVALID", "Provider 不得输出 MANUAL_CONFIRMED", status_code=422)
    if group_key is None:
        if status == ResolutionStatus.RESOLVED:
            raise AppError("P9_RESOLUTION_BINDING_INVALID", "RESOLVED 必须引用 stable group", status_code=422)
        return None
    group = groups.get(group_key)
    if group is None or status != ResolutionStatus.RESOLVED:
        raise AppError("P9_RESOLUTION_BINDING_INVALID", "stable group binding 无效", status_code=422)
    return group


def _stable_id(prefix: str, refs: list[str]) -> str:
    return f"p9-{prefix}-{_sha(sorted(refs))[:20]}"


def _compose_characters(inputs: P9Inputs, semantic: CharacterResolutionSemantic) -> CharacterResolutionContent:
    shot_map = _shot_fact_map(inputs)
    expected = {
        (shot_id, candidate.id)
        for shot_id, (_episode_id, shot) in shot_map.items()
        for candidate in shot.bindings.characters
    }
    actual = [(item.shot_anchor_id, item.source_candidate_id) for item in semantic.observations]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise AppError("P9_CHARACTER_OBSERVATION_SET_INVALID", "Character observations 必须与 P8 character bindings 一一对应", status_code=422)
    group_map = _groups(semantic.groups, inputs)
    members: dict[str, list[tuple[str, str]]] = {key: [] for key in group_map}
    observations: list[CharacterObservation] = []
    for item in semantic.observations:
        group = _binding(item.group_key, item.resolution_status, group_map)
        character_id = None
        if group is not None:
            members[group.group_key].append((item.shot_anchor_id, item.source_candidate_id))
        observations.append(
            CharacterObservation(
                shot_anchor_id=item.shot_anchor_id,
                source_candidate_id=item.source_candidate_id,
                character_id=character_id,
                resolution_status=item.resolution_status,
                reason=item.reason,
            )
        )
    entity_by_group: dict[str, CharacterEntity] = {}
    for key, group in group_map.items():
        refs = sorted({f"{shot_id}:{candidate_id}" for shot_id, candidate_id in members[key]})
        if not refs:
            raise AppError("P9_UNREFERENCED_GROUP", "Character stable group 没有任何 P8 observation", status_code=422)
        character_id = _stable_id("chr", refs)
        episode_ids = sorted({shot_map[shot_id][0] for shot_id, _candidate_id in members[key]})
        shot_ids = sorted({shot_id for shot_id, _candidate_id in members[key]})
        candidate_ids = sorted({candidate_id for _shot_id, candidate_id in members[key]})
        entity_by_group[key] = CharacterEntity(
            entity_id=character_id,
            character_id=character_id,
            display_name=group.display_name,
            aliases=group.aliases,
            source_candidate_ids=candidate_ids,
            episode_ids=episode_ids,
            shot_anchor_ids=shot_ids,
            evidence_refs=group.evidence_refs,
            confidence=group.confidence,
            resolution_status=ResolutionStatus.RESOLVED,
            notes=group.notes,
        )
    for index, item in enumerate(semantic.observations):
        if item.group_key is not None:
            observations[index] = observations[index].model_copy(update={"character_id": entity_by_group[item.group_key].character_id})
    return CharacterResolutionContent(entities=list(entity_by_group.values()), observations=observations)


def _compose_speakers(
    inputs: P9Inputs,
    characters: CharacterResolutionContent,
    semantic: SpeakerResolutionSemantic,
) -> SpeakerResolutionContent:
    utterance_map = _utterance_map(inputs)
    actual_ids = [item.utterance_id for item in semantic.attributions]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(utterance_map):
        raise AppError("P9_SPEAKER_UTTERANCE_SET_INVALID", "Speaker attribution 必须与 CURRENT P6 canonical utterance 一一对应", status_code=422)
    group_map = _groups(list(semantic.groups), inputs)
    valid_character_ids = {item.character_id for item in characters.entities}
    p7_character_ids = {
        item.character_id for context in inputs.contexts for item in context.source_bible_episode.characters
    }
    for group in semantic.groups:
        if group.character_id is not None and group.character_id not in valid_character_ids:
            raise AppError("P9_SPEAKER_CHARACTER_LINK_INVALID", "Speaker 引用了不存在的 P9 Character identity", status_code=422)
        if set(group.source_candidate_character_ids) - p7_character_ids:
            raise AppError("P9_SPEAKER_CANDIDATE_INVALID", "Speaker 引用了不存在的 P7 Character candidate", status_code=422)
    members: dict[str, list[str]] = {key: [] for key in group_map}
    attributions: list[SpeakerAttribution] = []
    for item in semantic.attributions:
        group = _binding(item.group_key, item.resolution_status, group_map)
        episode_id, utterance = utterance_map[item.utterance_id]
        if group is not None:
            members[group.group_key].append(item.utterance_id)
        attributions.append(
            SpeakerAttribution(
                episode_id=episode_id,
                utterance_id=utterance.id,
                utterance_number=utterance.utterance_number,
                start_us=utterance.start_us,
                end_us=utterance.end_us,
                text=utterance.text,
                speaker_id=None,
                resolution_status=item.resolution_status,
                reason=item.reason,
            )
        )
    entity_by_group: dict[str, SpeakerEntity] = {}
    shot_map = _shot_fact_map(inputs)
    for key, group in group_map.items():
        utterance_ids = sorted(set(members[key]))
        if not utterance_ids:
            raise AppError("P9_UNREFERENCED_GROUP", "Speaker stable group 没有 canonical utterance", status_code=422)
        speaker_id = _stable_id("spk", utterance_ids)
        episode_ids = sorted({utterance_map[value][0] for value in utterance_ids})
        shot_ids = sorted({
            shot_id
            for shot_id, (_episode_id, shot) in shot_map.items()
            if any(binding.utterance_id in set(utterance_ids) for binding in shot.dialogue)
        })
        entity_by_group[key] = SpeakerEntity(
            entity_id=speaker_id,
            speaker_id=speaker_id,
            display_name=group.display_name,
            aliases=group.aliases,
            source_candidate_ids=sorted(set(group.source_candidate_character_ids)),
            source_candidate_character_ids=sorted(set(group.source_candidate_character_ids)),
            episode_ids=episode_ids,
            shot_anchor_ids=shot_ids,
            utterance_ids=utterance_ids,
            evidence_refs=group.evidence_refs,
            confidence=group.confidence,
            resolution_status=ResolutionStatus.RESOLVED,
            notes=group.notes,
            character_id=group.character_id,
        )
    for index, item in enumerate(semantic.attributions):
        if item.group_key is not None:
            attributions[index] = attributions[index].model_copy(update={"speaker_id": entity_by_group[item.group_key].speaker_id})
    return SpeakerResolutionContent(entities=list(entity_by_group.values()), attributions=attributions)


def _compose_scenes(inputs: P9Inputs, semantic: SceneResolutionSemantic) -> SceneResolutionContent:
    shot_map = _shot_fact_map(inputs)
    actual_ids = [item.shot_anchor_id for item in semantic.assignments]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(shot_map):
        raise AppError("P9_SCENE_SHOT_SET_INVALID", "Scene assignments 必须与 CURRENT P5/P8 Shot 一一对应", status_code=422)
    group_map = _groups(semantic.groups, inputs)
    members: dict[str, list[str]] = {key: [] for key in group_map}
    assignments: list[SceneAssignment] = []
    for item in semantic.assignments:
        episode_id, shot = shot_map[item.shot_anchor_id]
        expected_candidates = {value.id for value in shot.bindings.scenes}
        if len(item.source_candidate_ids) != len(set(item.source_candidate_ids)) or set(item.source_candidate_ids) != expected_candidates:
            raise AppError("P9_SCENE_CANDIDATE_SET_INVALID", "Scene assignment candidate 集合必须保持 P8 事实", status_code=422)
        group = _binding(item.group_key, item.resolution_status, group_map)
        if group is not None:
            members[group.group_key].append(item.shot_anchor_id)
        assignments.append(
            SceneAssignment(
                episode_id=episode_id,
                shot_anchor_id=item.shot_anchor_id,
                shot_number=shot.shot_number,
                start_us=shot.start_us,
                end_us=shot.end_us,
                source_candidate_ids=item.source_candidate_ids,
                scene_id=None,
                resolution_status=item.resolution_status,
                reason=item.reason,
            )
        )
    entity_by_group: dict[str, SceneEntity] = {}
    for key, group in group_map.items():
        shot_ids = sorted(set(members[key]))
        if not shot_ids:
            raise AppError("P9_UNREFERENCED_GROUP", "Scene stable group 没有 Shot assignment", status_code=422)
        scene_id = _stable_id("scn", shot_ids)
        candidates = sorted({candidate.id for shot_id in shot_ids for candidate in shot_map[shot_id][1].bindings.scenes})
        entity_by_group[key] = SceneEntity(
            entity_id=scene_id,
            scene_id=scene_id,
            display_name=group.display_name,
            aliases=group.aliases,
            source_candidate_ids=candidates,
            episode_ids=sorted({shot_map[shot_id][0] for shot_id in shot_ids}),
            shot_anchor_ids=shot_ids,
            evidence_refs=group.evidence_refs,
            confidence=group.confidence,
            resolution_status=ResolutionStatus.RESOLVED,
            notes=group.notes,
            disambiguation_notes=group.notes,
        )
    for index, item in enumerate(semantic.assignments):
        if item.group_key is not None:
            assignments[index] = assignments[index].model_copy(update={"scene_id": entity_by_group[item.group_key].scene_id})
    return SceneResolutionContent(entities=list(entity_by_group.values()), assignments=assignments)


def _compose_props(inputs: P9Inputs, semantic: PropResolutionSemantic) -> PropResolutionContent:
    shot_map = _shot_fact_map(inputs)
    expected = {
        (shot_id, candidate.id)
        for shot_id, (_episode_id, shot) in shot_map.items()
        for candidate in shot.bindings.props
    }
    actual = [(item.shot_anchor_id, item.source_candidate_id) for item in semantic.observations]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise AppError("P9_PROP_OBSERVATION_SET_INVALID", "Prop observations 必须与 P8 prop bindings 一一对应", status_code=422)
    group_map = _groups(semantic.groups, inputs)
    members: dict[str, list[tuple[str, str]]] = {key: [] for key in group_map}
    observations: list[PropObservation] = []
    for item in semantic.observations:
        group = _binding(item.group_key, item.resolution_status, group_map)
        if group is not None:
            members[group.group_key].append((item.shot_anchor_id, item.source_candidate_id))
        observations.append(
            PropObservation(
                shot_anchor_id=item.shot_anchor_id,
                source_candidate_id=item.source_candidate_id,
                prop_id=None,
                resolution_status=item.resolution_status,
                reason=item.reason,
            )
        )
    entity_by_group: dict[str, PropEntity] = {}
    for key, group in group_map.items():
        refs = sorted({f"{shot_id}:{candidate_id}" for shot_id, candidate_id in members[key]})
        if not refs:
            raise AppError("P9_UNREFERENCED_GROUP", "Prop stable group 没有 P8 observation", status_code=422)
        prop_id = _stable_id("prop", refs)
        shot_ids = sorted({shot_id for shot_id, _candidate_id in members[key]})
        entity_by_group[key] = PropEntity(
            entity_id=prop_id,
            prop_id=prop_id,
            display_name=group.display_name,
            aliases=group.aliases,
            source_candidate_ids=sorted({candidate_id for _shot_id, candidate_id in members[key]}),
            episode_ids=sorted({shot_map[shot_id][0] for shot_id in shot_ids}),
            shot_anchor_ids=shot_ids,
            evidence_refs=group.evidence_refs,
            confidence=group.confidence,
            resolution_status=ResolutionStatus.RESOLVED,
            notes=group.notes,
            instance_notes=group.notes,
        )
    for index, item in enumerate(semantic.observations):
        if item.group_key is not None:
            observations[index] = observations[index].model_copy(update={"prop_id": entity_by_group[item.group_key].prop_id})
    return PropResolutionContent(entities=list(entity_by_group.values()), observations=observations)


def _canonical_dialogue(inputs: P9Inputs) -> list[dict]:
    p8_speakers: dict[str, set[tuple[str, str]]] = {}
    for episode in inputs.facts_content.episodes:
        for shot in episode.shots:
            for binding in shot.dialogue:
                if binding.speaker is not None:
                    p8_speakers.setdefault(binding.utterance_id, set()).add((binding.speaker.id, binding.speaker.label))
    result: list[dict] = []
    for context in inputs.contexts:
        for utterance in context.dialogue:
            candidates = sorted(p8_speakers.get(utterance.id, set()))
            if len(candidates) > 1:
                raise AppError("P8_SPEAKER_CANDIDATE_INCONSISTENT", "同一 canonical utterance 的 P8 speaker candidate 不一致", status_code=409)
            candidate = None if not candidates else {"id": candidates[0][0], "label": candidates[0][1]}
            result.append(
                {
                    "episode_id": context.episode.id,
                    "utterance_id": utterance.id,
                    "utterance_number": utterance.utterance_number,
                    "start_us": utterance.start_us,
                    "end_us": utterance.end_us,
                    "text": utterance.text,
                    "language": utterance.language,
                    "p8_speaker_candidate": candidate,
                }
            )
    return result


def _provider_input(inputs: P9Inputs, *, source_characters: CharacterResolutionContent | None = None) -> ProjectResolutionInput:
    return ProjectResolutionInput(
        episodes=tuple(
            ResolutionEpisodeVideo(
                source_path=resolve_source_asset_path(item.asset.relative_path),
                source_filename=item.asset.original_filename,
                mime_type=item.asset.mime_type,
                episode_id=item.episode.id,
                episode_order=item.episode.episode_order,
                duration_us=item.episode.duration_us,
                source_asset_sha256=item.asset.sha256,
            )
            for item in inputs.contexts
        ),
        source_language=get_project_language(inputs.contexts),
        source_bible=inputs.bible_content.model_dump(mode="json"),
        source_shot_facts=inputs.facts_content.model_dump(mode="json"),
        canonical_dialogue=_canonical_dialogue(inputs),
        source_characters=source_characters.model_dump(mode="json") if source_characters is not None else None,
    )


def get_project_language(contexts: tuple[EpisodeContext, ...]) -> str | None:
    # P9 canonical dialogue already carries per-utterance language. Keep this helper
    # detached from Session state so Provider execution never performs hidden DB reads.
    for context in contexts:
        for utterance in context.dialogue:
            if utterance.language:
                return utterance.language
    return None


def _dispatch(provider: SourceResolutionProvider, skill_id: str, payload: ProjectResolutionInput) -> ProviderDispatchResult:
    result = provider.analyze(skill_id, payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _run_provider_skill(
    context: TaskExecutionContext,
    task: TaskWorkerRead,
    inputs: P9Inputs,
    provider: SourceResolutionProvider,
    *,
    kind: SourceResolutionKind,
    payload: ProjectResolutionInput,
    staged_character_fingerprint: str | None = None,
) -> tuple[Any, ResolutionProviderJobProvenance, dict]:
    skill_id = _KIND_SKILL[kind]
    profile = provider.profile(skill_id)
    job_payload = {
        "profile": P9_PROMPT_VERSION,
        "schema_version": P9_SCHEMA_VERSION,
        "source_truth_contract": P9_SOURCE_TRUTH_CONTRACT,
        "professional_skill_id": skill_id,
        "professional_skill_version": get_professional_skill(skill_id).version,
        "resolution_kind": kind.value,
        "source_video_artifact_id": inputs.source.id,
        "source_bible_artifact_id": inputs.bible.id,
        "source_shot_facts_artifact_id": inputs.facts.id,
        "shot_anchors_artifact_id": inputs.shots.id,
        "source_dialogue_artifact_id": inputs.dialogue.id,
        "episode_ids": [item.episode.id for item in inputs.contexts],
        "provider_profile": profile,
        "staged_character_fingerprint": staged_character_fingerprint,
    }
    with context.session_factory() as db:
        job, dispatched = dispatch_provider_call(
            db,
            task_id=task.id,
            provider=provider.provider_name,
            model=provider.model_name,
            capability=_KIND_CAPABILITY[kind],
            payload=job_payload,
            artifact_id=inputs.facts.id,
            remote_call=lambda _job: _dispatch(provider, skill_id, payload),
        )
    provenance = ResolutionProviderJobProvenance(
        provider_job_id=job.id,
        provider=job.provider,
        model=job.model,
        capability=job.capability,
        professional_skill_id=skill_id,
        payload_fingerprint=job.payload_fingerprint,
        remote_job_id=job.remote_job_id,
    )
    return dispatched.value, provenance, profile


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> P9ExecutionResult:
    with context.session_factory() as db:
        inputs = _load_inputs(db, task.project_id)
        project = get_project(db, task.project_id)
        provider = _provider_for_project(project)
        _assert_task_snapshot(db, task, inputs, provider)

    jobs: dict[SourceResolutionKind, tuple[ResolutionProviderJobProvenance, ...]] = {}
    profiles: dict[SourceResolutionKind, dict] = {}

    context.checkpoint({"stage": "character_resolution", "scope": "ALL_FULL_EPISODES"}, progress_percent=8)
    raw, job, profile = _run_provider_skill(
        context, task, inputs, provider, kind=SourceResolutionKind.CHARACTER, payload=_provider_input(inputs)
    )
    semantic = raw if isinstance(raw, CharacterResolutionSemantic) else CharacterResolutionSemantic.model_validate(raw)
    characters = _compose_characters(inputs, semantic)
    jobs[SourceResolutionKind.CHARACTER] = (job,)
    profiles[SourceResolutionKind.CHARACTER] = profile

    context.checkpoint({"stage": "speaker_attribution", "scope": "ALL_FULL_EPISODES"}, progress_percent=32)
    staged_character_fingerprint = _sha(characters.model_dump(mode="json"))
    raw, job, profile = _run_provider_skill(
        context,
        task,
        inputs,
        provider,
        kind=SourceResolutionKind.SPEAKER,
        payload=_provider_input(inputs, source_characters=characters),
        staged_character_fingerprint=staged_character_fingerprint,
    )
    semantic = raw if isinstance(raw, SpeakerResolutionSemantic) else SpeakerResolutionSemantic.model_validate(raw)
    speakers = _compose_speakers(inputs, characters, semantic)
    jobs[SourceResolutionKind.SPEAKER] = (job,)
    profiles[SourceResolutionKind.SPEAKER] = profile

    context.checkpoint({"stage": "scene_resolution", "scope": "ALL_FULL_EPISODES"}, progress_percent=54)
    raw, job, profile = _run_provider_skill(
        context, task, inputs, provider, kind=SourceResolutionKind.SCENE, payload=_provider_input(inputs)
    )
    semantic = raw if isinstance(raw, SceneResolutionSemantic) else SceneResolutionSemantic.model_validate(raw)
    scenes = _compose_scenes(inputs, semantic)
    jobs[SourceResolutionKind.SCENE] = (job,)
    profiles[SourceResolutionKind.SCENE] = profile

    context.checkpoint({"stage": "prop_resolution", "scope": "ALL_FULL_EPISODES"}, progress_percent=76)
    raw, job, profile = _run_provider_skill(
        context, task, inputs, provider, kind=SourceResolutionKind.PROP, payload=_provider_input(inputs)
    )
    semantic = raw if isinstance(raw, PropResolutionSemantic) else PropResolutionSemantic.model_validate(raw)
    props = _compose_props(inputs, semantic)
    jobs[SourceResolutionKind.PROP] = (job,)
    profiles[SourceResolutionKind.PROP] = profile

    context.checkpoint({"stage": "validate_p9_resolution_set"}, progress_percent=94)
    return P9ExecutionResult(
        characters=characters,
        speakers=speakers,
        scenes=scenes,
        props=props,
        provider_jobs=jobs,
        provider_profiles=profiles,
    )


def _episode_provenance(inputs: P9Inputs) -> list[ResolutionEpisodeInputProvenance]:
    return [
        ResolutionEpisodeInputProvenance(
            episode_id=item.episode.id,
            source_asset_sha256=item.asset.sha256,
            shot_boundary_set_id=item.shot_boundary.id,
            shot_boundary_fingerprint=item.shot_boundary.input_fingerprint,
            source_evidence_set_id=item.evidence_set.id,
            source_evidence_fingerprint=item.evidence_set.input_fingerprint,
        )
        for item in inputs.contexts
    ]


def _persist_revision(
    db: Session,
    *,
    artifact: ArtifactNode,
    kind: SourceResolutionKind,
    content: BaseException | Any,
    provenance: SourceResolutionProvenance,
) -> SourceResolutionRevision:
    row = SourceResolutionRevision(
        project_id=artifact.project_id,
        artifact_id=artifact.id,
        resolution_kind=kind.value,
        source_video_artifact_id=provenance.source_video_artifact_id,
        source_bible_artifact_id=provenance.source_bible_artifact_id,
        source_shot_facts_artifact_id=provenance.source_shot_facts_artifact_id,
        shot_anchors_artifact_id=provenance.shot_anchors_artifact_id,
        source_dialogue_artifact_id=provenance.source_dialogue_artifact_id,
        generated_by_task_id=provenance.generated_by_task_id,
        schema_version=P9_SCHEMA_VERSION,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _artifact_fingerprint(task_fingerprint: str, kind: SourceResolutionKind, previous: ArtifactNode | None) -> str:
    skill = get_professional_skill(_KIND_SKILL[kind])
    return _sha(
        {
            "p9_task_input_fingerprint": task_fingerprint,
            "resolution_kind": kind.value,
            "schema_version": P9_SCHEMA_VERSION,
            "professional_skill": [skill.id, skill.version],
            "previous_artifact_id": previous.id if previous is not None else None,
        }
    )


def _publish_one(
    db: Session,
    *,
    task: Task,
    inputs: P9Inputs,
    result: P9ExecutionResult,
    kind: SourceResolutionKind,
    content: Any,
    previous: ArtifactNode | None,
    source_characters_artifact: ArtifactNode | None,
) -> ArtifactNode:
    skill = get_professional_skill(_KIND_SKILL[kind])
    profile = result.provider_profiles[kind]
    provenance = SourceResolutionProvenance(
        resolution_kind=kind,
        source_video_artifact_id=inputs.source.id,
        source_video_fingerprint=inputs.source.input_fingerprint,
        source_bible_artifact_id=inputs.bible.id,
        source_bible_fingerprint=inputs.bible.input_fingerprint,
        source_shot_facts_artifact_id=inputs.facts.id,
        source_shot_facts_fingerprint=inputs.facts.input_fingerprint,
        shot_anchors_artifact_id=inputs.shots.id,
        shot_anchors_fingerprint=inputs.shots.input_fingerprint,
        source_dialogue_artifact_id=inputs.dialogue.id if kind == SourceResolutionKind.SPEAKER else None,
        source_dialogue_fingerprint=inputs.dialogue.input_fingerprint if kind == SourceResolutionKind.SPEAKER else None,
        source_characters_artifact_id=source_characters_artifact.id if source_characters_artifact is not None else None,
        source_characters_fingerprint=source_characters_artifact.input_fingerprint if source_characters_artifact is not None else None,
        episode_inputs=_episode_provenance(inputs),
        provider_jobs=list(result.provider_jobs[kind]),
        provider=provider_name(profile),
        model=str(profile.get("model") or "") or None,
        prompt_version=P9_PROMPT_VERSION,
        schema_version=P9_SCHEMA_VERSION,
        professional_skill_id=skill.id,
        professional_skill_version=skill.version,
        source_truth_contract=P9_SOURCE_TRUTH_CONTRACT,
        generated_by_task_id=task.id,
        supersedes_artifact_id=previous.id if previous is not None else None,
    )
    fingerprint = _artifact_fingerprint(task.input_fingerprint, kind, previous)
    artifact = publish_validated_task_artifact(
        db,
        task_id=task.id,
        validation_passed=True,
        artifact_type=_KIND_ARTIFACT[kind],
        namespace=ArtifactNamespace.SOURCE,
        label=_KIND_LABEL[kind],
        input_fingerprint=fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        metadata_json={
            "schema_version": P9_SCHEMA_VERSION,
            "resolution_kind": kind.value,
            "source_video_artifact_id": inputs.source.id,
            "source_bible_artifact_id": inputs.bible.id,
            "source_shot_facts_artifact_id": inputs.facts.id,
            "shot_anchors_artifact_id": inputs.shots.id,
            "source_dialogue_artifact_id": inputs.dialogue.id if kind == SourceResolutionKind.SPEAKER else None,
            "source_characters_artifact_id": source_characters_artifact.id if source_characters_artifact is not None else None,
            "entity_count": len(content.entities),
            "provider": provenance.provider,
            "model": provenance.model,
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P9_SOURCE_TRUTH_CONTRACT,
            "document_title": _KIND_LABEL[kind],
        },
    )
    try:
        _persist_revision(db, artifact=artifact, kind=kind, content=content, provenance=provenance)
    except Exception:
        db.rollback()
        if db.scalar(select(SourceResolutionRevision.id).where(SourceResolutionRevision.artifact_id == artifact.id)) is None:
            db.delete(artifact)
            db.commit()
        raise
    for upstream_id, relation in (
        (inputs.source.id, ArtifactRelationType.DERIVED_FROM),
        (inputs.bible.id, ArtifactRelationType.USES),
        (inputs.facts.id, ArtifactRelationType.DERIVED_FROM),
        (inputs.shots.id, ArtifactRelationType.DERIVED_FROM),
    ):
        create_artifact_relation(
            db,
            project_id=task.project_id,
            source_node_id=upstream_id,
            target_node_id=artifact.id,
            relation_type=relation,
        )
    if kind == SourceResolutionKind.SPEAKER:
        create_artifact_relation(
            db,
            project_id=task.project_id,
            source_node_id=inputs.dialogue.id,
            target_node_id=artifact.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )
        if source_characters_artifact is None:
            raise AppError("P9_SOURCE_CHARACTERS_REQUIRED", "Speaker 发布需要本次 P9 Character Artifact", status_code=500)
        create_artifact_relation(
            db,
            project_id=task.project_id,
            source_node_id=source_characters_artifact.id,
            target_node_id=artifact.id,
            relation_type=ArtifactRelationType.USES,
        )
    if previous is not None:
        create_artifact_relation(
            db,
            project_id=task.project_id,
            source_node_id=artifact.id,
            target_node_id=previous.id,
            relation_type=ArtifactRelationType.SUPERSEDES,
        )
    return artifact


def provider_name(profile: dict) -> str | None:
    value = str(profile.get("provider") or "").strip()
    return value or None


def _publish_all(db: Session, *, task_id: str, result: P9ExecutionResult) -> dict[SourceResolutionKind, ArtifactNode]:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "P9 任务不存在", status_code=404)
    inputs = _load_inputs(db, task.project_id)
    provider = _provider_for_project(get_project(db, task.project_id))
    _assert_task_snapshot(db, task, inputs, provider)
    previous = {kind: _latest_artifact(db, task.project_id, artifact_type) for kind, artifact_type in _KIND_ARTIFACT.items()}
    contents = {
        SourceResolutionKind.CHARACTER: result.characters,
        SourceResolutionKind.SPEAKER: result.speakers,
        SourceResolutionKind.SCENE: result.scenes,
        SourceResolutionKind.PROP: result.props,
    }
    published: dict[SourceResolutionKind, ArtifactNode] = {}
    try:
        for kind in (
            SourceResolutionKind.CHARACTER,
            SourceResolutionKind.SPEAKER,
            SourceResolutionKind.SCENE,
            SourceResolutionKind.PROP,
        ):
            published[kind] = _publish_one(
                db,
                task=task,
                inputs=inputs,
                result=result,
                kind=kind,
                content=contents[kind],
                previous=previous[kind],
                source_characters_artifact=published.get(SourceResolutionKind.CHARACTER) if kind == SourceResolutionKind.SPEAKER else None,
            )
    except Exception:
        db.rollback()
        for artifact_type in _KIND_ARTIFACT.values():
            invalidate_current_artifact_type(db, project_id=task.project_id, artifact_type=artifact_type)
        raise
    return published


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != P9_TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.task_type == P9_TASK_TYPE, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
        .values(
            status=TaskStatus.RUNNING,
            attempt=task.attempt + 1,
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Task.started_at, now),
            finished_at=None,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    claimed = db.get(Task, task_id)
    if claimed is not None:
        db.refresh(claimed)
    return claimed


def _fail_if_running(factory: sessionmaker[Session], task_id: str, worker_id: str, error: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_failed(db, task_id, safe_error=error, worker_id=worker_id)


def run_p9_source_resolution_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p9-source-resolution-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        result = _execute(context, snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        _fail_if_running(session_factory, snapshot.id, worker_id, f"P9 最终归一失败（{exc.code}）")
        return
    except Exception as exc:
        _fail_if_running(session_factory, snapshot.id, worker_id, f"P9 最终归一失败（{type(exc).__name__}）")
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _publish_all(db, task_id=snapshot.id, result=result)
    except AppError as exc:
        _mark_publish_failed(session_factory, snapshot.id, f"P9 正式 Artifact 发布失败（{exc.code}）")
    except Exception as exc:
        _mark_publish_failed(session_factory, snapshot.id, f"P9 正式 Artifact 发布失败（{type(exc).__name__}）")


def _mark_publish_failed(factory: sessionmaker[Session], task_id: str, message: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != TaskStatus.SUCCEEDED:
            return
        now = utc_now()
        task.status = TaskStatus.FAILED
        task.progress_percent = min(task.progress_percent, 99)
        task.last_error = message[:1000]
        task.finished_at = now
        task.updated_at = now
        db.add(task)
        db.commit()


def _read_one(db: Session, project_id: str, kind: SourceResolutionKind):
    artifact_type = _KIND_ARTIFACT[kind]
    current = _current_artifact(db, project_id, artifact_type)
    latest = current or _latest_artifact(db, project_id, artifact_type)
    if latest is None:
        status = SourceResolutionResultStatus.NOT_BUILT
        if kind == SourceResolutionKind.CHARACTER:
            return CharacterResolutionRead(status=status)
        if kind == SourceResolutionKind.SPEAKER:
            return SpeakerResolutionRead(status=status)
        if kind == SourceResolutionKind.SCENE:
            return SceneResolutionRead(status=status)
        return PropResolutionRead(status=status)
    row = db.scalar(select(SourceResolutionRevision).where(SourceResolutionRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("SOURCE_RESOLUTION_CONTENT_MISSING", "P9 Artifact 缺少正式 revision 内容", status_code=500)
    status = SourceResolutionResultStatus.CURRENT if current is not None else SourceResolutionResultStatus.STALE
    provenance = SourceResolutionProvenance.model_validate(row.provenance_json)
    common = {
        "status": status,
        "artifact_id": latest.id,
        "revision": latest.revision,
        "input_fingerprint": latest.input_fingerprint,
        "provenance": provenance,
    }
    if kind == SourceResolutionKind.CHARACTER:
        return CharacterResolutionRead(content=CharacterResolutionContent.model_validate(row.content_json), **common)
    if kind == SourceResolutionKind.SPEAKER:
        return SpeakerResolutionRead(content=SpeakerResolutionContent.model_validate(row.content_json), **common)
    if kind == SourceResolutionKind.SCENE:
        return SceneResolutionRead(content=SceneResolutionContent.model_validate(row.content_json), **common)
    return PropResolutionRead(content=PropResolutionContent.model_validate(row.content_json), **common)


def get_source_resolution(db: Session, project_id: str) -> SourceResolutionRead:
    get_project(db, project_id)
    return SourceResolutionRead(
        project_id=project_id,
        characters=_read_one(db, project_id, SourceResolutionKind.CHARACTER),
        speakers=_read_one(db, project_id, SourceResolutionKind.SPEAKER),
        scenes=_read_one(db, project_id, SourceResolutionKind.SCENE),
        props=_read_one(db, project_id, SourceResolutionKind.PROP),
    )


def list_source_resolution_revisions(db: Session, project_id: str) -> list[SourceResolutionRevisionSummary]:
    get_project(db, project_id)
    artifact_types = [item.value for item in _KIND_ARTIFACT.values()]
    artifacts = list(
        db.scalars(
            select(ArtifactNode)
            .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type.in_(artifact_types))
            .order_by(ArtifactNode.created_at.desc(), ArtifactNode.revision.desc())
        ).all()
    )
    result: list[SourceResolutionRevisionSummary] = []
    type_to_kind = {artifact_type.value: kind for kind, artifact_type in _KIND_ARTIFACT.items()}
    for artifact in artifacts:
        row = db.scalar(select(SourceResolutionRevision).where(SourceResolutionRevision.artifact_id == artifact.id))
        if row is None:
            continue
        provenance = SourceResolutionProvenance.model_validate(row.provenance_json)
        result.append(
            SourceResolutionRevisionSummary(
                resolution_kind=type_to_kind[artifact.artifact_type],
                artifact_id=artifact.id,
                revision=artifact.revision,
                status=SourceResolutionResultStatus.CURRENT if artifact.is_current and artifact.validity == ArtifactValidity.CURRENT else SourceResolutionResultStatus.STALE,
                input_fingerprint=artifact.input_fingerprint,
                created_at=artifact.created_at.isoformat(),
                supersedes_artifact_id=provenance.supersedes_artifact_id,
                adjudication=provenance.adjudication,
            )
        )
    return result
