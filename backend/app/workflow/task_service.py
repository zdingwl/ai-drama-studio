import hashlib
import json
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.models import Project
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.plan_models import ProjectExecutionPlanRecord, ProjectExecutionPlanStepRecord
from app.sources.models import Episode
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskRead


class TaskCancelled(RuntimeError):
    """Internal cooperative-cancellation signal used by workers."""


def _canonical_sha256(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_task(db: Session, project_id: str, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    return task


def get_task(db: Session, project_id: str, task_id: str) -> Task:
    get_project(db, project_id)
    return _get_task(db, project_id, task_id)


def list_tasks(db: Session, project_id: str) -> list[Task]:
    get_project(db, project_id)
    return list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.created_at.desc(), Task.id.desc())
        ).all()
    )


def task_to_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        project_id=task.project_id,
        task_name=task.task_name,
        progress_percent=task.progress_percent,
        status=task.status,
        last_error=task.last_error,
        attempt=task.attempt,
        max_attempts=task.max_attempts,
        can_retry=task.status == TaskStatus.FAILED and task.attempt < task.max_attempts,
        can_cancel=(
            task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.INTERRUPTED}
            and not task.cancel_requested
        ),
        can_resume=task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _assert_current_artifact_inputs(db: Session, project_id: str, artifact_ids: list[str]) -> None:
    unique_ids = list(dict.fromkeys(artifact_ids))
    if not unique_ids:
        return
    rows = list(db.scalars(select(ArtifactNode).where(ArtifactNode.id.in_(unique_ids))).all())
    by_id = {row.id: row for row in rows}
    missing = [artifact_id for artifact_id in unique_ids if artifact_id not in by_id]
    if missing:
        raise AppError(
            "TASK_INPUT_ARTIFACT_NOT_FOUND",
            "任务输入引用了不存在的 Artifact",
            status_code=422,
            details={"artifact_ids": missing},
        )
    cross_project = [row.id for row in rows if row.project_id != project_id]
    if cross_project:
        raise AppError(
            "TASK_INPUT_ARTIFACT_PROJECT_MISMATCH",
            "任务输入 Artifact 不能跨项目",
            status_code=422,
            details={"artifact_ids": cross_project},
        )
    stale = [
        row.id
        for row in rows
        if row.validity != ArtifactValidity.CURRENT or not row.is_current
    ]
    if stale:
        raise AppError(
            "STALE_ARTIFACT_INPUT",
            "任务输入包含已过期 Artifact，必须基于当前正式结果重新创建任务",
            status_code=409,
            details={"artifact_ids": stale},
        )


def _assert_scope_is_current(db: Session, project: Project, payload: TaskCommandCreate) -> None:
    if payload.episode_id is not None:
        episode = db.get(Episode, payload.episode_id)
        if episode is None or episode.project_id != project.id:
            raise AppError("TASK_EPISODE_SCOPE_INVALID", "任务 Episode 范围无效", status_code=422)

    if payload.plan_step_key is not None and payload.plan_id is None:
        raise AppError("TASK_PLAN_SCOPE_INVALID", "指定 Plan Step 时必须同时指定 Plan", status_code=422)

    if payload.plan_id is None:
        return

    plan = db.get(ProjectExecutionPlanRecord, payload.plan_id)
    if (
        plan is None
        or plan.project_id != project.id
        or not plan.is_current
        or project.current_plan_id != plan.id
    ):
        raise AppError("TASK_PLAN_STALE", "任务必须绑定当前有效的 ProjectExecutionPlan", status_code=409)

    if payload.plan_step_key is not None:
        step = db.scalar(
            select(ProjectExecutionPlanStepRecord).where(
                ProjectExecutionPlanStepRecord.plan_id == plan.id,
                ProjectExecutionPlanStepRecord.step_key == payload.plan_step_key,
            )
        )
        if step is None:
            raise AppError("TASK_PLAN_STEP_NOT_FOUND", "任务绑定的 Plan Step 不存在", status_code=422)
        if step.status != "READY":
            raise AppError(
                "TASK_PLAN_STEP_NOT_READY",
                "当前 Plan Step 尚不可执行",
                status_code=409,
                details={"status": step.status},
            )


def _business_key(project_id: str, payload: TaskCommandCreate) -> str:
    return _canonical_sha256(
        {
            "project_id": project_id,
            "task_type": payload.task_type.strip(),
            "input_fingerprint": payload.input_fingerprint,
            "input_artifact_ids": sorted(set(payload.input_artifact_ids)),
            "plan_id": payload.plan_id,
            "plan_step_key": payload.plan_step_key,
            "episode_id": payload.episode_id,
        }
    )


