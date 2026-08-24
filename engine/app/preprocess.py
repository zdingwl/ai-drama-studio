"""F03「视频预处理」核心业务实现。

F03 只从 F02 已冻结的 Source Video 派生分析资产：proxy.mp4、可选 audio.wav、
thumbnail.jpg，并保存明确的 Source↔Proxy / Audio 时间映射。禁止在这里做 Shot Detection、
ASR、人物识别或覆盖 F02 original.<ext>。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from engine.app.core.database import init_database
from engine.app.core.media_time import derived_to_source_microseconds, seconds_to_microseconds
from engine.app.projects import ProjectError, _read_valid_manifest
from engine.app.source_videos import SourceVideoRecord, get_source_video

PREPROCESS_DIRNAME = "preprocess"
PREPROCESS_STAGING_DIRNAME = ".staging"
PROXY_FILENAME = "proxy.mp4"
AUDIO_FILENAME = "audio.wav"
THUMBNAIL_FILENAME = "thumbnail.jpg"
PREPROCESS_PROFILE_VERSION = 1
FILE_CHUNK_SIZE = 1024 * 1024
FFMPEG_TIMEOUT_SECONDS = 4 * 60 * 60
FFPROBE_TIMEOUT_SECONDS = 120
MAX_PROXY_WIDTH = 1280
MAX_PROXY_HEIGHT = 720
ANALYSIS_AUDIO_SAMPLE_RATE = 16000
ANALYSIS_AUDIO_CHANNELS = 1
# 用户重新点击“开始预处理”时，不能直接删除可能仍由 FFmpeg 写入的 processing 目录。
# 只有目录内系统文件已经超过此时间没有变化，才视为可以安全清理的旧残留。
PROCESSING_ACTIVITY_GRACE_SECONDS = 30


class PreprocessError(RuntimeError):
    """F03 可以安全映射给 Controller 的业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FileIntegrity:
    """派生文件校验后的大小和 SHA-256。"""

    file_size_bytes: int
    sha256: str


@dataclass(frozen=True)
class VideoTiming:
    """FFprobe 读取的视频流时间信息。"""

    duration_us: int
    start_time_us: int
    time_base_num: int
    time_base_den: int
    fps_num: int | None
    fps_den: int | None
    width: int
    height: int
    codec: str
    pixel_format: str | None


@dataclass(frozen=True)
class AudioTiming:
    """FFprobe 读取的音频流时间信息。"""

    duration_us: int
    start_time_us: int
    sample_rate: int
    channels: int
    codec: str


@dataclass(frozen=True)
class PreprocessAssetMetadata:
    """F03 三类派生资产通过统一 inspect 后得到的 ready 元数据。"""

    proxy_file_size_bytes: int
    proxy_sha256: str
    proxy_duration_us: int
    proxy_video_time_base_num: int
    proxy_video_time_base_den: int
    proxy_fps_num: int | None
    proxy_fps_den: int | None
    proxy_to_source_offset_us: int
    audio_file_size_bytes: int | None
    audio_sha256: str | None
    audio_duration_us: int | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_to_source_offset_us: int | None
    thumbnail_file_size_bytes: int
    thumbnail_sha256: str
    thumbnail_source_time_us: int
    source_video_time_base_num: int
    source_video_time_base_den: int


@dataclass(frozen=True)
class SourcePreprocessRecord:
    """F03 返回给 Controller / Vue 的预处理资产集。"""

    source_video_id: str
    project_id: str
    status: str
    profile_version: int
    source_sha256_snapshot: str
    proxy_relative_path: str
    proxy_file_size_bytes: int
    proxy_sha256: str
    proxy_duration_us: int
    proxy_video_time_base_num: int
    proxy_video_time_base_den: int
    proxy_fps_num: int | None
    proxy_fps_den: int | None
    proxy_to_source_offset_us: int
    audio_relative_path: str | None
    audio_file_size_bytes: int | None
    audio_sha256: str | None
    audio_duration_us: int | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_to_source_offset_us: int | None
    thumbnail_relative_path: str
    thumbnail_file_size_bytes: int
    thumbnail_sha256: str
    thumbnail_source_time_us: int
    source_video_time_base_num: int
    source_video_time_base_den: int
    created_at: datetime
    completed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """转换成 FastAPI/Pydantic 可直接返回的字典。"""
        return asdict(self)


def generate_proxy_video(
    *,
    source_path: Path,
    target_path: Path,
    video_stream_index: int,
    audio_stream_index: int | None,
) -> None:
    """把 F02 只读原片转成固定 F03 V1 分析 Proxy。

    业务作用：为 F04+ 提供体积更小、浏览器/算法更容易读取的 H.264 MP4，同时保持
    presentation timestamp 节奏，不主动把 VFR 改成 CFR。这里只生成 staging 文件；
    不写数据库、不发布 final、不生成 WAV/Thumbnail。
    """

    target_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-i", str(source_path),
        "-map", f"0:{video_stream_index}",
    ]
    if audio_stream_index is not None:
        command += ["-map", f"0:{audio_stream_index}"]
    command += [
        "-map_metadata", "-1",
        "-vf",
        "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-fps_mode", "passthrough",
    ]
    if audio_stream_index is None:
        command += ["-an"]
    else:
        command += ["-c:a", "aac", "-b:a", "128k"]
    command += ["-movflags", "+faststart", str(target_path)]
    _run_ffmpeg(command, "分析 Proxy 生成失败")
    _require_nonempty_file(target_path, "PREPROCESS_GENERATION_FAILED", "FFmpeg 没有生成可用的 proxy.mp4")


