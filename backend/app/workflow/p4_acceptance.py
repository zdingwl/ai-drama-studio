import hashlib
import time
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import func, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.skills.models import Capability
from app.workflow.models import ProviderJob, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate
from app.workflow.task_service import TaskCancelled, checkpoint_task, mark_task_failed, mark_task_succeeded


P4_ACCEPTANCE_PREFIX = "P4_ACCEPTANCE_"


class P4AcceptanceScenario(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"
    RESUME = "resume"


_SCENARIO_TASK_NAMES = {
    P4AcceptanceScenario.SUCCESS: "P4 验收：正常执行与安全调用",
    P4AcceptanceScenario.RETRY: "P4 验收：失败后重试",
    P4AcceptanceScenario.RESUME: "P4 验收：中断后继续",
}


def is_p4_acceptance_task(task: Task) -> bool:
    return task.task_type.startswith(P4_ACCEPTANCE_PREFIX)


def build_p4_acceptance_payload(
    *,
    project_id: str,
    scenario: P4AcceptanceScenario,
    idempotency_key: str,
) -> TaskCommandCreate:
    fingerprint = hashlib.sha256(
        f"{project_id}|{scenario.value}|{idempotency_key.strip()}".encode("utf-8")
    ).hexdigest()
    return TaskCommandCreate(
        task_type=f"{P4_ACCEPTANCE_PREFIX}{scenario.value.upper()}",
        task_name=_SCENARIO_TASK_NAMES[scenario],
        input_fingerprint=fingerprint,
        input_artifact_ids=[],
        max_attempts=3,
    )


def _claim_acceptance_task(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
) -> Task | None:
    with session_factory() as db:
        task = db.get(Task, task_id)
        if task is None or not is_p4_acceptance_task(task):
            return None
        if task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
            return None

        now = utc_now()
        result = db.execute(
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.QUEUED,
                Task.attempt < Task.max_attempts,
            )
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
        claimed = db.get(Task, task_id)
        if claimed is None:
            return None
        db.refresh(claimed)
        return claimed


def _checkpoint(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
    progress_percent: int,
    stage: str,
) -> None:
    with session_factory() as db:
        checkpoint_task(
            db,
            task_id,
            checkpoint={"stage": stage, "progress_percent": progress_percent},
            progress_percent=progress_percent,
            worker_id=worker_id,
        )


def _dispatch_local_provider_guardrail(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
) -> None:
    with session_factory() as db:
        def remote_call(job: ProviderJob) -> ProviderDispatchResult:
            # A second DB session must already be able to see the ProviderJob.
            # If commit-before-remote is ever broken, this acceptance task fails.
            with session_factory() as verifier:
                persisted = verifier.get(ProviderJob, job.id)
                if persisted is None:
                    raise RuntimeError("provider job was not committed before remote call")
            time.sleep(0.35)
            return ProviderDispatchResult(
                value={"accepted": True},
                remote_job_id=f"p4-local-{job.id}",
                completed=True,
            )

        dispatch_provider_call(
            db,
            task_id=task_id,
            provider="p4-local-mock",
            model="local-no-billing",
            capability=Capability.MEDIA_PREFLIGHT,
            payload={"acceptance": "p4-provider-guardrail"},
            remote_call=remote_call,
        )


def _mark_acceptance_interrupted(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
) -> None:
    with session_factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != TaskStatus.RUNNING or task.worker_id != worker_id:
            return
        now = utc_now()
        task.status = TaskStatus.INTERRUPTED
        task.last_error = "P4 验收：已模拟执行器中断，可从最近检查点继续"
        task.worker_id = None
        task.heartbeat_at = None
        task.finished_at = None
        task.updated_at = now
        db.add(task)
        db.commit()


def _finish_success(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
) -> None:
    with session_factory() as db:
        mark_task_succeeded(db, task_id, worker_id=worker_id)


def _finish_failure(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
    message: str,
) -> None:
    with session_factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != TaskStatus.RUNNING or task.worker_id != worker_id:
            return
        mark_task_failed(db, task_id, safe_error=message, worker_id=worker_id)


def run_p4_acceptance_task(
    session_factory: sessionmaker[Session],
    task_id: str,
) -> None:
    worker_id = f"p4-acceptance-{uuid4()}"
    task = _claim_acceptance_task(session_factory, task_id=task_id, worker_id=worker_id)
    if task is None:
        return

    scenario_name = task.task_type.removeprefix(P4_ACCEPTANCE_PREFIX).lower()
    try:
        scenario = P4AcceptanceScenario(scenario_name)
    except ValueError:
        _finish_failure(
            session_factory,
            task_id=task_id,
            worker_id=worker_id,
            message="P4 验收场景不存在",
        )
        return

    try:
        if scenario == P4AcceptanceScenario.RETRY and task.attempt == 1:
            _checkpoint(
                session_factory,
                task_id=task_id,
                worker_id=worker_id,
                progress_percent=40,
                stage="first-attempt-failure",
            )
            time.sleep(0.8)
            _finish_failure(
                session_factory,
                task_id=task_id,
                worker_id=worker_id,
                message="P4 验收：首次执行按预期失败，请点击重试",
            )
            return

        if scenario == P4AcceptanceScenario.RESUME and task.attempt == 1:
            _checkpoint(
                session_factory,
                task_id=task_id,
                worker_id=worker_id,
                progress_percent=55,
                stage="resume-checkpoint",
            )
            time.sleep(0.8)
            _mark_acceptance_interrupted(
                session_factory,
                task_id=task_id,
                worker_id=worker_id,
            )
            return

        starting_progress = max(task.progress_percent, 10)
        _checkpoint(
            session_factory,
            task_id=task_id,
            worker_id=worker_id,
            progress_percent=starting_progress,
            stage="started",
        )
        time.sleep(0.8)

        next_progress = max(task.progress_percent, 35)
        _checkpoint(
            session_factory,
            task_id=task_id,
            worker_id=worker_id,
            progress_percent=next_progress,
            stage="checkpoint-saved",
        )
        time.sleep(0.8)

        _dispatch_local_provider_guardrail(session_factory, task_id=task_id)
        _checkpoint(
            session_factory,
            task_id=task_id,
            worker_id=worker_id,
            progress_percent=max(task.progress_percent, 72),
            stage="safe-provider-call-finished",
        )
        time.sleep(0.8)

        _checkpoint(
            session_factory,
            task_id=task_id,
            worker_id=worker_id,
            progress_percent=92,
            stage="finalizing",
        )
        time.sleep(0.8)
        _finish_success(session_factory, task_id=task_id, worker_id=worker_id)
    except TaskCancelled:
        return
    except Exception:
        _finish_failure(
            session_factory,
            task_id=task_id,
            worker_id=worker_id,
            message="P4 验收任务执行失败",
        )
