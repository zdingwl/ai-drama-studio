"""F04「自动拉片」核心业务实现。

本模块只负责把 F03 已冻结 ``proxy.mp4`` 转成自动 Shot Candidate：
- TransNetV2 负责判断“哪些解码帧属于 transition”；
- FFprobe 负责给这些帧提供真实 PTS；
- 业务层把连续 transition 归并、去抖并映射到 Source Timeline；
- DB 保存 Auto Evidence，绝不生成或覆盖 F05 的人工 Final Shot。

特别注意：模型 frame index 只用于和 FFprobe 解码顺序对齐，任何正式时间字段都不能
通过 ``frame_index / fps`` 计算。F03 允许 VFR，因此真实 PTS 是唯一权威时间来源。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from engine.app.core.database import init_database
from engine.app.core.media_time import derived_to_source_microseconds, seconds_to_microseconds
from engine.app.preprocess import SourcePreprocessRecord, get_source_preprocess
from engine.app.projects import ProjectError, _read_valid_manifest

DETECTOR_NAME = "transnetv2_pytorch"
DETECTOR_PROFILE_VERSION = 1
DETECTOR_THRESHOLD = 0.5
MIN_BOUNDARY_GAP_US = 120_000
TRANSNET_PACKAGE_NAME = "transnetv2-pytorch"
TRANSNET_PACKAGE_VERSION = "1.0.5"
TRANSNET_WEIGHT_FILENAME = "transnetv2-pytorch-weights.pth"
PROXY_DURATION_TOLERANCE_US = 1_000
FILE_CHUNK_SIZE = 1024 * 1024
FFPROBE_TIMEOUT_SECONDS = 10 * 60


class ShotDetectionError(RuntimeError):
    """F04 可以安全映射给 Controller 的稳定业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FileIntegrity:
    """F04 对 F03 Proxy 重新计算得到的只读完整性信息。"""

    file_size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ProxyTimeline:
    """FFprobe 从 Proxy 主视频流读取的权威时间与逐帧 PTS。"""

    start_us: int
    duration_us: int
    end_us: int
    frame_pts_us: tuple[int, ...]
    ffprobe_version: str


@dataclass(frozen=True)
class CutEvent:
    """尚未组装成 Shot 的自动切换证据；时间属于 Proxy Timeline。"""

    proxy_time_us: int
    boundary_score: float


@dataclass(frozen=True)
class DetectionEvidence:
    """一次 TransNetV2 推理返回的自动边界与实际 runtime 元数据。"""

    events: tuple[CutEvent, ...]
    analyzed_frame_count: int
    detector_package_version: str
    torch_version: str
    detector_device: str