def extract_analysis_audio(
    *,
    source_path: Path,
    target_path: Path,
    audio_stream_index: int,
) -> None:
    """从 F02 Source 的主音频流生成 16kHz/mono/PCM16 分析 WAV。

    该 WAV 只服务 F08 ASR / F09 Speaker 等分析，不是最终混音母带。Source 无音频时
    上层不得调用本函数，更不能伪造静音 WAV。
    """

    target_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-i", str(source_path),
        "-map", f"0:{audio_stream_index}",
        "-vn",
        "-c:a", "pcm_s16le",
        "-ar", str(ANALYSIS_AUDIO_SAMPLE_RATE),
        "-ac", str(ANALYSIS_AUDIO_CHANNELS),
        str(target_path),
    ]
    _run_ffmpeg(command, "分析音频生成失败")
    _require_nonempty_file(target_path, "PREPROCESS_GENERATION_FAILED", "FFmpeg 没有生成可用的 audio.wav")


def generate_thumbnail(*, proxy_path: Path, target_path: Path, proxy_time_us: int) -> None:
    """从已生成 Proxy 的确定性时间点抽取一张 JPEG Thumbnail。

    ``proxy_time_us`` 属于 Proxy 时间域；最终 Source 时间由 inspect 阶段结合已保存 offset
    计算。这里只生成图片，不把 UI 秒数写回业务数据。
    """

    if proxy_time_us < 0:
        raise ValueError("proxy_time_us 不能小于 0")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    seek_seconds = f"{proxy_time_us / 1_000_000:.6f}"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-i", str(proxy_path),
        "-ss", seek_seconds,
        "-frames:v", "1",
        "-an",
        "-q:v", "2",
        str(target_path),
    ]
    _run_ffmpeg(command, "缩略图生成失败")
    _require_nonempty_file(target_path, "PREPROCESS_GENERATION_FAILED", "FFmpeg 没有生成可用的 thumbnail.jpg")


def inspect_preprocess_assets(
    *,
    source_path: Path,
    source_video: SourceVideoRecord,
    proxy_path: Path,
    audio_path: Path | None,
    thumbnail_path: Path,
) -> PreprocessAssetMetadata:
    """统一校验 F03 staging 资产，并计算 DB ready 所需全部元数据与时间映射。

    这是“能不能标记 ready”的唯一媒体校验入口。它会重新 FFprobe Source/Proxy/WAV，
    校验 Proxy 固定 Profile、WAV 16k mono、Thumbnail 可读取，并基于实际 stream start_time
    计算 Proxy/Audio → Source offset。它不修改文件、不写数据库。
    """

    source_payload = _probe_json(source_path)
    proxy_payload = _probe_json(proxy_path)
    thumbnail_payload = _probe_json(thumbnail_path)

    source_video_stream = _stream_by_index(source_payload, source_video.video_stream_index, "video")
    source_video_timing = _video_timing(
        source_payload,
        source_video_stream,
        fallback_start_us=source_video.source_start_time_us or 0,
    )
    proxy_video_stream = _first_regular_video_stream(proxy_payload)
    proxy_timing = _video_timing(proxy_payload, proxy_video_stream, fallback_start_us=0)

    if proxy_timing.codec.lower() != "h264":
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "Proxy 视频编码不是 H.264")
    if proxy_timing.pixel_format and proxy_timing.pixel_format.lower() != "yuv420p":
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "Proxy 像素格式不是 yuv420p")
    if proxy_timing.width > MAX_PROXY_WIDTH or proxy_timing.height > MAX_PROXY_HEIGHT:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "Proxy 分辨率超过 F03 V1 的 1280×720 上限")

    proxy_offset_us = source_video_timing.start_time_us - proxy_timing.start_time_us
    thumbnail_proxy_time_us = _thumbnail_time_us(proxy_timing.duration_us)
    thumbnail_source_time_us = derived_to_source_microseconds(thumbnail_proxy_time_us, proxy_offset_us)
    _validate_thumbnail(thumbnail_payload)

    proxy_file = _hash_file(proxy_path)
    thumbnail_file = _hash_file(thumbnail_path)

    audio_file_size: int | None = None
    audio_sha256: str | None = None
    audio_duration_us: int | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    audio_offset_us: int | None = None

    if source_video.audio_stream_index is None:
        if audio_path is not None and audio_path.exists():
            raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "无音频 Source 不应生成 audio.wav")
    else:
        if audio_path is None or not audio_path.is_file():
            raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "Source 存在音频，但缺少分析 audio.wav")
        source_audio_stream = _stream_by_index(source_payload, source_video.audio_stream_index, "audio")
        source_audio_timing = _audio_timing(
            source_payload,
            source_audio_stream,
            fallback_start_us=source_video.source_start_time_us or source_video_timing.start_time_us,
        )
        audio_payload = _probe_json(audio_path)
        audio_stream = _first_audio_stream(audio_payload)
        analysis_audio = _audio_timing(audio_payload, audio_stream, fallback_start_us=0)
        if analysis_audio.sample_rate != ANALYSIS_AUDIO_SAMPLE_RATE or analysis_audio.channels != ANALYSIS_AUDIO_CHANNELS:
            raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "分析 WAV 必须是 16000Hz 单声道")
        if analysis_audio.codec.lower() not in {"pcm_s16le", "pcm_s16be"}:
            raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "分析 WAV 不是 PCM 16-bit")
        audio_file = _hash_file(audio_path)
        audio_file_size = audio_file.file_size_bytes
        audio_sha256 = audio_file.sha256
        audio_duration_us = analysis_audio.duration_us
        audio_sample_rate = analysis_audio.sample_rate
        audio_channels = analysis_audio.channels
        audio_offset_us = source_audio_timing.start_time_us - analysis_audio.start_time_us

    return PreprocessAssetMetadata(
        proxy_file_size_bytes=proxy_file.file_size_bytes,
        proxy_sha256=proxy_file.sha256,
        proxy_duration_us=proxy_timing.duration_us,
        proxy_video_time_base_num=proxy_timing.time_base_num,
        proxy_video_time_base_den=proxy_timing.time_base_den,
        proxy_fps_num=proxy_timing.fps_num,
        proxy_fps_den=proxy_timing.fps_den,
        proxy_to_source_offset_us=proxy_offset_us,
        audio_file_size_bytes=audio_file_size,
        audio_sha256=audio_sha256,
        audio_duration_us=audio_duration_us,
        audio_sample_rate=audio_sample_rate,
        audio_channels=audio_channels,
        audio_to_source_offset_us=audio_offset_us,
        thumbnail_file_size_bytes=thumbnail_file.file_size_bytes,
        thumbnail_sha256=thumbnail_file.sha256,
        thumbnail_source_time_us=thumbnail_source_time_us,
        source_video_time_base_num=source_video_timing.time_base_num,
        source_video_time_base_den=source_video_timing.time_base_den,
    )


