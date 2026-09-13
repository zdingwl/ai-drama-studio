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
from app.p14.audio_contract import P14_AUDIO_TASK_TYPE
from app.p14.models import ReplicaTargetAudioCandidate, ReplicaTimingPlanCandidate
from app.p14.schemas import CandidateReviewStatus, ReplicaTimingPlanContent
from app.p14.timing_service import P14_TIMING_TASK_TYPE
from app.p15.models import ReplicaStoryboardCandidate
from app.p15.schemas import P15CandidateReviewStatus, P15ReviewCommand
from app.p15.service import accept_storyboard_candidate, create_storyboard_task, run_storyboard_task
from app.p16.models import ReplicaGenerationSelectionCandidate
from app.p16.schemas import SelectionReviewStatus
from app.p16.service import create_generation_task, run_generation_task
from app.p17.models import ReplicaPostCandidate
from app.p17.runtime import P17_TASK_TYPE, create_post_task, run_post_task
from app.p17.schemas import PostReviewStatus
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.replica_product.schemas import (
    ReplicaProductAction,
    ReplicaProductPendingRead,
    ReplicaProductStepRead,
    ReplicaProductStepStatus,
    ReplicaProductWorkflowRead,
)
from app.skills.models import ArtifactType
from app.target_assets.models import ReplicaTargetAssetsCandidate
from app.target_assets.service import create_target_assets_task, run_target_assets_task
from app.target_bible.service import create_replica_target_bible_task, run_replica_target_bible_task
from app.target_script.service import create_target_script_task, run_target_script_task
from app.target_script.timing_rewrite import P12_TIMING_REWRITE_TASK_TYPE
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    checkpoint_task,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    resume_task,
    retry_task,
    task_to_read,
)


REPLICA_ADAPTATION_TASK_TYPE = "REPLICA_PRODUCT_ADAPTATION"
REPLICA_GENERATION_TASK_TYPE = "REPLICA_PRODUCT_GENERATION"


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _assert_replica(project) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError("REPLICA_PRODUCT_ONLY", "三步式复刻工作台当前只用于复刻短剧", status_code=422)


def _current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    rows = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == artifact_type.value,
                ArtifactNode.validity == ArtifactValidity.CURRENT,
                ArtifactNode.is_current.is_(True),
            )
        ).all()
    )
    if len(rows) > 1:
        raise AppError("REPLICA_PRODUCT_CURRENT_AMBIGUOUS", f"{artifact_type.value} 存在多个当前正式结果", status_code=409)
    return rows[0] if rows else None


def _pending(db: Session, model, project_id: str, review_status: str):
    return db.scalar(
        select(model)
        .where(model.project_id == project_id, model.review_status == review_status)
        .order_by(model.created_at.desc(), model.id.desc())
        .limit(1)
    )


def _latest_task(db: Session, project_id: str, task_types: tuple[str, ...], statuses: tuple[TaskStatus, ...] | None = None) -> Task | None:
    query = select(Task).where(Task.project_id == project_id, Task.task_type.in_(task_types))
    if statuses is not None:
        query = query.where(Task.status.in_(statuses))
    return db.scalar(query.order_by(Task.created_at.desc(), Task.id.desc()).limit(1))


def _node_signature(node: ArtifactNode) -> list[object]:
    return [node.id, node.revision, node.input_fingerprint]


