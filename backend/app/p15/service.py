import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.errors import AppError
from app.core.time import utc_now
from app.p15.compiler import compile_bundle, input_artifact_ids, load_inputs, max_segment_duration_us, provenance
from app.p15.models import ReplicaGenerationSegmentsRevision, ReplicaStoryboardCandidate, ReplicaTargetStoryboardRevision
from app.p15.schemas import (
    P15ArtifactProvenance,
    P15CandidateRead,
    P15CandidateReviewStatus,
    P15ResultStatus,
    P15ReviewCommand,
    P15_SCHEMA_VERSION,
    ReplicaGenerationSegmentsContent,
    ReplicaGenerationSegmentsRead,
    ReplicaStoryboardBundle,
    ReplicaTargetStoryboardContent,
    ReplicaTargetStoryboardRead,
)
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import create_task_from_command, mark_task_failed, mark_task_succeeded


P15_TASK_TYPE = "P15_REPLICA_STORYBOARD_COMPILE"


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _assert_replica(project) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError("P15_REPLICA_ONLY", "P15 复刻分镜只允许 REPLICA 项目", status_code=422)


def _generation_sequence(db: Session, project_id: str) -> int:
    latest = db.scalar(
        select(func.max(ReplicaStoryboardCandidate.generation_sequence)).where(
            ReplicaStoryboardCandidate.project_id == project_id
        )
    )
    return int(latest or 0) + 1


def _fingerprint(inputs, generation_sequence: int) -> str:
    skill = get_professional_skill("storyboard-directing")
    return _sha(
        {
            "task": P15_TASK_TYPE,
            "inputs": [
                [node.id, node.revision, node.input_fingerprint]
                for node in (
                    inputs.source_snapshot_artifact,
                    inputs.target_bible_artifact,
                    inputs.target_script_artifact,
                    inputs.target_assets_artifact,
                    inputs.target_audio_artifact,
                    inputs.timing_plan_artifact,
                ) if node is not None
            ],
            "generation_sequence": generation_sequence,
            "max_segment_duration_us": max_segment_duration_us(),
            "skill": [skill.id, skill.version],
            "schema_version": P15_SCHEMA_VERSION,
        }
    )


def create_storyboard_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    _assert_replica(project)
    inputs = load_inputs(db, project)
    generation_sequence = _generation_sequence(db, project_id)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P15_TASK_TYPE,
            task_name="编译复刻分镜与生成计划",
            input_fingerprint=_fingerprint(inputs, generation_sequence),
            input_artifact_ids=input_artifact_ids(inputs),
            max_attempts=3,
        ),
    )
    if not (task.checkpoint_json or {}).get("p15_generation_sequence"):
        task.checkpoint_json = {**(task.checkpoint_json or {}), "p15_generation_sequence": generation_sequence}
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != P15_TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
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


