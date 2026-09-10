"""P9 lifecycle adapter for explicit retry semantics and safe task diagnostics.

The P9 base service owns CURRENT-input validation, four Professional Skill Provider calls,
ProviderJob-before-remote persistence and four-Artifact publication. This adapter mirrors the
already accepted P8 command behaviour: a new explicit POST for identical inputs may retry the
existing FAILED business task through the shared Task retry guardrails, while replaying the same
Idempotency-Key remains idempotent and does not consume another attempt.

P9 also uses its own background runner instead of the generic DB worker. Keep authored AppError
messages visible in Task.last_error here as well; otherwise a schema failure such as
P9_PROP_PROVIDER_RESPONSE_INVALID loses the safe validation field/constraint hint and becomes
impossible to diagnose from the product UI.
"""

from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.source_resolution import service as _base
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import TaskCancelled, mark_task_succeeded, retry_task
from app.workflow.worker import TaskExecutionContext


P9_TASK_TYPE = _base.P9_TASK_TYPE


def create_source_resolution_task(db: Session, *, project_id: str, idempotency_key: str):
    task = _base.create_source_resolution_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )
    if task.status == TaskStatus.FAILED and task.idempotency_key != idempotency_key.strip():
        return retry_task(db, project_id, task.id)
    return task


def _p9_task_error_message(exc: AppError) -> str:
    """Expose only the authored safe AppError code/message, never raw provider output."""

    return f"P9 最终归一失败（{exc.code}）：{exc.message}"


def run_p9_source_resolution_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    """Run the P9 task while preserving safe stage-specific validation diagnostics."""

    worker_id = f"p9-source-resolution-{uuid4()}"
    with session_factory() as db:
        claimed = _base._claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        result = _base._execute(context, snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        _base._fail_if_running(session_factory, snapshot.id, worker_id, _p9_task_error_message(exc))
        return
    except Exception as exc:
        _base._fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P9 最终归一失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _base._publish_all(db, task_id=snapshot.id, result=result)
    except AppError as exc:
        _base._mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P9 正式 Artifact 发布失败（{exc.code}）：{exc.message}",
        )
    except Exception as exc:
        _base._mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P9 正式 Artifact 发布失败（{type(exc).__name__}）",
        )


get_source_resolution = _base.get_source_resolution
list_source_resolution_revisions = _base.list_source_resolution_revisions
