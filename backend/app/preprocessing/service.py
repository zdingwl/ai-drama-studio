import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact_relation
from app.core.artifacts import artifact_root
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import VIDEO_PROJECT_TYPES
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.sources.media import decode_full_video, decode_preflight, probe_video, run_ffmpeg
from app.sources.models import Episode, SourceAsset
from app.sources.storage import resolve_source_asset_path
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    publish_validated_task_artifact,
)
from app.workflow.worker import TaskExecutionContext
from app.preprocessing.detector import DETECTOR_PROFILE, DETECTOR_PROFILE_VERSION, ShotRange, detect_shot_ranges
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.preprocessing.schemas import EpisodeShotBoundaryRead, ShotAnchorRead, ShotBoundaryResultStatus


P5_TASK_TYPE = "P5_SHOT_BOUNDARY"


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def is_p5_shot_boundary_task(task: Task) -> bool:
    return task.task_type == P5_TASK_TYPE


def _episode_with_asset(db: Session, project_id: str, episode_id: str) -> tuple[Episode, SourceAsset]:
    row = db.execute(
        select(Episode, SourceAsset)
        .join(SourceAsset, Episode.source_asset_id == SourceAsset.id)
        .where(Episode.id == episode_id, Episode.project_id == project_id)
    ).one_or_none()
    if row is None:
        raise AppError("EPISODE_NOT_FOUND", "Episode 不存在", status_code=404)
    return row


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )


def _current_source_video_artifact(db: Session, project_id: str) -> ArtifactNode:
    artifact = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    if artifact is None:
        raise AppError("SOURCE_VIDEO_REQUIRED", "请先上传原片视频", status_code=409)
    return artifact


def _assert_task_source_is_current(db: Session, task: TaskWorkerRead) -> ArtifactNode:
    source = _current_source_video_artifact(db, task.project_id)
    if source.id not in task.input_artifact_ids_json:
        raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，请重新开始镜头处理", status_code=409)
    return source


