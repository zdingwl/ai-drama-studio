"""F02「上传原视频」的核心业务实现。

本文件只处理 Source Video 原片导入：稳定 ID、流式写盘、FFprobe 基础校验、
数据库状态、读取以及异常中断恢复。F02 不在这里生成 Proxy、WAV、Thumbnail，
也不执行自动拉片或任何 AI。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from engine.app.core.database import init_database
from engine.app.projects import ProjectError, _read_valid_manifest

SOURCE_VIDEO_ID_PREFIX = "SOURCE_"
SOURCE_DIRNAME = "source"
SOURCE_STAGING_DIRNAME = ".staging"
SOURCE_ORIGINAL_BASENAME = "original"
UPLOAD_CHUNK_SIZE = 1024 * 1024
FFPROBE_TIMEOUT_SECONDS = 60
_SAFE_EXTENSION_RE = re.compile(r"^[a-z0-9]{1,10}$")


class AsyncReadableUpload(Protocol):
    """copy_upload_to_staging() 所需的最小上传流协议，便于单测而不绑定具体框架。"""

    async def read(self, size: int = -1) -> bytes: ...


class SourceVideoError(RuntimeError):
    """F02 可以安全返回给 Controller 的 Source Video 业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CopiedFileInfo:
    """上传文件写入 staging 后得到的完整性信息。"""

    file_size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SourceVideoMetadata:
    """FFprobe 解析后保存到 source_videos 的基础媒体元数据。"""

    container_format: str
    duration_us: int
    source_start_time_us: int | None
    video_stream_index: int
    video_codec: str
    width: int
    height: int
    fps_num: int | None
    fps_den: int | None
    audio_stream_index: int | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None


@dataclass(frozen=True)
class SourceVideoRecord:
    """F02 返回给 Controller/前端的唯一 Source Video 记录。"""

    id: str
    project_id: str
    original_filename: str
    relative_path: str
    file_size_bytes: int
    sha256: str
    status: str
    container_format: str
    duration_us: int
    source_start_time_us: int | None
    video_stream_index: int
    video_codec: str
    width: int
    height: int
    fps_num: int | None
    fps_den: int | None
    audio_stream_index: int | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """转换为 FastAPI/Pydantic 可直接消费的字典。"""
        return asdict(self)


def generate_source_video_id() -> str:
    """生成一份 Source Video 的稳定业务 ID。

    业务作用：正式导入原片时建立与用户文件名无关的永久身份；该 ID 同时用于
    ``source_videos.id`` 和 ``source/SOURCE_xxx`` 目录，后续 Feature 只引用稳定 ID。

    本函数没有数据库、文件或 FFprobe 副作用。
    """

    return f"{SOURCE_VIDEO_ID_PREFIX}{uuid4().hex}"


