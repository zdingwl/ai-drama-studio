import hashlib
import json
from collections.abc import Callable
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.core.time import utc_now
from app.evidence.manual_adjudication import get_episode_source_evidence
from app.evidence.service_v4 import create_source_evidence_task, run_p6_source_evidence_task
from app.preprocessing.service import create_shot_boundary_task, get_episode_shot_boundary, run_p5_shot_boundary_task
from app.projects.enums import SOURCE_BIBLE_PROJECT_TYPES
from app.projects.service import get_project
from app.shot_breakdown.service_v2 import create_shot_breakdown_task, get_shot_breakdown, run_p8_shot_breakdown_task
from app.skills.models import ArtifactType
from app.source_analysis.schemas import SourceAnalysisState, SourceAnalysisStatusRead, SourceScriptRead
from app.source_resolution.service_v2 import create_source_resolution_task, get_source_resolution, run_p9_source_resolution_task
from app.source_snapshot.service import finalize_source_video_snapshot, get_source_video_snapshot
from app.sources.models import Episode
from app.understanding.evidence_reference_runtime import run_p7_source_bible_task
from app.understanding.service import create_source_bible_task, get_source_bible
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    resume_task,
    retry_task,
)
from app.workflow.worker import TaskExecutionContext


SOURCE_ANALYSIS_TASK_TYPE = "SOURCE_ANALYSIS_PIPELINE"


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _assert_source_analysis_project(db: Session, project_id: str) -> None:
    project = get_project(db, project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError(
            "SOURCE_ANALYSIS_NOT_ALLOWED",
            "当前一键原片解析仅用于复刻短剧和重绘短剧",
            status_code=422,
        )


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )


def _latest_pipeline_task(db: Session, project_id: str) -> Task | None:
    return db.scalar(
        select(Task)
        .where(Task.project_id == project_id, Task.task_type == SOURCE_ANALYSIS_TASK_TYPE)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(1)
    )


def _pipeline_input_fingerprint(db: Session, project_id: str, source: ArtifactNode) -> str:
    project = get_project(db, project_id)
    latest = _latest_pipeline_task(db, project_id)
    restart_after_terminal = None
    if latest is not None and (
        latest.status in {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED}
        or (
            latest.status in {TaskStatus.FAILED, TaskStatus.INTERRUPTED}
            and latest.attempt >= latest.max_attempts
        )
    ):
        restart_after_terminal = latest.id
    return _sha(
        {
            "task": SOURCE_ANALYSIS_TASK_TYPE,
            "source_video": [source.id, source.input_fingerprint],
            "project_type": project.project_type.value,
            "source_language": project.source_language,
            "source_understanding_provider": project.source_understanding_provider.value,
            # A non-CURRENT snapshot after a terminal pipeline means an upstream
            # Source revision changed or the previous publication/recovery was exhausted.
            # Including that terminal task prevents the generic business-key
            # dedupe from replaying an old terminal task instead of scheduling
            # the missing/STALE recovery chain.
            "restart_after_terminal": restart_after_terminal,
        }
    )


def _pipeline_message(task: Task | None, state: SourceAnalysisState) -> str:
    if state == SourceAnalysisState.READY:
        return "原片解析完成，可以直接查看剧本和分镜。"
    if state == SourceAnalysisState.RUNNING:
        stage = str((task.checkpoint_json or {}).get("stage_label") or "正在解析原片") if task else "正在解析原片"
        return stage
    if state == SourceAnalysisState.NEEDS_REFRESH:
        return "原片分析结果已有更新，需要重新解析后再继续。"
    if state == SourceAnalysisState.FAILED:
        if task is not None and task.status == TaskStatus.INTERRUPTED:
            return task.last_error or "原片解析已中断，请重新解析继续。"
        return task.last_error or "原片解析失败，请重试。" if task else "原片解析失败，请重试。"
    return "上传原片后即可开始解析。"