@dataclass(frozen=True)
class ShotCandidateRecord:
    """F04 自动候选镜头；F05 不允许覆盖 detected_* 证据字段。"""

    id: str
    detection_id: str
    project_id: str
    ordinal: int
    detected_proxy_start_us: int
    detected_proxy_end_us: int
    detected_start_us: int
    detected_end_us: int
    duration_us: int
    end_boundary_kind: str
    end_boundary_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShotDetectionRecord:
    """Controller / Vue 读取的一次 F04 Detection Run 及全部候选镜头。"""

    id: str
    project_id: str
    source_video_id: str
    status: str
    detector_name: str
    detector_profile_version: int
    detector_threshold: float
    min_boundary_gap_us: int
    detector_package_version: str
    torch_version: str | None
    detector_device: str | None
    ffprobe_version: str | None
    preprocess_profile_version: int
    proxy_sha256_snapshot: str
    proxy_to_source_offset_us: int
    proxy_start_us: int | None
    proxy_end_us: int | None
    source_start_us: int | None
    source_end_us: int | None
    analyzed_frame_count: int | None
    detected_cut_count: int | None
    shot_count: int | None
    created_at: datetime
    completed_at: datetime | None
    candidates: tuple[ShotCandidateRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


def generate_shot_detection_id() -> str:
    """生成独立于 Project/Source/文件名的 F04 Detection Run UUID4 业务 ID。"""

    return f"SHOT_DETECTION_{uuid.uuid4().hex}"


def _generate_shot_candidate_id() -> str:
    """生成自动 Candidate ID；它不是 F05 之后的 Final Shot ID。"""

    return f"SHOT_CANDIDATE_{uuid.uuid4().hex}"


def inspect_proxy_timeline(*, proxy_path: Path) -> ProxyTimeline:
    """用 FFprobe 读取 Proxy 主视频流 start/duration 和每个解码帧真实 PTS。

    ``frame_pts_us`` 与 TransNetV2 prediction index 后续按顺序一一对齐。这里只负责媒体
    时间事实，不运行模型、不写数据库，也绝不使用 FPS 补造时间。
    """

    ffprobe_version = _read_ffprobe_version()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_streams",
        "-show_frames",
        "-show_entries",
        "stream=start_time,duration:frame=best_effort_timestamp_time,pts_time",
        "-of",
        "json",
        str(proxy_path),
    ]
    payload = _run_ffprobe_json(command)

    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams or not isinstance(streams[0], dict):
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy 没有可读取的主视频流")
    stream = streams[0]

    try:
        start_us = seconds_to_microseconds(stream.get("start_time") or "0")
        duration_us = seconds_to_microseconds(stream["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy 主视频流缺少有效 start_time / duration") from exc
    if duration_us <= 0:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy 主视频流时长无效")

    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "FFprobe 没有返回 Proxy 视频帧时间戳")

    frame_pts: list[int] = []
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", f"Proxy 第 {index + 1} 帧时间信息无效")
        raw_pts = frame.get("best_effort_timestamp_time")
        if raw_pts in (None, "N/A", ""):
            raw_pts = frame.get("pts_time")
        if raw_pts in (None, "N/A", ""):
            raise ShotDetectionError(
                "SHOT_DETECTION_INVALID_RESULT",
                f"Proxy 第 {index + 1} 帧缺少真实 PTS；系统不会使用 FPS 猜测时间",
            )
        try:
            frame_pts.append(seconds_to_microseconds(raw_pts))
        except ValueError as exc:
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", f"Proxy 第 {index + 1} 帧 PTS 无法解析") from exc

    if any(current < previous for previous, current in zip(frame_pts, frame_pts[1:])):
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy 帧 PTS 不是非递减顺序")

    return ProxyTimeline(
        start_us=start_us,
        duration_us=duration_us,
        end_us=start_us + duration_us,
        frame_pts_us=tuple(frame_pts),
        ffprobe_version=ffprobe_version,
    )