async def copy_upload_to_staging(
    upload_file: AsyncReadableUpload,
    staging_file: Path,
    *,
    chunk_size: int = UPLOAD_CHUNK_SIZE,
) -> CopiedFileInfo:
    """把浏览器上传的大视频分块写入 staging，同时计算真实大小和 SHA-256。

    这里只负责“搬运字节”。禁止一次性 ``read()`` 整个视频；也不判断媒体是否合法、
    不修改数据库状态、不发布 final 文件。发生写盘/读取异常时让上层统一做回滚。
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    hasher = hashlib.sha256()
    total_bytes = 0
    staging_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with staging_file.open("xb") as handle:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                hasher.update(chunk)
                total_bytes += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise SourceVideoError("SOURCE_VIDEO_IMPORT_FAILED", "原视频临时文件已经存在，系统不会覆盖") from exc
    except OSError as exc:
        raise SourceVideoError("SOURCE_VIDEO_IMPORT_FAILED", "原视频写入项目临时目录失败") from exc

    if total_bytes <= 0:
        raise SourceVideoError("SOURCE_VIDEO_EMPTY", "选择的视频文件为空")

    return CopiedFileInfo(file_size_bytes=total_bytes, sha256=hasher.hexdigest())


def probe_source_video(path: Path) -> SourceVideoMetadata:
    """调用本机 FFprobe 验证视频并返回规范化基础媒体元数据。

    本函数只读取文件：不转码、不生成 Proxy/WAV/Thumbnail、不修改数据库。
    时间统一转换成整数微秒，FPS 保留 rational 分子/分母。
    """

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFPROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SourceVideoError("SOURCE_VIDEO_FFPROBE_UNAVAILABLE", "未找到 FFprobe，请先安装并配置到 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise SourceVideoError("SOURCE_VIDEO_PROBE_FAILED", "FFprobe 读取媒体信息超时") from exc
    except OSError as exc:
        raise SourceVideoError("SOURCE_VIDEO_PROBE_FAILED", "FFprobe 无法启动") from exc

    if completed.returncode != 0:
        raise SourceVideoError("SOURCE_VIDEO_PROBE_FAILED", "FFprobe 无法读取该视频文件")

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SourceVideoError("SOURCE_VIDEO_PROBE_FAILED", "FFprobe 返回的媒体信息格式异常") from exc

    streams = payload.get("streams")
    format_info = payload.get("format")
    if not isinstance(streams, list) or not isinstance(format_info, dict):
        raise SourceVideoError("SOURCE_VIDEO_UNSUPPORTED", "选择的文件不是系统可读取的视频")

    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict)
        and stream.get("codec_type") == "video"
        and int((stream.get("disposition") or {}).get("attached_pic") or 0) != 1
    ]
    if not video_streams:
        raise SourceVideoError("SOURCE_VIDEO_UNSUPPORTED", "文件中没有可用的视频流")

    video = _choose_default_stream(video_streams)
    audio_streams = [
        stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    audio = _choose_default_stream(audio_streams) if audio_streams else None

    duration_us = _seconds_to_microseconds(
        format_info.get("duration") if format_info.get("duration") not in (None, "N/A") else video.get("duration"),
        required=True,
    )
    start_time_us = _seconds_to_microseconds(
        format_info.get("start_time") if format_info.get("start_time") not in (None, "N/A") else video.get("start_time"),
        required=False,
    )

    width = _positive_int(video.get("width"))
    height = _positive_int(video.get("height"))
    video_index = _nonnegative_int(video.get("index"))
    video_codec = str(video.get("codec_name") or "").strip()
    container_format = str(format_info.get("format_name") or "").strip()

    if duration_us is None or duration_us <= 0 or width is None or height is None:
        raise SourceVideoError("SOURCE_VIDEO_UNSUPPORTED", "视频时长或分辨率无效")
    if video_index is None or not video_codec or not container_format:
        raise SourceVideoError("SOURCE_VIDEO_UNSUPPORTED", "视频编码或容器信息不完整")

    fps_num, fps_den = _parse_rational(video.get("avg_frame_rate"))

    audio_index: int | None = None
    audio_codec: str | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    if audio is not None:
        audio_index = _nonnegative_int(audio.get("index"))
        audio_codec = str(audio.get("codec_name") or "").strip() or None
        audio_sample_rate = _positive_int(audio.get("sample_rate"))
        audio_channels = _positive_int(audio.get("channels"))

    return SourceVideoMetadata(
        container_format=container_format,
        duration_us=duration_us,
        source_start_time_us=start_time_us,
        video_stream_index=video_index,
        video_codec=video_codec,
        width=width,
        height=height,
        fps_num=fps_num,
        fps_den=fps_den,
        audio_stream_index=audio_index,
        audio_codec=audio_codec,
        audio_sample_rate=audio_sample_rate,
        audio_channels=audio_channels,
    )


async def import_source_video(
    *,
    project_id: str,
    upload_file: AsyncReadableUpload,
    original_filename: str,
    app_data_path: Path | None = None,
) -> SourceVideoRecord:
    """把用户选择的视频完整导入当前 Project，并最终形成唯一 ready Source Video。

    事务顺序固定：验证 F01 Project → 确认无 Source → DB importing → staging 分块写入 →
    FFprobe → 发布 final → DB ready。final 发布前失败可以安全清理本次 staging/DB；
    final 已发布后绝不删除原片，数据库最终提交失败时交给启动 Recovery。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    source_videos = _table(engine, "source_videos")

    try:
        _, workspace = _load_ready_project(engine, projects, project_id)
        with engine.connect() as connection:
            existing = connection.execute(
                source_videos.select().where(source_videos.c.project_id == project_id)
            ).mappings().first()
        if existing is not None:
            raise SourceVideoError("SOURCE_VIDEO_ALREADY_EXISTS", "当前项目已经存在原视频，F02 不允许覆盖")

        source_id = generate_source_video_id()
        display_filename = _safe_display_filename(original_filename)
        extension = _safe_extension(display_filename)
        internal_filename = f"{SOURCE_ORIGINAL_BASENAME}.{extension}"
        relative_path = f"{SOURCE_DIRNAME}/{source_id}/{internal_filename}"
        staging_dir = workspace / SOURCE_DIRNAME / SOURCE_STAGING_DIRNAME / source_id
        staging_file = staging_dir / internal_filename
        final_dir = workspace / SOURCE_DIRNAME / source_id
        created_at = datetime.now(timezone.utc)

        try:
            with engine.begin() as connection:
                connection.execute(
                    source_videos.insert().values(
                        id=source_id,
                        project_id=project_id,
                        original_filename=display_filename,
                        relative_path=relative_path,
                        status="importing",
                        created_at=created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise SourceVideoError("SOURCE_VIDEO_IMPORT_FAILED", "原视频导入记录创建失败") from exc

        final_published = False
        try:
            if final_dir.exists() or staging_dir.exists():
                raise SourceVideoError("SOURCE_VIDEO_IMPORT_FAILED", "原视频内部目录发生冲突，系统不会覆盖已有文件")

            copied = await copy_upload_to_staging(upload_file, staging_file)
            metadata = probe_source_video(staging_file)

            if final_dir.exists():
                raise SourceVideoError("SOURCE_VIDEO_IMPORT_FAILED", "原视频正式目录已经存在，系统不会覆盖")
            os.replace(staging_dir, final_dir)
            final_published = True

            try:
                with engine.begin() as connection:
                    connection.execute(
                        source_videos.update()
                        .where(source_videos.c.id == source_id, source_videos.c.status == "importing")
                        .values(
                            file_size_bytes=copied.file_size_bytes,
                            sha256=copied.sha256,
                            status="ready",
                            **asdict(metadata),
                        )
                    )
                    row = connection.execute(
                        source_videos.select().where(source_videos.c.id == source_id)
                    ).mappings().one()
            except SQLAlchemyError as exc:
                raise SourceVideoError(
                    "SOURCE_VIDEO_FINALIZATION_PENDING",
                    "原视频已经安全保存，但数据库最终状态未完成；重启应用后系统会自动恢复",
                ) from exc

            return _row_to_record(row)
        except Exception:
            if not final_published:
                _cleanup_owned_staging(staging_dir, staging_file)
                try:
                    with engine.begin() as connection:
                        connection.execute(
                            source_videos.delete().where(
                                source_videos.c.id == source_id,
                                source_videos.c.status == "importing",
                            )
                        )
                except SQLAlchemyError:
                    pass
            raise
    finally:
        engine.dispose()


def get_source_video(
    *,
    project_id: str,
    app_data_path: Path | None = None,
) -> SourceVideoRecord | None:
    """读取 Project 当前已经 ready 的 Source Video；无 Source 时返回 ``None``。

    读取时同时检查正式文件仍存在且仍位于该 Project Workspace 内。这里只读，不重新
    FFprobe、不更新 Project ``last_opened_at``，也不尝试自动修复被用户删除的原片。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    source_videos = _table(engine, "source_videos")
    try:
        _, workspace = _load_ready_project(engine, projects, project_id)
        with engine.connect() as connection:
            row = connection.execute(
                source_videos.select().where(
                    source_videos.c.project_id == project_id,
                    source_videos.c.status == "ready",
                )
            ).mappings().first()
        if row is None:
            return None

        source_path = _resolve_workspace_relative_path(workspace, row["relative_path"])
        if not source_path.is_file():
            raise SourceVideoError("SOURCE_VIDEO_FILE_MISSING", "原视频文件不存在或已被移动")
        return _row_to_record(row)
    finally:
        engine.dispose()


def recover_source_video_imports(*, app_data_path: Path | None = None) -> dict[str, int]:
    """应用启动时恢复上次异常退出遗留的 ``importing`` Source Video。

    合法 final 会重新计算 size/hash、FFprobe 并补成 ready；仅有系统明确拥有的 staging
    可安全清理并删除 importing 记录；未知文件、损坏 final 或归属不清时保留现场。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    source_videos = _table(engine, "source_videos")
    stats = {"recovered": 0, "removed": 0, "preserved": 0}

    try:
        with engine.connect() as connection:
            rows = connection.execute(
                source_videos.select().where(source_videos.c.status == "importing")
            ).mappings().all()

        for row in rows:
            source_id = row["id"]
            try:
                _, workspace = _load_ready_project(engine, projects, row["project_id"])
                final_file = _resolve_workspace_relative_path(workspace, row["relative_path"])
            except (ProjectError, SourceVideoError):
                stats["preserved"] += 1
                continue

            final_dir = final_file.parent
            staging_dir = workspace / SOURCE_DIRNAME / SOURCE_STAGING_DIRNAME / source_id
            staging_file = staging_dir / final_file.name

            if final_file.is_file():
                if not _directory_contains_only(final_dir, {final_file.name}):
                    stats["preserved"] += 1
                    continue
                try:
                    copied = _inspect_existing_file(final_file)
                    metadata = probe_source_video(final_file)
                    with engine.begin() as connection:
                        connection.execute(
                            source_videos.update()
                            .where(source_videos.c.id == source_id, source_videos.c.status == "importing")
                            .values(
                                file_size_bytes=copied.file_size_bytes,
                                sha256=copied.sha256,
                                status="ready",
                                **asdict(metadata),
                            )
                        )
                    stats["recovered"] += 1
                except (OSError, SQLAlchemyError, SourceVideoError):
                    stats["preserved"] += 1
                continue

            if final_dir.exists():
                stats["preserved"] += 1
                continue

            if staging_dir.is_dir():
                if _directory_contains_only(staging_dir, {staging_file.name}) and staging_file.is_file():
                    _cleanup_owned_staging(staging_dir, staging_file)
                    if not staging_dir.exists():
                        try:
                            with engine.begin() as connection:
                                connection.execute(
                                    source_videos.delete().where(
                                        source_videos.c.id == source_id,
                                        source_videos.c.status == "importing",
                                    )
                                )
                            stats["removed"] += 1
                        except SQLAlchemyError:
                            stats["preserved"] += 1
                    else:
                        stats["preserved"] += 1
                else:
                    stats["preserved"] += 1
                continue

            if staging_dir.exists():
                stats["preserved"] += 1
                continue

            try:
                with engine.begin() as connection:
                    connection.execute(
                        source_videos.delete().where(
                            source_videos.c.id == source_id,
                            source_videos.c.status == "importing",
                        )
                    )
                stats["removed"] += 1
            except SQLAlchemyError:
                stats["preserved"] += 1

        return stats
    finally:
        engine.dispose()


def _database_engine(database_path: Path) -> sa.Engine:
    """创建访问 app.db 的轻量 SQLAlchemy Engine。"""
    return sa.create_engine(f"sqlite:///{database_path.as_posix()}", future=True)


def _table(engine: sa.Engine, table_name: str) -> sa.Table:
    """反射 Alembic 已创建表，避免在业务层维护第二套 Schema。"""
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=engine)


def _load_ready_project(
    engine: sa.Engine,
    projects: sa.Table,
    project_id: str,
) -> tuple[sa.RowMapping, Path]:
    """验证 F01 Project ready、Workspace 和 project.json，并返回项目上下文。"""
    with engine.connect() as connection:
        row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().first()
    if row is None or row["status"] != "ready":
        raise ProjectError("PROJECT_NOT_FOUND", "没有找到可使用的项目")
    workspace = Path(row["workspace_path"])
    if not workspace.is_dir():
        raise ProjectError("PROJECT_WORKSPACE_MISSING", "项目文件夹不存在或已被移动")
    _read_valid_manifest(workspace, project_id)
    return row, workspace


def _safe_display_filename(filename: str) -> str:
    """去掉客户端可能带来的路径部分，仅保留用户可读文件名。"""
    normalized = (filename or "").replace("\\", "/").split("/")[-1].strip()
    return normalized or "source-video"


def _safe_extension(filename: str) -> str:
    """生成只用于内部文件名的安全扩展名；视频真实性仍由 FFprobe 判断。"""
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix if _SAFE_EXTENSION_RE.fullmatch(suffix or "") else "video"


def _choose_default_stream(streams: list[dict[str, Any]]) -> dict[str, Any]:
    """优先选择 disposition.default=1 的流，否则返回列表第一项。"""
    for stream in streams:
        if int((stream.get("disposition") or {}).get("default") or 0) == 1:
            return stream
    return streams[0]


def _seconds_to_microseconds(value: Any, *, required: bool) -> int | None:
    """把 FFprobe 十进制秒精确转换为整数微秒，不把 float 作为权威数据。"""
    if value in (None, "", "N/A"):
        return None
    try:
        seconds = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return int((seconds * Decimal(1_000_000)).to_integral_value(rounding=ROUND_HALF_UP))


def _parse_rational(value: Any) -> tuple[int | None, int | None]:
    """解析 FFprobe 的 rational FPS；0/0、N/A 等不可用值返回空。"""
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return None, None
    try:
        fraction = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None, None
    if fraction.numerator <= 0 or fraction.denominator <= 0:
        return None, None
    return fraction.numerator, fraction.denominator


def _positive_int(value: Any) -> int | None:
    """解析必须大于 0 的 FFprobe 整数字段。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    """解析必须大于等于 0 的 stream index。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _resolve_workspace_relative_path(workspace: Path, relative_path: str) -> Path:
    """把 DB 相对路径解析到 Workspace 内，并阻止路径穿越。"""
    root = workspace.resolve(strict=False)
    candidate = (root / Path(relative_path)).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise SourceVideoError("SOURCE_VIDEO_FILE_MISSING", "原视频路径已经超出项目 Workspace")
    return candidate


def _row_to_record(row: sa.RowMapping) -> SourceVideoRecord:
    """把 ready source_videos 行转换成前端 DTO。"""
    return SourceVideoRecord(
        id=row["id"],
        project_id=row["project_id"],
        original_filename=row["original_filename"],
        relative_path=row["relative_path"],
        file_size_bytes=int(row["file_size_bytes"]),
        sha256=row["sha256"],
        status=row["status"],
        container_format=row["container_format"],
        duration_us=int(row["duration_us"]),
        source_start_time_us=row["source_start_time_us"],
        video_stream_index=int(row["video_stream_index"]),
        video_codec=row["video_codec"],
        width=int(row["width"]),
        height=int(row["height"]),
        fps_num=row["fps_num"],
        fps_den=row["fps_den"],
        audio_stream_index=row["audio_stream_index"],
        audio_codec=row["audio_codec"],
        audio_sample_rate=row["audio_sample_rate"],
        audio_channels=row["audio_channels"],
        created_at=row["created_at"],
    )


def _cleanup_owned_staging(staging_dir: Path, staging_file: Path) -> None:
    """只删除本 Source 明确拥有的 staging 文件和空目录，不递归清理未知文件。"""
    try:
        staging_file.unlink(missing_ok=True)
    except OSError:
        return
    try:
        staging_dir.rmdir()
    except OSError:
        return
    for parent in (staging_dir.parent, staging_dir.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break


def _inspect_existing_file(path: Path) -> CopiedFileInfo:
    """Recovery 对已发布 final 重新计算大小与 SHA-256，不把整文件读进内存。"""
    hasher = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(UPLOAD_CHUNK_SIZE):
            total += len(chunk)
            hasher.update(chunk)
    if total <= 0:
        raise SourceVideoError("SOURCE_VIDEO_EMPTY", "恢复时发现原视频文件为空")
    return CopiedFileInfo(file_size_bytes=total, sha256=hasher.hexdigest())


def _directory_contains_only(directory: Path, allowed_names: set[str]) -> bool:
    """Recovery 删除/自动接管目录前确认其中没有未知用户文件。"""
    try:
        return {entry.name for entry in directory.iterdir()} == allowed_names
    except OSError:
        return False
