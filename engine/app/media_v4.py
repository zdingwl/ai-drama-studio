"""02 拉片 V4：TransNet 候选 + PySceneDetect 辅助 + Source PTS 帧级精修。

职责：
- TransNetV2 只负责提出“这里附近发生了转场”的候选区域；
- PySceneDetect AdaptiveDetector 作为第二证据，不与 TransNet 结果简单 union；
- 对每个候选点回到原视频逐帧 PTS，在 ±5 帧内用真实相邻帧视觉变化寻找最终 Cut；
- 最终 Shot 统一使用 [start_us, end_us)；end_us 永远代表下一 Shot 第一帧 PTS；
- Reference Clip 使用 FFmpeg trim 的排他 end 重新编码，禁止把下一 Shot 第一帧带入上一 Shot；
- keyframes_json 保存 IN / MID / OUT 的 Source PTS，以及边界置信度/待检查原因；
- 损坏历史 Proxy 的自动修复逻辑继续保留。

不负责：
- 不修改人工 Shot Revision 规则；
- 不把 PySceneDetect 单独检测到的 Cut 直接升级为 Final Cut，避免双模型简单并集造成过切。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any

from engine.app import media_v2 as v2
from engine.app.shot_revision_v2 import commit_auto_shot_revision
from engine.app.studio_v2 import episode_dir, get_episode_record, new_id

REFINE_RADIUS_FRAMES = 5
SOURCE_FRAME_COUNT_TOLERANCE = 2
BOUNDARY_REVIEW_THRESHOLD = 0.68
VISUAL_WEAK_THRESHOLD = 0.24


@dataclass(frozen=True)
class TransNetCandidate:
    proxy_cut_us: int
    transition_start_us: int
    transition_end_us: int
    peak_score: float


@dataclass(frozen=True)
class RefinedBoundary:
    cut_us: int
    source_frame_index: int
    confidence: float
    transnet_score: float
    visual_score: float
    visual_prominence: float
    pyscenedetect_confirmed: bool
    pyscenedetect_distance_frames: int | None
    offset_frames: int
    review_reasons: tuple[str, ...]


def _transnet_candidates(proxy_path: Path, frame_pts: tuple[int, ...]) -> list[TransNetCandidate]:
    """返回 TransNet 转场候选区，而不是直接把 transition end 当 Final Cut。"""

    try:
        import numpy as np
        import torch
        import transnetv2_pytorch
        from transnetv2_pytorch import TransNetV2
        from engine.app.transnet_runtime_v3 import TransNetRuntimeError, predict_single_frame_scores
    except ImportError as exc:
        raise v2.MediaPipelineError("未安装 TransNetV2 本地依赖，请执行 pip install -r engine/requirements.txt") from exc

    package_root = Path(transnetv2_pytorch.__file__).resolve().parent
    weights_path = next((
        item for item in (
            package_root / "transnetv2-pytorch-weights.pth",
            package_root / "weights" / "transnetv2-pytorch-weights.pth",
        ) if item.is_file()
    ), None)
    if weights_path is None:
        raise v2.MediaPipelineError("TransNetV2 权重文件缺失")

    model = TransNetV2(device="auto")
    try:
        state_dict = torch.load(weights_path, map_location=getattr(model, "device", "cpu"), weights_only=True)
    except TypeError:
        state_dict = torch.load(weights_path, map_location=getattr(model, "device", "cpu"))
    model.load_state_dict(state_dict)
    model.eval()

    try:
        raw_scores = predict_single_frame_scores(model, proxy_path)
    except TransNetRuntimeError as exc:
        raise v2.MediaPipelineError(str(exc)) from exc

    if hasattr(raw_scores, "detach"):
        raw_scores = raw_scores.detach().cpu().numpy()
    scores = np.asarray(raw_scores, dtype=np.float64).reshape(-1)
    scores, aligned_pts = v2._align_transnet_timeline(scores, frame_pts)

    candidates: list[TransNetCandidate] = []
    index = 0
    while index < len(scores):
        if float(scores[index]) <= v2.SHOT_THRESHOLD:
            index += 1
            continue
        first = index
        peak = float(scores[index])
        while index + 1 < len(scores) and float(scores[index + 1]) > v2.SHOT_THRESHOLD:
            index += 1
            peak = max(peak, float(scores[index]))
        last = index
        # TransNet transition 区结束后的第一帧只作为“候选 Cut 中心”。
        # V4 后面会回到 Source PTS ±5 帧重新寻找真实左右镜分界。
        center_index = min(last + 1, len(aligned_pts) - 1)
        if center_index > 0:
            candidates.append(TransNetCandidate(
                proxy_cut_us=int(aligned_pts[center_index]),
                transition_start_us=int(aligned_pts[first]),
                transition_end_us=int(aligned_pts[last]),
                peak_score=max(0.0, min(1.0, peak)),
            ))
        index += 1
    return candidates


def _pyscenedetect_cuts(source: Path) -> tuple[str, list[int]]:
    """运行 PySceneDetect AdaptiveDetector；失败只降级第二证据，不让主拉片失败。"""

    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import AdaptiveDetector
    except ImportError:
        return "NOT_AVAILABLE", []

    try:
        video = open_video(str(source))
        manager = SceneManager()
        try:
            detector = AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=6, window_width=2)
        except TypeError:
            detector = AdaptiveDetector()
        manager.add_detector(detector)
        manager.detect_scenes(video=video, show_progress=False)
        scenes = manager.get_scene_list()
        # 每个 scene 的 start（第一个 scene 除外）就是 PySceneDetect 的 Cut。
        cuts = [int(round(scene[0].get_seconds() * 1_000_000)) for scene in scenes[1:]]
        return "READY", cuts
    except Exception:
        return "FAILED", []


def _read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _source_visual_scores(source: Path, source_pts: tuple[int, ...]) -> tuple[list[float], tuple[int, ...]]:
    """一次顺序低分辨率解码原视频，计算每对相邻 Source frame 的视觉变化。

    score[i] 表示 frame i-1 -> frame i 的变化强度，因此 Final Cut 若为 source_pts[i]，
    score[i] 正好描述 Cut 左右两帧的视觉断裂。
    """

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise v2.MediaPipelineError("拉片 V4 需要 OpenCV / NumPy，请安装 engine/requirements.txt") from exc

    width, height = 320, 180
    frame_size = width * height * 3
    command = [
        "ffmpeg", "-v", "error", "-i", str(source),
        "-map", "0:v:0", "-an",
        "-vf", f"scale={width}:{height}",
        "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
    ]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise v2.MediaPipelineError("找不到媒体工具：ffmpeg，请确认 FFmpeg 已加入 PATH") from exc

    if process.stdout is None or process.stderr is None:
        process.kill()
        raise v2.MediaPipelineError("FFmpeg 原片帧级精修管道初始化失败")

    scores: list[float] = [0.0]
    previous_gray = None
    previous_hist = None
    decoded = 0
    try:
        while True:
            raw = _read_exact(process.stdout, frame_size)
            if not raw:
                break
            if len(raw) != frame_size:
                raise v2.MediaPipelineError(
                    f"原片帧级精修 rawvideo 不完整：期望 {frame_size} bytes，实际 {len(raw)} bytes"
                )
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist)

            if previous_gray is not None and previous_hist is not None:
                gray_delta = float(np.mean(cv2.absdiff(previous_gray, gray))) / 255.0
                hist_delta = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                edge_left = cv2.Canny(previous_gray, 80, 160)
                edge_right = cv2.Canny(gray, 80, 160)
                edge_delta = float(np.mean(cv2.absdiff(edge_left, edge_right))) / 255.0
                # 灰度断裂最能描述硬切；Histogram 抵抗亮度变化；Edge 辅助结构变化。
                score = min(1.0, gray_delta * 2.35 * 0.55 + hist_delta * 0.32 + edge_delta * 0.13)
                scores.append(float(score))
            previous_gray = gray
            previous_hist = hist
            decoded += 1
    finally:
        try:
            process.stdout.close()
        except Exception:
            pass

    stderr = process.stderr.read().decode("utf-8", errors="replace")
    return_code = process.wait()
    if return_code != 0:
        raise v2.MediaPipelineError(f"原片帧级精修 FFmpeg 解码失败：{stderr.strip()[-3000:]}")

    difference = abs(decoded - len(source_pts))
    if difference > SOURCE_FRAME_COUNT_TOLERANCE:
        raise v2.MediaPipelineError(
            f"原片精修帧数 {decoded} 与 Source PTS {len(source_pts)} 不一致，差 {difference} 帧"
        )
    usable = min(decoded, len(source_pts), len(scores))
    if usable < 2:
        raise v2.MediaPipelineError("原片没有足够帧用于 Shot 边界精修")
    return scores[:usable], source_pts[:usable]


def _nearest_index(points: tuple[int, ...], target_us: int) -> int:
    if not points:
        return 0
    lo, hi = 0, len(points) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if points[mid] < target_us:
            lo = mid + 1
        else:
            hi = mid
    right = lo
    left = max(0, right - 1)
    return left if abs(points[left] - target_us) <= abs(points[right] - target_us) else right


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2.0)


def _refine_candidates(
    candidates: list[TransNetCandidate],
    source_pts: tuple[int, ...],
    visual_scores: list[float],
    pyscene_cuts: list[int],
    pyscene_status: str,
) -> list[RefinedBoundary]:
    pyscene_indices = [_nearest_index(source_pts, value) for value in pyscene_cuts]
    refined: list[RefinedBoundary] = []

    for candidate in candidates:
        center = _nearest_index(source_pts, candidate.proxy_cut_us)
        start = max(1, center - REFINE_RADIUS_FRAMES)
        end = min(len(source_pts) - 1, center + REFINE_RADIUS_FRAMES)
        if start > end:
            continue

        local_indices = list(range(start, end + 1))
        local_scores = [float(visual_scores[index]) for index in local_indices]
        local_median = _median(local_scores)

        def scene_distance(index: int) -> int | None:
            if not pyscene_indices:
                return None
            return min(abs(index - item) for item in pyscene_indices)

        best_index = local_indices[0]
        best_rank = -1.0
        for index in local_indices:
            visual = float(visual_scores[index])
            distance = abs(index - center)
            py_distance = scene_distance(index)
            py_bonus = 0.12 if py_distance is not None and py_distance <= 1 else (0.05 if py_distance is not None and py_distance <= 2 else 0.0)
            # 距离只做轻微约束，真正的相邻帧视觉断裂优先。
            rank = visual + py_bonus - distance * 0.012
            if rank > best_rank:
                best_rank = rank
                best_index = index

        visual = float(visual_scores[best_index])
        prominence = max(0.0, visual - local_median)
        py_distance = scene_distance(best_index)
        py_confirmed = py_distance is not None and py_distance <= 2
        visual_confidence = min(1.0, visual * 1.45 + prominence * 1.35)
        py_confidence = 1.0 if py_confirmed else (0.35 if pyscene_status == "READY" else 0.45)
        confidence = max(0.0, min(1.0,
            candidate.peak_score * 0.38 + visual_confidence * 0.47 + py_confidence * 0.15
        ))

        reasons: list[str] = []
        if visual < VISUAL_WEAK_THRESHOLD:
            reasons.append("原片相邻帧变化较弱，可能是渐变/运动转场")
        if pyscene_status == "READY" and not py_confirmed:
            reasons.append("PySceneDetect 未确认该边界")
        elif pyscene_status != "READY":
            reasons.append("PySceneDetect 第二证据不可用")
        offset = best_index - center
        if abs(offset) >= 4:
            reasons.append(f"Source PTS 精修相对 TransNet 候选偏移 {offset:+d} 帧")
        if confidence < BOUNDARY_REVIEW_THRESHOLD:
            reasons.append("边界置信度偏低")

        refined.append(RefinedBoundary(
            cut_us=int(source_pts[best_index]),
            source_frame_index=best_index,
            confidence=confidence,
            transnet_score=candidate.peak_score,
            visual_score=visual,
            visual_prominence=prominence,
            pyscenedetect_confirmed=py_confirmed,
            pyscenedetect_distance_frames=py_distance,
            offset_frames=offset,
            review_reasons=tuple(dict.fromkeys(reasons)),
        ))

    # 同一个 Source PTS 可能被相邻 TransNet 候选重复命中，只保留置信度最高者。
    by_cut: dict[int, RefinedBoundary] = {}
    for item in refined:
        previous = by_cut.get(item.cut_us)
        if previous is None or item.confidence > previous.confidence:
            by_cut[item.cut_us] = item
    return sorted(by_cut.values(), key=lambda item: item.cut_us)


def _normalize_refined_boundaries(duration_us: int, cuts: list[RefinedBoundary]) -> tuple[list[int], dict[int, RefinedBoundary]]:
    boundaries = [0]
    accepted: dict[int, RefinedBoundary] = {}
    for item in cuts:
        value = item.cut_us
        if value <= 0 or value >= duration_us:
            continue
        if value - boundaries[-1] < v2.MIN_SHOT_DURATION_US:
            continue
        boundaries.append(value)
        accepted[value] = item
    if duration_us - boundaries[-1] < v2.MIN_SHOT_DURATION_US and len(boundaries) > 1:
        removed = boundaries.pop()
        accepted.pop(removed, None)
    boundaries.append(duration_us)
    return boundaries, accepted


def _frame_at_or_after(source_pts: tuple[int, ...], value: int) -> int:
    index = _nearest_index(source_pts, value)
    if source_pts[index] < value and index + 1 < len(source_pts):
        index += 1
    return index


def _review_times(source_pts: tuple[int, ...], start_us: int, end_us: int) -> tuple[int, int, int]:
    start_index = _frame_at_or_after(source_pts, start_us)
    end_index = _frame_at_or_after(source_pts, end_us)
    if end_index < len(source_pts) and source_pts[end_index] >= end_us:
        end_index -= 1
    end_index = max(start_index, min(end_index, len(source_pts) - 1))
    mid_target = start_us + max(0, end_us - start_us) // 2
    mid_index = max(start_index, min(end_index, _nearest_index(source_pts, mid_target)))
    return int(source_pts[start_index]), int(source_pts[mid_index]), int(source_pts[end_index])


def render_reference_exact(source: Path, output: Path, start_us: int, duration_us: int) -> None:
    """按 [start,end) 过滤原视频帧，确保 end_us 对应的下一镜第一帧不会进入当前 Reference Clip。"""

    output.parent.mkdir(parents=True, exist_ok=True)
    end_us = start_us + duration_us
    start_s = start_us / 1_000_000
    end_s = end_us / 1_000_000
    info = v2.probe_media(source)

    video_filter = f"[0:v:0]trim=start={start_s:.6f}:end={end_s:.6f},setpts=PTS-STARTPTS[v]"
    command = ["ffmpeg", "-y", "-i", str(source)]
    if info.get("has_audio"):
        audio_filter = f"[0:a:0]atrim=start={start_s:.6f}:end={end_s:.6f},asetpts=PTS-STARTPTS[a]"
        command += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
        ]
    else:
        command += [
            "-filter_complex", video_filter,
            "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        ]
    command += ["-movflags", "+faststart", str(output)]
    v2._run(command)


def _render_middle_thumbnail(reference: Path, output: Path, duration_us: int) -> None:
    v2._render_thumbnail(reference, output, duration_us)


def _candidate_analysis_with_repair(
    episode_id: str,
    proxy: Path,
    progress: v2.ProgressReporter | None,
) -> tuple[Path, list[TransNetCandidate]]:
    frame_pts = v2._frame_pts_us(proxy)
    try:
        return proxy, _transnet_candidates(proxy, frame_pts)
    except v2.MediaPipelineError as first_error:
        if not v2._is_transnet_decode_error(first_error):
            raise

        v2._report(progress, 16, "proxy_repair", "检测到分析 Proxy 损坏，正在从原片自动重建")

        def repair_progress(percent: float, stage_key: str, message: str, current: int | None, total: int | None) -> None:
            mapped = 16.0 + (max(0.0, min(100.0, percent)) / 100.0) * 6.0
            v2._report(progress, mapped, "proxy_repair", f"自动修复 Proxy · {message}", current, total)

        v2.preprocess_episode(episode_id, progress=repair_progress)
        repaired = get_episode_record(episode_id)
        if repaired is None or repaired.preprocess is None or not repaired.preprocess.proxy_path:
            raise v2.MediaPipelineError("分析 Proxy 自动重建后状态异常") from first_error
        repaired_proxy = Path(repaired.preprocess.proxy_path)
        repaired_pts = v2._frame_pts_us(repaired_proxy)
        try:
            return repaired_proxy, _transnet_candidates(repaired_proxy, repaired_pts)
        except v2.MediaPipelineError as retry_error:
            if v2._is_transnet_decode_error(retry_error):
                raise v2.MediaPipelineError(
                    "分析 Proxy 已自动重建并完成校验，但 TransNetV2 仍出现视频解码错误。\n"
                    f"首次错误：{first_error}\n重试错误：{retry_error}"
                ) from retry_error
            raise


def detect_episode_shots(episode_id: str, progress: v2.ProgressReporter | None = None) -> list[dict[str, Any]]:
    """02 拉片 V4 正式入口。"""

    episode = get_episode_record(episode_id)
    if episode is None:
        raise LookupError("剧集不存在")
    if episode.preprocess is None or episode.preprocess.status != "READY" or not episode.preprocess.proxy_path:
        raise v2.MediaPipelineError("请先完成该剧集的视频预处理")

    source = Path(episode.source_path)
    proxy = Path(episode.preprocess.proxy_path)
    if not source.is_file() or not proxy.is_file():
        raise v2.MediaPipelineError("原视频或代理视频文件缺失")

    v2._report(progress, 3, "probe", "正在读取原片媒体信息")
    info = v2.probe_media(source)
    duration_us = int(info["duration_us"])

    v2._report(progress, 8, "frame_pts", "正在读取 Proxy PTS 与 TransNet 候选")
    proxy, candidates = _candidate_analysis_with_repair(episode_id, proxy, progress)

    v2._report(progress, 22, "boundaries", "PySceneDetect 正在提供第二边界证据")
    pyscene_status, pyscene_cuts = _pyscenedetect_cuts(source)

    v2._report(progress, 28, "frame_pts", "正在读取原视频逐帧 Source PTS")
    source_pts = v2._frame_pts_us(source)

    v2._report(progress, 31, "boundaries", "正在原片 ±5 帧范围精修每个 Cut")
    visual_scores, source_pts = _source_visual_scores(source, source_pts)
    refined = _refine_candidates(candidates, source_pts, visual_scores, pyscene_cuts, pyscene_status)
    boundaries, accepted = _normalize_refined_boundaries(duration_us, refined)

    run_id = new_id("SHOTRUNV4")
    run_root = episode_dir(episode.project_id, episode.id) / "shots" / "runs" / run_id
    refs = run_root / "reference"
    thumbs = run_root / "thumbnails"
    refs.mkdir(parents=True, exist_ok=True)
    thumbs.mkdir(parents=True, exist_ok=True)

    payloads: list[dict[str, Any]] = []
    total_shots = max(1, len(boundaries) - 1)
    try:
        for index, (start_us, end_us) in enumerate(zip(boundaries, boundaries[1:]), start=1):
            duration = end_us - start_us
            reference = refs / f"shot_{index:04d}.mp4"
            thumbnail = thumbs / f"shot_{index:04d}.jpg"
            percent = 40 + ((index - 1) / total_shots) * 55
            v2._report(progress, percent, "reference_clips", f"正在生成帧精确 Reference Clip {index} / {total_shots}", index, total_shots)

            render_reference_exact(source, reference, start_us, duration)
            _render_middle_thumbnail(reference, thumbnail, duration)
            in_us, mid_us, out_us = _review_times(source_pts, start_us, end_us)

            outgoing = accepted.get(end_us)
            if outgoing is None:
                boundary_meta = {
                    "kind": "boundary_meta",
                    "confidence": 1.0,
                    "method": "video_end",
                    "review_reasons": [],
                    "pyscenedetect_status": pyscene_status,
                }
            else:
                boundary_meta = {
                    "kind": "boundary_meta",
                    "confidence": round(outgoing.confidence, 4),
                    "method": "TransNetV2 + Source PTS Refiner + PySceneDetect",
                    "transnet_score": round(outgoing.transnet_score, 4),
                    "visual_score": round(outgoing.visual_score, 4),
                    "visual_prominence": round(outgoing.visual_prominence, 4),
                    "pyscenedetect_confirmed": outgoing.pyscenedetect_confirmed,
                    "pyscenedetect_distance_frames": outgoing.pyscenedetect_distance_frames,
                    "pyscenedetect_status": pyscene_status,
                    "offset_frames": outgoing.offset_frames,
                    "review_reasons": list(outgoing.review_reasons),
                }

            keyframes = [
                {"kind": "start", "source_time_us": in_us, "local_time_us": max(0, in_us - start_us)},
                {"kind": "middle", "source_time_us": mid_us, "local_time_us": max(0, mid_us - start_us), "path": str(thumbnail)},
                {"kind": "end", "source_time_us": out_us, "local_time_us": max(0, out_us - start_us)},
                boundary_meta,
            ]
            reasons = list(boundary_meta.get("review_reasons") or [])
            if duration < 500_000:
                reasons.append("极短 Shot（< 500ms）")
                boundary_meta["review_reasons"] = list(dict.fromkeys(reasons))

            payloads.append({
                "ordinal": index,
                "start_us": start_us,
                "end_us": end_us,
                "duration_us": duration,
                "reference_clip_path": str(reference),
                "thumbnail_path": str(thumbnail) if thumbnail.exists() else None,
                "keyframes_json": json.dumps(keyframes, ensure_ascii=False),
                "short_description": None,
                "shot_type": None,
                "camera_motion": None,
                "status": "REVIEW" if boundary_meta.get("review_reasons") else "READY",
            })
            v2._report(progress, 40 + (index / total_shots) * 55, "reference_clips", f"已生成 {index} / {total_shots} 个帧精确 Shot", index, total_shots)

        v2._report(progress, 97, "persist", "V4 边界与检查帧已生成，正在安全切换 Current Revision", total_shots, total_shots)
        note = f"自动拉片 V4 {run_id} · TransNet候选 + Source PTS精修 + PySceneDetect({pyscene_status})"
        result = commit_auto_shot_revision(episode_id, payloads, note=note)
        review_count = sum(1 for item in payloads if item["status"] == "REVIEW")
        v2._report(progress, 100, "ready", f"拉片 V4 完成：{len(result)} Shots · {review_count} 待检查", len(result), len(result))
        return result
    except Exception:
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)
        raise