def _claim(db: Session, task_id: str, task_type: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != task_type or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.task_type == task_type, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
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


def _checkpoint(factory: sessionmaker[Session], task_id: str, worker_id: str, progress: int, stage: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise AppError("TASK_NOT_FOUND", "产品流程任务不存在", status_code=404)
        data = dict(task.checkpoint_json or {})
        data.update({"stage": stage})
        checkpoint_task(db, task_id, checkpoint=data, progress_percent=progress, worker_id=worker_id)


def _ensure_child_succeeded(
    factory: sessionmaker[Session],
    *,
    parent: TaskWorkerRead,
    stage: str,
    creator: Callable[[Session, str], Task],
    runner: Callable[[sessionmaker[Session], str], None],
) -> None:
    key = f"product-{parent.id}-a{parent.attempt}-{stage}"[:128]
    with factory() as db:
        child = creator(db, key)
        if child.status == TaskStatus.FAILED and child.attempt < child.max_attempts:
            child = retry_task(db, child.project_id, child.id)
        elif child.status == TaskStatus.INTERRUPTED and child.attempt < child.max_attempts:
            child = resume_task(db, child.project_id, child.id)
        child_id = child.id
        child_status = child.status
    if child_status == TaskStatus.QUEUED:
        runner(factory, child_id)
    with factory() as db:
        finished = db.get(Task, child_id)
        if finished is None:
            raise AppError("REPLICA_PRODUCT_CHILD_MISSING", "产品流程内部任务不存在", status_code=500)
        if finished.status != TaskStatus.SUCCEEDED:
            raise AppError(
                "REPLICA_PRODUCT_CHILD_FAILED",
                "这一步没有完成，请重试；详细原因可在调试模式查看。",
                status_code=409,
                details={"child_task_id": finished.id, "child_status": finished.status.value},
            )


def _adaptation_inputs(db: Session, project_id: str) -> tuple[object, ArtifactNode]:
    project = get_project(db, project_id)
    _assert_replica(project)
    snapshot = _current(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if snapshot is None:
        raise AppError("REPLICA_PRODUCT_SOURCE_REQUIRED", "请先完成原片解析", status_code=409)
    return project, snapshot


def create_adaptation_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project, snapshot = _adaptation_inputs(db, project_id)
    latest_asset_sequence = int(
        db.scalar(
            select(func.max(ReplicaTargetAssetsCandidate.generation_sequence)).where(
                ReplicaTargetAssetsCandidate.project_id == project_id
            )
        )
        or 0
    )
    fingerprint = _sha(
        {
            "task": REPLICA_ADAPTATION_TASK_TYPE,
            "source_snapshot": _node_signature(snapshot),
            "target_language": project.target_language,
            "target_region": project.target_region,
            "scene_strategy": project.scene_strategy.value,
            "visual_style": project.visual_style,
            "latest_target_assets_candidate_sequence": latest_asset_sequence,
        }
    )
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=REPLICA_ADAPTATION_TASK_TYPE,
            task_name="生成改编方案",
            input_fingerprint=fingerprint,
            input_artifact_ids=[snapshot.id],
            max_attempts=3,
        ),
    )
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts:
        task = retry_task(db, project_id, task.id)
    elif task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts:
        task = resume_task(db, project_id, task.id)
    if not task.checkpoint_json:
        task.checkpoint_json = {
            "source_snapshot_artifact_id": snapshot.id,
            "target_assets_candidate_sequence": latest_asset_sequence,
            "stage": "准备改编方案",
        }
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def _assert_adaptation_parent(db: Session, task: TaskWorkerRead) -> None:
    project, snapshot = _adaptation_inputs(db, task.project_id)
    candidate_sequence = int((task.checkpoint_json or {}).get("target_assets_candidate_sequence") or 0)
    expected = _sha(
        {
            "task": REPLICA_ADAPTATION_TASK_TYPE,
            "source_snapshot": _node_signature(snapshot),
            "target_language": project.target_language,
            "target_region": project.target_region,
            "scene_strategy": project.scene_strategy.value,
            "visual_style": project.visual_style,
            "latest_target_assets_candidate_sequence": candidate_sequence,
        }
    )
    if task.input_artifact_ids_json != [snapshot.id] or task.input_fingerprint != expected:
        raise AppError("STALE_ARTIFACT_INPUT", "原片或改编目标已变化，请重新生成改编方案", status_code=409)


def run_adaptation_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"replica-product-adaptation-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, REPLICA_ADAPTATION_TASK_TYPE, worker_id)
        if claimed is None:
            return
        parent = TaskWorkerRead.model_validate(claimed)
    try:
        with factory() as db:
            _assert_adaptation_parent(db, parent)
        _checkpoint(factory, parent.id, worker_id, 10, "正在建立改编设定")
        with factory() as db:
            bible = _current(db, parent.project_id, ArtifactType.TARGET_BIBLE)
        if bible is None:
            _ensure_child_succeeded(
                factory,
                parent=parent,
                stage="target-bible",
                creator=lambda db, key: create_replica_target_bible_task(db, project_id=parent.project_id, idempotency_key=key),
                runner=run_replica_target_bible_task,
            )
        _checkpoint(factory, parent.id, worker_id, 42, "正在改写目标对白")
        with factory() as db:
            script = _current(db, parent.project_id, ArtifactType.TARGET_SCRIPT)
        if script is None:
            _ensure_child_succeeded(
                factory,
                parent=parent,
                stage="target-script",
                creator=lambda db, key: create_target_script_task(db, project_id=parent.project_id, idempotency_key=key),
                runner=run_target_script_task,
            )
        _checkpoint(factory, parent.id, worker_id, 72, "正在准备人物和场景视觉方案")
        with factory() as db:
            assets = _current(db, parent.project_id, ArtifactType.TARGET_ASSETS)
            pending = _pending(db, ReplicaTargetAssetsCandidate, parent.project_id, "NEEDS_REVIEW")
            previous_candidate_exists = db.scalar(
                select(ReplicaTargetAssetsCandidate.id)
                .where(ReplicaTargetAssetsCandidate.project_id == parent.project_id)
                .limit(1)
            ) is not None
        if assets is None and pending is None:
            _ensure_child_succeeded(
                factory,
                parent=parent,
                stage="target-assets",
                creator=lambda db, key: create_target_assets_task(
                    db,
                    project_id=parent.project_id,
                    idempotency_key=key,
                    regenerate=previous_candidate_exists,
                ),
                runner=run_target_assets_task,
            )
        _checkpoint(factory, parent.id, worker_id, 96, "改编方案已生成，等待你确认")
        with factory() as db:
            current = db.get(Task, parent.id)
            if current is not None and current.status == TaskStatus.RUNNING:
                mark_task_succeeded(db, parent.id, worker_id=worker_id)
    except Exception as exc:
        message = f"生成改编方案失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"生成改编方案失败（{type(exc).__name__}）"
        with factory() as db:
            current = db.get(Task, parent.id)
            if current is not None and current.status == TaskStatus.RUNNING and current.worker_id == worker_id:
                mark_task_failed(db, parent.id, safe_error=message, worker_id=worker_id)


def _production_nodes(db: Session, project_id: str) -> tuple[object, list[ArtifactNode]]:
    project = get_project(db, project_id)
    _assert_replica(project)
    required = (
        ArtifactType.SOURCE_VIDEO_SNAPSHOT,
        ArtifactType.TARGET_BIBLE,
        ArtifactType.TARGET_SCRIPT,
        ArtifactType.TARGET_ASSETS,
        ArtifactType.TARGET_AUDIO,
        ArtifactType.TIMING_PLAN,
    )
    nodes: list[ArtifactNode] = []
    for artifact_type in required:
        node = _current(db, project_id, artifact_type)
        if node is None:
            raise AppError("REPLICA_PRODUCT_PRODUCTION_INPUT_REQUIRED", "请先完成改编设定、配音和对白时长检查", status_code=409)
        nodes.append(node)
    return project, nodes


def _production_fingerprint(nodes: list[ArtifactNode]) -> str:
    return _sha({"task": REPLICA_GENERATION_TASK_TYPE, "inputs": [_node_signature(node) for node in nodes]})


def create_generation_pipeline_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    _project, nodes = _production_nodes(db, project_id)
    latest_video_sequence = int(
        db.scalar(
            select(func.max(ReplicaGenerationSelectionCandidate.generation_sequence)).where(
                ReplicaGenerationSelectionCandidate.project_id == project_id
            )
        )
        or 0
    )
    fingerprint = _sha({"base": _production_fingerprint(nodes), "latest_video_candidate_sequence": latest_video_sequence})
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=REPLICA_GENERATION_TASK_TYPE,
            task_name="生成视频",
            input_fingerprint=fingerprint,
            input_artifact_ids=[node.id for node in nodes],
            max_attempts=3,
        ),
    )
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts:
        task = retry_task(db, project_id, task.id)
    elif task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts:
        task = resume_task(db, project_id, task.id)
    if not task.checkpoint_json:
        task.checkpoint_json = {"stage": "准备视频生成", "video_candidate_sequence": latest_video_sequence}
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def _assert_generation_parent(db: Session, task: TaskWorkerRead) -> list[ArtifactNode]:
    _project, nodes = _production_nodes(db, task.project_id)
    sequence = int((task.checkpoint_json or {}).get("video_candidate_sequence") or 0)
    expected = _sha({"base": _production_fingerprint(nodes), "latest_video_candidate_sequence": sequence})
    if task.input_artifact_ids_json != [node.id for node in nodes] or task.input_fingerprint != expected:
        raise AppError("STALE_ARTIFACT_INPUT", "改编设定、配音或时长结果已变化，请重新生成视频", status_code=409)
    return nodes