def create_task_from_command(
    db: Session,
    *,
    project_id: str,
    payload: TaskCommandCreate,
    idempotency_key: str,
) -> Task:
    project = get_project(db, project_id)
    normalized_idempotency_key = idempotency_key.strip()
    if not normalized_idempotency_key or len(normalized_idempotency_key) > 128:
        raise AppError("INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 无效", status_code=422)

    _assert_current_artifact_inputs(db, project_id, payload.input_artifact_ids)
    _assert_scope_is_current(db, project, payload)
    business_key = _business_key(project_id, payload)

    existing_by_key = db.scalar(
        select(Task).where(
            Task.project_id == project_id,
            Task.idempotency_key == normalized_idempotency_key,
        )
    )
    if existing_by_key is not None:
        if existing_by_key.business_key != business_key:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "同一个 Idempotency-Key 不能用于不同任务输入",
                status_code=409,
            )
        return existing_by_key

    existing_by_business = db.scalar(
        select(Task).where(Task.project_id == project_id, Task.business_key == business_key)
    )
    if existing_by_business is not None:
        return existing_by_business

    now = utc_now()
    task = Task(
        project_id=project_id,
        task_type=payload.task_type.strip(),
        task_name=payload.task_name.strip(),
        idempotency_key=normalized_idempotency_key,
        business_key=business_key,
        input_fingerprint=payload.input_fingerprint,
        input_artifact_ids_json=list(dict.fromkeys(payload.input_artifact_ids)),
        plan_id=payload.plan_id,
        plan_step_key=payload.plan_step_key,
        episode_id=payload.episode_id,
        status=TaskStatus.QUEUED,
        progress_percent=0,
        attempt=0,
        max_attempts=payload.max_attempts,
        checkpoint_json={},
        cancel_requested=False,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(Task).where(Task.project_id == project_id, Task.business_key == business_key)
        )
        if concurrent is not None:
            return concurrent
        raise
    db.refresh(task)
    return task


