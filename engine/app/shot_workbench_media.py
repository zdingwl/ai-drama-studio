"""F05 工作台只读媒体服务。

页面首次加载 Final Shot 时 `shot_workbench.get_shot_workbench()` 已完成 F04/F03 来源校验。
缩略图和 5 关键帧随后可能产生大量 HTTP 请求；这些请求不能每次重新 SHA-256 整个 Proxy，
否则长视频会被无意义重复 IO 拖慢。

本模块只读取已存在 F05 Source 范围和 F03 Proxy 路径，并按媒体相对时间抽单帧缓存。
不修改 Final Shot，不绕过首次工作台的上游完整性校验。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import sqlalchemy as sa

from engine.app.core.database import init_database
from engine.app.preprocess import get_source_preprocess
from engine.app.projects import ProjectError, _read_valid_manifest
from engine.app.shot_workbench import ShotWorkbenchError

FFMPEG_FRAME_TIMEOUT_SECONDS = 60


def get_workbench_proxy_path(*, project_id: str, app_data_path: Path | None = None) -> Path:
    """返回浏览器播放器使用的 F03 Proxy；要求 F05 Edit Set 已经存在。"""

    _read_source_range(project_id=project_id, app_data_path=app_data_path)
    preprocess = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
    if preprocess is None:
        raise ShotWorkbenchError("SHOT_WORKBENCH_MEDIA_MISSING", "F03 Proxy 已不存在")
    workspace = _project_workspace(project_id=project_id, app_data_path=app_data_path)
    path = _resolve_workspace_path(workspace, preprocess.proxy_relative_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise ShotWorkbenchError("SHOT_WORKBENCH_MEDIA_MISSING", "F03 proxy.mp4 文件不存在")
    return path


def render_workbench_frame(
    *,
    project_id: str,
    source_time_us: int,
    app_data_path: Path | None = None,
) -> Path:
    """按 Source 时间抽单帧 JPEG；相同时间命中 Workspace 缓存后直接返回。"""

    source_start_us, source_end_us = _read_source_range(project_id=project_id, app_data_path=app_data_path)
    if not source_start_us <= source_time_us < source_end_us:
        raise ShotWorkbenchError("SHOT_WORKBENCH_FRAME_TIME_INVALID", "预览帧时间超出 Final Shot 时间轴")

    workspace = _project_workspace(project_id=project_id, app_data_path=app_data_path)
    cache_dir = workspace / ".cache" / "f05" / "frames"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{source_time_us}.jpg"
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    proxy_path = get_workbench_proxy_path(project_id=project_id, app_data_path=app_data_path)
    relative_seconds = (source_time_us - source_start_us) / 1_000_000
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{relative_seconds:.6f}",
        "-i", str(proxy_path),
        "-frames:v", "1", "-q:v", "2", "-y", str(cache_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFMPEG_FRAME_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ShotWorkbenchError("SHOT_WORKBENCH_FFMPEG_UNAVAILABLE", "未找到 FFmpeg，无法生成镜头预览帧") from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ShotWorkbenchError("SHOT_WORKBENCH_FRAME_FAILED", "FFmpeg 生成镜头预览帧失败") from exc
    if completed.returncode != 0 or not cache_path.is_file() or cache_path.stat().st_size <= 0:
        cache_path.unlink(missing_ok=True)
        raise ShotWorkbenchError("SHOT_WORKBENCH_FRAME_FAILED", "镜头预览帧生成失败")
    return cache_path


def _read_source_range(*, project_id: str, app_data_path: Path | None) -> tuple[int, int]:
    """媒体高频请求只读 F05 已持久化的 Source 范围，不重新触发 F04 Proxy Hash。"""

    database_path = init_database(app_data_path)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    metadata = sa.MetaData()
    edit_sets = sa.Table("shot_edit_sets", metadata, autoload_with=engine)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                edit_sets.select().where(edit_sets.c.project_id == project_id)
            ).mappings().first()
        if row is None:
            raise ShotWorkbenchError("SHOT_WORKBENCH_NOT_INITIALIZED", "镜头工作台尚未初始化")
        return int(row["source_start_us"]), int(row["source_end_us"])
    finally:
        engine.dispose()


def _project_workspace(*, project_id: str, app_data_path: Path | None) -> Path:
    database_path = init_database(app_data_path)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    metadata = sa.MetaData()
    projects = sa.Table("projects", metadata, autoload_with=engine)
    try:
        with engine.connect() as connection:
            row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().first()
        if row is None or row["status"] != "ready":
            raise ProjectError("PROJECT_NOT_FOUND", "没有找到可使用的项目")
        workspace = Path(row["workspace_path"])
        if not workspace.is_dir():
            raise ProjectError("PROJECT_WORKSPACE_MISSING", "项目文件夹不存在或已被移动")
        _read_valid_manifest(workspace, project_id)
        return workspace
    finally:
        engine.dispose()


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path:
    root = workspace.resolve(strict=False)
    candidate = (root / Path(relative_path)).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise ShotWorkbenchError("SHOT_WORKBENCH_MEDIA_MISSING", "F05 Proxy 路径超出 Project Workspace")
    return candidate