def detect_proxy_cut_events(
    *,
    proxy_path: Path,
    frame_pts_us: tuple[int, ...],
    threshold: float = DETECTOR_THRESHOLD,
) -> DetectionEvidence:
    """运行本地 TransNetV2，并用真实 PTS 把 transition prediction 转成 CutEvent。

    TransNetV2 的 frame index 只是视觉证据索引。连续 ``score > threshold`` 的帧会归并成
    一个 transition interval，cut 锚定到该 interval 后第一帧的真实 PTS。模型秒数/FPS
    输出完全不进入正式业务数据。
    """

    if not 0 < threshold < 1:
        raise ValueError("TransNetV2 threshold 必须在 0 与 1 之间")
    if not frame_pts_us:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "没有可用于模型对齐的 Proxy PTS")

    try:
        import numpy as np
        import torch
        import transnetv2_pytorch
        from transnetv2_pytorch import TransNetV2
    except (ImportError, ModuleNotFoundError) as exc:
        raise ShotDetectionError(
            "SHOT_DETECTION_MODEL_UNAVAILABLE",
            "未安装 F04 本地 TransNetV2 运行依赖，请安装 engine/requirements.txt 后重启",
        ) from exc

    try:
        package_version = importlib.metadata.version(TRANSNET_PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ShotDetectionError("SHOT_DETECTION_MODEL_UNAVAILABLE", "无法读取 transnetv2-pytorch 版本") from exc
    if package_version != TRANSNET_PACKAGE_VERSION:
        raise ShotDetectionError(
            "SHOT_DETECTION_MODEL_INVALID",
            f"TransNetV2 版本不匹配：需要 {TRANSNET_PACKAGE_VERSION}，当前 {package_version}",
        )

    package_root = Path(transnetv2_pytorch.__file__).resolve().parent
    weight_candidates = [
        package_root / TRANSNET_WEIGHT_FILENAME,
        package_root / "weights" / TRANSNET_WEIGHT_FILENAME,
    ]
    weights_path = next((path for path in weight_candidates if path.is_file() and path.stat().st_size > 0), None)
    if weights_path is None:
        raise ShotDetectionError(
            "SHOT_DETECTION_MODEL_UNAVAILABLE",
            f"TransNetV2 权重缺失：{TRANSNET_WEIGHT_FILENAME}；请重新安装固定版本模型包",
        )

    try:
        model = TransNetV2(device="auto")
        map_location = getattr(model, "device", "cpu")
        try:
            state_dict = torch.load(weights_path, map_location=map_location, weights_only=True)
        except TypeError:
            # 兼容旧 PyTorch 的 torch.load 签名；正式 requirements 仍会锁定版本。
            state_dict = torch.load(weights_path, map_location=map_location)
        model.load_state_dict(state_dict)
        model.eval()
        with torch.no_grad():
            _, single_frame_predictions, _ = model.predict_video(str(proxy_path))
    except ShotDetectionError:
        raise
    except Exception as exc:
        raise ShotDetectionError("SHOT_DETECTION_MODEL_INVALID", "TransNetV2 模型加载或推理失败") from exc

    raw_scores = single_frame_predictions
    if hasattr(raw_scores, "detach"):
        raw_scores = raw_scores.detach().cpu().numpy()
    try:
        scores = np.asarray(raw_scores, dtype=np.float64).reshape(-1)
    except Exception as exc:
        raise ShotDetectionError("SHOT_DETECTION_MODEL_INVALID", "TransNetV2 返回的逐帧分数无法解析") from exc

    if len(scores) != len(frame_pts_us):
        raise ShotDetectionError(
            "SHOT_DETECTION_FRAME_ALIGNMENT_FAILED",
            f"模型预测帧数 {len(scores)} 与 FFprobe PTS 帧数 {len(frame_pts_us)} 不一致；系统不会按 FPS 补偿",
        )
    if len(scores) == 0:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "TransNetV2 没有返回任何逐帧预测")
    if not np.isfinite(scores).all() or (scores < 0).any() or (scores > 1).any():
        raise ShotDetectionError("SHOT_DETECTION_MODEL_INVALID", "TransNetV2 transition score 不在有效 0..1 范围")

    events: list[CutEvent] = []
    index = 0
    while index < len(scores):
        if float(scores[index]) <= threshold:
            index += 1
            continue
        transition_start = index
        while index + 1 < len(scores) and float(scores[index + 1]) > threshold:
            index += 1
        transition_end = index
        next_frame_index = transition_end + 1
        if next_frame_index < len(frame_pts_us):
            events.append(
                CutEvent(
                    proxy_time_us=frame_pts_us[next_frame_index],
                    boundary_score=float(scores[transition_start : transition_end + 1].max()),
                )
            )
        index += 1

    device_value = str(getattr(model, "device", "unknown"))
    if device_value == "unknown":
        try:
            device_value = str(next(model.parameters()).device)
        except Exception:
            device_value = "unknown"

    return DetectionEvidence(
        events=tuple(events),
        analyzed_frame_count=len(scores),
        detector_package_version=package_version,
        torch_version=str(torch.__version__),
        detector_device=device_value,
    )