def _publish_p15_candidate(db: Session, project_id: str) -> None:
    candidate = _pending(db, ReplicaStoryboardCandidate, project_id, P15CandidateReviewStatus.NEEDS_REVIEW.value)
    if candidate is None:
        raise AppError("REPLICA_PRODUCT_STORYBOARD_CANDIDATE_MISSING", "视频分镜编译完成但未找到可发布结果", status_code=500)
    command = P15ReviewCommand(
        expected_source_snapshot_artifact_id=candidate.source_snapshot_artifact_id,
        expected_target_bible_artifact_id=candidate.target_bible_artifact_id,
        expected_target_script_artifact_id=candidate.target_script_artifact_id,
        expected_target_assets_artifact_id=candidate.target_assets_artifact_id,
        expected_target_audio_artifact_id=candidate.target_audio_artifact_id,
        expected_timing_plan_artifact_id=candidate.timing_plan_artifact_id,
        expected_generation_sequence=candidate.generation_sequence,
        reason="用户显式点击“生成视频”，授权系统发布确定性 Replica 分镜与生成分段。",
    )
    accept_storyboard_candidate(db, project_id=project_id, candidate_id=candidate.id, command=command)


def run_generation_pipeline_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"replica-product-generation-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, REPLICA_GENERATION_TASK_TYPE, worker_id)
        if claimed is None:
            return
        parent = TaskWorkerRead.model_validate(claimed)
    try:
        with factory() as db:
            _assert_generation_parent(db, parent)
        _checkpoint(factory, parent.id, worker_id, 8, "正在整理正式分镜")
        with factory() as db:
            storyboard = _current(db, parent.project_id, ArtifactType.TARGET_STORYBOARD)
            segments = _current(db, parent.project_id, ArtifactType.GENERATION_SEGMENTS)
        if storyboard is None or segments is None:
            _ensure_child_succeeded(
                factory,
                parent=parent,
                stage="storyboard",
                creator=lambda db, key: create_storyboard_task(db, project_id=parent.project_id, idempotency_key=key),
                runner=run_storyboard_task,
            )
            with factory() as db:
                _publish_p15_candidate(db, parent.project_id)
        _checkpoint(factory, parent.id, worker_id, 24, "正在生成视频画面")
        with factory() as db:
            existing_selection = _current(db, parent.project_id, ArtifactType.GENERATION_SELECTION)
            pending_video = _pending(db, ReplicaGenerationSelectionCandidate, parent.project_id, SelectionReviewStatus.NEEDS_REVIEW.value)
        if existing_selection is None and pending_video is None:
            _ensure_child_succeeded(
                factory,
                parent=parent,
                stage="video-generation",
                creator=lambda db, key: create_generation_task(db, project_id=parent.project_id, idempotency_key=key),
                runner=run_generation_task,
            )
        _checkpoint(factory, parent.id, worker_id, 96, "视频已生成，等待你查看画面")
        with factory() as db:
            current = db.get(Task, parent.id)
            if current is not None and current.status == TaskStatus.RUNNING:
                mark_task_succeeded(db, parent.id, worker_id=worker_id)
    except Exception as exc:
        message = f"生成视频失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"生成视频失败（{type(exc).__name__}）"
        with factory() as db:
            current = db.get(Task, parent.id)
            if current is not None and current.status == TaskStatus.RUNNING and current.worker_id == worker_id:
                mark_task_failed(db, parent.id, safe_error=message, worker_id=worker_id)


