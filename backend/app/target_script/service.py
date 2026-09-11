import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.source_snapshot.models import SourceVideoSnapshotRevision
from app.source_snapshot.schemas import SourceVideoSnapshotContent
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import (
    ReplicaAdaptationPlanContent,
    ReplicaTargetBibleContent,
    TargetBibleArtifactKind,
)
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.providers import (
    TargetScriptProvider,
    TargetScriptProviderInput,
    TargetScriptProviderResult,
    build_target_script_provider,
)
from app.target_script.schemas import (
    P12_PROMPT_VERSION,
    P12_SCHEMA_VERSION,
    P12_SKILL_ID,
    P12_SOURCE_DIALOGUE_CONTRACT,
    P12_TARGET_CONTRACT,
    ReplicaTargetScriptContent,
    ReplicaTargetScriptRead,
    ReplicaTargetScriptRevisionSummary,
    TargetScriptDialogueLine,
    TargetScriptEpisode,
    TargetScriptProvenance,
    TargetScriptProviderJobProvenance,
    TargetScriptResultStatus,
    TargetScriptSemantic,
)
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    resume_task,
    retry_task,
)
from app.workflow.worker import TaskExecutionContext


P12_TASK_TYPE = "P12_TARGET_SCRIPT_LOCALIZATION"
# Engineering exists before formal admission. Flip only in the post-P11-PASS admission change.
P12_FORMALLY_ADMITTED = False


@dataclass(frozen=True)
class P12Inputs:
    project: Any
    snapshot_artifact: ArtifactNode
    snapshot_revision: SourceVideoSnapshotRevision
    snapshot_content: SourceVideoSnapshotContent
    adaptation_plan_artifact: ArtifactNode
    adaptation_plan_revision: ReplicaTargetRevision
    adaptation_plan: ReplicaAdaptationPlanContent
    target_bible_artifact: ArtifactNode
    target_bible_revision: ReplicaTargetRevision
    target_bible: ReplicaTargetBibleContent


@dataclass(frozen=True)
class P12ExecutionResult:
    target_script: ReplicaTargetScriptContent
    provider_job: TargetScriptProviderJobProvenance
    provider_profile: dict


def _sha(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _assert_storage_ready(db: Session) -> None:
    if not inspect(db.get_bind()).has_table(ReplicaTargetScriptRevision.__tablename__):
        raise AppError(
            "P12_DATABASE_MIGRATION_REQUIRED",
            "P12 数据库迁移尚未应用，请先执行 alembic upgrade head",
            status_code=503,
        )


def _assert_p12_admitted() -> None:
    """Fail closed until a post-P11-PASS change explicitly admits P12.

    TARGET_SCRIPT intentionally remains PLANNED while P12 itself is being accepted,
    so its capability availability cannot be the P12 execution switch. A separate
    admission constant makes the preimplementation state explicit and non-bypassable
    from API/UI inputs. P11 capabilities are rechecked as a second independent gate.
    """

    if not P12_FORMALLY_ADMITTED:
        raise AppError(
            "P12_NOT_ADMITTED",
            "P12 仅完成工程预实现；需在 P11 真实人工 PASS 后另行正式准入",
            status_code=409,
            details={"formal_admission": False},
        )

    blockers = [
        capability.value
        for capability in (Capability.LOCALIZATION, Capability.TARGET_BIBLE)
        if CAPABILITY_BY_ID[capability].availability != CapabilityAvailability.AVAILABLE
    ]
    if blockers:
        raise AppError(
            "P12_NOT_ADMITTED",
            "P11 尚未真实人工验收通过，当前不能执行目标剧本生成",
            status_code=409,
            details={"required_p11_capabilities": blockers},
        )


def _assert_replica(project: Any) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError(
            "REPLICA_TARGET_SCRIPT_NOT_ALLOWED",
            "当前 P12 目标剧本仅用于复刻短剧",
            status_code=422,
        )


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    rows = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == artifact_type.value,
                ArtifactNode.validity == ArtifactValidity.CURRENT,
                ArtifactNode.is_current.is_(True),
            )
        ).all()
    )
    if len(rows) > 1:
        raise AppError(
            "P12_CURRENT_ARTIFACT_AMBIGUOUS",
            f"{artifact_type.value} 存在多个 CURRENT Artifact",
            status_code=409,
        )
    return rows[0] if rows else None


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )


