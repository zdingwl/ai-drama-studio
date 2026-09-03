"""项目内原短剧视频管理服务。

本模块只处理项目入口页需要的 Source Episode 管理能力：
- 读取按 Episode.sort_order 排列的视频列表，并补充真实文件大小；
- 对正式上传入口做视频扩展名校验；
- 原地替换某一集原片，保留 Episode 稳定 ID 与排序；
- 替换原片后显式使旧 Preprocess / Current ShotRevision / Breakdown / 资产分析失效。

读取函数严格只读；任何重计算仍只能由显式 POST Task 命令触发。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import inspect, select

from engine.app import studio_v2
from engine.app.task_progress_v2 import ACTIVE_TASK_STATUSES, list_project_tasks

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
COPY_CHUNK_SIZE = 1024 * 1024


class SourceVideoManagementError(RuntimeError):
    """可以安全返回给项目视频管理页面的业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "").name.strip().replace("\x00", "")
    if not name:
        raise SourceVideoManagementError("VIDEO_FILENAME_REQUIRED", "视频文件名不能为空")
    return name


def _validated_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        allowed = " / ".join(sorted(item.lstrip(".").upper() for item in ALLOWED_VIDEO_EXTENSIONS))
        raise SourceVideoManagementError(
            "VIDEO_FORMAT_UNSUPPORTED",
            f"仅支持 {allowed} 视频文件",
        )
    return extension


def _episode_file_size(source_path: str) -> int | None:
    try:
        path = Path(source_path)
        return path.stat().st_size if path.is_file() else None
    except OSError:
        return None


def _serialize_episode(episode: studio_v2.Episode) -> dict[str, Any]:
    payload = studio_v2.serialize_episode(episode)
    payload["file_size_bytes"] = _episode_file_size(episode.source_path)
    return payload