def create_final_output_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    _assert_replica(project)
    return create_post_task(db, project_id=project_id, idempotency_key=idempotency_key)


def run_final_output_task(factory: sessionmaker[Session], task_id: str) -> None:
    run_post_task(factory, task_id)


def _timing_overflow_count(row: ReplicaTimingPlanCandidate | None) -> int:
    if row is None:
        return 0
    try:
        content = ReplicaTimingPlanContent.model_validate(row.content_json)
    except Exception:
        return 0
    return sum(1 for item in content.items if item.fit_status.value == "OVERFLOW")


def _product_task_copy(task: Task) -> tuple[str, str]:
    if task.task_type == REPLICA_ADAPTATION_TASK_TYPE:
        return "生成改编方案", str((task.checkpoint_json or {}).get("stage") or "正在生成改编方案。")
    if task.task_type == REPLICA_GENERATION_TASK_TYPE:
        return "生成视频", str((task.checkpoint_json or {}).get("stage") or "正在生成视频。")
    if task.task_type == P14_AUDIO_TASK_TYPE:
        return "生成配音", "正在生成并保存目标对白音频。"
    if task.task_type == P14_TIMING_TASK_TYPE:
        return "检查对白节奏", "正在检查每句对白是否能放进原片节奏。"
    if task.task_type == P12_TIMING_REWRITE_TASK_TYPE:
        return "调整过长对白", "正在缩短明显过长的对白。"
    if task.task_type == P17_TASK_TYPE:
        return "制作最终成片", "正在完成口型、剪辑、正式配音和字幕。"
    return "正在处理", "系统正在处理当前步骤。"