def preprocess_source_video(*, project_id: str, app_data_path: Path | None = None) -> SourcePreprocessRecord:
    """执行 F03 完整预处理：Source Integrity → staging → 生成 → 校验 → publish → DB ready。

    如果发现上次遗留 ``processing``，会先做“当前项目定向安全恢复”：完整 final 恢复成 ready；
    已停止写入且只有系统已知文件的 staging 自动清理后允许重试；最近仍有文件写入则认为任务
    仍在运行，不删除；存在未知文件时保留现场并阻止重试。F02 Source 永远不会被删除。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    preprocess_table = _table(engine, "source_preprocess")
    try:
        workspace = _load_workspace(engine, projects, project_id)
        source = get_source_video(project_id=project_id, app_data_path=app_data_path)
        if source is None:
            raise PreprocessError("PREPROCESS_SOURCE_REQUIRED", "请先完成 F02 原视频导入")

        with engine.connect() as connection:
            existing = connection.execute(
                preprocess_table.select().where(preprocess_table.c.project_id == project_id)
            ).mappings().first()
        if existing is not None:
            if existing["status"] == "ready":
                ready = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
                if ready is not None:
                    return ready
                raise PreprocessError("PREPROCESS_ALREADY_EXISTS", "当前项目已经完成视频预处理")

            retry_state = _resolve_processing_record_for_retry(
                engine=engine,
                preprocess_table=preprocess_table,
                workspace=workspace,
                source=source,
                source_row=existing,
            )
            if retry_state == "ready":
                ready = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
                if ready is not None:
                    return ready
                raise PreprocessError("PREPROCESS_RECOVERY_REQUIRED", "旧预处理结果已恢复，但当前无法读取，请重新打开项目")
            if retry_state == "active":
                raise PreprocessError("PREPROCESS_IN_PROGRESS", "视频预处理仍在运行，请稍后再试")
            if retry_state == "preserved":
                raise PreprocessError(
                    "PREPROCESS_RECOVERY_REQUIRED",
                    "检测到上次预处理遗留的未知或异常文件，系统为避免误删已保留现场；请检查 preprocess 目录后再试",
                )
            # removed 表示旧 processing 已安全清理，可继续重新生成。

        source_path = _resolve_workspace_path(workspace, source.relative_path)
        source_integrity = _hash_file(source_path)
        if source_integrity.file_size_bytes != source.file_size_bytes or source_integrity.sha256 != source.sha256:
            raise PreprocessError("SOURCE_VIDEO_INTEGRITY_MISMATCH", "原视频文件与 F02 导入记录不一致，已停止预处理")

        relative_root = f"{PREPROCESS_DIRNAME}/{source.id}"
        proxy_relative_path = f"{relative_root}/{PROXY_FILENAME}"
        audio_relative_path = f"{relative_root}/{AUDIO_FILENAME}" if source.audio_stream_index is not None else None
        thumbnail_relative_path = f"{relative_root}/{THUMBNAIL_FILENAME}"
        staging_dir = workspace / PREPROCESS_DIRNAME / PREPROCESS_STAGING_DIRNAME / source.id
        final_dir = workspace / PREPROCESS_DIRNAME / source.id
        proxy_staging = staging_dir / PROXY_FILENAME
        audio_staging = staging_dir / AUDIO_FILENAME if source.audio_stream_index is not None else None
        thumbnail_staging = staging_dir / THUMBNAIL_FILENAME
        created_at = datetime.now(timezone.utc)

        try:
            with engine.begin() as connection:
                connection.execute(
                    preprocess_table.insert().values(
                        source_video_id=source.id,
                        project_id=project_id,
                        status="processing",
                        profile_version=PREPROCESS_PROFILE_VERSION,
                        source_sha256_snapshot=source_integrity.sha256,
                        proxy_relative_path=proxy_relative_path,
                        audio_relative_path=audio_relative_path,
                        thumbnail_relative_path=thumbnail_relative_path,
                        created_at=created_at,
                        completed_at=None,
                    )
                )
        except IntegrityError as exc:
            raise PreprocessError("PREPROCESS_IN_PROGRESS", "视频预处理记录已经存在，请稍后再试") from exc
        except SQLAlchemyError as exc:
            raise PreprocessError("PREPROCESS_PROCESSING_FAILED", "视频预处理数据库记录创建失败") from exc

        final_published = False
        expected_names = {PROXY_FILENAME, THUMBNAIL_FILENAME}
        if audio_staging is not None:
            expected_names.add(AUDIO_FILENAME)

        try:
            if staging_dir.exists() or final_dir.exists():
                raise PreprocessError("PREPROCESS_PROCESSING_FAILED", "预处理内部目录发生冲突，系统不会覆盖已有文件")

            generate_proxy_video(
                source_path=source_path,
                target_path=proxy_staging,
                video_stream_index=source.video_stream_index,
                audio_stream_index=source.audio_stream_index,
            )
            proxy_duration_us = _probe_proxy_duration_us(proxy_staging)
            if audio_staging is not None and source.audio_stream_index is not None:
                extract_analysis_audio(
                    source_path=source_path,
                    target_path=audio_staging,
                    audio_stream_index=source.audio_stream_index,
                )
            generate_thumbnail(
                proxy_path=proxy_staging,
                target_path=thumbnail_staging,
                proxy_time_us=_thumbnail_time_us(proxy_duration_us),
            )
            metadata = inspect_preprocess_assets(
                source_path=source_path,
                source_video=source,
                proxy_path=proxy_staging,
                audio_path=audio_staging,
                thumbnail_path=thumbnail_staging,
            )

            # 预处理可能耗时很长。开始时校验一次还不够，正式 publish 前必须再次确认
            # F02 Source 没有在处理中被系统外替换，否则不能发布与快照不一致的派生资产。
            source_integrity_before_publish = _hash_file(source_path)
            if (
                source_integrity_before_publish.file_size_bytes != source.file_size_bytes
                or source_integrity_before_publish.sha256 != source.sha256
                or source_integrity_before_publish.sha256 != source_integrity.sha256
            ):
                raise PreprocessError(
                    "SOURCE_VIDEO_INTEGRITY_MISMATCH",
                    "原视频在预处理过程中发生变化，已停止发布预处理结果",
                )

            if final_dir.exists():
                raise PreprocessError("PREPROCESS_PROCESSING_FAILED", "预处理正式目录已经存在，系统不会覆盖")
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging_dir, final_dir)
            final_published = True

            completed_at = datetime.now(timezone.utc)
            try:
                with engine.begin() as connection:
                    result = connection.execute(
                        preprocess_table.update()
                        .where(
                            preprocess_table.c.source_video_id == source.id,
                            preprocess_table.c.status == "processing",
                        )
                        .values(status="ready", completed_at=completed_at, **asdict(metadata))
                    )
                    if result.rowcount != 1:
                        raise SQLAlchemyError("processing row 不存在")
                    row = connection.execute(
                        preprocess_table.select().where(preprocess_table.c.source_video_id == source.id)
                    ).mappings().one()
            except SQLAlchemyError as exc:
                raise PreprocessError(
                    "PREPROCESS_FINALIZATION_PENDING",
                    "预处理文件已经安全生成，但数据库最终状态未完成；重启应用后系统会自动恢复",
                ) from exc
            return _row_to_record(row)
        except Exception:
            if not final_published:
                _cleanup_owned_staging(staging_dir, expected_names)
                try:
                    with engine.begin() as connection:
                        connection.execute(
                            preprocess_table.delete().where(
                                preprocess_table.c.source_video_id == source.id,
                                preprocess_table.c.status == "processing",
                            )
                        )
                except SQLAlchemyError:
                    pass
            raise
    finally:
        engine.dispose()


def get_source_preprocess(*, project_id: str, app_data_path: Path | None = None) -> SourcePreprocessRecord | None:
    """读取项目当前 ready 的 F03 预处理资产集，并确认正式派生文件仍存在。

    页面刷新/重启只走该函数；不重新转码、不修改完成时间。无 F03 结果返回 ``None``。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    preprocess_table = _table(engine, "source_preprocess")
    try:
        workspace = _load_workspace(engine, projects, project_id)
        with engine.connect() as connection:
            row = connection.execute(
                preprocess_table.select().where(
                    preprocess_table.c.project_id == project_id,
                    preprocess_table.c.status == "ready",
                )
            ).mappings().first()
        if row is None:
            return None

        source = get_source_video(project_id=project_id, app_data_path=app_data_path)
        if source is None or source.id != row["source_video_id"]:
            raise PreprocessError("PREPROCESS_SOURCE_REQUIRED", "预处理结果对应的 Source Video 已不存在")
        if source.sha256 != row["source_sha256_snapshot"]:
            raise PreprocessError("SOURCE_VIDEO_INTEGRITY_MISMATCH", "Source Video 身份与预处理快照不一致")

        paths = _record_paths(workspace, row)
        for label, path in paths.items():
            if path is not None and not path.is_file():
                raise PreprocessError("PREPROCESS_FILE_MISSING", f"预处理文件缺失：{label}")
        return _row_to_record(row)
    finally:
        engine.dispose()