def _required_current_artifact(
    db: Session,
    project_id: str,
    artifact_type: ArtifactType,
    *,
    missing_code: str,
    stale_code: str,
    label: str,
) -> ArtifactNode:
    current = _current_artifact(db, project_id, artifact_type)
    if current is not None:
        return current
    latest = _latest_artifact(db, project_id, artifact_type)
    if latest is None:
        raise AppError(missing_code, f"P12 需要 CURRENT {label}", status_code=409)
    raise AppError(stale_code, f"{label} 已 STALE，请先重建上游结果", status_code=409)


def _load_inputs(db: Session, project_id: str) -> P12Inputs:
    project = get_project(db, project_id)
    _assert_replica(project)
    snapshot = _required_current_artifact(
        db,
        project_id,
        ArtifactType.SOURCE_VIDEO_SNAPSHOT,
        missing_code="P12_SOURCE_SNAPSHOT_REQUIRED",
        stale_code="P12_SOURCE_SNAPSHOT_STALE",
        label="SOURCE_VIDEO_SNAPSHOT",
    )
    plan_artifact = _required_current_artifact(
        db,
        project_id,
        ArtifactType.ADAPTATION_PLAN,
        missing_code="P12_ADAPTATION_PLAN_REQUIRED",
        stale_code="P12_ADAPTATION_PLAN_STALE",
        label="ADAPTATION_PLAN",
    )
    bible_artifact = _required_current_artifact(
        db,
        project_id,
        ArtifactType.TARGET_BIBLE,
        missing_code="P12_TARGET_BIBLE_REQUIRED",
        stale_code="P12_TARGET_BIBLE_STALE",
        label="TARGET_BIBLE",
    )

    snapshot_row = db.scalar(
        select(SourceVideoSnapshotRevision).where(SourceVideoSnapshotRevision.artifact_id == snapshot.id)
    )
    if snapshot_row is None:
        raise AppError("P12_SOURCE_SNAPSHOT_CONTENT_MISSING", "CURRENT Source Snapshot 缺少 typed revision", status_code=500)
    plan_row = db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == plan_artifact.id))
    bible_row = db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == bible_artifact.id))
    if plan_row is None or plan_row.artifact_kind != TargetBibleArtifactKind.ADAPTATION_PLAN.value:
        raise AppError("P12_ADAPTATION_PLAN_CONTENT_MISSING", "CURRENT Adaptation Plan 缺少 P11 typed revision", status_code=500)
    if bible_row is None or bible_row.artifact_kind != TargetBibleArtifactKind.TARGET_BIBLE.value:
        raise AppError("P12_TARGET_BIBLE_CONTENT_MISSING", "CURRENT Target Bible 缺少 P11 typed revision", status_code=500)

    snapshot_content = SourceVideoSnapshotContent.model_validate(snapshot_row.content_json)
    plan = ReplicaAdaptationPlanContent.model_validate(plan_row.content_json)
    bible = ReplicaTargetBibleContent.model_validate(bible_row.content_json)
    lineage_ids = {
        plan.source_snapshot_artifact_id,
        bible.source_snapshot_artifact_id,
        plan_row.source_snapshot_artifact_id,
        bible_row.source_snapshot_artifact_id,
    }
    if lineage_ids != {snapshot.id}:
        raise AppError(
            "P12_TARGET_LINEAGE_MISMATCH",
            "CURRENT ADAPTATION_PLAN / TARGET_BIBLE 与 CURRENT SOURCE_VIDEO_SNAPSHOT lineage 不一致",
            status_code=409,
        )
    if (
        plan.target_language != project.target_language
        or bible.target_language != project.target_language
        or plan.target_region != project.target_region
        or bible.target_region != project.target_region
    ):
        raise AppError(
            "P12_TARGET_CONFIG_MISMATCH",
            "CURRENT P11 Target Artifact 与项目目标语言或地区不一致",
            status_code=409,
        )
    return P12Inputs(
        project=project,
        snapshot_artifact=snapshot,
        snapshot_revision=snapshot_row,
        snapshot_content=snapshot_content,
        adaptation_plan_artifact=plan_artifact,
        adaptation_plan_revision=plan_row,
        adaptation_plan=plan,
        target_bible_artifact=bible_artifact,
        target_bible_revision=bible_row,
        target_bible=bible,
    )


