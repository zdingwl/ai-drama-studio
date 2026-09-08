from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
from statistics import median

import cv2
from scenedetect.backends.opencv import VideoStreamCv2
from scenedetect.backends.pyav import VideoStreamAv
from scenedetect.detectors import AdaptiveDetector, ThresholdDetector
from scenedetect.scene_manager import compute_downscale_factor

from app.core.errors import AppError


logger = logging.getLogger(__name__)

DETECTOR_PROFILE_VERSION = "p5-short-drama-v2"
DETECTOR_PROFILE = {
    "version": DETECTOR_PROFILE_VERSION,
    "decode_backends": ["pyav", "opencv"],
    "adaptive": {
        "adaptive_threshold": 3.0,
        "min_content_val": 15.0,
        "window_width": 2,
        "min_scene_len": "0.12s",
    },
    "fade_to_black": {
        "threshold": 14.0,
        "min_scene_len": "0.12s",
        "fade_bias": 0.0,
    },
    "flash_or_fade_to_white": {
        "threshold": 242.0,
        "min_scene_len": "0.12s",
        "fade_bias": 0.0,
    },
    "post_filter": {
        "dedupe_window_us": 70_000,
        "min_shot_us": 120_000,
    },
}


@dataclass(frozen=True)
class ShotRange:
    start_us: int
    end_us: int

    @property
    def duration_us(self) -> int:
        return self.end_us - self.start_us


class _ProgressCallbackError(Exception):
    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


def _timecode_us(timecode) -> int:
    return int(round(float(timecode.seconds) * 1_000_000))


def _cluster_cut_candidates(candidates: list[int], *, duration_us: int) -> list[int]:
    dedupe_window_us = int(DETECTOR_PROFILE["post_filter"]["dedupe_window_us"])
    min_shot_us = int(DETECTOR_PROFILE["post_filter"]["min_shot_us"])
    usable = sorted({item for item in candidates if 0 < item < duration_us})
    if not usable:
        return []

    clusters: list[list[int]] = []
    for candidate in usable:
        if not clusters or candidate - clusters[-1][-1] > dedupe_window_us:
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)

    merged = [int(round(median(cluster))) for cluster in clusters]
    filtered: list[int] = []
    previous = 0
    for cut in merged:
        if cut - previous < min_shot_us:
            continue
        if duration_us - cut < min_shot_us:
            continue
        filtered.append(cut)
        previous = cut
    return filtered


def _build_detectors() -> list:
    return [
        AdaptiveDetector(
            adaptive_threshold=3.0,
            min_content_val=15.0,
            window_width=2,
            min_scene_len="0.12s",
        ),
        ThresholdDetector(
            threshold=14.0,
            min_scene_len="0.12s",
            fade_bias=0.0,
            method=ThresholdDetector.Method.FLOOR,
        ),
        ThresholdDetector(
            threshold=242.0,
            min_scene_len="0.12s",
            fade_bias=0.0,
            method=ThresholdDetector.Method.CEILING,
        ),
    ]


def _open_backend(path: Path, backend: str):
    if backend == "pyav":
        return VideoStreamAv(str(path), threading_mode="AUTO")
    if backend == "opencv":
        return VideoStreamCv2(str(path), max_decode_attempts=20)
    raise ValueError(f"unsupported backend: {backend}")


def _emit_progress(callback: Callable[[float], None], ratio: float) -> None:
    try:
        callback(ratio)
    except Exception as exc:
        raise _ProgressCallbackError(exc) from exc


def _scan_with_backend(
    path: Path,
    *,
    backend: str,
    duration_us: int,
    on_progress: Callable[[float], None] | None,
) -> list[int]:
    video = _open_backend(path, backend)
    detectors = _build_detectors()
    candidates: list[int] = []
    last_timecode = None
    downscale_factor: int | None = None
    last_progress_percent = -1

    while True:
        frame = video.read()
        if frame is False:
            break
        timecode = video.position
        last_timecode = timecode

        if downscale_factor is None:
            downscale_factor = compute_downscale_factor(int(frame.shape[1]))
        detection_frame = frame
        if downscale_factor > 1:
            detection_frame = cv2.resize(
                frame,
                (
                    max(1, int(frame.shape[1]) // downscale_factor),
                    max(1, int(frame.shape[0]) // downscale_factor),
                ),
                interpolation=cv2.INTER_LINEAR,
            )

        for detector in detectors:
            for cut in detector.process_frame(timecode, detection_frame):
                candidates.append(_timecode_us(cut))

        if on_progress is not None:
            ratio = max(0.0, min(0.99, _timecode_us(timecode) / duration_us))
            percent = int(ratio * 100)
            if percent > last_progress_percent:
                last_progress_percent = percent
                _emit_progress(on_progress, ratio)

    if last_timecode is None:
        raise RuntimeError("video backend returned no decoded frames")

    for detector in detectors:
        for cut in detector.post_process(last_timecode):
            candidates.append(_timecode_us(cut))

    return candidates


def detect_shot_ranges(
    path: Path,
    *,
    duration_us: int,
    on_progress: Callable[[float], None] | None = None,
) -> list[ShotRange]:
    if duration_us <= 0:
        raise AppError("SHOT_BOUNDARY_DURATION_INVALID", "视频时长无效，无法建立镜头边界", status_code=422)

    candidates: list[int] | None = None
    backend_errors: list[Exception] = []
    for backend in ("pyav", "opencv"):
        try:
            candidates = _scan_with_backend(
                path,
                backend=backend,
                duration_us=duration_us,
                on_progress=on_progress,
            )
            break
        except _ProgressCallbackError as exc:
            raise exc.original
        except Exception as exc:
            backend_errors.append(exc)
            logger.warning(
                "P5 shot detection backend failed; trying fallback",
                extra={"backend": backend, "error_type": type(exc).__name__},
            )

    if candidates is None:
        raise AppError("SHOT_BOUNDARY_DETECTION_FAILED", "镜头边界检测失败", status_code=422) from backend_errors[-1]

    if on_progress is not None:
        on_progress(1.0)

    cuts = _cluster_cut_candidates(candidates, duration_us=duration_us)
    boundaries = [0, *cuts, duration_us]
    ranges = [ShotRange(start_us=start, end_us=end) for start, end in zip(boundaries, boundaries[1:])]
    if not ranges or any(item.duration_us <= 0 for item in ranges):
        raise AppError("SHOT_BOUNDARY_INVALID", "镜头边界结果无效", status_code=422)
    return ranges
