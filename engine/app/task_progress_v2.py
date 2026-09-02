"""AI Drama Studio V2 统一后台任务与真实进度状态。

职责：
- 保存耗时任务的 QUEUED / PROCESSING / READY / FAILED 状态；
- 保存真实可计算百分比，或明确标记为 indeterminate 阶段进度；
- 页面刷新后仍可恢复任务显示；
- 服务重启时把无法继续执行的 PROCESSING 任务标记为 INTERRUPTED/FAILED，而不是假装仍在运行。

注意：
Task 只描述“后台现在在做什么”，不替代业务 Run / Revision。
业务 Run 负责结果版本；Task 负责执行过程和错误。
"""
from __future__ import annotations

from datetime import datetime
import json
from threading import RLock
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.studio_v2 import Base, get_session, new_id, utcnow

ACTIVE_TASK_STATUSES = {"QUEUED", "PROCESSING"}
TERMINAL_TASK_STATUSES = {"READY", "READY_WITH_WARNINGS", "FAILED", "CANCELLED"}

# Workflow V2 P0: these are real local heavy jobs.  A legacy route is not allowed to opt
# out of same-scope active-task dedup by passing ``deduplicate_active=False``.  The current
# executor is intentionally one local Python process; P3 will add durable Idempotency-Key /
# command receipts for cross-process and request-replay semantics.
FORCE_ACTIVE_DEDUP_TASK_TYPES = {
    "EPISODE_PREPROCESS",
    "BATCH_PREPROCESS",
    "EPISODE_SHOTS",
    "BATCH_SHOTS",
    "EPISODE_BREAKDOWN_P2",
    "BATCH_BREAKDOWN_P2",
    "ASSET_EXTRACTION",
    "ASSET_EXTRACTION_V3",
    "AUTO_REMAKE_PREP_V1",
    "AUTO_OUTPUT_V1",
    "H3_GENERATE_READY_V1",
    "H3_QC_RETRY_V1",
    "POSTPRODUCTION_V1",
}
_TASK_CREATE_LOCK = RLock()


