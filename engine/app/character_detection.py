"""F06「自动人物识别」核心业务。

正式链路：

F05 confirmed Final Shots
→ F04 已冻结 FFprobe 真实 Proxy PTS
→ 约 4 FPS 自适应采样计划（每 Shot 3–12 个目标点）
→ 目标点吸附到 Shot 内最近的真实 PTS 帧
→ OpenCV 顺序解码 Proxy
→ YuNet Face Detection
→ SFace normalized embedding
→ Shot-local Track
→ 保守式跨 Shot Clustering
→ Character Candidate Evidence

关键边界：
- F06 不命名人物、不产生 Final Character；这些属于 F07。
- F06 不做 Whisper / Dialogue / Speaker；这些属于 F08–F10。
- 正式 Source 时间来自 FFprobe PTS + F03 offset，禁止 frame_index/fps 反推时间。
- 历史 Run 不覆盖；rerun 完整成功后才事务切换 is_current。
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import threading
import uuid
from typing import Any, Iterable

import numpy as np
from PIL import Image
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from engine.app.character_models import (
    CharacterModelError,
    SFACE_SPEC,
    YUNET_SPEC,
    require_character_models,
)
from engine.app.core.database import init_database
from engine.app.core.media_time import derived_to_source_microseconds
from engine.app.preprocess import get_source_preprocess
from engine.app.shot_detection import ShotDetectionError, inspect_proxy_timeline
from engine.app.shot_workbench import (
    FinalShotRecord,
    ShotWorkbenchError,
    get_shot_workbench,
    get_workbench_proxy_path,
    render_workbench_frame,
)

PROFILE_VERSION = "f06-v1"
OPENCV_PACKAGE = "opencv-python"
OPENCV_PACKAGE_VERSION = "4.11.0.86"
RUNTIME_DEVICE = "cpu"

TARGET_SAMPLE_FPS = 4
MIN_SAMPLES_PER_SHOT = 3
MAX_SAMPLES_PER_SHOT = 12
SAMPLE_EDGE_MARGIN_US = 40_000

FACE_SCORE_THRESHOLD = 0.80
FACE_NMS_THRESHOLD = 0.30
FACE_TOP_K = 5000
MIN_FACE_EDGE_PX = 32
SFACE_EMBEDDING_DIM = 128

# Shot 内 Tracking 允许比跨 Shot 聚类略宽松，因为还要求空间连续性。
TRACK_MIN_COSINE = 0.38
TRACK_MIN_IOU = 0.02
TRACK_MAX_CENTER_DISTANCE_IN_FACE_WIDTHS = 1.75
TRACK_MAX_GAP_US = 800_000

# SFace 官方 same-identity cosine 参考为 0.363；F06 V1 故意提高到 0.50，宁可拆开留给 F07 合并。
CLUSTER_MIN_COSINE = 0.50

EMBEDDING_NORM_TOLERANCE = 1e-3
F06_PREVIEW_JPEG_QUALITY = 92
_RUN_LOCK = threading.Lock()


class CharacterDetectionError(RuntimeError):
    """F06 可稳定映射到 HTTP error envelope 的业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CharacterTrackSampleRecord:
    """Track 中一条轻量自动 Evidence，不保存逐帧 embedding/JPEG。"""

    source_time_us: int
    bbox: tuple[int, int, int, int]
    detection_score: float
    face_quality: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = list(self.bbox)
        return payload