def build_shot_candidates(
    *,
    detection_id: str,
    project_id: str,
    cut_events: Iterable[CutEvent],
    proxy_start_us: int,
    proxy_end_us: int,
    proxy_to_source_offset_us: int,
    min_boundary_gap_us: int = MIN_BOUNDARY_GAP_US,
) -> tuple[ShotCandidateRecord, ...]:
    """把自动 CutEvent 变成完整覆盖检测区间的连续 Shot Candidate。"""

    if proxy_end_us <= proxy_start_us:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy 检测区间无效")
    if min_boundary_gap_us < 0:
        raise ValueError("min_boundary_gap_us 不能小于 0")

    normalized = _normalize_cut_events(
        cut_events=cut_events,
        proxy_start_us=proxy_start_us,
        proxy_end_us=proxy_end_us,
        min_boundary_gap_us=min_boundary_gap_us,
    )

    boundaries = [proxy_start_us, *[event.proxy_time_us for event in normalized], proxy_end_us]
    candidates: list[ShotCandidateRecord] = []
    for index in range(len(boundaries) - 1):
        proxy_start = boundaries[index]
        proxy_end = boundaries[index + 1]
        source_start = derived_to_source_microseconds(proxy_start, proxy_to_source_offset_us)
        source_end = derived_to_source_microseconds(proxy_end, proxy_to_source_offset_us)
        is_last = index == len(boundaries) - 2
        event = None if is_last else normalized[index]
        candidates.append(
            ShotCandidateRecord(
                id=_generate_shot_candidate_id(),
                detection_id=detection_id,
                project_id=project_id,
                ordinal=index + 1,
                detected_proxy_start_us=proxy_start,
                detected_proxy_end_us=proxy_end,
                detected_start_us=source_start,
                detected_end_us=source_end,
                duration_us=source_end - source_start,
                end_boundary_kind="video_end" if is_last else "cut",
                end_boundary_score=None if event is None else event.boundary_score,
            )
        )

    result = tuple(candidates)
    _validate_candidates(
        candidates=result,
        proxy_start_us=proxy_start_us,
        proxy_end_us=proxy_end_us,
        proxy_to_source_offset_us=proxy_to_source_offset_us,
    )
    return result