def get_source_analysis_status(db: Session, project_id: str) -> SourceAnalysisStatusRead:
    _assert_source_analysis_project(db, project_id)

    latest = _latest_pipeline_task(db, project_id)
    if latest is not None and latest.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        state = SourceAnalysisState.RUNNING
        stage = str((latest.checkpoint_json or {}).get("stage_label") or "正在解析原片")
        return SourceAnalysisStatusRead(
            project_id=project_id,
            state=state,
            progress_percent=latest.progress_percent,
            current_stage=stage,
            task_id=latest.id,
            can_retry=False,
            message=_pipeline_message(latest, state),
        )

    snapshot = get_source_video_snapshot(db, project_id)
    if _status_value(snapshot.status) == "CURRENT":
        return SourceAnalysisStatusRead(
            project_id=project_id,
            state=SourceAnalysisState.READY,
            progress_percent=100,
            current_stage="解析完成",
            task_id=latest.id if latest is not None else None,
            can_retry=False,
            message=_pipeline_message(latest, SourceAnalysisState.READY),
        )
    if latest is not None and latest.status in {TaskStatus.FAILED, TaskStatus.INTERRUPTED}:
        fallback_stage = "解析已中断" if latest.status == TaskStatus.INTERRUPTED else "解析失败"
        return SourceAnalysisStatusRead(
            project_id=project_id,
            state=SourceAnalysisState.FAILED,
            progress_percent=latest.progress_percent,
            current_stage=str((latest.checkpoint_json or {}).get("stage_label") or fallback_stage),
            task_id=latest.id,
            can_retry=latest.attempt < latest.max_attempts,
            message=_pipeline_message(latest, SourceAnalysisState.FAILED),
        )
    if _status_value(snapshot.status) == "STALE":
        return SourceAnalysisStatusRead(
            project_id=project_id,
            state=SourceAnalysisState.NEEDS_REFRESH,
            progress_percent=0,
            current_stage=None,
            task_id=latest.id if latest is not None else None,
            can_retry=False,
            message=_pipeline_message(latest, SourceAnalysisState.NEEDS_REFRESH),
        )
    return SourceAnalysisStatusRead(
        project_id=project_id,
        state=SourceAnalysisState.NOT_READY,
        progress_percent=0,
        current_stage=None,
        task_id=latest.id if latest is not None else None,
        can_retry=False,
        message=_pipeline_message(latest, SourceAnalysisState.NOT_READY),
    )