@dataclass(frozen=True)
class CharacterTrackRecord:
    """一个 Final Shot 内的一段人物人脸 Track Evidence。"""

    id: str
    run_id: str
    project_id: str
    final_shot_id: str
    final_shot_ordinal: int
    candidate_id: str
    track_ordinal_in_shot: int
    start_us: int
    end_us: int
    representative_source_us: int
    representative_bbox: tuple[int, int, int, int]
    sample_count: int
    mean_face_quality: float
    max_face_quality: float
    samples: tuple[CharacterTrackSampleRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["representative_bbox"] = list(self.representative_bbox)
        payload["samples"] = [sample.to_dict() for sample in self.samples]
        return payload


@dataclass(frozen=True)
class CharacterCandidateRecord:
    """F06 自动聚类人物候选；它不是 F07 Final Character。"""

    id: str
    run_id: str
    project_id: str
    ordinal: int
    track_count: int
    shot_count: int
    first_seen_us: int
    last_seen_us: int
    cover_track_id: str
    cover_source_us: int
    cover_bbox: tuple[int, int, int, int]
    cluster_score: float | None
    tracks: tuple[CharacterTrackRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cover_bbox"] = list(self.cover_bbox)
        payload["tracks"] = [track.to_dict() for track in self.tracks]
        return payload


@dataclass(frozen=True)
class CharacterDetectionRecord:
    """F06 一次 Run 及当前可展示的全部 Character Candidate。"""

    id: str
    project_id: str
    source_edit_set_id: str
    source_edit_set_revision: int
    source_start_us: int
    source_end_us: int
    status: str
    is_current: bool
    profile_version: str
    sampling_profile: dict[str, Any]
    detector_model_id: str
    detector_model_sha256: str
    recognizer_model_id: str
    recognizer_model_sha256: str
    opencv_version: str
    runtime_device: str
    sampled_frame_count: int
    face_observation_count: int
    track_count: int
    candidate_count: int
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    candidates: tuple[CharacterCandidateRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


@dataclass(frozen=True)
class SamplePoint:
    """一个已经吸附到 FFprobe 真实 PTS 的 F06 分析帧。"""

    frame_index: int
    source_time_us: int
    final_shot_id: str
    final_shot_ordinal: int


@dataclass(frozen=True)
class FaceObservation:
    """某一真实 PTS 帧中的一张合格人脸及其 SFace embedding。"""

    final_shot_id: str
    final_shot_ordinal: int
    source_time_us: int
    bbox: tuple[int, int, int, int]
    detection_score: float
    face_quality: float
    embedding: np.ndarray


@dataclass
class TrackDraft:
    """尚未持久化的 Shot-local Track；允许在构建阶段追加 Observation。"""

    id: str
    final_shot_id: str
    final_shot_ordinal: int
    observations: list[FaceObservation] = field(default_factory=list)
    embedding: np.ndarray | None = None
    candidate_id: str = ""
    track_ordinal_in_shot: int = 0

    @property
    def start_us(self) -> int:
        return self.observations[0].source_time_us

    @property
    def end_us(self) -> int:
        return self.observations[-1].source_time_us

    @property
    def sample_count(self) -> int:
        return len(self.observations)

    @property
    def representative(self) -> FaceObservation:
        return max(self.observations, key=lambda item: (item.face_quality, _bbox_area(item.bbox)))


@dataclass
class CandidateDraft:
    """尚未持久化的保守聚类 Candidate。"""

    id: str
    tracks: list[TrackDraft]
    centroid: np.ndarray
    cluster_score: float | None = None
    ordinal: int = 0


def generate_character_detection_id() -> str:
    """生成 F06 Run ID；重跑必须产生新 ID，历史不覆盖。"""

    return f"CHAR_DETECTION_{uuid.uuid4().hex}"


def _generate_candidate_id() -> str:
    """生成 F06 自动 Candidate ID；不能冒充 F07 Final Character ID。"""

    return f"CHAR_CANDIDATE_{uuid.uuid4().hex}"


def _generate_track_id() -> str:
    """生成 Shot-local Track Evidence ID。"""

    return f"TRACK_{uuid.uuid4().hex}"


def get_character_detection(
    *, project_id: str, app_data_path: Path | None = None
) -> CharacterDetectionRecord | None:
    """读取当前 F06 状态。

    读取优先级：
    1. 正在运行的 processing Run（便于页面看到正在分析）；
    2. 当前 is_current=1 的 ready Run；
    3. 没有成功结果时最近一次 failed Run；
    4. 完全未运行返回 None。

    ready Run 必须仍绑定同一套 confirmed F05 Edit Set + revision。
    """

    workbench = _require_confirmed_workbench(project_id=project_id, app_data_path=app_data_path)
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    runs = _table(engine, "character_detection_runs")
    candidates_table = _table(engine, "character_candidates")
    tracks_table = _table(engine, "character_tracks")
    try:
        with engine.connect() as connection:
            processing = connection.execute(
                runs.select()
                .where((runs.c.project_id == project_id) & (runs.c.status == "processing"))
                .order_by(runs.c.created_at.desc())
            ).mappings().first()
            if processing is not None:
                return _row_to_detection(processing, workbench, ())

            run_row = connection.execute(
                runs.select().where((runs.c.project_id == project_id) & (runs.c.is_current == 1))
            ).mappings().first()
            if run_row is None:
                run_row = connection.execute(
                    runs.select()
                    .where(runs.c.project_id == project_id)
                    .order_by(runs.c.created_at.desc())
                ).mappings().first()
            if run_row is None:
                return None

            if run_row["status"] == "ready":
                _validate_run_upstream(run_row, workbench)
                candidate_rows = list(
                    connection.execute(
                        candidates_table.select()
                        .where(candidates_table.c.run_id == run_row["id"])
                        .order_by(candidates_table.c.ordinal.asc())
                    ).mappings().all()
                )
                track_rows = list(
                    connection.execute(
                        tracks_table.select()
                        .where(tracks_table.c.run_id == run_row["id"])
                        .order_by(
                            tracks_table.c.candidate_id.asc(),
                            tracks_table.c.start_us.asc(),
                            tracks_table.c.track_ordinal_in_shot.asc(),
                        )
                    ).mappings().all()
                )
                records = _rows_to_candidates(candidate_rows, track_rows, workbench.shots)
                _validate_persisted_result(run_row, records)
                return _row_to_detection(run_row, workbench, records)

            return _row_to_detection(run_row, workbench, ())
    finally:
        engine.dispose()


def run_character_detection(
    *, project_id: str, app_data_path: Path | None = None
) -> CharacterDetectionRecord:
    """首次执行 F06 自动人物识别；已有 current ready Run 时拒绝静默覆盖。"""

    return _execute_character_detection(project_id=project_id, app_data_path=app_data_path, rerun=False)


def rerun_character_detection(
    *, project_id: str, app_data_path: Path | None = None
) -> CharacterDetectionRecord:
    """显式重跑 F06；旧 current ready 结果保留到新 Run 完整验证并事务切换成功。"""

    return _execute_character_detection(project_id=project_id, app_data_path=app_data_path, rerun=True)


def recover_character_detections(app_data_path: Path | None = None) -> int:
    """应用重启时把上次进程遗留的 processing F06 Run 标为 failed。

    F06 是同步本地推理，没有可恢复的外部 Provider task。Python 进程已经消失时，旧
    processing 不可能继续，因此必须显式失败，避免页面永远显示“处理中”。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    runs = _table(engine, "character_detection_runs")
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            result = connection.execute(
                runs.update()
                .where(runs.c.status == "processing")
                .values(
                    status="failed",
                    is_current=0,
                    completed_at=now,
                    error_code="CHARACTER_DETECTION_INTERRUPTED",
                    error_message="上次自动人物识别在应用退出前未完成，请重新运行",
                )
            )
            return int(result.rowcount or 0)
    finally:
        engine.dispose()


def render_character_candidate_cover(
    *, project_id: str, candidate_id: str, app_data_path: Path | None = None
) -> Path:
    """从当前 Candidate 的 Source time + bbox 重建头像 JPEG，并做可删除磁盘缓存。

    F06 Candidate 业务证据在 DB；这个 JPEG 只是 UI cache。缓存丢失时会复用 F05 的
    Source-time frame service 重新拿整帧，再裁出人脸，不改变 Candidate 数据。
    """

    detection = get_character_detection(project_id=project_id, app_data_path=app_data_path)
    if detection is None or detection.status != "ready":
        raise CharacterDetectionError("CHARACTER_DETECTION_NOT_READY", "自动人物识别结果尚未就绪")
    candidate = next((item for item in detection.candidates if item.id == candidate_id), None)
    if candidate is None:
        raise CharacterDetectionError("CHARACTER_CANDIDATE_NOT_FOUND", "人物候选不存在或不属于当前 Run")

    workspace = _project_workspace(project_id=project_id, app_data_path=app_data_path)
    cache_dir = workspace / ".cache" / "f06" / "candidates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{candidate.id}.jpg"
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    source_frame = render_workbench_frame(
        project_id=project_id,
        source_time_us=candidate.cover_source_us,
        app_data_path=app_data_path,
    )
    try:
        with Image.open(source_frame) as image:
            image = image.convert("RGB")
            x, y, width, height = candidate.cover_bbox
            margin_x = int(round(width * 0.22))
            margin_y = int(round(height * 0.28))
            left = max(0, x - margin_x)
            top = max(0, y - margin_y)
            right = min(image.width, x + width + margin_x)
            bottom = min(image.height, y + height + margin_y)
            if right <= left or bottom <= top:
                raise ValueError("invalid crop")
            crop = image.crop((left, top, right, bottom))
            temp_path = cache_path.with_suffix(".jpg.part")
            crop.save(temp_path, format="JPEG", quality=F06_PREVIEW_JPEG_QUALITY, optimize=True)
            temp_path.replace(cache_path)
    except (OSError, ValueError) as exc:
        cache_path.unlink(missing_ok=True)
        raise CharacterDetectionError("CHARACTER_COVER_RENDER_FAILED", "人物候选头像生成失败") from exc
    return cache_path


def _execute_character_detection(
    *, project_id: str, app_data_path: Path | None, rerun: bool
) -> CharacterDetectionRecord:
    """F06 run/rerun 共享的完整事务编排。"""

    workbench = _require_confirmed_workbench(project_id=project_id, app_data_path=app_data_path)
    preprocess = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
    if preprocess is None:
        raise CharacterDetectionError("CHARACTER_DETECTION_PROXY_REQUIRED", "F03 Proxy 不存在，无法识别人脸")

    try:
        model_paths = require_character_models(app_data_path)
    except CharacterModelError as exc:
        raise CharacterDetectionError(exc.code, exc.message) from exc

    cv2, detector, recognizer, opencv_version = _prepare_opencv_runtime(model_paths)
    proxy_path = _get_proxy_path(project_id=project_id, app_data_path=app_data_path)
    try:
        timeline = inspect_proxy_timeline(proxy_path=proxy_path)
    except ShotDetectionError as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_PTS_FAILED", f"无法读取 Proxy 真实帧时间：{exc.message}") from exc

    frame_source_pts = tuple(
        derived_to_source_microseconds(value, preprocess.proxy_to_source_offset_us)
        for value in timeline.frame_pts_us
    )
    sample_plan = _build_sample_plan(shots=workbench.shots, frame_source_pts=frame_source_pts)
    sampling_profile = _sampling_profile()

    database_path = init_database(app_data_path)

    # 单用户 V1 只允许一个本地人物推理任务实际进入模型区，避免重复按钮同时全片解码。
    if not _RUN_LOCK.acquire(blocking=False):
        raise CharacterDetectionError("CHARACTER_DETECTION_IN_PROGRESS", "已有自动人物识别任务正在运行")

    run_id = ""
    try:
        run_id = _create_processing_run(
            database_path=database_path,
            project_id=project_id,
            workbench=workbench,
            rerun=rerun,
            opencv_version=opencv_version,
            sampling_profile=sampling_profile,
        )
        observations = _detect_and_embed_faces(
            cv2=cv2,
            detector=detector,
            recognizer=recognizer,
            proxy_path=proxy_path,
            sample_plan=sample_plan,
            expected_frame_count=len(timeline.frame_pts_us),
        )
        tracks = _build_shot_tracks(observations)
        candidates = _cluster_tracks(tracks)
        _validate_algorithm_result(
            workbench=workbench,
            sample_plan=sample_plan,
            observations=observations,
            tracks=tracks,
            candidates=candidates,
        )
        _persist_ready_result(
            database_path=database_path,
            run_id=run_id,
            project_id=project_id,
            sample_plan=sample_plan,
            observations=observations,
            tracks=tracks,
            candidates=candidates,
        )
    except CharacterDetectionError as exc:
        if run_id:
            _mark_run_failed(database_path=database_path, run_id=run_id, error=exc)
        raise
    except Exception as exc:
        wrapped = CharacterDetectionError("CHARACTER_DETECTION_FAILED", "自动人物识别执行失败")
        if run_id:
            _mark_run_failed(database_path=database_path, run_id=run_id, error=wrapped)
        raise wrapped from exc
    finally:
        _RUN_LOCK.release()

    result = get_character_detection(project_id=project_id, app_data_path=app_data_path)
    if result is None or result.id != run_id or result.status != "ready":
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "人物识别完成后无法读取新的 Ready Run")
    return result


def _prepare_opencv_runtime(model_paths: dict[str, Path]) -> tuple[Any, Any, Any, str]:
    """加载固定 OpenCV + YuNet + SFace；这里只准备 runtime，不解码视频。"""

    try:
        package_version = importlib.metadata.version(OPENCV_PACKAGE)
        import cv2
    except (ImportError, ModuleNotFoundError, importlib.metadata.PackageNotFoundError) as exc:
        raise CharacterDetectionError(
            "CHARACTER_DETECTION_RUNTIME_UNAVAILABLE",
            "未安装 F06 OpenCV 依赖，请执行 python -m pip install -r engine/requirements.txt",
        ) from exc
    if package_version != OPENCV_PACKAGE_VERSION:
        raise CharacterDetectionError(
            "CHARACTER_DETECTION_RUNTIME_INVALID",
            f"F06 要求 {OPENCV_PACKAGE}=={OPENCV_PACKAGE_VERSION}，当前为 {package_version}",
        )

    yunet_path = model_paths[YUNET_SPEC.logical_id]
    sface_path = model_paths[SFACE_SPEC.logical_id]
    try:
        detector = cv2.FaceDetectorYN.create(
            str(yunet_path), "", (320, 320), FACE_SCORE_THRESHOLD, FACE_NMS_THRESHOLD, FACE_TOP_K
        )
        recognizer = cv2.FaceRecognizerSF.create(str(sface_path), "")
    except Exception as exc:
        raise CharacterDetectionError("CHARACTER_MODEL_INVALID", "OpenCV 无法加载固定 YuNet / SFace 模型") from exc
    return cv2, detector, recognizer, str(cv2.__version__)


def _build_sample_plan(
    *, shots: Iterable[FinalShotRecord], frame_source_pts: tuple[int, ...]
) -> tuple[SamplePoint, ...]:
    """把 4 FPS 目标采样点吸附到每个 Final Shot 内最近的真实 PTS 帧。

    数量按已确认 Contract 使用 round-half-up：
    ``round_half_up(duration_us * 4 / 1_000_000)``，再 clamp 到 3–12。

    这里允许使用 frame index 作为“解码顺序索引”，但 ``SamplePoint.source_time_us`` 只能
    来自 ``frame_source_pts[index]``，绝不使用 index/fps 推算正式时间。
    """

    if not frame_source_pts:
        raise CharacterDetectionError("CHARACTER_DETECTION_PTS_FAILED", "Proxy 没有可用的真实帧 PTS")
    if any(current < previous for previous, current in zip(frame_source_pts, frame_source_pts[1:])):
        raise CharacterDetectionError("CHARACTER_DETECTION_PTS_FAILED", "Proxy Source PTS 不是非递减顺序")

    selected: dict[int, SamplePoint] = {}
    for shot in shots:
        left = bisect_left(frame_source_pts, shot.final_start_us)
        right = bisect_left(frame_source_pts, shot.final_end_us)
        if left >= right:
            # 极短镜头在 Proxy 中没有独立解码帧时不补造假时间；该 Shot 本轮不会产生人物 Evidence。
            continue

        rounded_target_count = (shot.duration_us * TARGET_SAMPLE_FPS + 500_000) // 1_000_000
        target_count = max(
            MIN_SAMPLES_PER_SHOT,
            min(MAX_SAMPLES_PER_SHOT, int(rounded_target_count)),
        )
        margin = min(SAMPLE_EDGE_MARGIN_US, max(0, shot.duration_us // 20))
        target_start = shot.final_start_us + margin
        target_end = max(target_start, shot.final_end_us - 1 - margin)
        if target_count <= 1 or target_end <= target_start:
            targets = (target_start,)
        else:
            span = target_end - target_start
            targets = tuple(
                target_start + int(round(span * index / (target_count - 1)))
                for index in range(target_count)
            )

        for target in targets:
            frame_index = _nearest_frame_index(frame_source_pts, target, left, right)
            selected[frame_index] = SamplePoint(
                frame_index=frame_index,
                source_time_us=frame_source_pts[frame_index],
                final_shot_id=shot.id,
                final_shot_ordinal=shot.ordinal,
            )

    return tuple(selected[index] for index in sorted(selected))


def _nearest_frame_index(values: tuple[int, ...], target: int, left: int, right: int) -> int:
    """在 [left,right) 内找最接近 target 的真实 PTS 索引。"""

    position = bisect_left(values, target, left, right)
    if position <= left:
        return left
    if position >= right:
        return right - 1
    before = position - 1
    return before if abs(values[before] - target) <= abs(values[position] - target) else position


def _detect_and_embed_faces(
    *,
    cv2: Any,
    detector: Any,
    recognizer: Any,
    proxy_path: Path,
    sample_plan: tuple[SamplePoint, ...],
    expected_frame_count: int,
) -> tuple[FaceObservation, ...]:
    """顺序解码一次 Proxy，只对采样 frame index 执行 YuNet + SFace。

    解码结束时 frame count 必须与 FFprobe PTS 数量一致；否则 index 与真实 PTS 不能安全对齐，
    整个 Run 失败，不允许继续写 Evidence。
    """

    if not sample_plan:
        return ()
    selected_by_index = {item.frame_index: item for item in sample_plan}
    capture = cv2.VideoCapture(str(proxy_path))
    if not capture.isOpened():
        raise CharacterDetectionError("CHARACTER_DETECTION_VIDEO_OPEN_FAILED", "OpenCV 无法打开 F03 Proxy")

    observations: list[FaceObservation] = []
    frame_index = 0
    input_size: tuple[int, int] | None = None
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            sample = selected_by_index.get(frame_index)
            if sample is not None:
                height, width = frame.shape[:2]
                size = (int(width), int(height))
                if input_size != size:
                    detector.setInputSize(size)
                    input_size = size
                try:
                    _, faces = detector.detect(frame)
                except Exception as exc:
                    raise CharacterDetectionError("CHARACTER_DETECTION_MODEL_FAILED", "YuNet 人脸检测失败") from exc
                if faces is not None:
                    for face in faces:
                        observation = _face_row_to_observation(
                            cv2=cv2,
                            recognizer=recognizer,
                            frame=frame,
                            face=face,
                            sample=sample,
                        )
                        if observation is not None:
                            observations.append(observation)
            frame_index += 1
    finally:
        capture.release()

    if frame_index != expected_frame_count:
        raise CharacterDetectionError(
            "CHARACTER_DETECTION_FRAME_ALIGNMENT_FAILED",
            f"OpenCV 解码帧数 {frame_index} 与 FFprobe PTS 数 {expected_frame_count} 不一致，拒绝用错位 frame index 绑定时间",
        )
    return tuple(observations)


def _face_row_to_observation(
    *, cv2: Any, recognizer: Any, frame: np.ndarray, face: np.ndarray, sample: SamplePoint
) -> FaceObservation | None:
    """把一个 YuNet face row 转成经过质量门槛的 SFace Observation。"""

    values = np.asarray(face, dtype=np.float32).reshape(-1)
    if values.size < 15:
        return None
    x, y, width, height = (int(round(float(value))) for value in values[:4])
    detection_score = float(values[14])
    if detection_score < FACE_SCORE_THRESHOLD or width < MIN_FACE_EDGE_PX or height < MIN_FACE_EDGE_PX:
        return None

    image_h, image_w = frame.shape[:2]
    x = max(0, min(x, image_w - 1))
    y = max(0, min(y, image_h - 1))
    width = max(1, min(width, image_w - x))
    height = max(1, min(height, image_h - y))
    if width < MIN_FACE_EDGE_PX or height < MIN_FACE_EDGE_PX:
        return None
    bbox = (x, y, width, height)

    try:
        aligned = recognizer.alignCrop(frame, values)
        feature = np.asarray(recognizer.feature(aligned), dtype=np.float32).reshape(-1)
    except Exception as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_MODEL_FAILED", "SFace 对齐或特征提取失败") from exc
    embedding = _normalize_embedding(feature)
    quality = _face_quality(cv2=cv2, frame=frame, bbox=bbox, detection_score=detection_score)
    return FaceObservation(
        final_shot_id=sample.final_shot_id,
        final_shot_ordinal=sample.final_shot_ordinal,
        source_time_us=sample.source_time_us,
        bbox=bbox,
        detection_score=detection_score,
        face_quality=quality,
        embedding=embedding,
    )


def _normalize_embedding(feature: np.ndarray) -> np.ndarray:
    """把 SFace feature 固定为 128 维 finite normalized float32。"""

    vector = np.asarray(feature, dtype=np.float32).reshape(-1)
    if vector.size != SFACE_EMBEDDING_DIM or not np.all(np.isfinite(vector)):
        raise CharacterDetectionError("CHARACTER_DETECTION_MODEL_FAILED", "SFace embedding 维度或数值无效")
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1e-8:
        raise CharacterDetectionError("CHARACTER_DETECTION_MODEL_FAILED", "SFace embedding 范数无效")
    return np.ascontiguousarray(vector / norm, dtype=np.float32)


def _face_quality(*, cv2: Any, frame: np.ndarray, bbox: tuple[int, int, int, int], detection_score: float) -> float:
    """用检测置信度 + 人脸尺寸 + 清晰度选择更适合作 Cover 的 Evidence。"""

    x, y, width, height = bbox
    crop = frame[y : y + height, x : x + width]
    if crop.size == 0:
        return max(0.0, min(1.0, detection_score * 0.7))
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = min(1.0, sharpness / 250.0)
    image_h, image_w = frame.shape[:2]
    face_area_ratio = (width * height) / max(1, image_w * image_h)
    size_score = min(1.0, math.sqrt(face_area_ratio) / 0.22)
    quality = 0.55 * detection_score + 0.25 * size_score + 0.20 * sharpness_score
    return float(max(0.0, min(1.0, quality)))


def _build_shot_tracks(observations: tuple[FaceObservation, ...]) -> list[TrackDraft]:
    """在每个 Final Shot 内用 embedding + 空间连续性构建轻量 Track。"""

    by_shot: dict[str, list[FaceObservation]] = defaultdict(list)
    for observation in observations:
        by_shot[observation.final_shot_id].append(observation)

    all_tracks: list[TrackDraft] = []
    for shot_observations in by_shot.values():
        shot_observations.sort(key=lambda item: (item.source_time_us, item.bbox[0], item.bbox[1]))
        frames: dict[int, list[FaceObservation]] = defaultdict(list)
        for observation in shot_observations:
            frames[observation.source_time_us].append(observation)

        tracks: list[TrackDraft] = []
        for source_time_us in sorted(frames):
            current = frames[source_time_us]
            pairs: list[tuple[float, int, int]] = []
            for track_index, track in enumerate(tracks):
                last = track.observations[-1]
                if source_time_us - last.source_time_us > TRACK_MAX_GAP_US:
                    continue
                for observation_index, observation in enumerate(current):
                    cosine = _cosine_similarity(track.embedding if track.embedding is not None else last.embedding, observation.embedding)
                    iou = _bbox_iou(last.bbox, observation.bbox)
                    center_distance = _center_distance_in_face_widths(last.bbox, observation.bbox)
                    geometry_ok = iou >= TRACK_MIN_IOU or center_distance <= TRACK_MAX_CENTER_DISTANCE_IN_FACE_WIDTHS
                    if cosine >= TRACK_MIN_COSINE and geometry_ok:
                        score = cosine + min(0.08, iou * 0.08) - min(0.08, center_distance * 0.02)
                        pairs.append((score, track_index, observation_index))

            used_tracks: set[int] = set()
            used_observations: set[int] = set()
            for _, track_index, observation_index in sorted(pairs, reverse=True):
                if track_index in used_tracks or observation_index in used_observations:
                    continue
                track = tracks[track_index]
                track.observations.append(current[observation_index])
                track.embedding = _mean_normalized([item.embedding for item in track.observations])
                used_tracks.add(track_index)
                used_observations.add(observation_index)

            for observation_index, observation in enumerate(current):
                if observation_index in used_observations:
                    continue
                tracks.append(
                    TrackDraft(
                        id=_generate_track_id(),
                        final_shot_id=observation.final_shot_id,
                        final_shot_ordinal=observation.final_shot_ordinal,
                        observations=[observation],
                        embedding=observation.embedding.copy(),
                    )
                )

        tracks.sort(key=lambda item: (item.start_us, item.representative.bbox[0], item.representative.bbox[1]))
        for ordinal, track in enumerate(tracks, start=1):
            track.track_ordinal_in_shot = ordinal
        all_tracks.extend(tracks)

    all_tracks.sort(key=lambda item: (item.start_us, item.final_shot_ordinal, item.track_ordinal_in_shot))
    return all_tracks


def _cluster_tracks(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    """保守式跨 Shot 聚类：高阈值 + 同时共现硬冲突，宁可拆错不自动合错。"""

    candidates: list[CandidateDraft] = []
    ordered_tracks = sorted(
        tracks,
        key=lambda item: (
            -item.representative.face_quality,
            item.start_us,
            item.final_shot_ordinal,
            item.track_ordinal_in_shot,
        ),
    )
    for track in ordered_tracks:
        if track.embedding is None:
            raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Track 缺少 embedding")
        best: CandidateDraft | None = None
        best_similarity = -1.0
        for candidate in candidates:
            if any(_tracks_conflict(track, existing) for existing in candidate.tracks):
                continue
            similarity = _cosine_similarity(track.embedding, candidate.centroid)
            if similarity >= CLUSTER_MIN_COSINE and similarity > best_similarity:
                best = candidate
                best_similarity = similarity
        if best is None:
            candidates.append(
                CandidateDraft(
                    id=_generate_candidate_id(),
                    tracks=[track],
                    centroid=track.embedding.copy(),
                )
            )
        else:
            best.tracks.append(track)
            best.centroid = _weighted_track_centroid(best.tracks)

    candidates.sort(key=lambda item: min(track.start_us for track in item.tracks))
    for ordinal, candidate in enumerate(candidates, start=1):
        candidate.ordinal = ordinal
        candidate.centroid = _weighted_track_centroid(candidate.tracks)
        similarities = [_cosine_similarity(track.embedding, candidate.centroid) for track in candidate.tracks if track.embedding is not None]
        candidate.cluster_score = None if len(similarities) <= 1 else float(max(0.0, min(1.0, sum(similarities) / len(similarities))))
        for track in candidate.tracks:
            track.candidate_id = candidate.id
    return candidates


def _tracks_conflict(left: TrackDraft, right: TrackDraft) -> bool:
    """同一 Shot 且 Evidence 时间区间重叠时，两条 Track 不能自动归为同一个人。"""

    if left.final_shot_id != right.final_shot_id:
        return False
    return max(left.start_us, right.start_us) <= min(left.end_us, right.end_us)


def _validate_algorithm_result(
    *,
    workbench: Any,
    sample_plan: tuple[SamplePoint, ...],
    observations: tuple[FaceObservation, ...],
    tracks: list[TrackDraft],
    candidates: list[CandidateDraft],
) -> None:
    """在写 DB 前验证引用、时间、embedding 和 Candidate assignment 完整性。"""

    shots = {shot.id: shot for shot in workbench.shots}
    if any(item.final_shot_id not in shots for item in sample_plan):
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "采样计划引用了未知 Final Shot")
    for observation in observations:
        shot = shots.get(observation.final_shot_id)
        if shot is None or not shot.final_start_us <= observation.source_time_us < shot.final_end_us:
            raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "人脸 Evidence 时间超出所属 Final Shot")
        _validate_embedding(observation.embedding)
    track_ids = {track.id for track in tracks}
    if len(track_ids) != len(tracks):
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Track ID 重复")
    for track in tracks:
        if not track.observations or track.embedding is None or not track.candidate_id:
            raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Track 数据不完整")
        _validate_embedding(track.embedding)
    candidate_ids = {candidate.id for candidate in candidates}
    if len(candidate_ids) != len(candidates):
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Candidate ID 重复")
    assigned = [track.id for candidate in candidates for track in candidate.tracks]
    if sorted(assigned) != sorted(track_ids):
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "每个 Track 必须且只能属于一个 Candidate")
    for candidate in candidates:
        _validate_embedding(candidate.centroid)


def _create_processing_run(
    *,
    database_path: Path,
    project_id: str,
    workbench: Any,
    rerun: bool,
    opencv_version: str,
    sampling_profile: dict[str, Any],
) -> str:
    """先持久化 processing Run，防止失败时完全没有审计记录。"""

    engine = _database_engine(database_path)
    runs = _table(engine, "character_detection_runs")
    run_id = generate_character_detection_id()
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            processing = connection.execute(
                runs.select().where((runs.c.project_id == project_id) & (runs.c.status == "processing"))
            ).mappings().first()
            if processing is not None:
                raise CharacterDetectionError("CHARACTER_DETECTION_IN_PROGRESS", "当前项目已有自动人物识别正在运行")
            current = connection.execute(
                runs.select().where((runs.c.project_id == project_id) & (runs.c.is_current == 1))
            ).mappings().first()
            if rerun and current is None:
                raise CharacterDetectionError("CHARACTER_DETECTION_RERUN_NOT_READY", "当前没有可重跑的 Ready 人物识别结果")
            if not rerun and current is not None:
                raise CharacterDetectionError("CHARACTER_DETECTION_ALREADY_EXISTS", "当前项目已经存在自动人物识别结果")

            connection.execute(
                runs.insert().values(
                    id=run_id,
                    project_id=project_id,
                    source_edit_set_id=workbench.id,
                    source_edit_set_revision=workbench.revision,
                    status="processing",
                    is_current=0,
                    profile_version=PROFILE_VERSION,
                    sampling_profile_json=json.dumps(sampling_profile, ensure_ascii=False, separators=(",", ":")),
                    detector_model_id=YUNET_SPEC.logical_id,
                    detector_model_sha256=YUNET_SPEC.sha256,
                    recognizer_model_id=SFACE_SPEC.logical_id,
                    recognizer_model_sha256=SFACE_SPEC.sha256,
                    opencv_version=opencv_version,
                    runtime_device=RUNTIME_DEVICE,
                    sampled_frame_count=0,
                    face_observation_count=0,
                    track_count=0,
                    candidate_count=0,
                    started_at=now,
                    completed_at=None,
                    error_code=None,
                    error_message=None,
                    created_at=now,
                )
            )
    finally:
        engine.dispose()
    return run_id


def _persist_ready_result(
    *,
    database_path: Path,
    run_id: str,
    project_id: str,
    sample_plan: tuple[SamplePoint, ...],
    observations: tuple[FaceObservation, ...],
    tracks: list[TrackDraft],
    candidates: list[CandidateDraft],
) -> None:
    """一次事务写 Candidate/Track 并原子切换 current Run。"""

    engine = _database_engine(database_path)
    runs = _table(engine, "character_detection_runs")
    candidate_table = _table(engine, "character_candidates")
    track_table = _table(engine, "character_tracks")
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            run_row = connection.execute(runs.select().where(runs.c.id == run_id)).mappings().first()
            if run_row is None or run_row["status"] != "processing":
                raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "F06 processing Run 状态已改变")

            for candidate in candidates:
                cover_track = max(
                    candidate.tracks,
                    key=lambda item: (item.representative.face_quality, _bbox_area(item.representative.bbox)),
                )
                cover = cover_track.representative
                first_seen = min(track.start_us for track in candidate.tracks)
                last_seen = max(track.end_us for track in candidate.tracks)
                shot_count = len({track.final_shot_id for track in candidate.tracks})
                connection.execute(
                    candidate_table.insert().values(
                        id=candidate.id,
                        run_id=run_id,
                        project_id=project_id,
                        ordinal=candidate.ordinal,
                        track_count=len(candidate.tracks),
                        shot_count=shot_count,
                        first_seen_us=first_seen,
                        last_seen_us=last_seen,
                        cover_track_id=cover_track.id,
                        cover_source_us=cover.source_time_us,
                        cover_bbox_json=_encode_bbox(cover.bbox),
                        centroid_embedding_blob=_embedding_to_blob(candidate.centroid),
                        cluster_score=candidate.cluster_score,
                        created_at=now,
                    )
                )

            for track in tracks:
                representative = track.representative
                qualities = [item.face_quality for item in track.observations]
                connection.execute(
                    track_table.insert().values(
                        id=track.id,
                        run_id=run_id,
                        project_id=project_id,
                        final_shot_id=track.final_shot_id,
                        candidate_id=track.candidate_id,
                        track_ordinal_in_shot=track.track_ordinal_in_shot,
                        start_us=track.start_us,
                        end_us=track.end_us,
                        representative_source_us=representative.source_time_us,
                        representative_bbox_json=_encode_bbox(representative.bbox),
                        sample_count=track.sample_count,
                        mean_face_quality=float(sum(qualities) / len(qualities)),
                        max_face_quality=float(max(qualities)),
                        track_embedding_blob=_embedding_to_blob(track.embedding),
                        samples_json=_encode_samples(track.observations),
                        created_at=now,
                    )
                )

            # 新 Run 的所有 Evidence 已经在同一事务内写完，才撤销旧 current 并切换。
            connection.execute(
                runs.update()
                .where((runs.c.project_id == project_id) & (runs.c.is_current == 1))
                .values(is_current=0)
            )
            connection.execute(
                runs.update().where(runs.c.id == run_id).values(
                    status="ready",
                    is_current=1,
                    sampled_frame_count=len(sample_plan),
                    face_observation_count=len(observations),
                    track_count=len(tracks),
                    candidate_count=len(candidates),
                    completed_at=now,
                    error_code=None,
                    error_message=None,
                )
            )
    except SQLAlchemyError as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_PERSIST_FAILED", "自动人物识别结果保存失败") from exc
    finally:
        engine.dispose()


def _mark_run_failed(*, database_path: Path, run_id: str, error: CharacterDetectionError) -> None:
    """失败 Run 单独落 failed；不动上一份 is_current ready 结果。"""

    engine = _database_engine(database_path)
    runs = _table(engine, "character_detection_runs")
    try:
        with engine.begin() as connection:
            connection.execute(
                runs.update()
                .where((runs.c.id == run_id) & (runs.c.status == "processing"))
                .values(
                    status="failed",
                    is_current=0,
                    completed_at=datetime.now(timezone.utc),
                    error_code=error.code,
                    error_message=error.message,
                )
            )
    finally:
        engine.dispose()


def _rows_to_candidates(
    candidate_rows: list[sa.RowMapping], track_rows: list[sa.RowMapping], shots: tuple[FinalShotRecord, ...]
) -> tuple[CharacterCandidateRecord, ...]:
    """把 DB Evidence 转成 API Record；embedding 只校验，不暴露给前端。"""

    shot_ordinals = {shot.id: shot.ordinal for shot in shots}
    tracks_by_candidate: dict[str, list[CharacterTrackRecord]] = defaultdict(list)
    for row in track_rows:
        _blob_to_embedding(row["track_embedding_blob"])
        samples = _decode_samples(row["samples_json"])
        tracks_by_candidate[row["candidate_id"]].append(
            CharacterTrackRecord(
                id=row["id"],
                run_id=row["run_id"],
                project_id=row["project_id"],
                final_shot_id=row["final_shot_id"],
                final_shot_ordinal=shot_ordinals.get(row["final_shot_id"], 0),
                candidate_id=row["candidate_id"],
                track_ordinal_in_shot=row["track_ordinal_in_shot"],
                start_us=row["start_us"],
                end_us=row["end_us"],
                representative_source_us=row["representative_source_us"],
                representative_bbox=_decode_bbox(row["representative_bbox_json"]),
                sample_count=row["sample_count"],
                mean_face_quality=float(row["mean_face_quality"]),
                max_face_quality=float(row["max_face_quality"]),
                samples=samples,
            )
        )

    records: list[CharacterCandidateRecord] = []
    for row in candidate_rows:
        _blob_to_embedding(row["centroid_embedding_blob"])
        tracks = tuple(sorted(tracks_by_candidate.get(row["id"], []), key=lambda item: (item.start_us, item.final_shot_ordinal, item.track_ordinal_in_shot)))
        records.append(
            CharacterCandidateRecord(
                id=row["id"],
                run_id=row["run_id"],
                project_id=row["project_id"],
                ordinal=row["ordinal"],
                track_count=row["track_count"],
                shot_count=row["shot_count"],
                first_seen_us=row["first_seen_us"],
                last_seen_us=row["last_seen_us"],
                cover_track_id=row["cover_track_id"],
                cover_source_us=row["cover_source_us"],
                cover_bbox=_decode_bbox(row["cover_bbox_json"]),
                cluster_score=float(row["cluster_score"]) if row["cluster_score"] is not None else None,
                tracks=tracks,
            )
        )
    return tuple(records)


def _row_to_detection(
    row: sa.RowMapping, workbench: Any, candidates: tuple[CharacterCandidateRecord, ...]
) -> CharacterDetectionRecord:
    try:
        profile = json.loads(row["sampling_profile_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "F06 sampling profile JSON 损坏") from exc
    return CharacterDetectionRecord(
        id=row["id"],
        project_id=row["project_id"],
        source_edit_set_id=row["source_edit_set_id"],
        source_edit_set_revision=row["source_edit_set_revision"],
        source_start_us=workbench.source_start_us,
        source_end_us=workbench.source_end_us,
        status=row["status"],
        is_current=bool(row["is_current"]),
        profile_version=row["profile_version"],
        sampling_profile=profile,
        detector_model_id=row["detector_model_id"],
        detector_model_sha256=row["detector_model_sha256"],
        recognizer_model_id=row["recognizer_model_id"],
        recognizer_model_sha256=row["recognizer_model_sha256"],
        opencv_version=row["opencv_version"],
        runtime_device=row["runtime_device"],
        sampled_frame_count=row["sampled_frame_count"],
        face_observation_count=row["face_observation_count"],
        track_count=row["track_count"],
        candidate_count=row["candidate_count"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        candidates=candidates,
    )


def _validate_run_upstream(row: sa.RowMapping, workbench: Any) -> None:
    if row["source_edit_set_id"] != workbench.id or row["source_edit_set_revision"] != workbench.revision:
        raise CharacterDetectionError(
            "CHARACTER_DETECTION_UPSTREAM_CHANGED",
            "F06 人物结果与当前 F05 Final Shot revision 不一致，不能继续作为正式输入",
        )


def _validate_persisted_result(row: sa.RowMapping, candidates: tuple[CharacterCandidateRecord, ...]) -> None:
    if row["candidate_count"] != len(candidates):
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "F06 Candidate 数量与 Run 统计不一致")
    track_count = sum(len(candidate.tracks) for candidate in candidates)
    if row["track_count"] != track_count:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "F06 Track 数量与 Run 统计不一致")
    for candidate in candidates:
        if candidate.track_count != len(candidate.tracks):
            raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Candidate track_count 与实际 Track 不一致")


def _require_confirmed_workbench(*, project_id: str, app_data_path: Path | None) -> Any:
    try:
        workbench = get_shot_workbench(project_id=project_id, app_data_path=app_data_path)
    except ShotWorkbenchError as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_FINAL_SHOTS_REQUIRED", exc.message) from exc
    if workbench is None or workbench.status != "confirmed":
        raise CharacterDetectionError("CHARACTER_DETECTION_FINAL_SHOTS_REQUIRED", "请先完成并确认 F05 Final Shots")
    return workbench


def _get_proxy_path(*, project_id: str, app_data_path: Path | None) -> Path:
    try:
        return get_workbench_proxy_path(project_id=project_id, app_data_path=app_data_path)
    except ShotWorkbenchError as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_PROXY_REQUIRED", exc.message) from exc


def _sampling_profile() -> dict[str, Any]:
    return {
        "target_fps": TARGET_SAMPLE_FPS,
        "min_samples_per_shot": MIN_SAMPLES_PER_SHOT,
        "max_samples_per_shot": MAX_SAMPLES_PER_SHOT,
        "edge_margin_us": SAMPLE_EDGE_MARGIN_US,
        "face_score_threshold": FACE_SCORE_THRESHOLD,
        "minimum_face_edge_px": MIN_FACE_EDGE_PX,
        "track_min_cosine": TRACK_MIN_COSINE,
        "cluster_min_cosine": CLUSTER_MIN_COSINE,
    }


def _bbox_iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    x1, y1 = max(lx, rx), max(ly, ry)
    x2, y2 = min(lx + lw, rx + rw), min(ly + lh, ry + rh)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = lw * lh + rw * rh - intersection
    return 0.0 if union <= 0 else intersection / union


def _center_distance_in_face_widths(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    left_center = (lx + lw / 2, ly + lh / 2)
    right_center = (rx + rw / 2, ry + rh / 2)
    distance = math.hypot(left_center[0] - right_center[0], left_center[1] - right_center[1])
    scale = max(1.0, (lw + rw) / 2)
    return distance / scale


def _bbox_area(bbox: tuple[int, int, int, int]) -> int:
    return max(0, bbox[2]) * max(0, bbox[3])


def _cosine_similarity(left: np.ndarray | None, right: np.ndarray | None) -> float:
    if left is None or right is None:
        return -1.0
    return float(np.dot(left, right))


def _mean_normalized(vectors: list[np.ndarray]) -> np.ndarray:
    if not vectors:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "无法对空 embedding 集合求中心")
    mean = np.mean(np.stack(vectors, axis=0), axis=0).astype(np.float32)
    return _normalize_embedding(mean)


def _weighted_track_centroid(tracks: list[TrackDraft]) -> np.ndarray:
    vectors: list[np.ndarray] = []
    weights: list[float] = []
    for track in tracks:
        if track.embedding is None:
            continue
        vectors.append(track.embedding)
        weights.append(float(max(1, track.sample_count)))
    if not vectors:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Candidate 没有可用 Track embedding")
    matrix = np.stack(vectors, axis=0)
    centroid = np.average(matrix, axis=0, weights=np.asarray(weights, dtype=np.float32)).astype(np.float32)
    return _normalize_embedding(centroid)


def _validate_embedding(vector: np.ndarray) -> None:
    if vector.shape != (SFACE_EMBEDDING_DIM,) or vector.dtype != np.float32 or not np.all(np.isfinite(vector)):
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Embedding Schema 无效")
    if abs(float(np.linalg.norm(vector)) - 1.0) > EMBEDDING_NORM_TOLERANCE:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "Embedding 没有按 Contract 归一化")


def _embedding_to_blob(vector: np.ndarray | None) -> bytes:
    if vector is None:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "缺少 embedding")
    _validate_embedding(vector)
    return np.asarray(vector, dtype="<f4", order="C").tobytes(order="C")


def _blob_to_embedding(blob: bytes) -> np.ndarray:
    expected_bytes = SFACE_EMBEDDING_DIM * 4
    if not isinstance(blob, (bytes, bytearray, memoryview)) or len(blob) != expected_bytes:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "数据库 embedding BLOB 长度无效")
    vector = np.frombuffer(bytes(blob), dtype="<f4").astype(np.float32, copy=True)
    _validate_embedding(vector)
    return vector


def _encode_bbox(bbox: tuple[int, int, int, int]) -> str:
    return json.dumps(list(bbox), separators=(",", ":"))


def _decode_bbox(payload: str) -> tuple[int, int, int, int]:
    try:
        values = json.loads(payload)
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError
        bbox = tuple(int(value) for value in values)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "数据库 bbox JSON 无效") from exc
    if bbox[2] <= 0 or bbox[3] <= 0:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "数据库 bbox 宽高无效")
    return bbox  # type: ignore[return-value]


def _encode_samples(observations: list[FaceObservation]) -> str:
    payload = [
        {
            "source_time_us": item.source_time_us,
            "bbox": list(item.bbox),
            "detection_score": round(item.detection_score, 6),
            "face_quality": round(item.face_quality, 6),
        }
        for item in observations
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode_samples(payload: str) -> tuple[CharacterTrackSampleRecord, ...]:
    try:
        values = json.loads(payload)
        if not isinstance(values, list) or not values:
            raise ValueError
        result = []
        for item in values:
            if not isinstance(item, dict):
                raise ValueError
            bbox_raw = item["bbox"]
            if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
                raise ValueError
            result.append(
                CharacterTrackSampleRecord(
                    source_time_us=int(item["source_time_us"]),
                    bbox=tuple(int(value) for value in bbox_raw),  # type: ignore[arg-type]
                    detection_score=float(item["detection_score"]),
                    face_quality=float(item["face_quality"]),
                )
            )
        return tuple(result)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_INVALID_RESULT", "数据库 Track samples_json 无效") from exc


def _database_engine(database_path: Path) -> sa.Engine:
    return sa.create_engine(f"sqlite:///{database_path.as_posix()}")


def _table(engine: sa.Engine, name: str) -> sa.Table:
    metadata = sa.MetaData()
    try:
        return sa.Table(name, metadata, autoload_with=engine)
    except sa.exc.NoSuchTableError as exc:
        raise CharacterDetectionError("CHARACTER_DETECTION_SCHEMA_MISSING", f"数据库缺少 F06 表：{name}") from exc


def _project_workspace(*, project_id: str, app_data_path: Path | None) -> Path:
    """读取 Project Workspace 供 F06 UI cache 使用；不修改项目 manifest。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    try:
        with engine.connect() as connection:
            row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().first()
        if row is None:
            raise CharacterDetectionError("CHARACTER_DETECTION_PROJECT_NOT_FOUND", "项目不存在")
        workspace = Path(row["workspace_path"]).expanduser().resolve(strict=False)
        if not workspace.is_dir():
            raise CharacterDetectionError("CHARACTER_DETECTION_WORKSPACE_MISSING", "项目 Workspace 不存在")
        return workspace
    finally:
        engine.dispose()