def _canonical_dialogue_manifest(inputs: P12Inputs) -> list[dict]:
    manifest: list[dict] = []
    seen: set[str] = set()
    for episode in sorted(inputs.snapshot_content.episodes, key=lambda item: item.episode_order):
        for utterance in sorted(episode.canonical_dialogue, key=lambda item: item.utterance_number):
            if utterance.utterance_id in seen:
                raise AppError(
                    "P12_CANONICAL_DIALOGUE_ID_DUPLICATE",
                    "Source Snapshot canonical dialogue utterance_id 必须全局唯一",
                    status_code=409,
                )
            seen.add(utterance.utterance_id)
            manifest.append(
                {
                    "episode_id": episode.episode_id,
                    "episode_order": episode.episode_order,
                    "utterance_id": utterance.utterance_id,
                    "utterance_number": utterance.utterance_number,
                    "source_start_us": utterance.start_us,
                    "source_end_us": utterance.end_us,
                    "source_text": utterance.text,
                    "source_language": utterance.language,
                }
            )
    return manifest


def _provider_for_project(project: Any) -> TargetScriptProvider:
    return build_target_script_provider(get_settings(), project.source_understanding_provider)


def _fingerprint_inputs(inputs: P12Inputs, provider: TargetScriptProvider) -> str:
    skill = get_professional_skill(P12_SKILL_ID)
    return _sha(
        {
            "task": P12_TASK_TYPE,
            "source_snapshot": [
                inputs.snapshot_artifact.id,
                inputs.snapshot_artifact.revision,
                inputs.snapshot_artifact.input_fingerprint,
            ],
            "adaptation_plan": [
                inputs.adaptation_plan_artifact.id,
                inputs.adaptation_plan_artifact.revision,
                inputs.adaptation_plan_artifact.input_fingerprint,
            ],
            "target_bible": [
                inputs.target_bible_artifact.id,
                inputs.target_bible_artifact.revision,
                inputs.target_bible_artifact.input_fingerprint,
            ],
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
            "skill": [skill.id, skill.version],
            "provider_profile": provider.profile(),
            "prompt_version": P12_PROMPT_VERSION,
            "schema_version": P12_SCHEMA_VERSION,
            "target_contract": P12_TARGET_CONTRACT,
            "source_dialogue_contract": P12_SOURCE_DIALOGUE_CONTRACT,
            "canonical_dialogue": _canonical_dialogue_manifest(inputs),
        }
    )


def create_target_script_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    _assert_p12_admitted()
    inputs = _load_inputs(db, project_id)
    provider = _provider_for_project(inputs.project)
    fingerprint = _fingerprint_inputs(inputs, provider)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P12_TASK_TYPE,
            task_name="生成目标剧本与对白",
            input_fingerprint=fingerprint,
            input_artifact_ids=[
                inputs.snapshot_artifact.id,
                inputs.adaptation_plan_artifact.id,
                inputs.target_bible_artifact.id,
            ],
            max_attempts=3,
        ),
    )
    normalized_key = idempotency_key.strip()
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts and task.idempotency_key != normalized_key:
        return retry_task(db, project_id, task.id)
    if task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts and task.idempotency_key != normalized_key:
        return resume_task(db, project_id, task.id)
    return task


def _assert_task_inputs(task: TaskWorkerRead | Task, inputs: P12Inputs, provider: TargetScriptProvider) -> None:
    expected_ids = [
        inputs.snapshot_artifact.id,
        inputs.adaptation_plan_artifact.id,
        inputs.target_bible_artifact.id,
    ]
    if list(task.input_artifact_ids_json) != expected_ids:
        raise AppError("STALE_ARTIFACT_INPUT", "P12 三个硬输入已变化，请重新创建任务", status_code=409)
    if task.input_fingerprint != _fingerprint_inputs(inputs, provider):
        raise AppError("STALE_ARTIFACT_INPUT", "P12 Target 输入、配置或 Provider profile 已变化", status_code=409)


def _validate_semantic(inputs: P12Inputs, semantic: TargetScriptSemantic) -> None:
    expected = [item["utterance_id"] for item in _canonical_dialogue_manifest(inputs)]
    actual = [item.utterance_id for item in semantic.dialogue]
    if actual != expected or len(actual) != len(set(actual)):
        raise AppError(
            "P12_DIALOGUE_COVERAGE_INVALID",
            "P12 Provider dialogue 必须按 Source Snapshot canonical utterance 顺序一一完整覆盖",
            status_code=422,
        )