def _persist_candidate(factory: sessionmaker[Session], task: TaskWorkerRead) -> None:
    with factory() as db:
        project = get_project(db, task.project_id)
        _assert_replica(project)
        inputs = load_inputs(db, project)
        generation_sequence = int((task.checkpoint_json or {}).get("p15_generation_sequence") or 0)
        if generation_sequence <= 0:
            raise AppError("P15_TASK_CHECKPOINT_INVALID", "P15 Task 缺少 generation sequence", status_code=500)
        if task.input_artifact_ids_json != input_artifact_ids(inputs) or task.input_fingerprint != _fingerprint(inputs, generation_sequence):
            raise AppError("STALE_ARTIFACT_INPUT", "P15 输入已经变化，请重新创建任务", status_code=409)
        bundle = compile_bundle(inputs)
        prov = provenance(inputs, generation_sequence=generation_sequence, task_id=task.id)
        for pending in db.scalars(
            select(ReplicaStoryboardCandidate).where(
                ReplicaStoryboardCandidate.project_id == task.project_id,
                ReplicaStoryboardCandidate.review_status == P15CandidateReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            pending.review_status = P15CandidateReviewStatus.SUPERSEDED.value
            pending.review_reason = "A newer storyboard candidate was generated."
            pending.reviewed_at = utc_now()
            db.add(pending)
        db.add(
            ReplicaStoryboardCandidate(
                project_id=task.project_id,
                source_snapshot_artifact_id=inputs.source_snapshot_artifact.id,
                target_bible_artifact_id=inputs.target_bible_artifact.id,
                target_script_artifact_id=inputs.target_script_artifact.id,
                target_assets_artifact_id=inputs.target_assets_artifact.id,
                target_audio_artifact_id=inputs.target_audio_artifact.id if inputs.target_audio_artifact else None,
                timing_plan_artifact_id=inputs.timing_plan_artifact.id if inputs.timing_plan_artifact else None,
                generated_by_task_id=task.id,
                generation_sequence=generation_sequence,
                input_fingerprint=task.input_fingerprint,
                schema_version=P15_SCHEMA_VERSION,
                bundle_json=bundle.model_dump(mode="json"),
                provenance_json=prov.model_dump(mode="json"),
                review_status=P15CandidateReviewStatus.NEEDS_REVIEW.value,
            )
        )
        db.commit()


def _mark_after_success_failed(factory: sessionmaker[Session], task_id: str, message: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        now = utc_now()
        task.status = TaskStatus.FAILED
        task.progress_percent = min(task.progress_percent, 99)
        task.last_error = message[:1000]
        task.finished_at = now
        task.updated_at = now
        db.add(task)
        db.commit()


def run_storyboard_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p15-storyboard-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    try:
        with factory() as db:
            project = get_project(db, snapshot.project_id)
            inputs = load_inputs(db, project)
            seq = int((snapshot.checkpoint_json or {}).get("p15_generation_sequence") or 0)
            if snapshot.input_artifact_ids_json != input_artifact_ids(inputs) or snapshot.input_fingerprint != _fingerprint(inputs, seq):
                raise AppError("STALE_ARTIFACT_INPUT", "P15 输入已经变化，请重新创建任务", status_code=409)
            compile_bundle(inputs)
    except Exception as exc:
        message = f"P15 分镜编译失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P15 分镜编译失败（{type(exc).__name__}）"
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
        _persist_candidate(factory, snapshot)
    except Exception as exc:
        message = f"P15 candidate 发布失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P15 candidate 发布失败（{type(exc).__name__}）"
        _mark_after_success_failed(factory, snapshot.id, message)


def _candidate_read(row: ReplicaStoryboardCandidate) -> P15CandidateRead:
    return P15CandidateRead(
        id=row.id,
        project_id=row.project_id,
        generation_sequence=row.generation_sequence,
        input_fingerprint=row.input_fingerprint,
        review_status=P15CandidateReviewStatus(row.review_status),
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        content=ReplicaStoryboardBundle.model_validate(row.bundle_json),
        provenance=row.provenance_json,
    )


def list_storyboard_candidates(db: Session, project_id: str) -> list[P15CandidateRead]:
    project = get_project(db, project_id)
    _assert_replica(project)
    rows = list(
        db.scalars(
            select(ReplicaStoryboardCandidate)
            .where(ReplicaStoryboardCandidate.project_id == project_id)
            .order_by(ReplicaStoryboardCandidate.generation_sequence.desc(), ReplicaStoryboardCandidate.created_at.desc())
        ).all()
    )
    return [_candidate_read(row) for row in rows]


def _current_or_latest(db: Session, project_id: str, artifact_type: ArtifactType) -> tuple[ArtifactNode | None, ArtifactNode | None]:
    current = db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )
    latest = current or db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value)
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )
    return current, latest


