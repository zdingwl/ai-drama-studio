"""02 拉片 V5.1：在 V5 精度链路上增加安全的 Episode 级缓存。

V5.1 不改变任何 Shot Detection / Source PTS / Reference Clip 算法，只在 TransVLM 前增加：
- source + runtime + config manifest 校验；
- 命中时复用已成功生成的 transition segments；
- 不命中或显式 recompute 时执行 V5 TransVLM，再原子写入缓存；
- cache 与 shots/runs 完全隔离，Reference Clip / Current Revision 永远不是缓存。
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
    load_transition_segments,
    prepare_cache,
    runtime_signature,
    store_transition_segments,
)
from engine.app.shot_revision_v2 import commit_auto_shot_revision
from engine.app.studio_v2 import episode_dir, get_episode_record, new_id
from engine.app.transvlm_runtime_v5 import TransVLMTransition, detect_transition_segments, runtime_config


# 当前 wrapper 没有覆盖这些 CLI 参数，因此它们就是官方 Runtime 当前生产基线。
# Runtime 代码/prompt/flow pipeline 本身同时进入 runtime_signature；官方默认一旦变化，旧缓存自动失效。
TRANSVLM_CACHE_PROFILE: dict[str, Any] = {
    "model": "TransVLM-Qwen3-VL-4B-Instruct",
    "backend": "hf",
    "fps": 25.0,
    "window_size": 10.0,
    "stride": 9.0,
    "timestamp_format": "1f",
    "flow_codec": "libx264",
    "max_pixels_override": None,
}


def _expected_cache_manifest(episode: Any, source: Path) -> dict[str, Any]:
    config = runtime_config()
    signature = runtime_signature(config.inference_root, config.checkpoint_dir)
    return build_manifest(
        source_path=source,
        source_sha256=episode.source_sha256,
        runtime_signature_value=signature,
        transvlm_profile=TRANSVLM_CACHE_PROFILE,
    )


def detect_episode_shots(
    episode_id: str,
    progress: v2.ProgressReporter | None = None,
    *,
    recompute_scope: str = "auto",
) -> list[dict[str, Any]]:
    """V5.1 正式入口。

    ``recompute_scope``：
    - auto: 使用所有有效缓存；
    - transitions: 只丢弃最终 transition cache；
    - transvlm: 丢弃 TransVLM/window 及其下游；
    - flow: 丢弃 Flow 及其全部下游；
    - preprocess: 丢弃 Stage 02 模型 RGB 预处理及全部下游（不会删除 F03 Proxy/Audio）；
    - all: 只清空 ``cache/shot_v51``，绝不删除 source / shots / revisions。
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

        cached = load_transition_segments(shot_cache, expected_manifest)
        if cached is not None:
            segments = [
                TransVLMTransition(start_us=int(item["start_us"]), end_us=int(item["end_us"]))
                for item in cached
            ]
            v2._report(
                progress,
                v5.TRANSVLM_PROGRESS_END,
                "cache_hit",
                f"已复用本集有效 TransVLM Transition 缓存 · {len(segments)} 个转场区间",
            )
        else:
            if cache_prepare["invalidated"]:
                cache_message = "缓存依赖发生变化，已自动失效；正在重新执行 TransVLM"
            elif recompute_scope != "auto":
                cache_message = f"已按 {recompute_scope} 强制失效缓存；正在重新执行 TransVLM"
            else:
                cache_message = "未找到可用 Transition 缓存；正在执行 TransVLM"
            v2._report(progress, v5.TRANSVLM_PROGRESS_START, "cache_miss", cache_message)

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

            segments = detect_transition_segments(source, transvlm_work, progress=transvlm_report)
            # 只有官方 Runtime 成功返回并完成 parser 后才写缓存；失败 Run 不污染下一次。
            store_transition_segments(
                shot_cache,
                expected_manifest,
                [
                    {"start_us": int(item.start_us), "end_us": int(item.end_us)}
                    for item in segments
                ],
            )

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
            f" · cache={recompute_scope}"
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
        # 失败只清本次 shots/runs；Episode cache 是独立层。
        # Transition cache 只有在 TransVLM 成功返回后才会写，因此可安全保留用于修复下游 renderer 后重试。
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)
        raise
