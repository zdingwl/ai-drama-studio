import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    checkpoint_task,
    claim_next_task,
    heartbeat_task,
    mark_task_failed,
    mark_task_succeeded,
)


class TaskHandler(Protocol):
    def __call__(self, context: "TaskExecutionContext", task: TaskWorkerRead) -> None: ...


@dataclass
class TaskHandlerRegistry:
    handlers: dict[str, TaskHandler] = field(default_factory=dict)

    def register(self, task_type: str, handler: TaskHandler) -> None:
        normalized = task_type.strip()
        if not normalized:
            raise ValueError("task_type must not be empty")
        self.handlers[normalized] = handler

    def get(self, task_type: str) -> TaskHandler | None:
        return self.handlers.get(task_type)


@dataclass(frozen=True)
class TaskExecutionContext:
    session_factory: sessionmaker[Session]
    task_id: str
    worker_id: str

    def heartbeat(self) -> None:
        with self.session_factory() as db:
            heartbeat_task(db, self.task_id, worker_id=self.worker_id)

    def checkpoint(self, checkpoint: dict, *, progress_percent: int) -> None:
        with self.session_factory() as db:
            checkpoint_task(
                db,
                self.task_id,
                checkpoint=checkpoint,
                progress_percent=progress_percent,
                worker_id=self.worker_id,
            )


def _finish_worker_failure(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
    safe_error: str,
) -> Task:
    with session_factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise RuntimeError("claimed task disappeared")
        if task.status == TaskStatus.RUNNING and task.cancel_requested:
            return mark_task_succeeded(db, task_id, worker_id=worker_id)
        if task.status != TaskStatus.RUNNING:
            return task
        return mark_task_failed(db, task_id, safe_error=safe_error, worker_id=worker_id)


def _app_error_task_message(exc: AppError) -> str:
    """Expose only the authored safe AppError code/message, never raw exception details."""

    return f"任务执行失败（{exc.code}）：{exc.message}"


def run_worker_once(
    session_factory: sessionmaker[Session],
    registry: TaskHandlerRegistry,
    *,
    worker_id: str,
) -> Task | None:
    with session_factory() as db:
        claimed = claim_next_task(db, worker_id)
        if claimed is None:
            return None
        task_snapshot = TaskWorkerRead.model_validate(claimed)

    handler = registry.get(task_snapshot.task_type)
    if handler is None:
        return _finish_worker_failure(
            session_factory,
            task_id=task_snapshot.id,
            worker_id=worker_id,
            safe_error="任务执行器未注册",
        )

    context = TaskExecutionContext(
        session_factory=session_factory,
        task_id=task_snapshot.id,
        worker_id=worker_id,
    )
    try:
        handler(context, task_snapshot)
    except TaskCancelled:
        with session_factory() as db:
            task = db.get(Task, task_snapshot.id)
            if task is None:
                raise RuntimeError("cancelled task disappeared")
            return task
    except AppError as exc:
        return _finish_worker_failure(
            session_factory,
            task_id=task_snapshot.id,
            worker_id=worker_id,
            safe_error=_app_error_task_message(exc),
        )
    except Exception as exc:
        return _finish_worker_failure(
            session_factory,
            task_id=task_snapshot.id,
            worker_id=worker_id,
            safe_error=f"任务执行失败（{type(exc).__name__}）",
        )

    with session_factory() as db:
        return mark_task_succeeded(db, task_snapshot.id, worker_id=worker_id)


def run_worker_loop(
    session_factory: sessionmaker[Session],
    registry: TaskHandlerRegistry,
    *,
    worker_id: str,
    should_stop: Callable[[], bool],
    poll_interval_seconds: float = 1.0,
) -> None:
    """Run the DB-backed queue. P5+ registers real handlers; P4 supplies only the runtime."""

    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")
    while not should_stop():
        task = run_worker_once(session_factory, registry, worker_id=worker_id)
        if task is None:
            time.sleep(poll_interval_seconds)