def run_shot_detection(*, project_id: str, app_data_path: Path | None = None) -> ShotDetectionRecord:
    """执行 F04 完整闭环：上游校验 → processing → 模型+PTS → Candidates → ready。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    runs = _table(engine, "shot_detection_runs")
    candidate_table = _table(engine, "shot_candidates")
    detection_id: str | None = None

    try:
        workspace = _load_workspace(engine, projects, project_id)
        preprocess = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
        if preprocess is None:
            raise ShotDetectionError("SHOT_DETECTION_PREPROCESS_REQUIRED", "请先完成 F03 视频预处理")

        with engine.connect() as connection:
            existing = connection.execute(runs.select().where(runs.c.project_id == project_id)).mappings().first()
        if existing is not None:
            if existing["status"] == "ready":
                raise ShotDetectionError("SHOT_DETECTION_ALREADY_EXISTS", "当前项目已经完成自动拉片")
            raise ShotDetectionError("SHOT_DETECTION_IN_PROGRESS", "自动拉片正在运行或上次运行尚未恢复，请重启应用后再试")

        proxy_path = _resolve_workspace_path(workspace, preprocess.proxy_relative_path)
        initial_integrity = _hash_file(proxy_path)
        _require_proxy_integrity(initial_integrity, preprocess)

        detection_id = generate_shot_detection_id()
        created_at = datetime.now(timezone.utc)
        try:
            with engine.begin() as connection:
                connection.execute(
                    runs.insert().values(
                        id=detection_id,
                        project_id=project_id,
                        source_video_id=preprocess.source_video_id,
                        status="processing",
                        detector_name=DETECTOR_NAME,
                        detector_profile_version=DETECTOR_PROFILE_VERSION,
                        detector_threshold=DETECTOR_THRESHOLD,
                        min_boundary_gap_us=MIN_BOUNDARY_GAP_US,
                        detector_package_version=TRANSNET_PACKAGE_VERSION,
                        preprocess_profile_version=preprocess.profile_version,
                        proxy_sha256_snapshot=preprocess.proxy_sha256,
                        proxy_to_source_offset_us=preprocess.proxy_to_source_offset_us,
                        created_at=created_at,
                    )
                )
        except IntegrityError as exc:
            raise ShotDetectionError("SHOT_DETECTION_IN_PROGRESS", "自动拉片记录已经存在，请勿重复提交") from exc
        except SQLAlchemyError as exc:
            raise ShotDetectionError("SHOT_DETECTION_FAILED", "自动拉片 processing 记录创建失败") from exc

        try:
            timeline = inspect_proxy_timeline(proxy_path=proxy_path)
            if abs(timeline.duration_us - preprocess.proxy_duration_us) > PROXY_DURATION_TOLERANCE_US:
                raise ShotDetectionError(
                    "SHOT_DETECTION_INVALID_RESULT",
                    "F04 读取的 Proxy 时长与 F03 记录不一致，已停止检测",
                )

            evidence = detect_proxy_cut_events(
                proxy_path=proxy_path,
                frame_pts_us=timeline.frame_pts_us,
                threshold=DETECTOR_THRESHOLD,
            )
            candidates = build_shot_candidates(
                detection_id=detection_id,
                project_id=project_id,
                cut_events=evidence.events,
                proxy_start_us=timeline.start_us,
                proxy_end_us=timeline.end_us,
                proxy_to_source_offset_us=preprocess.proxy_to_source_offset_us,
                min_boundary_gap_us=MIN_BOUNDARY_GAP_US,
            )

            final_integrity = _hash_file(proxy_path)
            _require_proxy_integrity(final_integrity, preprocess)
            if final_integrity != initial_integrity:
                raise ShotDetectionError(
                    "SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH",
                    "Proxy 在自动拉片运行过程中发生变化，结果不会保存",
                )

            source_start_us = derived_to_source_microseconds(timeline.start_us, preprocess.proxy_to_source_offset_us)
            source_end_us = derived_to_source_microseconds(timeline.end_us, preprocess.proxy_to_source_offset_us)
            detected_cut_count = len(candidates) - 1
            completed_at = datetime.now(timezone.utc)

            try:
                with engine.begin() as connection:
                    connection.execute(candidate_table.insert(), [candidate.to_dict() for candidate in candidates])
                    result = connection.execute(
                        runs.update()
                        .where(runs.c.id == detection_id, runs.c.status == "processing")
                        .values(
                            status="ready",
                            torch_version=evidence.torch_version,
                            detector_device=evidence.detector_device,
                            ffprobe_version=timeline.ffprobe_version,
                            proxy_start_us=timeline.start_us,
                            proxy_end_us=timeline.end_us,
                            source_start_us=source_start_us,
                            source_end_us=source_end_us,
                            analyzed_frame_count=evidence.analyzed_frame_count,
                            detected_cut_count=detected_cut_count,
                            shot_count=len(candidates),
                            completed_at=completed_at,
                        )
                    )
                    if result.rowcount != 1:
                        raise SQLAlchemyError("processing run 不存在")
            except SQLAlchemyError as exc:
                raise ShotDetectionError("SHOT_DETECTION_FAILED", "自动拉片结果写入数据库失败") from exc

            ready = get_shot_detection(project_id=project_id, app_data_path=app_data_path)
            if ready is None:
                raise ShotDetectionError("SHOT_DETECTION_FAILED", "自动拉片已完成但结果无法重新读取")
            return ready
        except Exception:
            _delete_processing_run(engine=engine, runs=runs, candidates=candidate_table, detection_id=detection_id)
            raise
    finally:
        engine.dispose()


def get_shot_detection(*, project_id: str, app_data_path: Path | None = None) -> ShotDetectionRecord | None:
    """读取项目当前 F04 结果；ready 时同时验证 F03 快照和 Proxy 实体仍然一致。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    runs = _table(engine, "shot_detection_runs")
    candidates = _table(engine, "shot_candidates")
    try:
        workspace = _load_workspace(engine, projects, project_id)
        with engine.connect() as connection:
            row = connection.execute(runs.select().where(runs.c.project_id == project_id)).mappings().first()
        if row is None:
            return None

        candidate_rows: list[sa.RowMapping] = []
        if row["status"] == "ready":
            preprocess = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
            if preprocess is None:
                raise ShotDetectionError("SHOT_DETECTION_UPSTREAM_CHANGED", "F04 对应的 F03 预处理结果已不存在")
            _require_upstream_snapshot(row, preprocess)
            proxy_path = _resolve_workspace_path(workspace, preprocess.proxy_relative_path)
            _require_proxy_integrity(_hash_file(proxy_path), preprocess)
            with engine.connect() as connection:
                candidate_rows = list(
                    connection.execute(
                        candidates.select()
                        .where(candidates.c.detection_id == row["id"])
                        .order_by(candidates.c.ordinal.asc())
                    ).mappings().all()
                )
            if len(candidate_rows) != row["shot_count"]:
                raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "F04 ready 记录与 Shot Candidate 数量不一致")

        return _row_to_detection_record(row, candidate_rows)
    finally:
        engine.dispose()


