"""One-click script asset extraction, isolated to SCRIPT_TO_DRAMA.

The first queued task runs existing checkpointed analysis and publishes its normal
source artifacts. Only after publication can the existing world task be queued.
If enqueueing world fails, a repeated command resumes at world without reanalysing.
"""
from uuid import uuid4

from sqlalchemy import update, func
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactValidity
from app.core.errors import AppError
from app.core.time import utc_now
from app.core.config import get_settings
from app.script_localization.long_text import CHUNK_CONTRACT_VERSION
from app.script_localization.providers import ScriptLocalizationProvider
from app.script_to_drama import service
from app.skills.models import ArtifactType
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded, task_to_read
from app.workflow.worker import TaskExecutionContext

TASK_TYPE = "SCRIPT_TO_DRAMA_ASSET_EXTRACTION"


def start_extraction(db: Session, project_id: str, idempotency_key: str) -> Task:
    """Return one queued task: analysis then world, or world if analysis already CURRENT."""
    service.require_project(db, project_id)
    world = service._current(db, project_id, ArtifactType.TARGET_BIBLE)
    if world is not None:
        raise AppError("SCRIPT_TO_DRAMA_ASSETS_ALREADY_EXTRACTED", "当前剧本的资产已经提取，请在资产库审核；切换剧本后可重新提取", status_code=409)
    if service._current(db, project_id, ArtifactType.SOURCE_TEXT_SNAPSHOT) is not None:
        return service.start_stage(db, project_id, "world", idempotency_key)
    bundle = service._inputs(db, project_id, "analyze")
    provider = ScriptLocalizationProvider(get_settings(), bundle.project.source_understanding_provider)
    task = create_task_from_command(
        db, project_id=project_id, idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=TASK_TYPE,
            task_name="提取剧本资产：原文结构化→人物／场景／道具",
            input_fingerprint=service._fingerprint(bundle, "analyze", provider.profile()),
            input_artifact_ids=[item.id for item in bundle.artifacts],
            initial_checkpoint_json={"stage": "analyze", "contract": CHUNK_CONTRACT_VERSION, "parts": [], "job_ids": [], "next_stage": "world"},
            max_attempts=3,
        ),
    )
    return task


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    now = utc_now()
    changed = db.execute(update(Task).where(
        Task.id == task_id, Task.task_type == TASK_TYPE,
        Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts,
    ).values(
        status=TaskStatus.RUNNING, attempt=Task.attempt + 1,
        worker_id=worker_id, heartbeat_at=now,
        started_at=func.coalesce(Task.started_at, now), finished_at=None, updated_at=now,
    ))
    if changed.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(Task, task_id)


def run_extraction_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"script-to-drama-extract-{uuid4()}"
    with factory() as db:
        task = _claim(db, task_id, worker_id)
        if task is None:
            return
        snapshot = TaskWorkerRead.model_validate(task)
    context = TaskExecutionContext(factory, snapshot.id, worker_id)
    try:
        stage, result, jobs = service._execute(context, snapshot)
        if stage != "analyze":
            raise AppError("SCRIPT_TO_DRAMA_EXTRACTION_STAGE_INVALID", "资产提取任务阶段无效", status_code=409)
    except TaskCancelled:
        return
    except AppError as exc:
        with factory() as db:
            mark_task_failed(db, snapshot.id, safe_error=f"资产提取失败（{exc.code}）：{exc.message}", worker_id=worker_id)
        return
    except Exception as exc:
        with factory() as db:
            mark_task_failed(db, snapshot.id, safe_error=f"资产提取异常（{type(exc).__name__}）", worker_id=worker_id)
        return
    with factory() as db:
        done = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if done.status == TaskStatus.CANCELLED:
        return
    try:
        with factory() as db:
            service._publish(db, snapshot.id, "analyze", result, jobs)
    except AppError as exc:
        with factory() as db:
            service._publish_failed(db, snapshot.id, f"剧本分析发布失败（{exc.code}）：{exc.message}")
        return
    except Exception as exc:
        with factory() as db:
            service._publish_failed(db, snapshot.id, f"剧本分析发布异常（{type(exc).__name__}）")
        return
    # A distinct durable world task is queued only once the analysis artifacts
    # are CURRENT. The endpoint can retry this enqueue step without reanalysis.
    try:
        with factory() as db:
            service.start_stage(db, snapshot.project_id, "world", f"asset-extract-world-{snapshot.id}")
    except AppError:
        # Analysis remains a valid, independently completed artifact; the next
        # extract command sees it and starts the missing world task directly.
        return
