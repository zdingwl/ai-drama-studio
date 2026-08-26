"""02 拉片 V5.1：V5 精度链路 + 安全 Episode 多级缓存。

V5.1 不改变 Shot Detection、Source PTS 落帧或 Reference Clip 算法。缓存依赖链为：

    official model RGB -> whole-video NeuFlow -> raw TransVLM JSONL -> transition segments

第一次仍按官方执行顺序完整运行，只在官方单视频流程成功后捕获它实际使用的 RGB/Flow。
后续可按缓存层级跳过昂贵阶段；任何 source/runtime/profile 变化都会由 strict manifest 自动失效。
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from engine.app import media_v2 as v2
from engine.app import media_v5 as v5
from engine.app.reference_render_v4 import render_reference_exact
from engine.app.shot_cache_v51 import (
    VALID_RECOMPUTE_SCOPES,
    build_manifest,
    cache_paths,
    cached_transvlm_output,
    clear_cache,
    load_transition_segments,
    prepare_cache,
    runtime_signature,
    store_transition_segments,
)
from engine.app.shot_revision_v2 import commit_auto_shot_revision
from engine.app.studio_v2 import episode_dir, get_episode_record, new_id
from engine.app.transvlm_runtime_v51 import (
    TRANSVLM_RUNTIME_PROFILE,
    TransVLMTransition,
    cache_signature_files,
    detect_transition_segments,
    parse_transition_output,
    runtime_config,
)


def _expected_cache_manifest(episode: Any, source: Path) -> dict[str, Any]:
    config = runtime_config()
    signature = runtime_signature(
        config.inference_root,
        config.checkpoint_dir,
        extra_files=cache_signature_files(),
    )
    return build_manifest(
        source_path=source,
        source_sha256=episode.source_sha256,
        runtime_signature_value=signature,
        transvlm_profile=TRANSVLM_RUNTIME_PROFILE,
    )


def _probe_cached_video(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        info = v2.probe_media(path)
    except Exception:
        return None
    if not info.get("width") or not info.get("height") or int(info.get("duration_us") or 0) <= 0:
        return None
    return info


def _validate_cached_model_inputs(paths) -> tuple[bool, bool]:
    """Cheap structural gate for cached RGB/flow without re-decoding the whole episode.

    Artifacts are written atomically only after official inference succeeds, so ffprobe-level checks
    are enough for normal reuse.  A malformed/orphaned file invalidates itself and every downstream
    layer before the next expensive model run.
    """

    rgb_info = _probe_cached_video(paths.model_rgb)
    if rgb_info is None:
        if paths.model_rgb.exists() or paths.model_flow.exists():
            clear_cache(paths, "preprocess")
        return False, False

    target_fps = float(TRANSVLM_RUNTIME_PROFILE["fps"])
    rgb_fps = float(rgb_info.get("fps") or 0.0)
    if abs(rgb_fps - target_fps) > 1e-3:
        clear_cache(paths, "preprocess")
        return False, False

    flow_info = _probe_cached_video(paths.model_flow)
    if flow_info is None:
        if paths.model_flow.exists():
            clear_cache(paths, "flow")
        return True, False

    flow_fps = float(flow_info.get("fps") or 0.0)
    same_shape = (
        int(rgb_info["width"]) == int(flow_info["width"])
        and int(rgb_info["height"]) == int(flow_info["height"])
    )
    duration_delta = abs(int(rgb_info["duration_us"]) - int(flow_info["duration_us"]))
    if not same_shape or abs(flow_fps - target_fps) > 1e-3 or duration_delta > 120_000:
        clear_cache(paths, "flow")
        return True, False
    return True, True


def _transition_dicts(segments: list[TransVLMTransition]) -> list[dict[str, int]]:
    return [
        {"start_us": int(item.start_us), "end_us": int(item.end_us)}
        for item in segments
    ]


def detect_episode_shots(
    episode_id: str,
    progress: v2.ProgressReporter | None = None,
    *,
    recompute_scope: str = "auto",
) -> list[dict[str, Any]]:
    """V5.1 formal entry with dependency-aware recomputation.

    ``recompute_scope``:
    - auto: reuse the deepest valid cache;
    - transitions: rebuild transition cache from raw TransVLM output when available;
    - transvlm: rerun Qwen windows, reusing RGB + Flow;
    - flow: recompute NeuFlow + Qwen, reusing model RGB;
    - preprocess/all: start from Source again.
    """

    if recompute_scope not in VALID_RECOMPUTE_SCOPES:
        raise ValueError(f"不支持的重新计算范围：{recompute_scope}")

    episode = get_episode_record(episode_id)
    if episode is None:
        raise LookupError("剧集不存在")
    if episode.preprocess is None or episode.preprocess.status != "READY" or not episode.preprocess.proxy_path:
        raise v2.MediaPipelineError("请先完成该剧集的视频预处理")

    source = Path(episode.source_path)
    if not source.is_file():
        raise v2.MediaPipelineError("原视频文件缺失")

    episode_root = episode_dir(episode.project_id, episode.id)
    shot_cache = cache_paths(episode_root)
    expected_manifest = _expected_cache_manifest(episode, source)
    cache_prepare = prepare_cache(
        shot_cache,
        expected_manifest,
        recompute_scope=recompute_scope,
    )

    run_id = new_id("SHOTRUNV51")
    run_root = episode_root / "shots" / "runs" / run_id
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

        segments: list[TransVLMTransition] | None = None
        cache_used = "none"

        # Deepest cache first: merged transition segments.
        cached = load_transition_segments(shot_cache, expected_manifest)
        if cached is not None:
            segments = [
                TransVLMTransition(start_us=int(item["start_us"]), end_us=int(item["end_us"]))
                for item in cached
            ]
            cache_used = "transitions"
            v2._report(
                progress,
                v5.TRANSVLM_PROGRESS_END,
                "cache_hit",
                f"已复用本集 Transition 缓存 · {len(segments)} 个转场区间",
            )

        # If only transitions were cleared, raw per-window model output can be parsed again without
        # loading Qwen or NeuFlow at all.
        if segments is None:
            raw_output = cached_transvlm_output(shot_cache, expected_manifest)
            if raw_output is not None:
                try:
                    segments = parse_transition_output(raw_output)
                except v2.MediaPipelineError:
                    clear_cache(shot_cache, "transvlm")
                    segments = None
                else:
                    cache_used = "transvlm"
                    store_transition_segments(shot_cache, expected_manifest, _transition_dicts(segments))
                    v2._report(
                        progress,
                        v5.TRANSVLM_PROGRESS_END,
                        "cache_hit",
                        f"已从缓存的 TransVLM Window 输出重建 {len(segments)} 个转场区间",
                    )

        if segments is None:
            rgb_ok, flow_ok = _validate_cached_model_inputs(shot_cache)

            if cache_prepare["invalidated"]:
                cache_message = "缓存依赖发生变化，已自动失效；正在按官方链路重新计算"
            elif recompute_scope != "auto":
                cache_message = f"已按 {recompute_scope} 强制失效缓存；正在从对应层重新计算"
            elif flow_ok:
                cache_message = "Transition/TransVLM 缓存缺失；复用 RGB + Flow，仅重新执行 Qwen"
            elif rgb_ok:
                cache_message = "Flow 缓存缺失；复用模型 RGB，重新执行 NeuFlow + Qwen"
            else:
                cache_message = "未找到可用模型缓存；从原片执行完整 TransVLM"
            v2._report(progress, v5.TRANSVLM_PROGRESS_START, "cache_miss", cache_message)

            model_rgb = shot_cache.model_rgb if rgb_ok else None
            model_flow = shot_cache.model_flow if flow_ok else None
            cache_rgb = None if rgb_ok else shot_cache.model_rgb
            cache_flow = None if flow_ok else shot_cache.model_flow

            def transvlm_report(
                runtime_percent: float,
                stage_key: str,
                message: str,
                current: int | None,
                total: int | None,
            ) -> None:
                v2._report(
                    progress,
                    v5._map_transvlm_progress(runtime_percent),
                    stage_key,
                    message,
                    current,
                    total,
                )

            segments = detect_transition_segments(
                source,
                transvlm_work,
                progress=transvlm_report,
                model_rgb_path=model_rgb,
                model_flow_path=model_flow,
                cache_rgb_path=cache_rgb,
                cache_flow_path=cache_flow,
                output_cache_path=shot_cache.transvlm_output,
            )
            cache_used = "rgb+flow" if flow_ok else "rgb" if rgb_ok else "source"

            # Validate captured media.  If a cache copy somehow failed structurally, discard that
            # layer for future runs but keep the current successful inference result.
            _validate_cached_model_inputs(shot_cache)
            store_transition_segments(shot_cache, expected_manifest, _transition_dicts(segments))

        v2._report(progress, 62, "boundaries", f"TransVLM 返回 {len(segments)} 个转场区间，正在映射 Source 帧")
        visual_scores, source_pts = v5._source_visual_scores(source, source_pts)
        resolved = v5._resolve_transitions(segments, source_pts, visual_scores)
        boundaries, accepted = v5._accepted_boundaries(duration_us, resolved)

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
            v5._render_middle_thumbnail(reference, thumbnail, duration)
            in_us, mid_us, out_us = v5._review_times(source_pts, start_us, end_us)

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
                {
                    "kind": "middle",
                    "source_time_us": mid_us,
                    "local_time_us": max(0, mid_us - start_us),
                    "path": str(thumbnail),
                },
                {"kind": "end", "source_time_us": out_us, "local_time_us": max(0, out_us - start_us)},
                boundary_meta,
            ]
            reasons = list(boundary_meta.get("review_reasons") or [])
            if duration < 500_000:
                reasons.append("极短 Shot（< 500ms）")
            boundary_meta["review_reasons"] = list(dict.fromkeys(reasons))

            payloads.append(
                {
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
                }
            )
            v2._report(
                progress,
                68 + (index / total_shots) * 27,
                "reference_clips",
                f"已生成 {index} / {total_shots} 个 TransVLM Shot",
                index,
                total_shots,
            )

        v2._report(
            progress,
            97,
            "persist",
            "TransVLM V5.1 结果已生成，正在安全切换 Current Revision",
            total_shots,
            total_shots,
        )
        note = (
            f"自动拉片 V5.1 {run_id} · TransVLM-Qwen3-VL-4B + Source PTS frame ownership"
            f" · recompute={recompute_scope} · cache_used={cache_used}"
        )
        result = commit_auto_shot_revision(episode_id, payloads, note=note)
        review_count = sum(1 for item in payloads if item["status"] == "REVIEW")
        v2._report(
            progress,
            100,
            "ready",
            f"拉片 V5.1 完成：{len(result)} Shots · {review_count} 待检查",
            len(result),
            len(result),
        )
        return result
    except Exception:
        # Failed shot production removes only this run.  Episode cache is an independent layer and
        # only publishes upstream artifacts after official inference succeeds.
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)
        raise