def create_source_analysis_task(db: Session, *, project_id: str, idempotency_key: str) -> Task | None:
    _assert_source_analysis_project(db, project_id)
    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    if source is None:
        raise AppError("SOURCE_VIDEO_REQUIRED", "请先上传原片视频", status_code=409)
    episode_count = int(db.scalar(select(func.count(Episode.id)).where(Episode.project_id == project_id)) or 0)
    if episode_count <= 0:
        raise AppError("SOURCE_VIDEO_REQUIRED", "请先上传至少一个原片 Episode", status_code=409)

    snapshot = get_source_video_snapshot(db, project_id)
    if _status_value(snapshot.status) == "CURRENT":
        return None

    latest = _latest_pipeline_task(db, project_id)
    if latest is not None and latest.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        return latest
    if latest is not None and latest.status == TaskStatus.FAILED and latest.attempt < latest.max_attempts:
        return retry_task(db, project_id, latest.id)
    if latest is not None and latest.status == TaskStatus.INTERRUPTED and latest.attempt < latest.max_attempts:
        return resume_task(db, project_id, latest.id)

    payload = TaskCommandCreate(
        task_type=SOURCE_ANALYSIS_TASK_TYPE,
        task_name="解析原片",
        input_fingerprint=_pipeline_input_fingerprint(db, project_id, source),
        input_artifact_ids=[source.id],
        max_attempts=3,
    )
    return create_task_from_command(
        db,
        project_id=project_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


def _claim_pipeline_task(db: Session, task_id: str, *, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if (
        task is None
        or task.task_type != SOURCE_ANALYSIS_TASK_TYPE
        or task.status != TaskStatus.QUEUED
        or task.attempt >= task.max_attempts
    ):
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == SOURCE_ANALYSIS_TASK_TYPE,
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


def _child_idempotency_key(
    parent_task_id: str,
    parent_attempt: int,
    stage: str,
    episode_id: str | None = None,
) -> str:
    suffix = f"-{episode_id}" if episode_id else ""
    return f"source-analysis-{parent_task_id}-a{parent_attempt}-{stage}{suffix}"[:128]


def _ensure_child_succeeded(
    context: TaskExecutionContext,
    *,
    child: Task,
    runner: Callable[[sessionmaker[Session], str], None],
) -> None:
    with context.session_factory() as db:
        current = db.get(Task, child.id)
        if current is None:
            raise AppError("SOURCE_ANALYSIS_CHILD_MISSING", "原片解析子任务不存在", status_code=500)
        if current.status == TaskStatus.FAILED and current.attempt < current.max_attempts:
            current = retry_task(db, current.project_id, current.id)
        elif current.status == TaskStatus.INTERRUPTED and current.attempt < current.max_attempts:
            current = resume_task(db, current.project_id, current.id)
        if current.status == TaskStatus.SUCCEEDED:
            return
        if current.status in {TaskStatus.CANCELLED, TaskStatus.FAILED}:
            raise AppError(
                "SOURCE_ANALYSIS_CHILD_FAILED",
                current.last_error or f"{current.task_name}失败",
                status_code=409,
            )
    runner(context.session_factory, child.id)
    with context.session_factory() as db:
        finished = db.get(Task, child.id)
        if finished is None or finished.status != TaskStatus.SUCCEEDED:
            raise AppError(
                "SOURCE_ANALYSIS_CHILD_FAILED",
                finished.last_error if finished is not None and finished.last_error else f"{child.task_name}失败",
                status_code=409,
            )


def _episode_ids(db: Session, project_id: str) -> list[str]:
    return list(
        db.scalars(
            select(Episode.id)
            .where(Episode.project_id == project_id)
            .order_by(Episode.episode_order.asc(), Episode.created_at.asc())
        ).all()
    )


def _execute_pipeline(context: TaskExecutionContext, task: TaskWorkerRead) -> None:
    with context.session_factory() as db:
        source = _current_artifact(db, task.project_id, ArtifactType.SOURCE_VIDEO)
        if source is None or source.id not in task.input_artifact_ids_json:
            raise AppError("STALE_ARTIFACT_INPUT", "原片已变化，请重新开始解析", status_code=409)
        episode_ids = _episode_ids(db, task.project_id)
    if not episode_ids:
        raise AppError("SOURCE_VIDEO_REQUIRED", "没有可解析的原片 Episode", status_code=409)

    total_episodes = len(episode_ids)
    for index, episode_id in enumerate(episode_ids, 1):
        context.checkpoint(
            {"stage": "shot_boundary", "stage_label": f"正在建立镜头结构（{index}/{total_episodes}）"},
            progress_percent=2 + int((index - 1) / total_episodes * 18),
        )
        with context.session_factory() as db:
            current = get_episode_shot_boundary(db, task.project_id, episode_id)
            if _status_value(current.status) != "CURRENT":
                child = create_shot_boundary_task(
                    db,
                    project_id=task.project_id,
                    episode_id=episode_id,
                    idempotency_key=_child_idempotency_key(task.id, task.attempt, "p5", episode_id),
                )
            else:
                child = None
        if child is not None:
            _ensure_child_succeeded(context, child=child, runner=run_p5_shot_boundary_task)

    for index, episode_id in enumerate(episode_ids, 1):
        context.checkpoint(
            {"stage": "source_evidence", "stage_label": f"正在识别对白和画面文字（{index}/{total_episodes}）"},
            progress_percent=22 + int((index - 1) / total_episodes * 23),
        )
        with context.session_factory() as db:
            current = get_episode_source_evidence(db, task.project_id, episode_id)
            if _status_value(current.status) != "CURRENT":
                child = create_source_evidence_task(
                    db,
                    project_id=task.project_id,
                    episode_id=episode_id,
                    idempotency_key=_child_idempotency_key(task.id, task.attempt, "p6", episode_id),
                )
            else:
                child = None
        if child is not None:
            _ensure_child_succeeded(context, child=child, runner=run_p6_source_evidence_task)

    context.checkpoint(
        {"stage": "episode_understanding", "stage_label": "正在理解整集剧情和人物关系"},
        progress_percent=48,
    )
    with context.session_factory() as db:
        current_bible = get_source_bible(db, task.project_id)
        if _status_value(current_bible.status) != "CURRENT":
            child = create_source_bible_task(
                db,
                project_id=task.project_id,
                idempotency_key=_child_idempotency_key(task.id, task.attempt, "p7"),
            )
        else:
            child = None
    if child is not None:
        _ensure_child_succeeded(context, child=child, runner=run_p7_source_bible_task)

    context.checkpoint(
        {"stage": "shot_breakdown", "stage_label": "正在整理逐镜动作和镜头语言"},
        progress_percent=68,
    )
    with context.session_factory() as db:
        current_breakdown = get_shot_breakdown(db, task.project_id)
        if _status_value(current_breakdown.status) != "CURRENT":
            child = create_shot_breakdown_task(
                db,
                project_id=task.project_id,
                idempotency_key=_child_idempotency_key(task.id, task.attempt, "p8"),
            )
        else:
            child = None
    if child is not None:
        _ensure_child_succeeded(context, child=child, runner=run_p8_shot_breakdown_task)

    context.checkpoint(
        {"stage": "source_resolution", "stage_label": "正在统一人物、说话人、场景和道具"},
        progress_percent=84,
    )
    with context.session_factory() as db:
        current_resolution = get_source_resolution(db, task.project_id)
        resolution_ready = all(
            _status_value(section.status) == "CURRENT"
            for section in (
                current_resolution.characters,
                current_resolution.speakers,
                current_resolution.scenes,
                current_resolution.props,
            )
        )
        if not resolution_ready:
            child = create_source_resolution_task(
                db,
                project_id=task.project_id,
                idempotency_key=_child_idempotency_key(task.id, task.attempt, "p9"),
            )
        else:
            child = None
    if child is not None:
        _ensure_child_succeeded(context, child=child, runner=run_p9_source_resolution_task)

    context.checkpoint(
        {"stage": "publish", "stage_label": "正在整理最终剧本和分镜结果"},
        progress_percent=96,
    )
    with context.session_factory() as db:
        snapshot = finalize_source_video_snapshot(db, task.project_id)
        if _status_value(snapshot.status) != "CURRENT":
            raise AppError("SOURCE_ANALYSIS_PUBLICATION_FAILED", "原片结果未能形成当前正式版本", status_code=409)


def run_source_analysis_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"source-analysis-{uuid4()}"
    with session_factory() as db:
        claimed = _claim_pipeline_task(db, task_id, worker_id=worker_id)
        if claimed is None:
            return
        task_snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(
        session_factory=session_factory,
        task_id=task_snapshot.id,
        worker_id=worker_id,
    )
    try:
        _execute_pipeline(context, task_snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        with session_factory() as db:
            current = db.get(Task, task_snapshot.id)
            if current is not None and current.status == TaskStatus.RUNNING and current.worker_id == worker_id:
                mark_task_failed(
                    db,
                    task_snapshot.id,
                    worker_id=worker_id,
                    safe_error=f"原片解析失败：{exc.message}",
                )
        return
    except Exception as exc:
        with session_factory() as db:
            current = db.get(Task, task_snapshot.id)
            if current is not None and current.status == TaskStatus.RUNNING and current.worker_id == worker_id:
                mark_task_failed(
                    db,
                    task_snapshot.id,
                    worker_id=worker_id,
                    safe_error=f"原片解析失败（{type(exc).__name__}）",
                )
        return
    with session_factory() as db:
        current = db.get(Task, task_snapshot.id)
        if current is not None and current.status == TaskStatus.RUNNING and current.worker_id == worker_id:
            mark_task_succeeded(db, task_snapshot.id, worker_id=worker_id)


# Compatibility shim for callers that historically imported the deterministic
# Source Script composer from this orchestration module. The canonical composer
# lives in script_service; keeping this lazy import avoids a circular import.
def compose_source_script(db: Session, project_id: str) -> SourceScriptRead:
    from app.source_analysis.script_service import get_source_script as compose

    return compose(db, project_id)


get_source_script = compose_source_script
