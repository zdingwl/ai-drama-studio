from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.errors import AppError
from app.core.time import utc_now
from app.p14.models import ReplicaTargetAudioCandidate, ReplicaTimingPlanCandidate
from app.p14.schemas import CandidateReviewStatus, ReplicaTimingPlanContent, TimingFitStatus
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.providers import TargetScriptProvider
from app.target_script.schemas import (
    P12_SCHEMA_VERSION,
    P12_SKILL_ID,
    P12_SOURCE_DIALOGUE_CONTRACT,
    P12_TARGET_CONTRACT,
    P12_TIMING_REWRITE_CONTRACT,
    P12_TIMING_REWRITE_PROMPT_VERSION,
    ReplicaTargetScriptContent,
    TargetScriptProviderJobProvenance,
    TargetScriptProvenance,
    TargetScriptRevisionMode,
    TargetScriptTimingRewriteCommand,
    TargetScriptTimingRewriteSemantic,
)
from app.target_script.service import P12Inputs, _load_inputs, _provider_for_project, _sha
from app.target_script.timing_rewrite_provider import TimingRewriteProviderInput, rewrite_for_timing
from app.workflow.models import ProviderJob, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import create_task_from_command, mark_task_failed, mark_task_succeeded


P12_TIMING_REWRITE_TASK_TYPE = "P12_TARGET_SCRIPT_TIMING_REWRITE"
MIN_RETAKE_DURATION_FACTOR = 0.8


@dataclass(frozen=True)
class TimingRewriteContext:
    inputs: P12Inputs
    script_artifact: ArtifactNode
    script: ReplicaTargetScriptContent
    audio_artifact: ArtifactNode
    timing_candidate: ReplicaTimingPlanCandidate
    timing: ReplicaTimingPlanContent
    selected_items: list


@dataclass(frozen=True)
class TimingRewriteExecutionResult:
    target_script: ReplicaTargetScriptContent
    provider_job: TargetScriptProviderJobProvenance
    provider_profile: dict
    rewritten_utterance_ids: list[str]


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )


def _load_context(db: Session, project_id: str, command: TargetScriptTimingRewriteCommand) -> TimingRewriteContext:
    inputs = _load_inputs(db, project_id)
    script_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_SCRIPT)
    if script_artifact is None:
        raise AppError("P12_TIMING_REWRITE_SCRIPT_REQUIRED", "Timing Rewrite 需要 CURRENT TARGET_SCRIPT", status_code=409)
    if (
        script_artifact.id != command.expected_target_script_artifact_id
        or script_artifact.revision != command.expected_target_script_revision
    ):
        raise AppError("P12_TIMING_REWRITE_SCRIPT_CHANGED", "TARGET_SCRIPT 已变化，请重新执行 Timing 分诊", status_code=409)
    script_row = db.scalar(
        select(ReplicaTargetScriptRevision).where(ReplicaTargetScriptRevision.artifact_id == script_artifact.id)
    )
    if script_row is None:
        raise AppError("P12_TARGET_SCRIPT_CONTENT_MISSING", "TARGET_SCRIPT 缺少 typed revision", status_code=500)
    script = ReplicaTargetScriptContent.model_validate(script_row.content_json)
    if (
        script.source_snapshot_artifact_id != inputs.snapshot_artifact.id
        or script.adaptation_plan_artifact_id != inputs.adaptation_plan_artifact.id
        or script.target_bible_artifact_id != inputs.target_bible_artifact.id
    ):
        raise AppError("P12_TIMING_REWRITE_LINEAGE_MISMATCH", "CURRENT TARGET_SCRIPT 与 P12 CURRENT 硬输入 lineage 不一致", status_code=409)

    audio_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    if audio_artifact is None:
        raise AppError("P12_TIMING_REWRITE_AUDIO_REQUIRED", "Timing Rewrite 需要 CURRENT TARGET_AUDIO", status_code=409)

    candidate = db.get(ReplicaTimingPlanCandidate, command.timing_candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise AppError("P12_TIMING_REWRITE_TIMING_NOT_FOUND", "Timing candidate 不存在", status_code=404)
    if candidate.review_status != CandidateReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P12_TIMING_REWRITE_TIMING_NOT_REVIEWABLE", "Timing candidate 已失效或已审核", status_code=409)
    if candidate.generation_sequence != command.expected_timing_generation_sequence:
        raise AppError("P12_TIMING_REWRITE_TIMING_CHANGED", "Timing candidate generation sequence 已变化", status_code=409)
    if candidate.target_script_artifact_id != script_artifact.id or candidate.target_audio_artifact_id != audio_artifact.id:
        raise AppError("P12_TIMING_REWRITE_TIMING_STALE", "Timing candidate 不属于 CURRENT TARGET_SCRIPT / TARGET_AUDIO", status_code=409)
    timing = ReplicaTimingPlanContent.model_validate(candidate.content_json)

    by_id = {item.utterance_id: item for item in timing.items}
    selected_items = []
    for utterance_id in command.utterance_ids:
        item = by_id.get(utterance_id)
        if item is None:
            raise AppError(
                "P12_TIMING_REWRITE_UTTERANCE_UNKNOWN",
                "定向修订请求包含 Timing 中不存在的对白",
                status_code=422,
                details={"utterance_id": utterance_id},
            )
        if item.fit_status != TimingFitStatus.OVERFLOW:
            raise AppError(
                "P12_TIMING_REWRITE_NOT_OVERFLOW",
                "只有 OVERFLOW 对白才能进入 Timing Rewrite",
                status_code=409,
                details={"utterance_id": utterance_id},
            )
        required_factor = item.source_slot_duration_us / item.actual_speech_duration_us
        if required_factor >= MIN_RETAKE_DURATION_FACTOR:
            raise AppError(
                "P12_TIMING_REWRITE_RETAKE_FIRST",
                "该对白仍位于受控 Retake 可尝试区间，不能直接走 P12 Timing Rewrite",
                status_code=409,
                details={"utterance_id": utterance_id, "required_duration_factor": required_factor},
            )
        selected_items.append(item)

    script_ids = {line.utterance_id for episode in script.episodes for line in episode.dialogue}
    unknown = [item.utterance_id for item in selected_items if item.utterance_id not in script_ids]
    if unknown:
        raise AppError("P12_TIMING_REWRITE_SCRIPT_COVERAGE_INVALID", "Timing 与 TARGET_SCRIPT utterance 集合不一致", status_code=409)

    return TimingRewriteContext(
        inputs=inputs,
        script_artifact=script_artifact,
        script=script,
        audio_artifact=audio_artifact,
        timing_candidate=candidate,
        timing=timing,
        selected_items=selected_items,
    )


def _provider_payload(context: TimingRewriteContext) -> TimingRewriteProviderInput:
    line_by_id = {line.utterance_id: line for episode in context.script.episodes for line in episode.dialogue}
    rows: list[dict] = []
    for item in context.selected_items:
        line = line_by_id[item.utterance_id]
        rows.append(
            {
                "utterance_id": line.utterance_id,
                "utterance_number": line.utterance_number,
                "source_text": line.source_text,
                "translation_text": line.translation_text,
                "localization_text": line.localization_text,
                "final_target_dialogue": line.final_target_dialogue,
                "target_character_id": line.target_character_id,
                "source_slot_duration_us": item.source_slot_duration_us,
                "actual_speech_duration_us": item.actual_speech_duration_us,
                "required_duration_factor": item.source_slot_duration_us / item.actual_speech_duration_us,
            }
        )
    return TimingRewriteProviderInput(
        target_language=context.inputs.project.target_language,
        target_region=context.inputs.project.target_region,
        adaptation_plan=context.inputs.adaptation_plan.model_dump(mode="json"),
        target_bible=context.inputs.target_bible.model_dump(mode="json"),
        dialogue_requests=rows,
    )


def _fingerprint(context: TimingRewriteContext, command: TargetScriptTimingRewriteCommand, provider: TargetScriptProvider) -> str:
    return _sha(
        {
            "task": P12_TIMING_REWRITE_TASK_TYPE,
            "source_snapshot": [context.inputs.snapshot_artifact.id, context.inputs.snapshot_artifact.revision, context.inputs.snapshot_artifact.input_fingerprint],
            "adaptation_plan": [context.inputs.adaptation_plan_artifact.id, context.inputs.adaptation_plan_artifact.revision, context.inputs.adaptation_plan_artifact.input_fingerprint],
            "target_bible": [context.inputs.target_bible_artifact.id, context.inputs.target_bible_artifact.revision, context.inputs.target_bible_artifact.input_fingerprint],
            "base_target_script": [context.script_artifact.id, context.script_artifact.revision, context.script_artifact.input_fingerprint],
            "target_audio": [context.audio_artifact.id, context.audio_artifact.revision, context.audio_artifact.input_fingerprint],
            "timing_candidate": [context.timing_candidate.id, context.timing_candidate.generation_sequence],
            "selected": [
                [
                    item.utterance_id,
                    item.source_slot_duration_us,
                    item.actual_speech_duration_us,
                    item.source_slot_duration_us / item.actual_speech_duration_us,
                ]
                for item in context.selected_items
            ],
            "provider_profile": provider.profile(),
            "prompt_version": P12_TIMING_REWRITE_PROMPT_VERSION,
            "contract": P12_TIMING_REWRITE_CONTRACT,
            "command": command.model_dump(mode="json"),
        }
    )


def create_timing_rewrite_task(
    db: Session,
    *,
    project_id: str,
    idempotency_key: str,
    command: TargetScriptTimingRewriteCommand,
) -> Task:
    context = _load_context(db, project_id, command)
    provider = _provider_for_project(context.inputs.project)
    fingerprint = _fingerprint(context, command, provider)
    task = create_task_from_command(
        db,
        project_id=project_id,
        payload=TaskCommandCreate(
            task_type=P12_TIMING_REWRITE_TASK_TYPE,
            task_name="缩短超时目标对白",
            input_fingerprint=fingerprint,
            input_artifact_ids=[
                context.inputs.snapshot_artifact.id,
                context.inputs.adaptation_plan_artifact.id,
                context.inputs.target_bible_artifact.id,
                context.script_artifact.id,
                context.audio_artifact.id,
            ],
            max_attempts=3,
        ),
        idempotency_key=idempotency_key,
    )
    if not (task.checkpoint_json or {}).get("p12_timing_rewrite_command"):
        task.checkpoint_json = {
            **(task.checkpoint_json or {}),
            "p12_timing_rewrite_command": command.model_dump(mode="json"),
        }
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != P12_TIMING_REWRITE_TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
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


def _compose_rewrite(
    baseline: ReplicaTargetScriptContent,
    semantic: TargetScriptTimingRewriteSemantic,
    selected_ids: list[str],
) -> ReplicaTargetScriptContent:
    actual = [item.utterance_id for item in semantic.dialogue]
    if actual != selected_ids or len(actual) != len(set(actual)):
        raise AppError(
            "P12_TIMING_REWRITE_COVERAGE_INVALID",
            "Timing Rewrite Provider 必须只按选择顺序完整覆盖 selected utterance",
            status_code=422,
        )
    replacement = {item.utterance_id: item for item in semantic.dialogue}
    episodes = []
    for episode in baseline.episodes:
        dialogue = []
        for line in episode.dialogue:
            item = replacement.get(line.utterance_id)
            if item is None:
                dialogue.append(line.model_copy(deep=True))
            else:
                dialogue.append(
                    line.model_copy(
                        update={
                            "localization_text": item.localization_text,
                            "final_target_dialogue": item.final_target_dialogue,
                            "localization_notes": list(item.localization_notes),
                        },
                        deep=True,
                    )
                )
        episodes.append(episode.model_copy(update={"dialogue": dialogue}, deep=True))
    result = baseline.model_copy(update={"episodes": episodes}, deep=True)

    before = {line.utterance_id: line.model_dump(mode="json") for episode in baseline.episodes for line in episode.dialogue}
    after = {line.utterance_id: line.model_dump(mode="json") for episode in result.episodes for line in episode.dialogue}
    selected = set(selected_ids)
    for utterance_id, payload in before.items():
        if utterance_id not in selected and after.get(utterance_id) != payload:
            raise AppError("P12_TIMING_REWRITE_UNSELECTED_CHANGED", "未选择对白在 Timing Rewrite 中发生变化", status_code=500)
    return result


def _execute(
    factory: sessionmaker[Session],
    task: TaskWorkerRead,
    command: TargetScriptTimingRewriteCommand,
) -> TimingRewriteExecutionResult:
    with factory() as db:
        context = _load_context(db, task.project_id, command)
        provider = _provider_for_project(context.inputs.project)
        expected_ids = [
            context.inputs.snapshot_artifact.id,
            context.inputs.adaptation_plan_artifact.id,
            context.inputs.target_bible_artifact.id,
            context.script_artifact.id,
            context.audio_artifact.id,
        ]
        if task.input_artifact_ids_json != expected_ids or task.input_fingerprint != _fingerprint(context, command, provider):
            raise AppError("STALE_ARTIFACT_INPUT", "Timing Rewrite 输入已经变化，请重新创建任务", status_code=409)
        payload = _provider_payload(context)
        profile = provider.profile()
        base_script = context.script
        base_script_id = context.script_artifact.id
        timing_candidate_id = context.timing_candidate.id

    job_payload = {
        "profile": P12_TIMING_REWRITE_PROMPT_VERSION,
        "contract": P12_TIMING_REWRITE_CONTRACT,
        "professional_skill_id": P12_SKILL_ID,
        "base_target_script_artifact_id": base_script_id,
        "timing_candidate_id": timing_candidate_id,
        "utterance_ids": command.utterance_ids,
        "provider_profile": profile,
    }
    with factory() as db:
        job, dispatched = dispatch_provider_call(
            db,
            task_id=task.id,
            provider=provider.provider_name,
            model=provider.model_name,
            capability=Capability.TARGET_SCRIPT,
            payload=job_payload,
            artifact_id=base_script_id,
            remote_call=lambda _job: (
                lambda result: ProviderDispatchResult(
                    value=result.semantic,
                    remote_job_id=result.remote_job_id,
                    completed=True,
                )
            )(rewrite_for_timing(provider, payload)),
        )
    semantic = dispatched.value if isinstance(dispatched.value, TargetScriptTimingRewriteSemantic) else TargetScriptTimingRewriteSemantic.model_validate(dispatched.value)
    target_script = _compose_rewrite(base_script, semantic, command.utterance_ids)
    provenance = TargetScriptProviderJobProvenance(
        provider_job_id=job.id,
        provider=job.provider,
        model=job.model,
        capability=job.capability,
        professional_skill_id=P12_SKILL_ID,
        payload_fingerprint=job.payload_fingerprint,
        remote_job_id=job.remote_job_id,
    )
    return TimingRewriteExecutionResult(
        target_script=target_script,
        provider_job=provenance,
        provider_profile=profile,
        rewritten_utterance_ids=list(command.utterance_ids),
    )


def _next_revision(db: Session, project_id: str) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.TARGET_SCRIPT.value,
        )
    )
    return int(latest or 0) + 1


