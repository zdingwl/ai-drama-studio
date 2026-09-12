from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.errors import AppError
from app.core.time import utc_now
from app.p14.audio_contract import _flatten_dialogue
from app.p14.common import _assert_replica, _claim_specific, _current_artifact, _existing_command_task, _latest_artifact, _mark_stage_failed, _next_artifact_revision, _next_generation_sequence, _sha, _text_sha
from app.p14.models import ReplicaTargetAudioRevision, ReplicaTimingPlanCandidate, ReplicaTimingPlanRevision
from app.p14.schemas import P14_TIMING_SCHEMA_VERSION, P14_TIMING_SKILL_ID, P14ResultStatus, CandidateReviewStatus, ReplicaTargetAudioContent, ReplicaTimingPlanContent, ReplicaTimingPlanRead, TimingDialogueItem, TimingFitStatus, TimingPlanCandidateProvenance, TimingPlanCandidateRead, TimingPlanProvenance, TimingPlanReviewCommand
from app.projects.models import Project
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.schemas import ReplicaTargetScriptContent
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import create_task_from_command, mark_task_failed, mark_task_succeeded

P14_TIMING_TASK_TYPE = "replica_dialogue_timing"


def _load_timing_inputs(
    db: Session, project_id: str
) -> tuple[Project, ArtifactNode, ReplicaTargetScriptContent, ArtifactNode, ReplicaTargetAudioContent]:
    project = get_project(db, project_id)
    _assert_replica(project)
    script_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_SCRIPT)
    if script_artifact is None:
        raise AppError("P14_TARGET_SCRIPT_REQUIRED", "P14 Timing 需要 CURRENT TARGET_SCRIPT", status_code=409)
    audio_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    if audio_artifact is None:
        raise AppError("P14_TARGET_AUDIO_REQUIRED", "P14 Timing 需要人工确认后的 CURRENT TARGET_AUDIO", status_code=409)
    script_row = db.scalar(select(ReplicaTargetScriptRevision).where(ReplicaTargetScriptRevision.artifact_id == script_artifact.id))
    audio_row = db.scalar(select(ReplicaTargetAudioRevision).where(ReplicaTargetAudioRevision.artifact_id == audio_artifact.id))
    if script_row is None or audio_row is None:
        raise AppError("P14_TIMING_INPUT_CONTENT_MISSING", "P14 Timing 输入缺少 typed revision", status_code=500)
    script = ReplicaTargetScriptContent.model_validate(script_row.content_json)
    audio = ReplicaTargetAudioContent.model_validate(audio_row.content_json)
    if audio.target_script_artifact_id != script_artifact.id:
        raise AppError("P14_TIMING_LINEAGE_MISMATCH", "TARGET_AUDIO 不属于 CURRENT TARGET_SCRIPT", status_code=409)
    return project, script_artifact, script, audio_artifact, audio


def _compose_timing(
    script_artifact: ArtifactNode,
    script: ReplicaTargetScriptContent,
    audio_artifact: ArtifactNode,
    audio: ReplicaTargetAudioContent,
) -> ReplicaTimingPlanContent:
    lines = _flatten_dialogue(script)
    if len(lines) != len(audio.clips):
        raise AppError("P14_TIMING_AUDIO_COVERAGE_INVALID", "TARGET_AUDIO 必须逐句完整覆盖 TARGET_SCRIPT", status_code=409)
    items: list[TimingDialogueItem] = []
    for (episode_id, episode_order, line), clip in zip(lines, audio.clips, strict=True):
        if clip.utterance_id != line.utterance_id or clip.episode_id != episode_id:
            raise AppError("P14_TIMING_AUDIO_COVERAGE_INVALID", "TARGET_AUDIO utterance 顺序与 TARGET_SCRIPT 不一致", status_code=409)
        if clip.final_target_dialogue_sha256 != _text_sha(line.final_target_dialogue):
            raise AppError("P14_TIMING_DIALOGUE_CHANGED", "TARGET_AUDIO 对应的 Final Target Dialogue 已变化", status_code=409)
        slot = line.source_end_us - line.source_start_us
        duration = clip.actual_speech_duration_us
        overflow = max(0, duration - slot)
        residual = max(0, slot - duration)
        items.append(
            TimingDialogueItem(
                episode_id=episode_id,
                episode_order=episode_order,
                utterance_id=line.utterance_id,
                utterance_number=line.utterance_number,
                target_character_id=line.target_character_id,
                source_start_us=line.source_start_us,
                source_end_us=line.source_end_us,
                source_slot_duration_us=slot,
                actual_speech_duration_us=duration,
                planned_speech_start_us=line.source_start_us,
                planned_speech_end_us=line.source_start_us + duration,
                residual_hold_us=residual,
                overflow_us=overflow,
                fit_status=TimingFitStatus.OVERFLOW if overflow else TimingFitStatus.FIT,
            )
        )
    total_overflow = sum(item.overflow_us for item in items)
    return ReplicaTimingPlanContent(
        target_script_artifact_id=script_artifact.id,
        target_audio_artifact_id=audio_artifact.id,
        items=items,
        has_overflow=total_overflow > 0,
        total_overflow_us=total_overflow,
    )