def create_shot_boundary_task(
    db: Session,
    *,
    project_id: str,
    episode_id: str,
    idempotency_key: str,
) -> Task:
    project = get_project(db, project_id)
    if project.project_type not in VIDEO_PROJECT_TYPES:
        raise AppError("SHOT_BOUNDARY_NOT_ALLOWED", "当前项目类型不处理原片镜头", status_code=422)
    episode, asset = _episode_with_asset(db, project_id, episode_id)
    source_artifact = _current_source_video_artifact(db, project_id)
    fingerprint = _canonical_sha256(
        {
            "task": P5_TASK_TYPE,
            "detector_profile": DETECTOR_PROFILE_VERSION,
            "source_video_artifact_id": source_artifact.id,
            "source_video_fingerprint": source_artifact.input_fingerprint,
            "episode_id": episode.id,
            "episode_order": episode.episode_order,
            "source_asset_id": asset.id,
            "source_sha256": asset.sha256,
            "duration_us": episode.duration_us,
        }
    )
    payload = TaskCommandCreate(
        task_type=P5_TASK_TYPE,
        task_name=f"第 {episode.episode_order} 集：镜头技术预处理",
        input_fingerprint=fingerprint,
        input_artifact_ids=[source_artifact.id],
        episode_id=episode.id,
        max_attempts=3,
    )
    return create_task_from_command(
        db,
        project_id=project_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


def _generated_set_root(project_id: str, set_id: str) -> Path:
    root = artifact_root() / "projects" / project_id / "source" / "shot-boundary" / set_id
    root.mkdir(parents=True, exist_ok=False)
    return root


def _relative_artifact_path(path: Path) -> str:
    return path.resolve().relative_to(artifact_root().resolve()).as_posix()


def _resolve_generated_path(relative_path: str) -> Path:
    root = artifact_root().resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError("SHOT_MEDIA_PATH_INVALID", "镜头媒体路径无效", status_code=422) from exc
    if not candidate.is_file():
        raise AppError("SHOT_MEDIA_NOT_FOUND", "镜头媒体文件不存在", status_code=404)
    return candidate


def _seconds(us: int) -> str:
    return f"{us / 1_000_000:.6f}"


def _materialize_shot(source_path: Path, output_root: Path, shot_number: int, shot: ShotRange) -> tuple[str, str]:
    thumbnail_path = output_root / f"shot_{shot_number:04d}.jpg"
    clip_path = output_root / f"shot_{shot_number:04d}.mp4"
    midpoint_us = shot.start_us + max(1, shot.duration_us // 2)

    run_ffmpeg(
        [
            "-v",
            "error",
            "-ss",
            _seconds(midpoint_us),
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-2:force_original_aspect_ratio=decrease",
            "-q:v",
            "3",
            "-y",
            str(thumbnail_path),
        ],
        timeout_seconds=180,
        code="SHOT_THUMBNAIL_FAILED",
        message="镜头缩略图生成失败",
    )
    run_ffmpeg(
        [
            "-v",
            "error",
            "-ss",
            _seconds(shot.start_us),
            "-i",
            str(source_path),
            "-t",
            _seconds(shot.duration_us),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-avoid_negative_ts",
            "make_zero",
            "-y",
            str(clip_path),
        ],
        timeout_seconds=300,
        code="SHOT_REFERENCE_CLIP_FAILED",
        message="镜头参考片段生成失败",
    )
    decode_full_video(clip_path, timeout_seconds=300)
    return _relative_artifact_path(thumbnail_path), _relative_artifact_path(clip_path)


def _validate_ranges(ranges: list[ShotRange], *, duration_us: int) -> None:
    if not ranges or ranges[0].start_us != 0 or ranges[-1].end_us != duration_us:
        raise AppError("SHOT_BOUNDARY_COVERAGE_INVALID", "镜头边界没有完整覆盖视频", status_code=422)
    previous_end = 0
    for item in ranges:
        if item.start_us != previous_end or item.end_us <= item.start_us:
            raise AppError("SHOT_BOUNDARY_ORDER_INVALID", "镜头边界必须有序且不能重叠", status_code=422)
        previous_end = item.end_us


def _persist_boundary_set(
    db: Session,
    *,
    set_id: str,
    task: TaskWorkerRead,
    source_artifact_id: str,
    ranges: list[ShotRange],
    materialized: list[tuple[str, str]],
) -> ShotBoundarySet:
    if task.episode_id is None:
        raise AppError("TASK_EPISODE_SCOPE_INVALID", "镜头任务缺少 Episode", status_code=422)
    current_source = _current_source_video_artifact(db, task.project_id)
    if current_source.id != source_artifact_id:
        raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，请重新开始镜头处理", status_code=409)

    latest_revision = db.scalar(
        select(func.max(ShotBoundarySet.revision)).where(ShotBoundarySet.episode_id == task.episode_id)
    )
    db.execute(
        update(ShotBoundarySet)
        .where(
            ShotBoundarySet.episode_id == task.episode_id,
            ShotBoundarySet.is_current.is_(True),
        )
        .values(is_current=False)
    )
    boundary_set = ShotBoundarySet(
        id=set_id,
        project_id=task.project_id,
        episode_id=task.episode_id,
        source_video_artifact_id=source_artifact_id,
        task_id=task.id,
        revision=(latest_revision or 0) + 1,
        input_fingerprint=task.input_fingerprint,
        detector_profile_json=DETECTOR_PROFILE,
        is_current=True,
    )
    db.add(boundary_set)
    db.flush()
    for index, (shot, media_paths) in enumerate(zip(ranges, materialized), start=1):
        thumbnail_relative_path, reference_clip_relative_path = media_paths
        db.add(
            ShotAnchor(
                project_id=task.project_id,
                episode_id=task.episode_id,
                shot_boundary_set_id=boundary_set.id,
                shot_number=index,
                start_us=shot.start_us,
                end_us=shot.end_us,
                duration_us=shot.duration_us,
                thumbnail_relative_path=thumbnail_relative_path,
                reference_clip_relative_path=reference_clip_relative_path,
            )
        )
    db.commit()
    db.refresh(boundary_set)
    return boundary_set


def _execute_shot_boundary_task(context: TaskExecutionContext, task: TaskWorkerRead) -> ShotBoundarySet:
    if task.episode_id is None:
        raise AppError("TASK_EPISODE_SCOPE_INVALID", "镜头任务缺少 Episode", status_code=422)

    with context.session_factory() as db:
        source_artifact = _assert_task_source_is_current(db, task)
        episode, asset = _episode_with_asset(db, task.project_id, task.episode_id)
        source_path = resolve_source_asset_path(asset.relative_path)

    context.checkpoint({"stage": "media_preflight"}, progress_percent=5)
    probe = probe_video(source_path)
    decode_preflight(source_path)
    duration_us = min(episode.duration_us, probe.duration_us)
    if abs(episode.duration_us - probe.duration_us) > 250_000:
        raise AppError("SOURCE_TIMEBASE_CHANGED", "原片媒体时长与入库记录不一致", status_code=409)
    context.checkpoint({"stage": "shot_detection"}, progress_percent=12)

    last_progress = 12

    def on_detection_progress(ratio: float) -> None:
        nonlocal last_progress
        progress = 12 + int(max(0.0, min(1.0, ratio)) * 38)
        if progress <= last_progress:
            return
        last_progress = progress
        context.checkpoint(
            {"stage": "shot_detection", "scan_percent": int(ratio * 100)},
            progress_percent=progress,
        )

    ranges = detect_shot_ranges(source_path, duration_us=duration_us, on_progress=on_detection_progress)
    _validate_ranges(ranges, duration_us=duration_us)
    context.checkpoint({"stage": "materialize", "shot_count": len(ranges)}, progress_percent=52)

    set_id = str(uuid4())
    output_root = _generated_set_root(task.project_id, set_id)
    materialized: list[tuple[str, str]] = []
    try:
        for index, shot in enumerate(ranges, start=1):
            materialized.append(_materialize_shot(source_path, output_root, index, shot))
            progress = 52 + int(index / len(ranges) * 40)
            context.checkpoint(
                {
                    "stage": "materialize",
                    "shot_count": len(ranges),
                    "completed_shots": index,
                },
                progress_percent=min(progress, 92),
            )
        context.checkpoint({"stage": "validate_output", "shot_count": len(ranges)}, progress_percent=96)
        with context.session_factory() as db:
            current_source = _current_source_video_artifact(db, task.project_id)
            if current_source.id != source_artifact.id:
                raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，请重新开始镜头处理", status_code=409)
            boundary_set = _persist_boundary_set(
                db,
                set_id=set_id,
                task=task,
                source_artifact_id=source_artifact.id,
                ranges=ranges,
                materialized=materialized,
            )
        return boundary_set
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def _aggregate_artifact_payload(db: Session, project_id: str, source_artifact_id: str) -> list[dict]:
    rows = list(
        db.execute(
            select(ShotBoundarySet, Episode)
            .join(Episode, ShotBoundarySet.episode_id == Episode.id)
            .where(
                ShotBoundarySet.project_id == project_id,
                ShotBoundarySet.source_video_artifact_id == source_artifact_id,
                ShotBoundarySet.is_current.is_(True),
            )
            .order_by(Episode.episode_order.asc())
        ).all()
    )
    payload: list[dict] = []
    for boundary_set, episode in rows:
        shot_count = int(
            db.scalar(
                select(func.count(ShotAnchor.id)).where(ShotAnchor.shot_boundary_set_id == boundary_set.id)
            )
            or 0
        )
        payload.append(
            {
                "episode_id": episode.id,
                "episode_order": episode.episode_order,
                "shot_boundary_set_id": boundary_set.id,
                "set_revision": boundary_set.revision,
                "set_fingerprint": boundary_set.input_fingerprint,
                "shot_count": shot_count,
            }
        )
    return payload


def _publish_boundary_artifact(db: Session, *, task_id: str, boundary_set_id: str) -> ArtifactNode:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    boundary_set = db.get(ShotBoundarySet, boundary_set_id)
    if boundary_set is None or boundary_set.task_id != task.id:
        raise AppError("SHOT_BOUNDARY_SET_NOT_FOUND", "镜头结果不存在", status_code=404)

    source_artifact = _current_source_video_artifact(db, task.project_id)
    if boundary_set.source_video_artifact_id != source_artifact.id:
        raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，镜头结果不能发布", status_code=409)
    aggregate = _aggregate_artifact_payload(db, task.project_id, source_artifact.id)
    aggregate_fingerprint = _canonical_sha256(
        {
            "source_video_artifact_id": source_artifact.id,
            "source_video_fingerprint": source_artifact.input_fingerprint,
            "episodes": aggregate,
        }
    )
    project = get_project(db, task.project_id)
    artifact = publish_validated_task_artifact(
        db,
        task_id=task.id,
        validation_passed=True,
        artifact_type=ArtifactType.SHOT_ANCHORS,
        namespace=ArtifactNamespace.SOURCE,
        label=f"镜头时间锚点（{len(aggregate)} 集）",
        input_fingerprint=aggregate_fingerprint,
        skill_id=project.root_skill_id,
        skill_version=project.root_skill_version,
        metadata_json={
            "source_video_artifact_id": source_artifact.id,
            "episode_sets": aggregate,
            "detector_profile": DETECTOR_PROFILE_VERSION,
        },
    )
    create_artifact_relation(
        db,
        project_id=task.project_id,
        source_node_id=source_artifact.id,
        target_node_id=artifact.id,
        relation_type=ArtifactRelationType.DERIVED_FROM,
    )
    return artifact


def _discard_boundary_set(session_factory: sessionmaker[Session], boundary_set_id: str) -> None:
    relative_paths: list[str] = []
    with session_factory() as db:
        boundary_set = db.get(ShotBoundarySet, boundary_set_id)
        if boundary_set is None:
            return
        anchors = list(
            db.scalars(select(ShotAnchor).where(ShotAnchor.shot_boundary_set_id == boundary_set.id)).all()
        )
        for anchor in anchors:
            relative_paths.extend([anchor.thumbnail_relative_path, anchor.reference_clip_relative_path])
            db.delete(anchor)
        db.delete(boundary_set)
        db.commit()
    if relative_paths:
        root = artifact_root().resolve()
        first = (root / relative_paths[0]).resolve()
        try:
            first.relative_to(root)
        except ValueError:
            return
        shutil.rmtree(first.parent, ignore_errors=True)


def _claim_p5_task(db: Session, task_id: str, *, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if (
        task is None
        or task.task_type != P5_TASK_TYPE
        or task.status != TaskStatus.QUEUED
        or task.attempt >= task.max_attempts
    ):
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == P5_TASK_TYPE,
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


def _mark_output_failed(db: Session, task_id: str, *, safe_error: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    if task.status != TaskStatus.SUCCEEDED:
        raise AppError("TASK_NOT_SUCCEEDED", "只有已完成任务才能记录输出发布失败", status_code=409)
    now = utc_now()
    task.status = TaskStatus.FAILED
    task.progress_percent = min(task.progress_percent, 99)
    task.last_error = (safe_error.strip() or "镜头结果发布失败")[:1000]
    task.finished_at = now
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _fail_if_running(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
    worker_id: str,
    safe_error: str,
) -> None:
    with session_factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != TaskStatus.RUNNING or task.worker_id != worker_id:
            return
        mark_task_failed(db, task_id, safe_error=safe_error, worker_id=worker_id)


def run_p5_shot_boundary_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p5-shot-boundary-{uuid4()}"
    with session_factory() as db:
        claimed = _claim_p5_task(db, task_id, worker_id=worker_id)
        if claimed is None:
            return
        task_snapshot = TaskWorkerRead.model_validate(claimed)

    context = TaskExecutionContext(
        session_factory=session_factory,
        task_id=task_snapshot.id,
        worker_id=worker_id,
    )
    boundary_set: ShotBoundarySet | None = None
    try:
        boundary_set = _execute_shot_boundary_task(context, task_snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        _fail_if_running(
            session_factory,
            task_id=task_snapshot.id,
            worker_id=worker_id,
            safe_error=f"镜头处理失败（{exc.code}）",
        )
        return
    except Exception as exc:
        _fail_if_running(
            session_factory,
            task_id=task_snapshot.id,
            worker_id=worker_id,
            safe_error=f"镜头处理失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, task_snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        _discard_boundary_set(session_factory, boundary_set.id)
        return

    try:
        with session_factory() as db:
            _publish_boundary_artifact(db, task_id=task_snapshot.id, boundary_set_id=boundary_set.id)
    except Exception as exc:
        _discard_boundary_set(session_factory, boundary_set.id)
        with session_factory() as db:
            _mark_output_failed(
                db,
                task_snapshot.id,
                safe_error=f"镜头结果发布失败（{type(exc).__name__}）",
            )


def _latest_boundary_set(db: Session, project_id: str, episode_id: str) -> ShotBoundarySet | None:
    return db.scalar(
        select(ShotBoundarySet)
        .where(
            ShotBoundarySet.project_id == project_id,
            ShotBoundarySet.episode_id == episode_id,
        )
        .order_by(ShotBoundarySet.revision.desc())
        .limit(1)
    )


def get_episode_shot_boundary(db: Session, project_id: str, episode_id: str) -> EpisodeShotBoundaryRead:
    episode, asset = _episode_with_asset(db, project_id, episode_id)
    boundary_set = _latest_boundary_set(db, project_id, episode_id)
    if boundary_set is None:
        return EpisodeShotBoundaryRead(
            episode_id=episode.id,
            episode_order=episode.episode_order,
            source_filename=asset.original_filename,
            status=ShotBoundaryResultStatus.NOT_BUILT,
            revision=None,
            artifact_revision=None,
            shot_count=0,
            shots=[],
        )

    source_artifact = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    shot_artifact = _current_artifact(db, project_id, ArtifactType.SHOT_ANCHORS)
    current_set_ids = {
        str(item.get("shot_boundary_set_id"))
        for item in ((shot_artifact.metadata_json.get("episode_sets") if shot_artifact else None) or [])
    }
    is_current = (
        boundary_set.is_current
        and source_artifact is not None
        and boundary_set.source_video_artifact_id == source_artifact.id
        and shot_artifact is not None
        and boundary_set.id in current_set_ids
    )
    anchors = list(
        db.scalars(
            select(ShotAnchor)
            .where(ShotAnchor.shot_boundary_set_id == boundary_set.id)
            .order_by(ShotAnchor.shot_number.asc())
        ).all()
    )
    shots = [
        ShotAnchorRead(
            id=anchor.id,
            shot_number=anchor.shot_number,
            start_us=anchor.start_us,
            end_us=anchor.end_us,
            duration_us=anchor.duration_us,
            thumbnail_url=(
                f"/api/v3/projects/{project_id}/episodes/{episode_id}/shot-boundary/"
                f"shots/{anchor.id}/thumbnail"
            ),
            reference_clip_url=(
                f"/api/v3/projects/{project_id}/episodes/{episode_id}/shot-boundary/"
                f"shots/{anchor.id}/reference-clip"
            ),
        )
        for anchor in anchors
    ]
    return EpisodeShotBoundaryRead(
        episode_id=episode.id,
        episode_order=episode.episode_order,
        source_filename=asset.original_filename,
        status=ShotBoundaryResultStatus.CURRENT if is_current else ShotBoundaryResultStatus.STALE,
        revision=boundary_set.revision,
        artifact_revision=shot_artifact.revision if is_current and shot_artifact is not None else None,
        shot_count=len(shots),
        shots=shots,
    )


def get_shot_media_path(
    db: Session,
    *,
    project_id: str,
    episode_id: str,
    shot_id: str,
    kind: str,
) -> Path:
    anchor = db.get(ShotAnchor, shot_id)
    if anchor is None or anchor.project_id != project_id or anchor.episode_id != episode_id:
        raise AppError("SHOT_NOT_FOUND", "镜头不存在", status_code=404)
    if kind == "thumbnail":
        return _resolve_generated_path(anchor.thumbnail_relative_path)
    if kind == "reference_clip":
        return _resolve_generated_path(anchor.reference_clip_relative_path)
    raise AppError("SHOT_MEDIA_KIND_INVALID", "镜头媒体类型无效", status_code=422)