def _target_character_by_utterance(inputs: P12Inputs) -> dict[str, str | None]:
    speaker_entities = {item.speaker_id: item for item in inputs.snapshot_content.source_speakers.entities}
    target_by_source = {item.source_character_id: item.target_character_id for item in inputs.target_bible.characters}
    attributions: dict[str, Any] = {}
    for item in inputs.snapshot_content.source_speakers.attributions:
        if item.utterance_id in attributions:
            raise AppError(
                "P12_SPEAKER_ATTRIBUTION_DUPLICATE",
                "Source Snapshot 同一 utterance 存在重复 Speaker attribution",
                status_code=409,
            )
        attributions[item.utterance_id] = item

    result: dict[str, str | None] = {}
    for manifest_item in _canonical_dialogue_manifest(inputs):
        utterance_id = manifest_item["utterance_id"]
        attribution = attributions.get(utterance_id)
        target_character_id: str | None = None
        if attribution is not None and attribution.speaker_id:
            speaker = speaker_entities.get(attribution.speaker_id)
            if speaker is not None and speaker.character_id:
                target_character_id = target_by_source.get(speaker.character_id)
        result[utterance_id] = target_character_id
    return result


def _compose(inputs: P12Inputs, semantic: TargetScriptSemantic) -> ReplicaTargetScriptContent:
    _validate_semantic(inputs, semantic)
    semantic_by_id = {item.utterance_id: item for item in semantic.dialogue}
    target_characters = _target_character_by_utterance(inputs)
    episodes: dict[str, TargetScriptEpisode] = {}
    for item in _canonical_dialogue_manifest(inputs):
        localized = semantic_by_id[item["utterance_id"]]
        episode = episodes.setdefault(
            item["episode_id"],
            TargetScriptEpisode(
                episode_id=item["episode_id"],
                episode_order=item["episode_order"],
                dialogue=[],
            ),
        )
        episode.dialogue.append(
            TargetScriptDialogueLine(
                utterance_id=item["utterance_id"],
                utterance_number=item["utterance_number"],
                source_start_us=item["source_start_us"],
                source_end_us=item["source_end_us"],
                source_text=item["source_text"],
                source_language=item["source_language"],
                target_character_id=target_characters[item["utterance_id"]],
                translation_text=localized.translation_text,
                localization_text=localized.localization_text,
                final_target_dialogue=localized.final_target_dialogue,
                localization_notes=list(localized.localization_notes),
            )
        )
    return ReplicaTargetScriptContent(
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        source_snapshot_artifact_id=inputs.snapshot_artifact.id,
        adaptation_plan_artifact_id=inputs.adaptation_plan_artifact.id,
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        episodes=sorted(episodes.values(), key=lambda item: item.episode_order),
    )


def _provider_input(inputs: P12Inputs) -> TargetScriptProviderInput:
    return TargetScriptProviderInput(
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        adaptation_plan=inputs.adaptation_plan.model_dump(mode="json"),
        target_bible=inputs.target_bible.model_dump(mode="json"),
        canonical_dialogue_manifest=_canonical_dialogue_manifest(inputs),
    )


def _dispatch(provider: TargetScriptProvider, payload: TargetScriptProviderInput) -> ProviderDispatchResult:
    result: TargetScriptProviderResult = provider.localize(payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> P12ExecutionResult:
    _assert_p12_admitted()
    with context.session_factory() as db:
        inputs = _load_inputs(db, task.project_id)
        provider = _provider_for_project(inputs.project)
        _assert_task_inputs(task, inputs, provider)
        profile = provider.profile()

    context.checkpoint({"stage": "canonical_source_dialogue"}, progress_percent=15)
    payload = _provider_input(inputs)
    context.checkpoint({"stage": "translate_and_localize"}, progress_percent=25)
    job_payload = {
        "profile": P12_PROMPT_VERSION,
        "schema_version": P12_SCHEMA_VERSION,
        "target_contract": P12_TARGET_CONTRACT,
        "source_dialogue_contract": P12_SOURCE_DIALOGUE_CONTRACT,
        "professional_skill_id": P12_SKILL_ID,
        "professional_skill_version": get_professional_skill(P12_SKILL_ID).version,
        "source_snapshot_artifact_id": inputs.snapshot_artifact.id,
        "adaptation_plan_artifact_id": inputs.adaptation_plan_artifact.id,
        "target_bible_artifact_id": inputs.target_bible_artifact.id,
        "target_language": inputs.project.target_language,
        "target_region": inputs.project.target_region,
        "dialogue_count": len(payload.canonical_dialogue_manifest),
        "provider_profile": profile,
    }
    with context.session_factory() as db:
        job, dispatched = dispatch_provider_call(
            db,
            task_id=task.id,
            provider=provider.provider_name,
            model=provider.model_name,
            capability=Capability.TARGET_SCRIPT,
            payload=job_payload,
            artifact_id=inputs.target_bible_artifact.id,
            remote_call=lambda _job: _dispatch(provider, payload),
        )
    context.checkpoint({"stage": "validate_dialogue_lineage"}, progress_percent=82)
    raw = dispatched.value
    semantic = raw if isinstance(raw, TargetScriptSemantic) else TargetScriptSemantic.model_validate(raw)
    target_script = _compose(inputs, semantic)
    context.checkpoint({"stage": "validate_target_script"}, progress_percent=94)
    provenance = TargetScriptProviderJobProvenance(
        provider_job_id=job.id,
        provider=job.provider,
        model=job.model,
        capability=job.capability,
        professional_skill_id=P12_SKILL_ID,
        payload_fingerprint=job.payload_fingerprint,
        remote_job_id=job.remote_job_id,
    )
    return P12ExecutionResult(
        target_script=target_script,
        provider_job=provenance,
        provider_profile=profile,
    )


def _next_revision(db: Session, project_id: str) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.TARGET_SCRIPT.value,
        )
    )
    return int(latest or 0) + 1