def create_timing_plan_task(
    db: Session, *, project_id: str, idempotency_key: str, regenerate: bool = False
) -> Task:
    project, script_artifact, script, audio_artifact, audio = _load_timing_inputs(db, project_id)
    existing = _existing_command_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        task_type=P14_TIMING_TASK_TYPE,
    )
    if existing is not None:
        return existing
    _compose_timing(script_artifact, script, audio_artifact, audio)
    current = _current_artifact(db, project_id, ArtifactType.TIMING_PLAN)
    if current is not None and not regenerate:
        raise AppError("P14_TIMING_ALREADY_CURRENT", "已有 CURRENT TIMING_PLAN；重新生成必须使用显式 regenerate", status_code=409)
    sequence = _next_generation_sequence(db, project_id, ReplicaTimingPlanCandidate)
    fingerprint = _sha(
        {
            "target_script": [script_artifact.id, script_artifact.revision, script_artifact.input_fingerprint],
            "target_audio": [audio_artifact.id, audio_artifact.revision, audio_artifact.input_fingerprint],
            "generation_sequence": sequence,
        }
    )
    task = create_task_from_command(
        db,
        project_id=project.id,
        payload=TaskCommandCreate(
            task_type=P14_TIMING_TASK_TYPE,
            task_name="计算目标对白时序",
            input_fingerprint=fingerprint,
            input_artifact_ids=[script_artifact.id, audio_artifact.id],
            max_attempts=3,
        ),
        idempotency_key=idempotency_key,
    )
    if not task.checkpoint_json.get("generation_sequence"):
        task.checkpoint_json = {**task.checkpoint_json, "generation_sequence": sequence}
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def run_timing_plan_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p14-timing-{uuid4()}"
    with factory() as db:
        claimed = _claim_specific(db, task_id, P14_TIMING_TASK_TYPE, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
        sequence = int(snapshot.checkpoint_json.get("generation_sequence") or 0)
    try:
        _checkpoint(factory, snapshot.id, worker_id, progress=30, stage="validate_actual_speech_duration")
        with factory() as db:
            _project, script_artifact, script, audio_artifact, audio = _load_timing_inputs(db, snapshot.project_id)
            if snapshot.input_artifact_ids_json != [script_artifact.id, audio_artifact.id]:
                raise AppError("P14_TIMING_INPUT_CHANGED", "P14 Timing 输入已变化，请重新计算", status_code=409)
            content = _compose_timing(script_artifact, script, audio_artifact, audio)
            skill = get_professional_skill(P14_TIMING_SKILL_ID)
            provenance = TimingPlanCandidateProvenance(
                target_script_artifact_id=script_artifact.id,
                target_script_revision=script_artifact.revision,
                target_script_fingerprint=script_artifact.input_fingerprint,
                target_audio_artifact_id=audio_artifact.id,
                target_audio_revision=audio_artifact.revision,
                target_audio_fingerprint=audio_artifact.input_fingerprint,
                generation_sequence=sequence,
                professional_skill_version=skill.version,
                generated_by_task_id=snapshot.id,
            )
        _checkpoint(factory, snapshot.id, worker_id, progress=90, stage="stage_timing_review", has_overflow=content.has_overflow)
        with factory() as db:
            finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
            if finished.status == TaskStatus.CANCELLED:
                return
            existing = db.scalar(select(ReplicaTimingPlanCandidate).where(ReplicaTimingPlanCandidate.generated_by_task_id == snapshot.id))
            if existing is None:
                db.add(
                    ReplicaTimingPlanCandidate(
                        project_id=snapshot.project_id,
                        target_script_artifact_id=content.target_script_artifact_id,
                        target_audio_artifact_id=content.target_audio_artifact_id,
                        generated_by_task_id=snapshot.id,
                        generation_sequence=sequence,
                        input_fingerprint=snapshot.input_fingerprint,
                        schema_version=P14_TIMING_SCHEMA_VERSION,
                        content_json=content.model_dump(mode="json"),
                        provenance_json=provenance.model_dump(mode="json"),
                        review_status=CandidateReviewStatus.NEEDS_REVIEW.value,
                    )
                )
                db.commit()
    except Exception as exc:
        message = f"P14 Timing 失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P14 Timing 失败（{type(exc).__name__}）"
        with factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, snapshot.id, safe_error=message, worker_id=worker_id)
                return
        _mark_stage_failed(factory, snapshot.id, message)


