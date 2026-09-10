"""P9 lifecycle adapter for explicit retry semantics.

The P9 base service owns CURRENT-input validation, four Professional Skill Provider calls,
ProviderJob-before-remote persistence and four-Artifact publication. This adapter only mirrors the
already accepted P8 command behaviour: a new explicit POST for identical inputs may retry the
existing FAILED business task through the shared Task retry guardrails, while replaying the same
Idempotency-Key remains idempotent and does not consume another attempt.
"""

from sqlalchemy.orm import Session

from app.source_resolution import service as _base
from app.workflow.models import TaskStatus
from app.workflow.task_service import retry_task


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


get_source_resolution = _base.get_source_resolution
list_source_resolution_revisions = _base.list_source_resolution_revisions
run_p9_source_resolution_task = _base.run_p9_source_resolution_task