def get_storyboard(db: Session, project_id: str) -> ReplicaTargetStoryboardRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    current, latest = _current_or_latest(db, project_id, ArtifactType.TARGET_STORYBOARD)
    if latest is None:
        return ReplicaTargetStoryboardRead(project_id=project_id, status=P15ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaTargetStoryboardRevision).where(ReplicaTargetStoryboardRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P15_STORYBOARD_CONTENT_MISSING", "TARGET_STORYBOARD 缺少 typed revision", status_code=500)
    return ReplicaTargetStoryboardRead(
        project_id=project_id,
        status=P15ResultStatus.CURRENT if current is not None else P15ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaTargetStoryboardContent.model_validate(row.content_json),
        provenance=P15ArtifactProvenance.model_validate(row.provenance_json),
    )


def get_generation_segments(db: Session, project_id: str) -> ReplicaGenerationSegmentsRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    current, latest = _current_or_latest(db, project_id, ArtifactType.GENERATION_SEGMENTS)
    if latest is None:
        return ReplicaGenerationSegmentsRead(project_id=project_id, status=P15ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaGenerationSegmentsRevision).where(ReplicaGenerationSegmentsRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P15_SEGMENTS_CONTENT_MISSING", "GENERATION_SEGMENTS 缺少 typed revision", status_code=500)
    return ReplicaGenerationSegmentsRead(
        project_id=project_id,
        status=P15ResultStatus.CURRENT if current is not None else P15ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaGenerationSegmentsContent.model_validate(row.content_json),
        provenance=P15ArtifactProvenance.model_validate(row.provenance_json),
    )


def _review_candidate(db: Session, project_id: str, candidate_id: str, command: P15ReviewCommand) -> tuple[ReplicaStoryboardCandidate, object, object]:
    project = get_project(db, project_id)
    _assert_replica(project)
    inputs = load_inputs(db, project)
    candidate = db.get(ReplicaStoryboardCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise AppError("P15_CANDIDATE_NOT_FOUND", "P15 分镜候选不存在", status_code=404)
    if candidate.review_status != P15CandidateReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P15_CANDIDATE_NOT_REVIEWABLE", "P15 分镜候选已经审核或失效", status_code=409)
    expected = [value for value in [
        command.expected_source_snapshot_artifact_id,
        command.expected_target_bible_artifact_id,
        command.expected_target_script_artifact_id,
        command.expected_target_assets_artifact_id,
        command.expected_target_audio_artifact_id,
        command.expected_timing_plan_artifact_id,
    ] if value is not None]
    if expected != input_artifact_ids(inputs) or candidate.generation_sequence != command.expected_generation_sequence:
        raise AppError("P15_REVIEW_INPUT_CHANGED", "P15 正式输入或 candidate sequence 已变化", status_code=409)
    candidate_ids = [value for value in [
        candidate.source_snapshot_artifact_id,
        candidate.target_bible_artifact_id,
        candidate.target_script_artifact_id,
        candidate.target_assets_artifact_id,
        candidate.target_audio_artifact_id,
        candidate.timing_plan_artifact_id,
    ] if value is not None]
    if candidate_ids != expected:
        raise AppError("P15_CANDIDATE_STALE", "P15 candidate 不属于当前正式输入", status_code=409)
    return candidate, project, inputs


def reject_storyboard_candidate(db: Session, *, project_id: str, candidate_id: str, command: P15ReviewCommand) -> P15CandidateRead:
    candidate, _project, _inputs = _review_candidate(db, project_id, candidate_id, command)
    candidate.review_status = P15CandidateReviewStatus.REJECTED.value
    candidate.review_reason = command.reason
    candidate.reviewed_at = utc_now()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_read(candidate)


def _next_artifact_revision(db: Session, project_id: str, artifact_type: ArtifactType) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
    )
    return int(latest or 0) + 1


def accept_storyboard_candidate(db: Session, *, project_id: str, candidate_id: str, command: P15ReviewCommand) -> ReplicaTargetStoryboardRead:
    candidate, project, inputs = _review_candidate(db, project_id, candidate_id, command)
    bundle = ReplicaStoryboardBundle.model_validate(candidate.bundle_json)
    base_prov = provenance(inputs, generation_sequence=candidate.generation_sequence, task_id=candidate.generated_by_task_id or "")
    previous_storyboard_current, previous_storyboard = _current_or_latest(db, project_id, ArtifactType.TARGET_STORYBOARD)
    previous_segments_current, previous_segments = _current_or_latest(db, project_id, ArtifactType.GENERATION_SEGMENTS)
    reviewed_at = utc_now()
    skill = get_professional_skill("storyboard-directing")
    storyboard_fp = _sha({"candidate_id": candidate.id, "storyboard": bundle.storyboard.model_dump(mode="json")})
    storyboard_artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_STORYBOARD.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="复刻目标分镜",
        revision=_next_artifact_revision(db, project_id, ArtifactType.TARGET_STORYBOARD),
        input_fingerprint=storyboard_fp,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={"schema_version": P15_SCHEMA_VERSION, "shot_count": len(bundle.storyboard.shots), "candidate_id": candidate.id},
    )
    try:
        stale_roots = [node for node in (previous_storyboard_current, previous_segments_current) if node is not None]
        if stale_roots:
            _mark_stale_with_downstream(db, stale_roots)
        db.add(storyboard_artifact)
        db.flush()
        segments_content = bundle.generation_segments.model_copy(update={"target_storyboard_artifact_id": storyboard_artifact.id}, deep=True)
        segments_fp = _sha({"candidate_id": candidate.id, "storyboard_artifact_id": storyboard_artifact.id, "segments": segments_content.model_dump(mode="json")})
        segments_artifact = ArtifactNode(
            project_id=project_id,
            artifact_type=ArtifactType.GENERATION_SEGMENTS.value,
            namespace=ArtifactNamespace.PRODUCTION,
            label="视频生成分段计划",
            revision=_next_artifact_revision(db, project_id, ArtifactType.GENERATION_SEGMENTS),
            input_fingerprint=segments_fp,
            skill_id=skill.id,
            skill_version=skill.version,
            validity=ArtifactValidity.CURRENT,
            is_current=True,
            metadata_json={"schema_version": P15_SCHEMA_VERSION, "segment_count": len(segments_content.segments), "candidate_id": candidate.id},
        )
        db.add(segments_artifact)
        db.flush()
        storyboard_prov = P15ArtifactProvenance(
            **base_prov.model_dump(),
            candidate_id=candidate.id,
            reviewed_at=reviewed_at,
            review_reason=command.reason,
            supersedes_artifact_id=previous_storyboard.id if previous_storyboard is not None else None,
        )
        segments_prov = P15ArtifactProvenance(
            **base_prov.model_dump(),
            candidate_id=candidate.id,
            reviewed_at=reviewed_at,
            review_reason=command.reason,
            supersedes_artifact_id=previous_segments.id if previous_segments is not None else None,
        )
        db.add(
            ReplicaTargetStoryboardRevision(
                project_id=project_id,
                artifact_id=storyboard_artifact.id,
                candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P15_SCHEMA_VERSION,
                content_json=bundle.storyboard.model_dump(mode="json"),
                provenance_json=storyboard_prov.model_dump(mode="json"),
            )
        )
        db.add(
            ReplicaGenerationSegmentsRevision(
                project_id=project_id,
                artifact_id=segments_artifact.id,
                target_storyboard_artifact_id=storyboard_artifact.id,
                candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P15_SCHEMA_VERSION,
                content_json=segments_content.model_dump(mode="json"),
                provenance_json=segments_prov.model_dump(mode="json"),
            )
        )
        for source in (
            inputs.source_snapshot_artifact,
            inputs.target_bible_artifact,
            inputs.target_script_artifact,
            inputs.target_assets_artifact,
            inputs.target_audio_artifact,
            inputs.timing_plan_artifact,
        ):
            if source is None:
                continue
            db.add(
                ArtifactEdge(
                    project_id=project_id,
                    source_node_id=source.id,
                    target_node_id=storyboard_artifact.id,
                    relation_type=ArtifactRelationType.DERIVED_FROM if source.id == inputs.source_snapshot_artifact.id else ArtifactRelationType.USES,
                )
            )
        db.add(ArtifactEdge(project_id=project_id, source_node_id=storyboard_artifact.id, target_node_id=segments_artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
        if previous_storyboard is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=storyboard_artifact.id, target_node_id=previous_storyboard.id, relation_type=ArtifactRelationType.SUPERSEDES))
        if previous_segments is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=segments_artifact.id, target_node_id=previous_segments.id, relation_type=ArtifactRelationType.SUPERSEDES))
        candidate.review_status = P15CandidateReviewStatus.ACCEPTED.value
        candidate.review_reason = command.reason
        candidate.reviewed_at = reviewed_at
        db.add(candidate)
        for other in db.scalars(
            select(ReplicaStoryboardCandidate).where(
                ReplicaStoryboardCandidate.project_id == project_id,
                ReplicaStoryboardCandidate.id != candidate.id,
                ReplicaStoryboardCandidate.review_status == P15CandidateReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            other.review_status = P15CandidateReviewStatus.SUPERSEDED.value
            other.review_reason = "Another storyboard candidate was accepted."
            other.reviewed_at = reviewed_at
            db.add(other)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_storyboard(db, project_id)
