"""02 拉片 V5：TransVLM-first Shot Transition Detection。

正式边界：
- TransVLM 是唯一转场模型，直接从 Source 视频返回 transition segments；
- 不再运行 TransNetV2 / PySceneDetect；
- Source PTS 负责把模型的秒级区间落到真实帧；
- 短转场（hard-like）在 TransVLM 区间内寻找最强相邻帧断裂；
- 长转场（dissolve/fade/wipe-like）使用区间中心对应的 Source frame 作为连续 Shot timeline 公共边界；
- transition start/end 始终保留在 boundary metadata，后续资产采样可避开转场污染区域；
- Reference Clip 继续使用 V4.1 的 frame ownership renderer，禁止相邻 Shot 共享 Cut frame。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from engine.app import media_v2 as v2
from engine.app.media_v4 import _nearest_index, _review_times, _source_visual_scores
from engine.app.reference_render_v4 import render_reference_exact
from engine.app.shot_revision_v2 import commit_auto_shot_revision
from engine.app.studio_v2 import episode_dir, get_episode_record, new_id
from engine.app.transvlm_runtime_v5 import TransVLMTransition, detect_transition_segments

# TransVLM 官方默认 timestamp_format=1f，转场时间以 0.1s 粒度输出；
# 因此 hard cut 不直接取 segment 的 start/end，而是在这个模型给出的局部范围内回到 Source frame 决定。
HARD_LIKE_MAX_US = 180_000
HARD_SEARCH_PAD_FRAMES = 2
WIDE_TRANSITION_REVIEW_US = 1_500_000


@dataclass(frozen=True)
class ResolvedTransition:
    cut_us: int
    transition_start_us: int
    transition_end_us: int
    source_frame_index: int
    kind: str
    visual_score: float | None
    review_reasons: tuple[str, ...]


def _frame_at_or_after(points: tuple[int, ...], target_us: int) -> int:
    index = _nearest_index(points, target_us)
    if points[index] < target_us and index + 1 < len(points):
        index += 1
    return max(0, min(index, len(points) - 1))


def _resolve_transition(
    segment: TransVLMTransition,
    source_pts: tuple[int, ...],
    visual_scores: list[float],
) -> ResolvedTransition | None:
    if len(source_pts) < 2:
        return None

    start_us = max(0, int(segment.start_us))
    end_us = max(start_us + 1, int(segment.end_us))
    start_index = _frame_at_or_after(source_pts, start_us)
    end_index = _frame_at_or_after(source_pts, end_us)
    start_index = max(1, min(start_index, len(source_pts) - 1))
    end_index = max(start_index, min(end_index, len(source_pts) - 1))

    duration_us = end_us - start_us
    reasons: list[str] = []

    if duration_us <= HARD_LIKE_MAX_US:
        left = max(1, start_index - HARD_SEARCH_PAD_FRAMES)
        right = min(len(source_pts) - 1, end_index + HARD_SEARCH_PAD_FRAMES)
        best_index = max(range(left, right + 1), key=lambda index: float(visual_scores[index]))
        visual_score = float(visual_scores[best_index])
        kind = "HARD_LIKE"
        cut_index = best_index
    else:
        midpoint_us = start_us + duration_us // 2
        cut_index = _nearest_index(source_pts, midpoint_us)
        cut_index = max(1, min(cut_index, len(source_pts) - 1))
        visual_score = float(visual_scores[cut_index]) if cut_index < len(visual_scores) else None
        kind = "GRADUAL"
        if duration_us >= WIDE_TRANSITION_REVIEW_US:
            reasons.append("TransVLM 检测到较长转场区间，建议人工快速检查")

    cut_us = int(source_pts[cut_index])
    if cut_us <= 0:
        return None
    return ResolvedTransition(
        cut_us=cut_us,
        transition_start_us=start_us,
        transition_end_us=end_us,
        source_frame_index=cut_index,
        kind=kind,
        visual_score=visual_score,
        review_reasons=tuple(reasons),
    )


def _resolve_transitions(
    segments: list[TransVLMTransition],
    source_pts: tuple[int, ...],
    visual_scores: list[float],
) -> list[ResolvedTransition]:
    resolved: list[ResolvedTransition] = []
    for segment in segments:
        item = _resolve_transition(segment, source_pts, visual_scores)
        if item is not None:
            resolved.append(item)

    # 如果 overlapping / merged segment 最终落到同一 Source frame，只保留更窄、更具体的转场。
    by_cut: dict[int, ResolvedTransition] = {}
    for item in resolved:
        previous = by_cut.get(item.cut_us)
        if previous is None:
            by_cut[item.cut_us] = item
            continue
        previous_width = previous.transition_end_us - previous.transition_start_us
        current_width = item.transition_end_us - item.transition_start_us
        if current_width < previous_width:
            by_cut[item.cut_us] = item
    return sorted(by_cut.values(), key=lambda item: item.cut_us)


def _accepted_boundaries(
    duration_us: int,
    resolved: list[ResolvedTransition],
) -> tuple[list[int], dict[int, ResolvedTransition]]:
    clean = v2._normalize_boundaries(duration_us, [item.cut_us for item in resolved])
    lookup = {item.cut_us: item for item in resolved if item.cut_us in set(clean[1:-1])}
    return clean, lookup


def _render_middle_thumbnail(reference: Path, output: Path, duration_us: int) -> None:
    v2._render_thumbnail(reference, output, duration_us)


def detect_episode_shots(episode_id: str, progress: v2.ProgressReporter | None = None) -> list[dict[str, Any]]:
    """02 拉片 V5 正式入口：TransVLM → Source frame ownership → Current Revision。"""

    episode = get_episode_record(episode_id)
    if episode is None:
        raise LookupError("剧集不存在")
    if episode.preprocess is None or episode.preprocess.status != "READY" or not episode.preprocess.proxy_path:
        raise v2.MediaPipelineError("请先完成该剧集的视频预处理")

    source = Path(episode.source_path)
    if not source.is_file():
        raise v2.MediaPipelineError("原视频文件缺失")

    run_id = new_id("SHOTRUNV5")
    run_root = episode_dir(episode.project_id, episode.id) / "shots" / "runs" / run_id
    refs = run_root / "reference"
    thumbs = run_root / "thumbnails"
    transvlm_work = run_root / "transvlm"
    refs.mkdir(parents=True, exist_ok=True)
    thumbs.mkdir(parents=True, exist_ok=True)

    try:
        v2._report(progress, 3, "probe", "正在读取原片媒体信息")
        info = v2.probe_media(source)
        duration_us = int(info["duration_us"])

        v2._report(progress, 8, "frame_pts", "正在读取原片 Source PTS")
        source_pts = v2._frame_pts_us(source)

        v2._report(progress, 12, "transvlm", "TransVLM 正在检测完整 Shot Transition 区间")
        segments = detect_transition_segments(source, transvlm_work)

        v2._report(progress, 62, "boundaries", f"TransVLM 返回 {len(segments)} 个转场区间，正在映射 Source 帧")
        visual_scores, source_pts = _source_visual_scores(source, source_pts)
        resolved = _resolve_transitions(segments, source_pts, visual_scores)
        boundaries, accepted = _accepted_boundaries(duration_us, resolved)

        payloads: list[dict[str, Any]] = []
        total_shots = max(1, len(boundaries) - 1)
        for index, (start_us, end_us) in enumerate(zip(boundaries, boundaries[1:]), start=1):
            duration = end_us - start_us
            reference = refs / f"shot_{index:04d}.mp4"
            thumbnail = thumbs / f"shot_{index:04d}.jpg"
            percent = 68 + ((index - 1) / total_shots) * 27
            v2._report(
                progress,
                percent,
                "reference_clips",
                f"正在生成 TransVLM 帧精确 Reference Clip {index} / {total_shots}",
                index,
                total_shots,
            )

            render_reference_exact(source, reference, start_us, duration, frame_pts=source_pts)
            _render_middle_thumbnail(reference, thumbnail, duration)
            in_us, mid_us, out_us = _review_times(source_pts, start_us, end_us)

            outgoing = accepted.get(end_us)
            if outgoing is None:
                boundary_meta: dict[str, Any] = {
                    "kind": "boundary_meta",
                    "confidence": 1.0,
                    "method": "video_end",
                    "review_reasons": [],
                }
            else:
                boundary_meta = {
                    "kind": "boundary_meta",
                    "confidence": None,
                    "method": "TransVLM + Source PTS",
                    "transition_kind": outgoing.kind,
                    "transition_start_us": outgoing.transition_start_us,
                    "transition_end_us": outgoing.transition_end_us,
                    "transition_duration_us": outgoing.transition_end_us - outgoing.transition_start_us,
                    "source_frame_index": outgoing.source_frame_index,
                    "visual_score": round(outgoing.visual_score, 4) if outgoing.visual_score is not None else None,
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
                "status": "REVIEW" if boundary_meta["review_reasons"] else "READY",
            })
            v2._report(
                progress,
                68 + (index / total_shots) * 27,
                "reference_clips",
                f"已生成 {index} / {total_shots} 个 TransVLM Shot",
                index,
                total_shots,
            )

        v2._report(progress, 97, "persist", "TransVLM V5 结果已生成，正在安全切换 Current Revision", total_shots, total_shots)
        note = f"自动拉片 V5 {run_id} · TransVLM-Qwen3-VL-4B + Source PTS frame ownership"
        result = commit_auto_shot_revision(episode_id, payloads, note=note)
        review_count = sum(1 for item in payloads if item["status"] == "REVIEW")
        v2._report(
            progress,
            100,
            "ready",
            f"拉片 V5 完成：{len(result)} Shots · {review_count} 待检查",
            len(result),
            len(result),
        )
        return result
    except Exception:
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)
        raise