def _timing_candidate_read(row: ReplicaTimingPlanCandidate) -> TimingPlanCandidateRead:
    return TimingPlanCandidateRead(
        id=row.id,
        project_id=row.project_id,
        target_script_artifact_id=row.target_script_artifact_id,
        target_audio_artifact_id=row.target_audio_artifact_id,
        generated_by_task_id=row.generated_by_task_id,
        generation_sequence=row.generation_sequence,
        input_fingerprint=row.input_fingerprint,
        review_status=CandidateReviewStatus(row.review_status),
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        created_at=row.created_at.isoformat(),
        content=ReplicaTimingPlanContent.model_validate(row.content_json),
        provenance=TimingPlanCandidateProvenance.model_validate(row.provenance_json),
    )


def list_timing_plan_candidates(db: Session, project_id: str) -> list[TimingPlanCandidateRead]:
    project = get_project(db, project_id)
    _assert_replica(project)
    rows = db.scalars(
        select(ReplicaTimingPlanCandidate)
        .where(ReplicaTimingPlanCandidate.project_id == project_id)
        .order_by(ReplicaTimingPlanCandidate.created_at.desc(), ReplicaTimingPlanCandidate.generation_sequence.desc())
    ).all()
    return [_timing_candidate_read(row) for row in rows]


