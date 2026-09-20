import logging
from collections.abc import Callable
from threading import Event, Thread

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.evidence.service_v4 import is_p6_source_evidence_task, run_p6_source_evidence_task
from app.p14.audio_contract import P14_AUDIO_TASK_TYPE
from app.p14.audio_runtime import run_target_audio_task
from app.p14.timing_service import P14_TIMING_TASK_TYPE, run_timing_plan_task
from app.p15.service import P15_TASK_TYPE, run_storyboard_task
from app.p16.runtime import P16_SEGMENT_TASK_TYPE, P16_TASK_TYPE, run_generation_task
from app.p17.runtime import P17_TASK_TYPE, run_post_task
from app.preprocessing.service import is_p5_shot_boundary_task, run_p5_shot_boundary_task
from app.replica_pipeline.asset_images import ASSET_PROMPT_TASK_TYPE, TASK_TYPE as ASSET_IMAGES_TASK_TYPE, run_asset_images_task
from app.replica_pipeline.h3_prompting import TASK_TYPE as H3_PROMPT_TASK_TYPE, run_h3_prompt_task
from app.replica_pipeline.localized_storyboard import TASK_TYPE as LOCALIZED_STORYBOARD_TASK_TYPE, run_localized_storyboard_task
from app.script_localization.long_pipeline import TASK_TYPE as LONG_SCRIPT_LOCALIZATION_TASK_TYPE, run_long_stage_task
from app.script_localization.service import TASK_TYPE as SCRIPT_LOCALIZATION_TASK_TYPE, run_stage_task
from app.script_to_drama.extraction import TASK_TYPE as SCRIPT_TO_DRAMA_EXTRACTION_TASK_TYPE, run_extraction_task
from app.script_to_drama.production_media import TASK_TYPE as SCRIPT_TO_DRAMA_PRODUCTION_TASK_TYPE, run_stage_task as run_script_to_drama_production_task
from app.script_to_drama.service import TASK_TYPE as SCRIPT_TO_DRAMA_TASK_TYPE, run_stage_task as run_script_to_drama_stage_task
from app.shot_breakdown.service_v2 import P8_TASK_TYPE, run_p8_shot_breakdown_task
from app.source_analysis.service import SOURCE_ANALYSIS_TASK_TYPE, run_source_analysis_task
from app.source_resolution.service_v2 import P9_TASK_TYPE, run_p9_source_resolution_task
from app.understanding.evidence_reference_runtime import run_p7_source_bible_task
from app.understanding.service import P7_TASK_TYPE
from app.workflow.models import Task, TaskStatus
from app.workflow.p4_acceptance import is_p4_acceptance_task, run_p4_acceptance_task


logger = logging.getLogger(__name__)
TaskRunner = Callable[[sessionmaker[Session], str], None]


def _runner_for_task(task: Task) -> TaskRunner | None:
    if is_p4_acceptance_task(task):
        return run_p4_acceptance_task
    if is_p5_shot_boundary_task(task):
        return run_p5_shot_boundary_task
    if is_p6_source_evidence_task(task):
        return run_p6_source_evidence_task
    if task.task_type == P7_TASK_TYPE:
        return run_p7_source_bible_task
    if task.task_type == P8_TASK_TYPE:
        return run_p8_shot_breakdown_task
    if task.task_type == P9_TASK_TYPE:
        return run_p9_source_resolution_task
    if task.task_type == P14_AUDIO_TASK_TYPE:
        return run_target_audio_task
    if task.task_type == P14_TIMING_TASK_TYPE:
        return run_timing_plan_task
    if task.task_type == P15_TASK_TYPE:
        return run_storyboard_task
    if task.task_type in {P16_TASK_TYPE, P16_SEGMENT_TASK_TYPE}:
        return run_generation_task
    if task.task_type == P17_TASK_TYPE:
        return run_post_task
    if task.task_type == LOCALIZED_STORYBOARD_TASK_TYPE:
        return run_localized_storyboard_task
    if task.task_type in {ASSET_IMAGES_TASK_TYPE, ASSET_PROMPT_TASK_TYPE}:
        return run_asset_images_task
    if task.task_type == H3_PROMPT_TASK_TYPE:
        return run_h3_prompt_task
    if task.task_type == SOURCE_ANALYSIS_TASK_TYPE:
        return run_source_analysis_task
    if task.task_type == SCRIPT_LOCALIZATION_TASK_TYPE:
        return run_stage_task
    if task.task_type == LONG_SCRIPT_LOCALIZATION_TASK_TYPE:
        return run_long_stage_task
    if task.task_type == SCRIPT_TO_DRAMA_EXTRACTION_TASK_TYPE:
        return run_extraction_task
    if task.task_type == SCRIPT_TO_DRAMA_TASK_TYPE:
        return run_script_to_drama_stage_task
    if task.task_type == SCRIPT_TO_DRAMA_PRODUCTION_TASK_TYPE:
        return run_script_to_drama_production_task
    return None


def _next_dispatchable(factory: sessionmaker[Session]) -> tuple[str, TaskRunner] | None:
    with factory() as db:
        rows = list(
            db.scalars(
                select(Task)
                .where(Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
                .order_by(Task.created_at.asc(), Task.id.asc())
                .limit(64)
            ).all()
        )
        for task in rows:
            runner = _runner_for_task(task)
            if runner is not None:
                return task.id, runner
    return None


def _reconcile_unhandled_runner_exception(
    factory: sessionmaker[Session],
    task_id: str,
    exc: Exception,
) -> None:
    """Keep a buggy runner from leaving a Task permanently RUNNING/QUEUED."""
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            return
        now = utc_now()
        task.status = TaskStatus.FAILED
        task.last_error = f"统一任务调度器捕获未处理异常（{type(exc).__name__}）"[:1000]
        task.finished_at = now
        task.worker_id = None
        task.heartbeat_at = None
        task.updated_at = now
        db.add(task)
        db.commit()


def run_dispatcher_once(factory: sessionmaker[Session]) -> bool:
    resolved = _next_dispatchable(factory)
    if resolved is None:
        return False
    task_id, runner = resolved
    try:
        runner(factory, task_id)
    except Exception as exc:  # pragma: no cover - defensive process boundary
        logger.exception("task runner escaped unexpectedly: task_id=%s", task_id)
        _reconcile_unhandled_runner_exception(factory, task_id, exc)
    return True


class PersistentTaskDispatcher:
    """Single persistent in-process queue consumer for the local desktop Studio runtime."""

    def __init__(self, factory: sessionmaker[Session], *, poll_interval_seconds: float = 0.25):
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.factory = factory
        self.poll_interval_seconds = poll_interval_seconds
        self._stop = Event()
        self._thread = Thread(target=self._run, name="ai-drama-task-dispatcher", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            worked = run_dispatcher_once(self.factory)
            if not worked:
                self._stop.wait(self.poll_interval_seconds)