def _artifact_fingerprint(task: Task, content: ReplicaTargetScriptContent) -> str:
    return _sha(
        {
            "task_input_fingerprint": task.input_fingerprint,
            "artifact_type": ArtifactType.TARGET_SCRIPT.value,
            "schema_version": P12_SCHEMA_VERSION,
            "content": content.model_dump(mode="json"),
        }
    )


def _provenance(
    *,
    task: Task,
    inputs: P12Inputs,
    result: P12ExecutionResult,
    previous: ArtifactNode | None,
) -> TargetScriptProvenance:
    skill = get_professional_skill(P12_SKILL_ID)
    return TargetScriptProvenance(
        source_snapshot_artifact_id=inputs.snapshot_artifact.id,
        source_snapshot_revision=inputs.snapshot_artifact.revision,
        source_snapshot_fingerprint=inputs.snapshot_artifact.input_fingerprint,
        adaptation_plan_artifact_id=inputs.adaptation_plan_artifact.id,
        adaptation_plan_revision=inputs.adaptation_plan_artifact.revision,
        adaptation_plan_fingerprint=inputs.adaptation_plan_artifact.input_fingerprint,
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        target_bible_revision=inputs.target_bible_artifact.revision,
        target_bible_fingerprint=inputs.target_bible_artifact.input_fingerprint,
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        professional_skill_id=skill.id,
        professional_skill_version=skill.version,
        provider=result.provider_job.provider,
        model=result.provider_job.model,
        provider_job=result.provider_job,
        generated_by_task_id=task.id,
        supersedes_artifact_id=previous.id if previous is not None else None,
    )


def _publish(db: Session, *, task_id: str, result: P12ExecutionResult) -> ArtifactNode:
    _assert_p12_admitted()
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "P12 任务不存在", status_code=404)
    if task.status != TaskStatus.SUCCEEDED:
        raise AppError("TASK_NOT_SUCCEEDED", "只有执行成功的 P12 Task 才能发布目标剧本", status_code=409)
    inputs = _load_inputs(db, task.project_id)
    provider = _provider_for_project(inputs.project)
    _assert_task_inputs(task, inputs, provider)

    previous = _current_artifact(db, task.project_id, ArtifactType.TARGET_SCRIPT)
    if previous is not None:
        _mark_stale_with_downstream(db, [previous])

    skill = get_professional_skill(P12_SKILL_ID)
    fingerprint = _artifact_fingerprint(task, result.target_script)
    artifact = ArtifactNode(
        project_id=task.project_id,
        artifact_type=ArtifactType.TARGET_SCRIPT.value,
        namespace=ArtifactNamespace.TARGET,
        label="目标剧本与对白",
        revision=_next_revision(db, task.project_id),
        input_fingerprint=fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": P12_SCHEMA_VERSION,
            "source_snapshot_artifact_id": inputs.snapshot_artifact.id,
            "adaptation_plan_artifact_id": inputs.adaptation_plan_artifact.id,
            "target_bible_artifact_id": inputs.target_bible_artifact.id,
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
            "dialogue_count": sum(len(item.dialogue) for item in result.target_script.episodes),
            "document_title": "目标剧本与对白",
        },
    )
    try:
        db.add(artifact)
        db.flush()
        provenance = _provenance(task=task, inputs=inputs, result=result, previous=previous)
        db.add(
            ReplicaTargetScriptRevision(
                project_id=task.project_id,
                artifact_id=artifact.id,
                source_snapshot_artifact_id=inputs.snapshot_artifact.id,
                adaptation_plan_artifact_id=inputs.adaptation_plan_artifact.id,
                target_bible_artifact_id=inputs.target_bible_artifact.id,
                generated_by_task_id=task.id,
                schema_version=P12_SCHEMA_VERSION,
                content_json=result.target_script.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.add_all(
            [
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=inputs.snapshot_artifact.id,
                    target_node_id=artifact.id,
                    relation_type=ArtifactRelationType.DERIVED_FROM,
                ),
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=inputs.adaptation_plan_artifact.id,
                    target_node_id=artifact.id,
                    relation_type=ArtifactRelationType.USES,
                ),
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=inputs.target_bible_artifact.id,
                    target_node_id=artifact.id,
                    relation_type=ArtifactRelationType.USES,
                ),
            ]
        )
        if previous is not None:
            db.add(
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=artifact.id,
                    target_node_id=previous.id,
                    relation_type=ArtifactRelationType.SUPERSEDES,
                )
            )
        _invalidate_project_plan(db, inputs.project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(artifact)
    return artifact


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if (
        task is None
        or task.task_type != P12_TASK_TYPE
        or task.status != TaskStatus.QUEUED
        or task.attempt >= task.max_attempts
    ):
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == P12_TASK_TYPE,
            Task.status == TaskStatus.QUEUED,
            Task.attempt < Task.max_attempts,
        )
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