class BackgroundTaskRecord(Base):
    """一个可持久化的后台执行任务。

    为什么存在：长时间 FFmpeg / TransNet / VLM / 生成任务不能让 HTTP 请求一直挂着，
    也不能把进度只放在前端内存里。
    """

    __tablename__ = "v2_background_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str | None] = mapped_column(ForeignKey("v2_episodes.id", ondelete="SET NULL"), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED", index=True)

    # determinate = 有真实百分比；indeterminate = 只能知道当前阶段，不伪造百分比。
    progress_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="determinate")
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_item: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def serialize_task(task: BackgroundTaskRecord) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "episode_id": task.episode_id,
        "task_type": task.task_type,
        "title": task.title,
        "status": task.status,
        "progress_mode": task.progress_mode,
        "progress_percent": task.progress_percent,
        "stage_key": task.stage_key,
        "stage_label": task.stage_label,
        "current_item": task.current_item,
        "current_index": task.current_index,
        "total_items": task.total_items,
        "message": task.message,
        "error_message": task.error_message,
        "result": json.loads(task.result_json) if task.result_json else None,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "updated_at": task.updated_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def create_task(
    *,
    project_id: str,
    task_type: str,
    title: str,
    episode_id: str | None = None,
    progress_mode: str = "determinate",
    total_items: int | None = None,
    deduplicate_active: bool = True,
) -> dict[str, Any]:
    """创建 Task；同一作用域已有活动任务时默认直接返回旧任务。

    ``_TASK_CREATE_LOCK`` closes the local-process query -> insert race so two nearly
    simultaneous HTTP clicks cannot both pass the active-task check and create duplicate
    heavy work.  Formal heavy task types are always deduplicated even if a historical route
    passes ``deduplicate_active=False``.  Full cross-process command receipts /
    Idempotency-Key semantics belong to Workflow V2 P3.
    """

    should_deduplicate = deduplicate_active or task_type in FORCE_ACTIVE_DEDUP_TASK_TYPES
    with _TASK_CREATE_LOCK:
        with get_session() as session:
            if should_deduplicate:
                existing = session.scalar(
                    select(BackgroundTaskRecord)
                    .where(
                        BackgroundTaskRecord.project_id == project_id,
                        BackgroundTaskRecord.task_type == task_type,
                        BackgroundTaskRecord.episode_id == episode_id,
                        BackgroundTaskRecord.status.in_(ACTIVE_TASK_STATUSES),
                    )
                    .order_by(BackgroundTaskRecord.created_at.desc())
                )
                if existing is not None:
                    return serialize_task(existing)

            task = BackgroundTaskRecord(
                id=new_id("TASK"),
                project_id=project_id,
                episode_id=episode_id,
                task_type=task_type,
                title=title,
                status="QUEUED",
                progress_mode=progress_mode,
                progress_percent=0.0 if progress_mode == "determinate" else None,
                total_items=total_items,
                message="等待后台执行",
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return serialize_task(task)


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        return serialize_task(task) if task else None


def list_project_tasks(project_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
    safe_limit = max(1, min(100, int(limit)))
    with get_session() as session:
        tasks = session.scalars(
            select(BackgroundTaskRecord)
            .where(BackgroundTaskRecord.project_id == project_id)
            .order_by(BackgroundTaskRecord.created_at.desc())
            .limit(safe_limit)
        ).all()
        return [serialize_task(item) for item in tasks]


def start_task(task_id: str, *, stage_key: str | None = None, stage_label: str | None = None, message: str | None = None) -> None:
    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if task is None:
            return
        now = utcnow()
        task.status = "PROCESSING"
        task.started_at = task.started_at or now
        task.updated_at = now
        task.stage_key = stage_key
        task.stage_label = stage_label
        task.message = message or stage_label or "正在执行"
        session.commit()


def update_task(
    task_id: str,
    *,
    progress_percent: float | None = None,
    progress_mode: str | None = None,
    stage_key: str | None = None,
    stage_label: str | None = None,
    current_item: str | None = None,
    current_index: int | None = None,
    total_items: int | None = None,
    message: str | None = None,
) -> None:
    """更新任务进度。

    只有能真实计算时才传 progress_percent；无法计算的模型阶段使用 progress_mode='indeterminate'。
    """

    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if task is None or task.status in TERMINAL_TASK_STATUSES:
            return
        task.status = "PROCESSING"
        task.started_at = task.started_at or utcnow()
        task.updated_at = utcnow()
        if progress_mode is not None:
            task.progress_mode = progress_mode
            if progress_mode == "indeterminate" and progress_percent is None:
                task.progress_percent = None
        if progress_percent is not None:
            task.progress_percent = max(0.0, min(100.0, float(progress_percent)))
        if stage_key is not None:
            task.stage_key = stage_key
        if stage_label is not None:
            task.stage_label = stage_label
        if current_item is not None:
            task.current_item = current_item
        if current_index is not None:
            task.current_index = current_index
        if total_items is not None:
            task.total_items = total_items
        if message is not None:
            task.message = message
        session.commit()


def finish_task(task_id: str, *, result: Any = None, message: str = "处理完成", status: str = "READY") -> None:
    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if task is None:
            return
        now = utcnow()
        task.status = status
        task.progress_mode = "determinate"
        task.progress_percent = 100.0
        task.message = message
        task.result_json = json.dumps(result, ensure_ascii=False, default=str) if result is not None else None
        task.updated_at = now
        task.completed_at = now
        session.commit()


def fail_task(task_id: str, error: Exception | str) -> None:
    message = str(error)
    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if task is None:
            return
        now = utcnow()
        task.status = "FAILED"
        task.message = "任务执行失败"
        task.error_message = message
        task.updated_at = now
        task.completed_at = now
        session.commit()


def recover_interrupted_tasks() -> int:
    """应用启动时关闭上一次进程遗留的活动 Task。

    当前本地执行器不是外部任务队列，Python 进程退出后无法继续原函数；因此必须显式标记中断，
    避免 UI 永久显示“处理中”。
    """

    recovered = 0
    with get_session() as session:
        tasks = session.scalars(
            select(BackgroundTaskRecord).where(BackgroundTaskRecord.status.in_(ACTIVE_TASK_STATUSES))
        ).all()
        now = utcnow()
        for task in tasks:
            task.status = "FAILED"
            task.message = "服务重启导致任务中断，可重新执行"
            task.error_message = "TASK_INTERRUPTED_BY_PROCESS_RESTART"
            task.updated_at = now
            task.completed_at = now
            recovered += 1
        session.commit()
    return recovered