def _product_failure_copy(task: Task | None) -> str | None:
    if task is None or task.status != TaskStatus.FAILED:
        return None
    if task.task_type == REPLICA_ADAPTATION_TASK_TYPE:
        return "改编方案没有生成完成，请重试。"
    if task.task_type == REPLICA_GENERATION_TASK_TYPE:
        return "视频没有生成完成，请重试。"
    if task.task_type == P14_AUDIO_TASK_TYPE:
        return "配音没有生成完成，请重试或重新选择声线。"
    if task.task_type == P14_TIMING_TASK_TYPE:
        return "对白节奏检查没有完成，请重试。"
    if task.task_type == P12_TIMING_REWRITE_TASK_TYPE:
        return "对白调整没有完成，请重试。"
    if task.task_type == P17_TASK_TYPE:
        return "最终成片没有制作完成，请重试。"
    return "当前操作没有完成，请重试。"


def get_replica_product_workflow(db: Session, project_id: str) -> ReplicaProductWorkflowRead:
    project = get_project(db, project_id)
    _assert_replica(project)

    source_video = _current(db, project_id, ArtifactType.SOURCE_VIDEO)
    snapshot = _current(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    bible = _current(db, project_id, ArtifactType.TARGET_BIBLE)
    script = _current(db, project_id, ArtifactType.TARGET_SCRIPT)
    assets = _current(db, project_id, ArtifactType.TARGET_ASSETS)
    audio = _current(db, project_id, ArtifactType.TARGET_AUDIO)
    timing = _current(db, project_id, ArtifactType.TIMING_PLAN)
    selection = _current(db, project_id, ArtifactType.GENERATION_SELECTION)
    final = _current(db, project_id, ArtifactType.FINAL_OUTPUT)

    asset_candidate = _pending(db, ReplicaTargetAssetsCandidate, project_id, "NEEDS_REVIEW")
    audio_candidate = _pending(db, ReplicaTargetAudioCandidate, project_id, CandidateReviewStatus.NEEDS_REVIEW.value)
    timing_candidate = _pending(db, ReplicaTimingPlanCandidate, project_id, CandidateReviewStatus.NEEDS_REVIEW.value)
    video_candidate = _pending(db, ReplicaGenerationSelectionCandidate, project_id, SelectionReviewStatus.NEEDS_REVIEW.value)
    final_candidate = _pending(db, ReplicaPostCandidate, project_id, PostReviewStatus.NEEDS_REVIEW.value)

    active = _latest_task(
        db,
        project_id,
        (
            REPLICA_ADAPTATION_TASK_TYPE,
            REPLICA_GENERATION_TASK_TYPE,
            P14_AUDIO_TASK_TYPE,
            P14_TIMING_TASK_TYPE,
            P12_TIMING_REWRITE_TASK_TYPE,
            P17_TASK_TYPE,
        ),
        (TaskStatus.QUEUED, TaskStatus.RUNNING),
    )
    latest_product = _latest_task(
        db,
        project_id,
        (
            REPLICA_ADAPTATION_TASK_TYPE,
            REPLICA_GENERATION_TASK_TYPE,
            P14_AUDIO_TASK_TYPE,
            P14_TIMING_TASK_TYPE,
            P12_TIMING_REWRITE_TASK_TYPE,
            P17_TASK_TYPE,
        ),
    )
    last_error = _product_failure_copy(latest_product)

    if source_video is None:
        action = ReplicaProductAction.UPLOAD_SOURCE
        headline, description, progress = "先上传原片", "上传完整原片后，系统会自动完成镜头、对白和剧情理解。", 0
    elif snapshot is None:
        action = ReplicaProductAction.ANALYZE_SOURCE
        headline, description, progress = "解析原片", "一次解析即可得到原片剧本、分镜、人物、场景和道具。", 10
    elif final is not None:
        action = ReplicaProductAction.COMPLETE
        headline, description, progress = "成片已完成", "最终成片已经确认，可以直接播放和使用。", 100
    elif asset_candidate is not None:
        action = ReplicaProductAction.REVIEW_ADAPTATION
        headline, description, progress = "确认改编方案", "人物、场景和视觉方向已经准备好，只需要确认整体改编方向。", 42
    elif bible is None or script is None or assets is None:
        action = ReplicaProductAction.GENERATE_ADAPTATION
        headline, description, progress = "生成改编方案", "系统会自动完成目标设定、对白改写和视觉方案。", 30
    elif audio_candidate is not None:
        action = ReplicaProductAction.REVIEW_AUDIO
        headline, description, progress = "试听并确认配音", "听一下主要角色和对白表现，满意后继续检查节奏。", 56
    elif audio is None:
        action = ReplicaProductAction.CAST_VOICES
        headline, description, progress = "给角色选声线", "为主要角色选一个合适的声音，系统会生成全部目标对白。", 50
    elif timing_candidate is not None and _timing_overflow_count(timing_candidate) > 0:
        action = ReplicaProductAction.FIX_DIALOGUE_DURATION
        headline, description, progress = "调整少量过长对白", "有几句对白放不进原片节奏，只处理这些异常句即可。", 64
    elif timing is None:
        action = ReplicaProductAction.REVIEW_AUDIO
        headline, description, progress = "检查对白节奏", "配音已经确认，系统将检查每句对白是否能放进原片节奏。", 62
    elif video_candidate is not None:
        action = ReplicaProductAction.REVIEW_VIDEO
        headline, description, progress = "检查生成视频", "视频已经生成。只需要看人物、动作、场景和连续性是否满意。", 82
    elif selection is None:
        action = ReplicaProductAction.GENERATE_VIDEO
        headline, description, progress = "生成视频", "系统会自动整理镜头、分段生成并检查生成结果。", 70
    elif final_candidate is not None:
        action = ReplicaProductAction.REVIEW_FINAL
        headline, description, progress = "检查最终成片", "后期、正式配音和字幕已经合成，请播放最终成片确认效果。", 94
    else:
        action = ReplicaProductAction.BUILD_FINAL
        headline, description, progress = "制作最终成片", "系统会完成必要口型、剪辑、正式配音和字幕。", 88

    if active is not None:
        headline, description = _product_task_copy(active)
        progress = max(progress, active.progress_percent)

    source_status = ReplicaProductStepStatus.COMPLETE if snapshot is not None else ReplicaProductStepStatus.READY
    if source_video is None:
        source_status = ReplicaProductStepStatus.NEEDS_ACTION
    adaptation_complete = timing is not None
    adaptation_needs_action = action in {
        ReplicaProductAction.REVIEW_ADAPTATION,
        ReplicaProductAction.CAST_VOICES,
        ReplicaProductAction.REVIEW_AUDIO,
        ReplicaProductAction.FIX_DIALOGUE_DURATION,
    }
    adaptation_status = ReplicaProductStepStatus.COMPLETE if adaptation_complete else (
        ReplicaProductStepStatus.NEEDS_ACTION if adaptation_needs_action else (ReplicaProductStepStatus.READY if snapshot is not None else ReplicaProductStepStatus.WAITING)
    )
    production_status = ReplicaProductStepStatus.COMPLETE if final is not None else (
        ReplicaProductStepStatus.NEEDS_ACTION if action in {ReplicaProductAction.REVIEW_VIDEO, ReplicaProductAction.REVIEW_FINAL} else (
            ReplicaProductStepStatus.READY if timing is not None else ReplicaProductStepStatus.WAITING
        )
    )
    if active is not None:
        if active.task_type in {REPLICA_ADAPTATION_TASK_TYPE, P14_AUDIO_TASK_TYPE, P14_TIMING_TASK_TYPE, P12_TIMING_REWRITE_TASK_TYPE}:
            adaptation_status = ReplicaProductStepStatus.WORKING
        elif active.task_type in {REPLICA_GENERATION_TASK_TYPE, P17_TASK_TYPE}:
            production_status = ReplicaProductStepStatus.WORKING

    return ReplicaProductWorkflowRead(
        project_id=project_id,
        next_action=action,
        headline=headline,
        description=description,
        progress_percent=min(progress, 100),
        active_task=task_to_read(active) if active is not None else None,
        last_error=last_error,
        steps=[
            ReplicaProductStepRead(key="source", title="原片", status=source_status, summary="上传、解析并查看原片剧本与分镜"),
            ReplicaProductStepRead(key="adaptation", title="改编设定", status=adaptation_status, summary="目标人物、对白、视觉与配音"),
            ReplicaProductStepRead(key="production", title="生成成片", status=production_status, summary="生成视频、检查画面并完成后期"),
        ],
        pending=ReplicaProductPendingRead(
            target_assets_candidate_id=asset_candidate.id if asset_candidate is not None else None,
            target_audio_candidate_id=audio_candidate.id if audio_candidate is not None else None,
            timing_candidate_id=timing_candidate.id if timing_candidate is not None else None,
            video_candidate_id=video_candidate.id if video_candidate is not None else None,
            final_candidate_id=final_candidate.id if final_candidate is not None else None,
            timing_overflow_count=_timing_overflow_count(timing_candidate),
        ),
    )