def _fail_if_running(factory: sessionmaker[Session], task_id: str, worker_id: str, message: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_failed(db, task_id, safe_error=message, worker_id=worker_id)


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


def run_target_script_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p12-target-script-{uuid4()}"
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
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P12 目标剧本失败（{exc.code}）：{exc.message}",
        )
        return
    except Exception as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P12 目标剧本失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _publish(db, task_id=snapshot.id, result=result)
    except AppError as exc:
        _mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P12 TARGET_SCRIPT 发布失败（{exc.code}）：{exc.message}",
        )
    except Exception as exc:
        _mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P12 TARGET_SCRIPT 发布失败（{type(exc).__name__}）",
        )


def get_target_script(db: Session, project_id: str) -> ReplicaTargetScriptRead:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    current = _current_artifact(db, project_id, ArtifactType.TARGET_SCRIPT)
    latest = current or _latest_artifact(db, project_id, ArtifactType.TARGET_SCRIPT)
    if latest is None:
        return ReplicaTargetScriptRead(project_id=project_id, status=TargetScriptResultStatus.NOT_BUILT)
    row = db.scalar(
        select(ReplicaTargetScriptRevision).where(ReplicaTargetScriptRevision.artifact_id == latest.id)
    )
    if row is None:
        raise AppError("P12_TARGET_SCRIPT_CONTENT_MISSING", "TARGET_SCRIPT 缺少 P12 typed revision", status_code=500)
    return ReplicaTargetScriptRead(
        project_id=project_id,
        status=TargetScriptResultStatus.CURRENT if current is not None else TargetScriptResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaTargetScriptContent.model_validate(row.content_json),
        provenance=TargetScriptProvenance.model_validate(row.provenance_json),
    )


def list_target_script_revisions(db: Session, project_id: str) -> list[ReplicaTargetScriptRevisionSummary]:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    artifacts = list(
        db.scalars(
            select(ArtifactNode)
            .where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == ArtifactType.TARGET_SCRIPT.value,
            )
            .order_by(ArtifactNode.created_at.desc(), ArtifactNode.revision.desc())
        ).all()
    )
    result: list[ReplicaTargetScriptRevisionSummary] = []
    for artifact in artifacts:
        row = db.scalar(
            select(ReplicaTargetScriptRevision).where(ReplicaTargetScriptRevision.artifact_id == artifact.id)
        )
        if row is None:
            continue
        result.append(
            ReplicaTargetScriptRevisionSummary(
                artifact_id=artifact.id,
                revision=artifact.revision,
                validity=artifact.validity.value,
                input_fingerprint=artifact.input_fingerprint,
                source_snapshot_artifact_id=row.source_snapshot_artifact_id,
                adaptation_plan_artifact_id=row.adaptation_plan_artifact_id,
                target_bible_artifact_id=row.target_bible_artifact_id,
                created_at=artifact.created_at.isoformat(),
            )
        )
    return result