def list_project_source_videos(project_id: str) -> list[dict[str, Any]]:
    """只读返回项目当前视频顺序及页面所需媒体元信息。"""

    with studio_v2.get_session() as session:
        project = session.get(studio_v2.Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        episodes = session.scalars(
            select(studio_v2.Episode)
            .where(studio_v2.Episode.project_id == project_id)
            .order_by(studio_v2.Episode.sort_order)
        ).all()
        result: list[dict[str, Any]] = []
        for episode in episodes:
            _ = episode.preprocess
            _ = episode.shots
            result.append(_serialize_episode(episode))
        return result


def _assert_project_idle(project_id: str) -> None:
    """修改 Source 时禁止与项目后台任务并发，避免旧任务回写新的 Source。"""

    active = [
        task
        for task in list_project_tasks(project_id, limit=100)
        if task.get("status") in ACTIVE_TASK_STATUSES
    ]
    if not active:
        return
    first = active[0]
    title = str(first.get("title") or first.get("task_type") or "后台任务")
    raise SourceVideoManagementError(
        "PROJECT_TASK_ACTIVE",
        f"当前项目仍有任务正在执行：{title}。请等待任务结束后再修改原视频",
    )


def import_project_source_video(project_id: str, upload: UploadFile) -> dict[str, Any]:
    """通过页面正式入口导入一集，复用现有 Episode 导入服务并补上生产校验。"""

    filename = _safe_filename(upload.filename)
    _validated_extension(filename)
    _assert_project_idle(project_id)
    payload = studio_v2.import_episode(project_id=project_id, upload=upload)
    episode = studio_v2.get_episode_record(str(payload["id"]))
    if episode is None:
        raise SourceVideoManagementError("VIDEO_IMPORT_INCONSISTENT", "视频已导入但剧集记录读取失败")
    return _serialize_episode(episode)


def _copy_upload_to_staging(upload: UploadFile, staging_path: Path) -> tuple[int, str]:
    """分块保存替换文件并在一次遍历中计算大小和 SHA-256。"""

    staging_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        upload.file.seek(0)
    except (AttributeError, OSError):
        pass

    try:
        with staging_path.open("xb") as target:
            while True:
                chunk = upload.file.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
    except FileExistsError as exc:
        raise SourceVideoManagementError("VIDEO_REPLACE_CONFLICT", "替换视频临时文件发生冲突，请重试") from exc
    except OSError as exc:
        raise SourceVideoManagementError("VIDEO_REPLACE_WRITE_FAILED", "替换视频写入磁盘失败") from exc

    if size <= 0:
        staging_path.unlink(missing_ok=True)
        raise SourceVideoManagementError("VIDEO_EMPTY", "选择的视频文件为空")
    return size, digest.hexdigest()


def _invalidate_episode_derivatives_in_session(session: Any, episode: studio_v2.Episode) -> None:
    """原片变化后撤销所有依赖旧媒体事实的 Current 状态，但保留历史 Revision/Run。"""

    # 延迟 import 避免 studio_v2 / breakdown / shot revision 模型加载环。
    from engine.app.breakdown_models_v1 import BreakdownRun
    from engine.app.content_analysis_v2 import ContentAnalysisRun
    from engine.app.shot_revision_v2 import ShotRevision

    if episode.preprocess is not None:
        session.delete(episode.preprocess)

    for shot in list(episode.shots):
        session.delete(shot)

    table_names = set(inspect(session.get_bind()).get_table_names())

    if ShotRevision.__table__.name in table_names:
        current_revisions = session.scalars(
            select(ShotRevision).where(
                ShotRevision.episode_id == episode.id,
                ShotRevision.is_current.is_(True),
            )
        ).all()
        for revision in current_revisions:
            revision.is_current = False

    now = studio_v2.utcnow()
    if BreakdownRun.__table__.name in table_names:
        active_breakdowns = session.scalars(
            select(BreakdownRun).where(
                BreakdownRun.episode_id == episode.id,
                BreakdownRun.status.in_(("PROCESSING", "READY", "READY_WITH_WARNINGS")),
            )
        ).all()
        for run in active_breakdowns:
            run.status = "STALE"
            run.is_current = False
            if run.completed_at is None:
                run.completed_at = now

    if ContentAnalysisRun.__table__.name in table_names:
        current_asset_runs = session.scalars(
            select(ContentAnalysisRun).where(
                ContentAnalysisRun.project_id == episode.project_id,
                ContentAnalysisRun.is_current.is_(True),
            )
        ).all()
        for run in current_asset_runs:
            if run.status not in {"FAILED", "STALE"}:
                run.status = "STALE"

    episode.status = "IMPORTED"
    episode.duration_us = None
    episode.width = None
    episode.height = None
    episode.fps = None
    episode.updated_at = now

    project = session.get(studio_v2.Project, episode.project_id)
    if project is not None:
        project.updated_at = now


def replace_episode_source_video(episode_id: str, upload: UploadFile) -> dict[str, Any]:
    """原地替换 Episode Source，并原子撤销旧媒体派生状态。

    文件发布使用同目录 staging + backup + ``os.replace``。数据库提交失败时恢复旧文件，
    避免出现“数据库还是旧 SHA，但磁盘已经换成新视频”的半提交状态。
    """

    filename = _safe_filename(upload.filename)
    extension = _validated_extension(filename)

    with studio_v2.get_session() as session:
        existing = session.get(studio_v2.Episode, episode_id)
        if existing is None:
            raise LookupError("剧集不存在")
        project_id = existing.project_id
        expected_source_path = existing.source_path
        expected_sha256 = existing.source_sha256

    _assert_project_idle(project_id)

    old_path = Path(expected_source_path)
    if not old_path.is_file():
        raise SourceVideoManagementError("SOURCE_VIDEO_FILE_MISSING", "当前原视频文件不存在，无法安全替换")

    source_dir = old_path.parent
    token = uuid4().hex
    staging_path = source_dir / f".replacement-{token}{extension}.tmp"
    backup_path = source_dir / f".source-backup-{token}{old_path.suffix.lower() or '.video'}"
    new_path = source_dir / f"original{extension}"

    _, staged_sha256 = _copy_upload_to_staging(upload, staging_path)

    backup_moved = False
    new_published = False
    committed = False
    try:
        with studio_v2.get_session() as session:
            episode = session.get(studio_v2.Episode, episode_id)
            if episode is None:
                raise LookupError("剧集不存在")
            if episode.source_path != expected_source_path or episode.source_sha256 != expected_sha256:
                raise SourceVideoManagementError(
                    "VIDEO_REPLACE_CONFLICT",
                    "原视频在替换期间已经发生变化，请刷新页面后重试",
                )

            if new_path != old_path and new_path.exists():
                raise SourceVideoManagementError(
                    "VIDEO_REPLACE_CONFLICT",
                    "目标视频文件名已存在，系统不会覆盖来源不明的文件",
                )

            os.replace(old_path, backup_path)
            backup_moved = True
            os.replace(staging_path, new_path)
            new_published = True

            try:
                episode.original_filename = filename
                episode.source_path = str(new_path)
                episode.source_sha256 = staged_sha256
                _invalidate_episode_derivatives_in_session(session, episode)
                session.commit()
                committed = True
            except Exception:
                session.rollback()
                raise

        # 用全新 Session 读取，避免 expire_on_commit=False 下 relationship collection
        # 仍保留已删除 Shot/Preprocess 导致响应误报旧 shot_count/status。
        refreshed = studio_v2.get_episode_record(episode_id)
        if refreshed is None:
            raise SourceVideoManagementError("VIDEO_REPLACE_INCONSISTENT", "替换完成后剧集记录读取失败")
        payload = _serialize_episode(refreshed)
        backup_path.unlink(missing_ok=True)
        return payload
    except Exception:
        if not committed:
            try:
                if new_published and new_path.exists():
                    new_path.unlink()
                if backup_moved and backup_path.exists():
                    os.replace(backup_path, old_path)
            except OSError:
                # 原异常仍是主错误；残留 backup 文件可人工恢复，且数据库仍指向旧路径。
                pass
        raise
    finally:
        staging_path.unlink(missing_ok=True)
        if committed:
            backup_path.unlink(missing_ok=True)


__all__ = [
    "ALLOWED_VIDEO_EXTENSIONS",
    "SourceVideoManagementError",
    "import_project_source_video",
    "list_project_source_videos",
    "replace_episode_source_video",
]