def get_timing_plan(db: Session, project_id: str) -> ReplicaTimingPlanRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    current = _current_artifact(db, project_id, ArtifactType.TIMING_PLAN)
    latest = current or _latest_artifact(db, project_id, ArtifactType.TIMING_PLAN)
    if latest is None:
        return ReplicaTimingPlanRead(project_id=project_id, status=P14ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaTimingPlanRevision).where(ReplicaTimingPlanRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P14_TIMING_CONTENT_MISSING", "TIMING_PLAN 缺少 typed revision", status_code=500)
    return ReplicaTimingPlanRead(
        project_id=project_id,
        status=P14ResultStatus.CURRENT if current else P14ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaTimingPlanContent.model_validate(row.content_json),
        provenance=TimingPlanProvenance.model_validate(row.provenance_json),
    )


def _validate_timing_review(
    candidate: ReplicaTimingPlanCandidate,
    script_artifact: ArtifactNode,
    audio_artifact: ArtifactNode,
    command: TimingPlanReviewCommand,
) -> ReplicaTimingPlanContent:
    if candidate.review_status != CandidateReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P14_TIMING_CANDIDATE_NOT_REVIEWABLE", "Timing 候选当前状态不能再次审核", status_code=409)
    if command.expected_target_script_artifact_id != script_artifact.id or candidate.target_script_artifact_id != script_artifact.id:
        raise AppError("P14_TIMING_SCRIPT_CHANGED", "Target Script 已变化，请重新计算 Timing", status_code=409)
    if command.expected_target_audio_artifact_id != audio_artifact.id or candidate.target_audio_artifact_id != audio_artifact.id:
        raise AppError("P14_TIMING_AUDIO_CHANGED", "Target Audio 已变化，请重新计算 Timing", status_code=409)
    if command.expected_generation_sequence != candidate.generation_sequence:
        raise AppError("P14_TIMING_CANDIDATE_CHANGED", "Timing 候选生成序列已变化", status_code=409)
    return ReplicaTimingPlanContent.model_validate(candidate.content_json)


def reject_timing_plan_candidate(
    db: Session, *, project_id: str, candidate_id: str, command: TimingPlanReviewCommand
) -> TimingPlanCandidateRead:
    project, script_artifact, _script, audio_artifact, _audio = _load_timing_inputs(db, project_id)
    candidate = db.get(ReplicaTimingPlanCandidate, candidate_id)
    if candidate is None or candidate.project_id != project.id:
        raise AppError("P14_TIMING_CANDIDATE_NOT_FOUND", "Timing 候选不存在", status_code=404)
    _validate_timing_review(candidate, script_artifact, audio_artifact, command)
    candidate.review_status = CandidateReviewStatus.REJECTED.value
    candidate.review_reason = command.reason.strip()
    candidate.reviewed_at = utc_now()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _timing_candidate_read(candidate)


def accept_timing_plan_candidate(
    db: Session, *, project_id: str, candidate_id: str, command: TimingPlanReviewCommand
) -> ReplicaTimingPlanRead:
    project, script_artifact, _script, audio_artifact, _audio = _load_timing_inputs(db, project_id)
    candidate = db.get(ReplicaTimingPlanCandidate, candidate_id)
    if candidate is None or candidate.project_id != project.id:
        raise AppError("P14_TIMING_CANDIDATE_NOT_FOUND", "Timing 候选不存在", status_code=404)
    content = _validate_timing_review(candidate, script_artifact, audio_artifact, command)
    if content.has_overflow:
        raise AppError(
            "P14_TIMING_OVERFLOW_UNRESOLVED",
            "存在真实语音超出 Source slot 的对白；未显式解决前不得发布正式 TIMING_PLAN",
            status_code=409,
            details={"total_overflow_us": content.total_overflow_us},
        )
    candidate_provenance = TimingPlanCandidateProvenance.model_validate(candidate.provenance_json)
    previous_current = _current_artifact(db, project_id, ArtifactType.TIMING_PLAN)
    previous_latest = _latest_artifact(db, project_id, ArtifactType.TIMING_PLAN)
    if previous_current is not None:
        _mark_stale_with_downstream(db, [previous_current])
    fingerprint = _sha({"candidate_id": candidate.id, "content": content.model_dump(mode="json")})
    skill = get_professional_skill(P14_TIMING_SKILL_ID)
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.TIMING_PLAN.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="目标对白时序",
        revision=_next_artifact_revision(db, project_id, ArtifactType.TIMING_PLAN),
        input_fingerprint=fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={"schema_version": P14_TIMING_SCHEMA_VERSION, "item_count": len(content.items), "has_overflow": False},
    )
    reviewed_at = utc_now()
    provenance = TimingPlanProvenance(
        **candidate_provenance.model_dump(),
        candidate_id=candidate.id,
        reviewed_at=reviewed_at.isoformat(),
        review_reason=command.reason.strip(),
        supersedes_artifact_id=previous_latest.id if previous_latest else None,
    )
    try:
        db.add(artifact)
        db.flush()
        db.add(
            ReplicaTimingPlanRevision(
                project_id=project_id,
                artifact_id=artifact.id,
                target_script_artifact_id=script_artifact.id,
                target_audio_artifact_id=audio_artifact.id,
                candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P14_TIMING_SCHEMA_VERSION,
                content_json=content.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.add(ArtifactEdge(project_id=project_id, source_node_id=audio_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=script_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
        if previous_latest is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=previous_latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
        for other in db.scalars(
            select(ReplicaTimingPlanCandidate).where(
                ReplicaTimingPlanCandidate.project_id == project_id,
                ReplicaTimingPlanCandidate.review_status == CandidateReviewStatus.NEEDS_REVIEW.value,
                ReplicaTimingPlanCandidate.id != candidate.id,
            )
        ).all():
            other.review_status = CandidateReviewStatus.SUPERSEDED.value
            other.review_reason = "A newer timing candidate was explicitly accepted."
            other.reviewed_at = reviewed_at
            db.add(other)
        candidate.review_status = CandidateReviewStatus.ACCEPTED.value
        candidate.review_reason = command.reason.strip()
        candidate.reviewed_at = reviewed_at
        db.add(candidate)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(artifact)
    return ReplicaTimingPlanRead(
        project_id=project_id,
        status=P14ResultStatus.CURRENT,
        artifact_id=artifact.id,
        revision=artifact.revision,
        input_fingerprint=artifact.input_fingerprint,
        content=content,
        provenance=provenance,
    )
