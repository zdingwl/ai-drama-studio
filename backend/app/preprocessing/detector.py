from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from threading import Event, Thread

from scenedetect import SceneManager, open_video
from scenedetect.detectors import AdaptiveDetector, ThresholdDetector

from app.core.errors import AppError


DETECTOR_PROFILE_VERSION = "p5-short-drama-v1"
DETECTOR_PROFILE = {
    "version": DETECTOR_PROFILE_VERSION,
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


def detect_shot_ranges(
    path: Path,
    *,
    duration_us: int,
    on_progress: Callable[[float], None] | None = None,
) -> list[ShotRange]:
    if duration_us <= 0:
        raise AppError("SHOT_BOUNDARY_DURATION_INVALID", "视频时长无效，无法建立镜头边界", status_code=422)

    try:
        video = open_video(str(path), backend="opencv")
    except Exception as exc:
        raise AppError("SHOT_BOUNDARY_VIDEO_OPEN_FAILED", "镜头检测无法打开视频", status_code=422) from exc

    manager = SceneManager()
    manager.auto_downscale = True
    manager.add_detector(
        AdaptiveDetector(
            adaptive_threshold=3.0,
            min_content_val=15.0,
            window_width=2,
            min_scene_len="0.12s",
        )
    )
    manager.add_detector(
        ThresholdDetector(
            threshold=14.0,
            min_scene_len="0.12s",
            fade_bias=0.0,
            method=ThresholdDetector.Method.FLOOR,
        )
    )
    manager.add_detector(
        ThresholdDetector(
            threshold=242.0,
            min_scene_len="0.12s",
            fade_bias=0.0,
            method=ThresholdDetector.Method.CEILING,
        )
    )

    monitor_done = Event()
    monitor_errors: list[Exception] = []

    def monitor() -> None:
        if on_progress is None:
            return
        while not monitor_done.wait(0.75):
            try:
                position_us = _timecode_us(video.position)
                ratio = max(0.0, min(0.99, position_us / duration_us))
                on_progress(ratio)
            except Exception as exc:
                monitor_errors.append(exc)
                manager.stop()
                return

    monitor_thread = Thread(target=monitor, name="p5-shot-detect-progress", daemon=True)
    monitor_thread.start()
    detection_error: Exception | None = None
    try:
        manager.detect_scenes(video=video, show_progress=False)
    except Exception as exc:
        detection_error = exc
    finally:
        monitor_done.set()
        monitor_thread.join(timeout=2.0)

    if monitor_errors:
        raise monitor_errors[0]
    if detection_error is not None:
        raise AppError("SHOT_BOUNDARY_DETECTION_FAILED", "镜头边界检测失败", status_code=422) from detection_error

    if on_progress is not None:
        on_progress(1.0)

    scenes = manager.get_scene_list(start_in_scene=True)
    candidates = [_timecode_us(scene_start) for scene_start, _ in scenes[1:]]
    cuts = _cluster_cut_candidates(candidates, duration_us=duration_us)
    boundaries = [0, *cuts, duration_us]
    ranges = [ShotRange(start_us=start, end_us=end) for start, end in zip(boundaries, boundaries[1:])]
    if not ranges or any(item.duration_us <= 0 for item in ranges):
        raise AppError("SHOT_BOUNDARY_INVALID", "镜头边界结果无效", status_code=422)
    return ranges