def cancel_task(db: Session, project_id: str, task_id: str) -> Task:
    task = _get_task(db, project_id, task_id)
    now = utc_now()
    if task.status == TaskStatus.CANCELLED:
        return task
    if task.status == TaskStatus.RUNNING:
        task.cancel_requested = True
        task.updated_at = now
    elif task.status in {TaskStatus.QUEUED, TaskStatus.INTERRUPTED}:
        task.status = TaskStatus.CANCELLED
        task.cancel_requested = True
        task.finished_at = now
        task.worker_id = None
        task.heartbeat_at = None
        task.updated_at = now
    else:
        raise AppError("TASK_NOT_CANCELLABLE", "当前任务状态不能取消", status_code=409)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def retry_task(db: Session, project_id: str, task_id: str) -> Task:
    task = _get_task(db, project_id, task_id)
    if task.status != TaskStatus.FAILED:
        raise AppError("TASK_NOT_RETRYABLE", "只有失败任务可以重试", status_code=409)
    if task.attempt >= task.max_attempts:
        raise AppError("TASK_RETRY_LIMIT_REACHED", "任务已达到最大重试次数", status_code=409)
    _assert_current_artifact_inputs(db, project_id, task.input_artifact_ids_json)
    if task.plan_id is not None:
        project = get_project(db, project_id)
        if project.current_plan_id != task.plan_id:
            raise AppError("TASK_PLAN_STALE", "原任务计划已失效，不能重试", status_code=409)
    task.status = TaskStatus.QUEUED
    task.cancel_requested = False
    task.worker_id = None
    task.heartbeat_at = None
    task.finished_at = None
    task.last_error = None
    task.updated_at = utc_now()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def resume_task(db: Session, project_id: str, task_id: str) -> Task:
    task = _get_task(db, project_id, task_id)
    if task.status != TaskStatus.INTERRUPTED:
        raise AppError("TASK_NOT_RESUMABLE", "只有中断任务可以继续", status_code=409)
    if task.attempt >= task.max_attempts:
        raise AppError("TASK_RETRY_LIMIT_REACHED", "任务已达到最大执行次数，不能继续", status_code=409)
    _assert_current_artifact_inputs(db, project_id, task.input_artifact_ids_json)
    if task.plan_id is not None:
        project = get_project(db, project_id)
        if project.current_plan_id != task.plan_id:
            raise AppError("TASK_PLAN_STALE", "原任务计划已失效，不能继续", status_code=409)
    task.status = TaskStatus.QUEUED
    task.cancel_requested = False
    task.worker_id = None
    task.heartbeat_at = None
    task.finished_at = None
    task.last_error = None
    task.updated_at = utc_now()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def claim_next_task(db: Session, worker_id: str) -> Task | None:
    candidate_id = db.scalar(
        select(Task.id)
        .where(Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
        .order_by(Task.created_at.asc(), Task.id.asc())
        .limit(1)
    )
    if candidate_id is None:
        return None

    now = utc_now()
    result = db.execute(
        update(Task)
        .where(Task.id == candidate_id, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
        .values(
            status=TaskStatus.RUNNING,
            attempt=Task.attempt + 1,
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
    task = db.get(Task, candidate_id)
    if task is None:
        return None
    db.refresh(task)
    return task


def _assert_running_worker(task: Task, worker_id: str | None) -> None:
    if task.status != TaskStatus.RUNNING:
        raise AppError("TASK_NOT_RUNNING", "任务当前未处于运行状态", status_code=409)
    if worker_id is not None and task.worker_id != worker_id:
        raise AppError("TASK_WORKER_MISMATCH", "任务已被其他 Worker 接管", status_code=409)


def heartbeat_task(db: Session, task_id: str, *, worker_id: str | None = None) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    _assert_running_worker(task, worker_id)
    task.heartbeat_at = utc_now()
    task.updated_at = task.heartbeat_at
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def checkpoint_task(
    db: Session,
    task_id: str,
    *,
    checkpoint: dict,
    progress_percent: int,
    worker_id: str | None = None,
) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    _assert_running_worker(task, worker_id)
    if not 0 <= progress_percent <= 100:
        raise AppError("TASK_PROGRESS_INVALID", "任务进度必须在 0 到 100 之间", status_code=422)
    now = utc_now()
    if task.cancel_requested:
        task.status = TaskStatus.CANCELLED
        task.finished_at = now
        task.worker_id = None
        task.heartbeat_at = None
        task.updated_at = now
        db.add(task)
        db.commit()
        raise TaskCancelled(task.id)
    task.checkpoint_json = checkpoint
    task.progress_percent = progress_percent
    task.heartbeat_at = now
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def mark_task_succeeded(db: Session, task_id: str, *, worker_id: str | None = None) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    _assert_running_worker(task, worker_id)
    now = utc_now()
    if task.cancel_requested:
        task.status = TaskStatus.CANCELLED
    else:
        task.status = TaskStatus.SUCCEEDED
        task.progress_percent = 100
        task.last_error = None
    task.finished_at = now
    task.worker_id = None
    task.heartbeat_at = None
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def mark_task_failed(
    db: Session,
    task_id: str,
    *,
    safe_error: str,
    worker_id: str | None = None,
) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    _assert_running_worker(task, worker_id)
    now = utc_now()
    task.status = TaskStatus.FAILED
    task.last_error = (safe_error.strip() or "任务执行失败")[:1000]
    task.finished_at = now
    task.worker_id = None
    task.heartbeat_at = None
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def mark_interrupted_tasks(db: Session, *, stale_before: datetime) -> list[Task]:
    rows = list(
        db.scalars(
            select(Task).where(
                Task.status == TaskStatus.RUNNING,
                or_(Task.heartbeat_at.is_(None), Task.heartbeat_at < stale_before),
            )
        ).all()
    )
    now = utc_now()
    for task in rows:
        if task.attempt >= task.max_attempts:
            task.status = TaskStatus.FAILED
            task.finished_at = now
            task.last_error = "任务执行器心跳中断，且已达到最大执行次数"
        else:
            task.status = TaskStatus.INTERRUPTED
            task.finished_at = None
            task.last_error = "任务执行器心跳中断，可从最近检查点继续"
        task.worker_id = None
        task.heartbeat_at = None
        task.updated_at = now
        db.add(task)
    if rows:
        db.commit()
        for task in rows:
            db.refresh(task)
    return rows


def publish_validated_task_artifact(
    db: Session,
    *,
    task_id: str,
    validation_passed: bool,
    artifact_type: ArtifactType,
    namespace: ArtifactNamespace,
    label: str,
    input_fingerprint: str,
    skill_id: str,
    skill_version: str,
    metadata_json: dict | None = None,
) -> ArtifactNode:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    if task.status != TaskStatus.SUCCEEDED:
        raise AppError("TASK_NOT_SUCCEEDED", "只有技术执行成功的任务才允许进入输出校验", status_code=409)
    if not validation_passed:
        raise AppError(
            "TASK_OUTPUT_VALIDATION_FAILED",
            "任务输出校验未通过，不能发布正式 Artifact",
            status_code=422,
        )
    _assert_current_artifact_inputs(db, task.project_id, task.input_artifact_ids_json)
    if task.plan_id is not None:
        project = get_project(db, task.project_id)
        if project.current_plan_id != task.plan_id:
            raise AppError("TASK_PLAN_STALE", "任务对应计划已失效，不能发布正式 Artifact", status_code=409)
    return create_artifact(
        db,
        project_id=task.project_id,
        artifact_type=artifact_type,
        namespace=namespace,
        label=label,
        input_fingerprint=input_fingerprint,
        skill_id=skill_id,
        skill_version=skill_version,
        metadata_json=metadata_json,
    )
