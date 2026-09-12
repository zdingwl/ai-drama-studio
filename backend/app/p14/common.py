import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import ProjectType
from app.projects.models import Project
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import checkpoint_task


def _sha(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_replica(project: Project) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError("REPLICA_P14_NOT_ALLOWED", "P14 目标配音与时序当前只允许 REPLICA 项目", status_code=422)


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.is_current.is_(True),
            ArtifactNode.validity == ArtifactValidity.CURRENT,
        )
    )


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value)
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )


def _next_artifact_revision(db: Session, project_id: str, artifact_type: ArtifactType) -> int:
    value = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
    )
    return int(value or 0) + 1


def _next_generation_sequence(db: Session, project_id: str, model: type) -> int:
    value = db.scalar(select(func.max(model.generation_sequence)).where(model.project_id == project_id))
    return int(value or 0) + 1


def _existing_command_task(
    db: Session,
    *,
    project_id: str,
    idempotency_key: str,
    task_type: str,
    command_payload: dict | None = None,
) -> Task | None:
    normalized = idempotency_key.strip()
    existing = db.scalar(
        select(Task).where(Task.project_id == project_id, Task.idempotency_key == normalized)
    )
    if existing is None:
        return None
    if existing.task_type != task_type:
        raise AppError(
            "IDEMPOTENCY_KEY_REUSED",
            "同一个 Idempotency-Key 不能用于不同 P14 命令",
            status_code=409,
        )
    if command_payload is not None:
        stored = (existing.checkpoint_json or {}).get("p14_audio_command")
        if stored != command_payload:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "同一个 Idempotency-Key 不能用于不同 voice binding",
                status_code=409,
            )
    return existing


def _claim_specific(db: Session, task_id: str, task_type: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != task_type or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
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


def _checkpoint(factory: sessionmaker[Session], task_id: str, worker_id: str, *, progress: int, **values: object) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise AppError("TASK_NOT_FOUND", "P14 Task 不存在", status_code=404)
        checkpoint = dict(task.checkpoint_json or {})
        checkpoint.update(values)
        checkpoint_task(db, task_id, checkpoint=checkpoint, progress_percent=progress, worker_id=worker_id)


def _mark_stage_failed(factory: sessionmaker[Session], task_id: str, message: str) -> None:
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