def recover_source_preprocesses(*, app_data_path: Path | None = None) -> dict[str, int]:
    """应用启动时恢复异常退出遗留的 F03 ``processing`` 记录。

    合法 final 会重新 inspect 后补成 ready；仅有系统明确拥有的 staging 时安全清理并删除
    processing 记录；final 损坏、出现未知文件或无法确认归属时保留现场。绝不删除 F02 Source。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    source_table = _table(engine, "source_videos")
    preprocess_table = _table(engine, "source_preprocess")
    stats = {"recovered": 0, "removed": 0, "preserved": 0}
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                preprocess_table.select().where(preprocess_table.c.status == "processing")
            ).mappings().all()

        for row in rows:
            try:
                workspace = _load_workspace(engine, projects, row["project_id"])
                with engine.connect() as connection:
                    source_row = connection.execute(
                        source_table.select().where(
                            source_table.c.id == row["source_video_id"],
                            source_table.c.status == "ready",
                        )
                    ).mappings().first()
                if source_row is None:
                    stats["preserved"] += 1
                    continue
                source = _source_row_to_record(source_row)
                source_path = _resolve_workspace_path(workspace, source.relative_path)
                source_integrity = _hash_file(source_path)
                if (
                    source_integrity.file_size_bytes != source.file_size_bytes
                    or source_integrity.sha256 != source.sha256
                    or source_integrity.sha256 != row["source_sha256_snapshot"]
                ):
                    stats["preserved"] += 1
                    continue
            except (OSError, ProjectError, PreprocessError):
                stats["preserved"] += 1
                continue

            final_dir = workspace / PREPROCESS_DIRNAME / source.id
            staging_dir = workspace / PREPROCESS_DIRNAME / PREPROCESS_STAGING_DIRNAME / source.id
            expected_names = {PROXY_FILENAME, THUMBNAIL_FILENAME}
            audio_path: Path | None = None
            if row["audio_relative_path"] is not None:
                expected_names.add(AUDIO_FILENAME)

            if final_dir.is_dir():
                if not _directory_contains_only(final_dir, expected_names):
                    stats["preserved"] += 1
                    continue
                proxy_path = final_dir / PROXY_FILENAME
                thumbnail_path = final_dir / THUMBNAIL_FILENAME
                if row["audio_relative_path"] is not None:
                    audio_path = final_dir / AUDIO_FILENAME
                try:
                    metadata = inspect_preprocess_assets(
                        source_path=source_path,
                        source_video=source,
                        proxy_path=proxy_path,
                        audio_path=audio_path,
                        thumbnail_path=thumbnail_path,
                    )
                    completed_at = datetime.now(timezone.utc)
                    with engine.begin() as connection:
                        connection.execute(
                            preprocess_table.update()
                            .where(
                                preprocess_table.c.source_video_id == source.id,
                                preprocess_table.c.status == "processing",
                            )
                            .values(status="ready", completed_at=completed_at, **asdict(metadata))
                        )
                    stats["recovered"] += 1
                except (OSError, SQLAlchemyError, PreprocessError):
                    stats["preserved"] += 1
                continue

            if final_dir.exists():
                stats["preserved"] += 1
                continue

            if staging_dir.is_dir():
                if _directory_entries_subset(staging_dir, expected_names):
                    _cleanup_owned_staging(staging_dir, expected_names)
                    if not staging_dir.exists():
                        try:
                            with engine.begin() as connection:
                                connection.execute(
                                    preprocess_table.delete().where(
                                        preprocess_table.c.source_video_id == source.id,
                                        preprocess_table.c.status == "processing",
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
                        preprocess_table.delete().where(
                            preprocess_table.c.source_video_id == source.id,
                            preprocess_table.c.status == "processing",
                        )
                    )
                stats["removed"] += 1
            except SQLAlchemyError:
                stats["preserved"] += 1

        return stats
    finally:
        engine.dispose()


def _resolve_processing_record_for_retry(
    *,
    engine: sa.Engine,
    preprocess_table: sa.Table,
    workspace: Path,
    source: SourceVideoRecord,
    source_row: sa.RowMapping,
) -> str:
    """用户重试 F03 时，只处理当前项目旧 ``processing`` 记录。

    返回值：
    - ``ready``：发现完整 final 并成功恢复；
    - ``removed``：确认是旧残留，已安全清理，可重新开始；
    - ``active``：staging 最近仍在写入，可能有另一个 FFmpeg 正在运行；
    - ``preserved``：存在未知/异常文件，不能自动删除。

    这个 helper 不会触碰 F02 Source，也不会递归删除 preprocess 之外的任何目录。
    """

    if source_row["status"] != "processing":
        return "preserved"

    source_path = _resolve_workspace_path(workspace, source.relative_path)
    source_integrity = _hash_file(source_path)
    if (
        source_integrity.file_size_bytes != source.file_size_bytes
        or source_integrity.sha256 != source.sha256
        or source_integrity.sha256 != source_row["source_sha256_snapshot"]
    ):
        return "preserved"

    final_dir = workspace / PREPROCESS_DIRNAME / source.id
    staging_dir = workspace / PREPROCESS_DIRNAME / PREPROCESS_STAGING_DIRNAME / source.id
    expected_names = {PROXY_FILENAME, THUMBNAIL_FILENAME}
    audio_path: Path | None = None
    if source_row["audio_relative_path"] is not None:
        expected_names.add(AUDIO_FILENAME)

    if final_dir.is_dir():
        if not _directory_contains_only(final_dir, expected_names):
            return "preserved"
        proxy_path = final_dir / PROXY_FILENAME
        thumbnail_path = final_dir / THUMBNAIL_FILENAME
        if source_row["audio_relative_path"] is not None:
            audio_path = final_dir / AUDIO_FILENAME
        try:
            metadata = inspect_preprocess_assets(
                source_path=source_path,
                source_video=source,
                proxy_path=proxy_path,
                audio_path=audio_path,
                thumbnail_path=thumbnail_path,
            )
            with engine.begin() as connection:
                result = connection.execute(
                    preprocess_table.update()
                    .where(
                        preprocess_table.c.source_video_id == source.id,
                        preprocess_table.c.status == "processing",
                    )
                    .values(status="ready", completed_at=datetime.now(timezone.utc), **asdict(metadata))
                )
                if result.rowcount != 1:
                    return "preserved"
            return "ready"
        except (OSError, SQLAlchemyError, PreprocessError):
            return "preserved"

    if final_dir.exists():
        return "preserved"

    if staging_dir.is_dir():
        if not _directory_entries_subset(staging_dir, expected_names):
            return "preserved"
        if _directory_has_recent_activity(staging_dir, PROCESSING_ACTIVITY_GRACE_SECONDS):
            return "active"
        _cleanup_owned_staging(staging_dir, expected_names)
        if staging_dir.exists():
            return "preserved"
        try:
            with engine.begin() as connection:
                connection.execute(
                    preprocess_table.delete().where(
                        preprocess_table.c.source_video_id == source.id,
                        preprocess_table.c.status == "processing",
                    )
                )
            return "removed"
        except SQLAlchemyError:
            return "preserved"

    if staging_dir.exists():
        return "preserved"

    if _record_is_recent(source_row.get("created_at"), PROCESSING_ACTIVITY_GRACE_SECONDS):
        return "active"

    try:
        with engine.begin() as connection:
            connection.execute(
                preprocess_table.delete().where(
                    preprocess_table.c.source_video_id == source.id,
                    preprocess_table.c.status == "processing",
                )
            )
        return "removed"
    except SQLAlchemyError:
        return "preserved"


def _directory_has_recent_activity(directory: Path, grace_seconds: int) -> bool:
    """检查 staging 是否最近仍有写入，避免重试请求误删正在运行的 FFmpeg 输出。"""

    now = time.time()
    try:
        entries = list(directory.iterdir())
        if not entries:
            return False
        return any(now - entry.stat().st_mtime <= grace_seconds for entry in entries if entry.is_file())
    except OSError:
        return True


def _record_is_recent(value: Any, grace_seconds: int) -> bool:
    """没有 staging 时用 processing 创建时间保护极短的并发窗口。"""

    if value is None:
        return False
    if isinstance(value, datetime):
        created = value
    else:
        try:
            created = datetime.fromisoformat(str(value))
        except ValueError:
            return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() <= grace_seconds


def _run_ffmpeg(command: list[str], failure_message: str) -> None:
    """统一运行 FFmpeg，并把系统/编码失败转换成稳定 F03 错误。"""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PreprocessError("PREPROCESS_FFMPEG_UNAVAILABLE", "未找到 FFmpeg，请先安装并配置到 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise PreprocessError("PREPROCESS_PROCESSING_FAILED", "FFmpeg 处理超时") from exc
    except OSError as exc:
        raise PreprocessError("PREPROCESS_PROCESSING_FAILED", "FFmpeg 无法启动") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        suffix = f"：{detail[-1][:240]}" if detail else ""
        raise PreprocessError("PREPROCESS_GENERATION_FAILED", f"{failure_message}{suffix}")


def _probe_json(path: Path) -> dict[str, Any]:
    """用 FFprobe 读取 format/streams JSON；不修改媒体。"""
    command = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
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
        raise PreprocessError("PREPROCESS_FFPROBE_UNAVAILABLE", "未找到 FFprobe，请先安装并配置到 PATH") from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "FFprobe 无法读取预处理媒体") from exc
    if completed.returncode != 0:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", f"FFprobe 无法读取文件：{path.name}")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "FFprobe 返回的 JSON 无法解析") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("streams"), list):
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "FFprobe 媒体信息不完整")
    return payload


def _database_engine(database_path: Path) -> sa.Engine:
    return sa.create_engine(f"sqlite:///{database_path.as_posix()}", future=True)


def _table(engine: sa.Engine, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=engine)


def _load_workspace(engine: sa.Engine, projects: sa.Table, project_id: str) -> Path:
    with engine.connect() as connection:
        row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().first()
    if row is None or row["status"] != "ready":
        raise ProjectError("PROJECT_NOT_FOUND", "没有找到可使用的项目")
    workspace = Path(row["workspace_path"])
    if not workspace.is_dir():
        raise ProjectError("PROJECT_WORKSPACE_MISSING", "项目文件夹不存在或已被移动")
    _read_valid_manifest(workspace, project_id)
    return workspace


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path:
    root = workspace.resolve(strict=False)
    candidate = (root / Path(relative_path)).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise PreprocessError("PREPROCESS_FILE_MISSING", "预处理路径超出 Project Workspace")
    return candidate


def _hash_file(path: Path) -> FileIntegrity:
    """分块读取文件，计算实际大小和 SHA-256。"""
    if not path.is_file():
        raise PreprocessError("PREPROCESS_FILE_MISSING", f"文件不存在：{path.name}")
    hasher = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(FILE_CHUNK_SIZE):
                total += len(chunk)
                hasher.update(chunk)
    except OSError as exc:
        raise PreprocessError("PREPROCESS_FILE_MISSING", f"文件无法读取：{path.name}") from exc
    if total <= 0:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", f"文件为空：{path.name}")
    return FileIntegrity(total, hasher.hexdigest())


def _require_nonempty_file(path: Path, code: str, message: str) -> None:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            raise PreprocessError(code, message)
    except OSError as exc:
        raise PreprocessError(code, message) from exc


def _format_info(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("format")
    return value if isinstance(value, dict) else {}


def _stream_by_index(payload: dict[str, Any], index: int, codec_type: str) -> dict[str, Any]:
    for stream in payload.get("streams", []):
        if isinstance(stream, dict) and stream.get("index") == index and stream.get("codec_type") == codec_type:
            return stream
    raise PreprocessError("PREPROCESS_VALIDATION_FAILED", f"找不到 Source 的主{codec_type}流 index={index}")


def _first_regular_video_stream(payload: dict[str, Any]) -> dict[str, Any]:
    for stream in payload.get("streams", []):
        if (
            isinstance(stream, dict)
            and stream.get("codec_type") == "video"
            and int((stream.get("disposition") or {}).get("attached_pic") or 0) != 1
        ):
            return stream
    raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "媒体中没有可用视频流")


def _first_audio_stream(payload: dict[str, Any]) -> dict[str, Any]:
    for stream in payload.get("streams", []):
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            return stream
    raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "媒体中没有可用音频流")


def _parse_rational(value: Any, *, allow_empty: bool) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        if allow_empty:
            return None, None
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "媒体 time_base 缺失")
    try:
        fraction = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", f"无效 rational: {text}") from exc
    if fraction.denominator <= 0 or (not allow_empty and fraction.numerator == 0):
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", f"无效 rational: {text}")
    if allow_empty and fraction.numerator <= 0:
        return None, None
    return fraction.numerator, fraction.denominator


def _seconds_us(value: Any, fallback: int | None = None) -> int:
    if value in (None, "", "N/A"):
        if fallback is None:
            raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "媒体时间信息缺失")
        return fallback
    try:
        return seconds_to_microseconds(value)
    except ValueError as exc:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", f"无效媒体时间: {value}") from exc


def _duration_us(payload: dict[str, Any], stream: dict[str, Any]) -> int:
    # F03 的调用者已经选定了主视频/主音频流。后续 F04/ASR 要的是该业务流自己的时长，
    # 不能优先使用整个容器 duration（容器可能因另一条流尾巴更长而被拉长）。
    raw = stream.get("duration")
    if raw in (None, "", "N/A"):
        raw = _format_info(payload).get("duration")
    duration = _seconds_us(raw)
    if duration <= 0:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "媒体时长必须大于 0")
    return duration


def _stream_start_us(payload: dict[str, Any], stream: dict[str, Any], fallback: int) -> int:
    raw = stream.get("start_time")
    if raw in (None, "", "N/A"):
        raw = _format_info(payload).get("start_time")
    return _seconds_us(raw, fallback=fallback)


def _video_timing(payload: dict[str, Any], stream: dict[str, Any], *, fallback_start_us: int) -> VideoTiming:
    tb_num, tb_den = _parse_rational(stream.get("time_base"), allow_empty=False)
    fps_num, fps_den = _parse_rational(stream.get("avg_frame_rate"), allow_empty=True)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    codec = str(stream.get("codec_name") or "").strip()
    if width <= 0 or height <= 0 or not codec or tb_num is None or tb_den is None:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "视频流元数据不完整")
    return VideoTiming(
        duration_us=_duration_us(payload, stream),
        start_time_us=_stream_start_us(payload, stream, fallback_start_us),
        time_base_num=tb_num,
        time_base_den=tb_den,
        fps_num=fps_num,
        fps_den=fps_den,
        width=width,
        height=height,
        codec=codec,
        pixel_format=str(stream.get("pix_fmt") or "").strip() or None,
    )


def _audio_timing(payload: dict[str, Any], stream: dict[str, Any], *, fallback_start_us: int) -> AudioTiming:
    sample_rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)
    codec = str(stream.get("codec_name") or "").strip()
    if sample_rate <= 0 or channels <= 0 or not codec:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "音频流元数据不完整")
    return AudioTiming(
        duration_us=_duration_us(payload, stream),
        start_time_us=_stream_start_us(payload, stream, fallback_start_us),
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
    )


def _validate_thumbnail(payload: dict[str, Any]) -> None:
    stream = _first_regular_video_stream(payload)
    if int(stream.get("width") or 0) <= 0 or int(stream.get("height") or 0) <= 0:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "Thumbnail 尺寸无效")


def _thumbnail_time_us(proxy_duration_us: int) -> int:
    if proxy_duration_us <= 0:
        raise PreprocessError("PREPROCESS_VALIDATION_FAILED", "Proxy 时长无效，无法生成 Thumbnail")
    return min(proxy_duration_us // 10, 5_000_000)


def _probe_proxy_duration_us(proxy_path: Path) -> int:
    payload = _probe_json(proxy_path)
    return _duration_us(payload, _first_regular_video_stream(payload))


def _cleanup_owned_staging(staging_dir: Path, expected_names: set[str]) -> None:
    """只在目录没有未知文件时删除 F03 自己拥有的 staging 文件。"""
    if not staging_dir.is_dir() or not _directory_entries_subset(staging_dir, expected_names):
        return
    try:
        for entry in list(staging_dir.iterdir()):
            if entry.is_file() and entry.name in expected_names:
                entry.unlink(missing_ok=True)
        staging_dir.rmdir()
    except OSError:
        return
    for parent in (staging_dir.parent, staging_dir.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break


def _directory_entries_subset(directory: Path, allowed_names: set[str]) -> bool:
    try:
        return all(entry.is_file() and entry.name in allowed_names for entry in directory.iterdir())
    except OSError:
        return False


def _directory_contains_only(directory: Path, allowed_names: set[str]) -> bool:
    try:
        entries = list(directory.iterdir())
        return {entry.name for entry in entries} == allowed_names and all(entry.is_file() for entry in entries)
    except OSError:
        return False


def _record_paths(workspace: Path, row: sa.RowMapping) -> dict[str, Path | None]:
    return {
        PROXY_FILENAME: _resolve_workspace_path(workspace, row["proxy_relative_path"]),
        AUDIO_FILENAME: _resolve_workspace_path(workspace, row["audio_relative_path"]) if row["audio_relative_path"] else None,
        THUMBNAIL_FILENAME: _resolve_workspace_path(workspace, row["thumbnail_relative_path"]),
    }


def _row_to_record(row: sa.RowMapping) -> SourcePreprocessRecord:
    return SourcePreprocessRecord(
        source_video_id=row["source_video_id"], project_id=row["project_id"], status=row["status"],
        profile_version=int(row["profile_version"]), source_sha256_snapshot=row["source_sha256_snapshot"],
        proxy_relative_path=row["proxy_relative_path"], proxy_file_size_bytes=int(row["proxy_file_size_bytes"]),
        proxy_sha256=row["proxy_sha256"], proxy_duration_us=int(row["proxy_duration_us"]),
        proxy_video_time_base_num=int(row["proxy_video_time_base_num"]), proxy_video_time_base_den=int(row["proxy_video_time_base_den"]),
        proxy_fps_num=row["proxy_fps_num"], proxy_fps_den=row["proxy_fps_den"], proxy_to_source_offset_us=int(row["proxy_to_source_offset_us"]),
        audio_relative_path=row["audio_relative_path"], audio_file_size_bytes=row["audio_file_size_bytes"], audio_sha256=row["audio_sha256"],
        audio_duration_us=row["audio_duration_us"], audio_sample_rate=row["audio_sample_rate"], audio_channels=row["audio_channels"],
        audio_to_source_offset_us=row["audio_to_source_offset_us"], thumbnail_relative_path=row["thumbnail_relative_path"],
        thumbnail_file_size_bytes=int(row["thumbnail_file_size_bytes"]), thumbnail_sha256=row["thumbnail_sha256"],
        thumbnail_source_time_us=int(row["thumbnail_source_time_us"]), source_video_time_base_num=int(row["source_video_time_base_num"]),
        source_video_time_base_den=int(row["source_video_time_base_den"]), created_at=row["created_at"], completed_at=row["completed_at"],
    )


def _source_row_to_record(row: sa.RowMapping) -> SourceVideoRecord:
    return SourceVideoRecord(
        id=row["id"], project_id=row["project_id"], original_filename=row["original_filename"], relative_path=row["relative_path"],
        file_size_bytes=int(row["file_size_bytes"]), sha256=row["sha256"], status=row["status"], container_format=row["container_format"],
        duration_us=int(row["duration_us"]), source_start_time_us=row["source_start_time_us"], video_stream_index=int(row["video_stream_index"]),
        video_codec=row["video_codec"], width=int(row["width"]), height=int(row["height"]), fps_num=row["fps_num"], fps_den=row["fps_den"],
        audio_stream_index=row["audio_stream_index"], audio_codec=row["audio_codec"], audio_sample_rate=row["audio_sample_rate"],
        audio_channels=row["audio_channels"], created_at=row["created_at"],
    )