def recover_shot_detections(*, app_data_path: Path | None = None) -> dict[str, int]:
    """应用启动时删除无法续跑的旧 F04 processing；绝不删除 ready 自动证据。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    runs = _table(engine, "shot_detection_runs")
    candidates = _table(engine, "shot_candidates")
    removed = 0
    try:
        with engine.begin() as connection:
            rows = connection.execute(runs.select().where(runs.c.status == "processing")).mappings().all()
            for row in rows:
                connection.execute(candidates.delete().where(candidates.c.detection_id == row["id"]))
                result = connection.execute(runs.delete().where(runs.c.id == row["id"], runs.c.status == "processing"))
                removed += result.rowcount or 0
        return {"removed": removed}
    finally:
        engine.dispose()


def _normalize_cut_events(
    *,
    cut_events: Iterable[CutEvent],
    proxy_start_us: int,
    proxy_end_us: int,
    min_boundary_gap_us: int,
) -> tuple[CutEvent, ...]:
    """过滤区间外事件、同时间去重，并在固定近邻窗口内保留最高分边界。"""

    by_timestamp: dict[int, CutEvent] = {}
    for event in cut_events:
        if not proxy_start_us < event.proxy_time_us < proxy_end_us:
            continue
        existing = by_timestamp.get(event.proxy_time_us)
        if existing is None or event.boundary_score > existing.boundary_score:
            by_timestamp[event.proxy_time_us] = event

    ordered = sorted(by_timestamp.values(), key=lambda event: event.proxy_time_us)
    if min_boundary_gap_us == 0 or len(ordered) <= 1:
        return tuple(ordered)

    normalized: list[CutEvent] = []
    cluster: list[CutEvent] = []
    cluster_start_us: int | None = None
    for event in ordered:
        if cluster_start_us is None or event.proxy_time_us - cluster_start_us <= min_boundary_gap_us:
            if cluster_start_us is None:
                cluster_start_us = event.proxy_time_us
            cluster.append(event)
            continue
        normalized.append(max(cluster, key=lambda item: (item.boundary_score, -item.proxy_time_us)))
        cluster = [event]
        cluster_start_us = event.proxy_time_us
    if cluster:
        normalized.append(max(cluster, key=lambda item: (item.boundary_score, -item.proxy_time_us)))

    return tuple(sorted(normalized, key=lambda event: event.proxy_time_us))


def _validate_candidates(
    *,
    candidates: tuple[ShotCandidateRecord, ...],
    proxy_start_us: int,
    proxy_end_us: int,
    proxy_to_source_offset_us: int,
) -> None:
    """在 DB commit 前统一检查跨行连续性；SQLite 单行 CHECK 无法承担这些规则。"""

    if not candidates:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "自动拉片没有生成任何 Shot Candidate")
    expected_source_start = derived_to_source_microseconds(proxy_start_us, proxy_to_source_offset_us)
    expected_source_end = derived_to_source_microseconds(proxy_end_us, proxy_to_source_offset_us)
    if candidates[0].detected_proxy_start_us != proxy_start_us or candidates[0].detected_start_us != expected_source_start:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "第一个 Shot 没有从检测区间起点开始")
    if candidates[-1].detected_proxy_end_us != proxy_end_us or candidates[-1].detected_end_us != expected_source_end:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "最后一个 Shot 没有覆盖到检测区间终点")

    for index, candidate in enumerate(candidates):
        if candidate.ordinal != index + 1:
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Shot Candidate ordinal 不连续")
        if candidate.detected_proxy_end_us <= candidate.detected_proxy_start_us:
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Shot Candidate Proxy 时间区间无效")
        if candidate.detected_end_us <= candidate.detected_start_us:
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Shot Candidate Source 时间区间无效")
        if candidate.duration_us != candidate.detected_end_us - candidate.detected_start_us:
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Shot Candidate duration 与 Source 时间不一致")
        if (
            candidate.detected_proxy_end_us - candidate.detected_proxy_start_us
            != candidate.detected_end_us - candidate.detected_start_us
        ):
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy 与 Source Shot 时长不一致")
        if index + 1 < len(candidates):
            next_candidate = candidates[index + 1]
            if candidate.detected_proxy_end_us != next_candidate.detected_proxy_start_us:
                raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Proxy Shot Candidate 存在 gap 或 overlap")
            if candidate.detected_end_us != next_candidate.detected_start_us:
                raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "Source Shot Candidate 存在 gap 或 overlap")
            if candidate.end_boundary_kind != "cut" or candidate.end_boundary_score is None:
                raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "非末尾 Shot 缺少 cut 自动边界证据")
        elif candidate.end_boundary_kind != "video_end" or candidate.end_boundary_score is not None:
            raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "末尾 Shot 必须以 video_end 收口")


def _require_upstream_snapshot(row: sa.RowMapping, preprocess: SourcePreprocessRecord) -> None:
    """ready F04 读取时确认它仍然对应同一份 F03 输入。"""

    if (
        row["source_video_id"] != preprocess.source_video_id
        or row["preprocess_profile_version"] != preprocess.profile_version
        or row["proxy_sha256_snapshot"] != preprocess.proxy_sha256
        or row["proxy_to_source_offset_us"] != preprocess.proxy_to_source_offset_us
    ):
        raise ShotDetectionError("SHOT_DETECTION_UPSTREAM_CHANGED", "F03 输入与 F04 检测快照不一致，旧结果已失效")


def _require_proxy_integrity(integrity: FileIntegrity, preprocess: SourcePreprocessRecord) -> None:
    if integrity.file_size_bytes != preprocess.proxy_file_size_bytes or integrity.sha256 != preprocess.proxy_sha256:
        raise ShotDetectionError(
            "SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH",
            "磁盘 proxy.mp4 与 F03 完整性记录不一致，已停止自动拉片",
        )


def _delete_processing_run(*, engine: sa.Engine, runs: sa.Table, candidates: sa.Table, detection_id: str) -> None:
    """正常异常路径只删除本次尚未 ready 的 F04 DB 记录，不触碰任何媒体文件。"""

    try:
        with engine.begin() as connection:
            connection.execute(candidates.delete().where(candidates.c.detection_id == detection_id))
            connection.execute(runs.delete().where(runs.c.id == detection_id, runs.c.status == "processing"))
    except SQLAlchemyError:
        # Recovery 会在下次应用启动再次清理 processing；这里不覆盖原始业务异常。
        pass


def _row_to_detection_record(row: sa.RowMapping, candidate_rows: list[sa.RowMapping]) -> ShotDetectionRecord:
    return ShotDetectionRecord(
        id=row["id"],
        project_id=row["project_id"],
        source_video_id=row["source_video_id"],
        status=row["status"],
        detector_name=row["detector_name"],
        detector_profile_version=row["detector_profile_version"],
        detector_threshold=float(row["detector_threshold"]),
        min_boundary_gap_us=row["min_boundary_gap_us"],
        detector_package_version=row["detector_package_version"],
        torch_version=row["torch_version"],
        detector_device=row["detector_device"],
        ffprobe_version=row["ffprobe_version"],
        preprocess_profile_version=row["preprocess_profile_version"],
        proxy_sha256_snapshot=row["proxy_sha256_snapshot"],
        proxy_to_source_offset_us=row["proxy_to_source_offset_us"],
        proxy_start_us=row["proxy_start_us"],
        proxy_end_us=row["proxy_end_us"],
        source_start_us=row["source_start_us"],
        source_end_us=row["source_end_us"],
        analyzed_frame_count=row["analyzed_frame_count"],
        detected_cut_count=row["detected_cut_count"],
        shot_count=row["shot_count"],
        created_at=_as_datetime(row["created_at"]),
        completed_at=_as_datetime(row["completed_at"]) if row["completed_at"] is not None else None,
        candidates=tuple(
            ShotCandidateRecord(
                id=item["id"],
                detection_id=item["detection_id"],
                project_id=item["project_id"],
                ordinal=item["ordinal"],
                detected_proxy_start_us=item["detected_proxy_start_us"],
                detected_proxy_end_us=item["detected_proxy_end_us"],
                detected_start_us=item["detected_start_us"],
                detected_end_us=item["detected_end_us"],
                duration_us=item["duration_us"],
                end_boundary_kind=item["end_boundary_kind"],
                end_boundary_score=float(item["end_boundary_score"]) if item["end_boundary_score"] is not None else None,
            )
            for item in candidate_rows
        ),
    )


def _read_ffprobe_version() -> str:
    try:
        completed = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ShotDetectionError("SHOT_DETECTION_FFPROBE_UNAVAILABLE", "未找到 FFprobe，请先安装并配置到 PATH") from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ShotDetectionError("SHOT_DETECTION_FAILED", "FFprobe 无法启动") from exc
    if completed.returncode != 0:
        raise ShotDetectionError("SHOT_DETECTION_FAILED", "FFprobe 版本读取失败")
    first_line = (completed.stdout or completed.stderr or "").strip().splitlines()
    if not first_line:
        raise ShotDetectionError("SHOT_DETECTION_FAILED", "FFprobe 没有返回版本信息")
    return first_line[0][:256]


def _run_ffprobe_json(command: list[str]) -> dict[str, Any]:
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
        raise ShotDetectionError("SHOT_DETECTION_FFPROBE_UNAVAILABLE", "未找到 FFprobe，请先安装并配置到 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ShotDetectionError("SHOT_DETECTION_FAILED", "FFprobe 逐帧时间扫描超时") from exc
    except OSError as exc:
        raise ShotDetectionError("SHOT_DETECTION_FAILED", "FFprobe 无法读取 Proxy") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        suffix = f"：{detail[-1][:240]}" if detail else ""
        raise ShotDetectionError("SHOT_DETECTION_FAILED", f"FFprobe 读取 Proxy 失败{suffix}")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "FFprobe 返回的逐帧 JSON 无法解析") from exc
    if not isinstance(payload, dict):
        raise ShotDetectionError("SHOT_DETECTION_INVALID_RESULT", "FFprobe 返回结构无效")
    return payload


def _hash_file(path: Path) -> FileIntegrity:
    if not path.is_file():
        raise ShotDetectionError("SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH", "F03 proxy.mp4 不存在")
    hasher = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(FILE_CHUNK_SIZE):
                total += len(chunk)
                hasher.update(chunk)
    except OSError as exc:
        raise ShotDetectionError("SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH", "F03 proxy.mp4 无法读取") from exc
    if total <= 0:
        raise ShotDetectionError("SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH", "F03 proxy.mp4 为空")
    return FileIntegrity(total, hasher.hexdigest())


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
        raise ShotDetectionError("SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH", "F04 Proxy 路径超出 Project Workspace")
    return candidate


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