def _publish(
    db: Session,
    *,
    task_id: str,
    command: TargetScriptTimingRewriteCommand,
    result: TimingRewriteExecutionResult,
) -> ArtifactNode:
    task = db.get(Task, task_id)
    if task is None or task.status != TaskStatus.SUCCEEDED:
        raise AppError("TASK_NOT_SUCCEEDED", "只有成功的 Timing Rewrite Task 才能发布 TARGET_SCRIPT", status_code=409)
    context = _load_context(db, task.project_id, command)
    provider = _provider_for_project(context.inputs.project)
    expected_ids = [
        context.inputs.snapshot_artifact.id,
        context.inputs.adaptation_plan_artifact.id,
        context.inputs.target_bible_artifact.id,
        context.script_artifact.id,
        context.audio_artifact.id,
    ]
    if task.input_artifact_ids_json != expected_ids or task.input_fingerprint != _fingerprint(context, command, provider):
        raise AppError("STALE_ARTIFACT_INPUT", "Timing Rewrite 发布前输入已经变化", status_code=409)

    old_script = context.script_artifact
    skill = get_professional_skill(P12_SKILL_ID)
    fingerprint = _sha(
        {
            "task_input_fingerprint": task.input_fingerprint,
            "artifact_type": ArtifactType.TARGET_SCRIPT.value,
            "schema_version": P12_SCHEMA_VERSION,
            "revision_mode": TargetScriptRevisionMode.TIMING_REWRITE.value,
            "content": result.target_script.model_dump(mode="json"),
        }
    )
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
            "source_snapshot_artifact_id": context.inputs.snapshot_artifact.id,
            "adaptation_plan_artifact_id": context.inputs.adaptation_plan_artifact.id,
            "target_bible_artifact_id": context.inputs.target_bible_artifact.id,
            "revision_mode": TargetScriptRevisionMode.TIMING_REWRITE.value,
            "rewritten_utterance_count": len(result.rewritten_utterance_ids),
        },
    )
    provenance = TargetScriptProvenance(
        source_snapshot_artifact_id=context.inputs.snapshot_artifact.id,
        source_snapshot_revision=context.inputs.snapshot_artifact.revision,
        source_snapshot_fingerprint=context.inputs.snapshot_artifact.input_fingerprint,
        adaptation_plan_artifact_id=context.inputs.adaptation_plan_artifact.id,
        adaptation_plan_revision=context.inputs.adaptation_plan_artifact.revision,
        adaptation_plan_fingerprint=context.inputs.adaptation_plan_artifact.input_fingerprint,
        target_bible_artifact_id=context.inputs.target_bible_artifact.id,
        target_bible_revision=context.inputs.target_bible_artifact.revision,
        target_bible_fingerprint=context.inputs.target_bible_artifact.input_fingerprint,
        target_language=context.inputs.project.target_language,
        target_region=context.inputs.project.target_region,
        professional_skill_version=skill.version,
        provider=result.provider_job.provider,
        model=result.provider_job.model,
        provider_job=result.provider_job,
        prompt_version=P12_TIMING_REWRITE_PROMPT_VERSION,
        schema_version=P12_SCHEMA_VERSION,
        target_contract=P12_TARGET_CONTRACT,
        source_dialogue_contract=P12_SOURCE_DIALOGUE_CONTRACT,
        generated_by_task_id=task.id,
        supersedes_artifact_id=old_script.id,
        revision_mode=TargetScriptRevisionMode.TIMING_REWRITE,
        base_target_script_artifact_id=old_script.id,
        rewritten_utterance_ids=result.rewritten_utterance_ids,
        timing_candidate_id=context.timing_candidate.id,
        timing_generation_sequence=context.timing_candidate.generation_sequence,
    )
    reviewed_at = utc_now()
    try:
        _mark_stale_with_downstream(db, [old_script])
        db.add(artifact)
        db.flush()
        db.add(
            ReplicaTargetScriptRevision(
                project_id=task.project_id,
                artifact_id=artifact.id,
                source_snapshot_artifact_id=context.inputs.snapshot_artifact.id,
                adaptation_plan_artifact_id=context.inputs.adaptation_plan_artifact.id,
                target_bible_artifact_id=context.inputs.target_bible_artifact.id,
                generated_by_task_id=task.id,
                schema_version=P12_SCHEMA_VERSION,
                content_json=result.target_script.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.add_all(
            [
                ArtifactEdge(project_id=task.project_id, source_node_id=context.inputs.snapshot_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM),
                ArtifactEdge(project_id=task.project_id, source_node_id=context.inputs.adaptation_plan_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES),
                ArtifactEdge(project_id=task.project_id, source_node_id=context.inputs.target_bible_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES),
                ArtifactEdge(project_id=task.project_id, source_node_id=artifact.id, target_node_id=old_script.id, relation_type=ArtifactRelationType.SUPERSEDES),
            ]
        )
        for candidate in db.scalars(
            select(ReplicaTimingPlanCandidate).where(
                ReplicaTimingPlanCandidate.project_id == task.project_id,
                ReplicaTimingPlanCandidate.review_status == CandidateReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            candidate.review_status = CandidateReviewStatus.SUPERSEDED.value
            candidate.review_reason = "TARGET_SCRIPT changed by timing-driven rewrite."
            candidate.reviewed_at = reviewed_at
            db.add(candidate)
        for candidate in db.scalars(
            select(ReplicaTargetAudioCandidate).where(
                ReplicaTargetAudioCandidate.project_id == task.project_id,
                ReplicaTargetAudioCandidate.review_status == CandidateReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            candidate.review_status = CandidateReviewStatus.SUPERSEDED.value
            candidate.review_reason = "TARGET_SCRIPT changed by timing-driven rewrite."
            candidate.reviewed_at = reviewed_at
            db.add(candidate)
        _invalidate_project_plan(db, context.inputs.project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(artifact)
    return artifact


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


def run_timing_rewrite_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p12-timing-rewrite-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
        command = TargetScriptTimingRewriteCommand.model_validate((claimed.checkpoint_json or {}).get("p12_timing_rewrite_command") or {})
    try:
        result = _execute(factory, snapshot, command)
    except Exception as exc:
        message = f"P12 Timing Rewrite 失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P12 Timing Rewrite 失败（{type(exc).__name__}）"
        with factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, snapshot.id, safe_error=message, worker_id=worker_id)
        return

    with factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with factory() as db:
            _publish(db, task_id=snapshot.id, command=command, result=result)
    except Exception as exc:
        message = f"P12 Timing Rewrite 发布失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P12 Timing Rewrite 发布失败（{type(exc).__name__}）"
        _mark_publish_failed(factory, snapshot.id, message)
