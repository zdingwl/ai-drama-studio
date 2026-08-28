#!/usr/bin/env python3
"""Isolated Qwen3-VL runner for Breakdown P2-E2 overlapping Episode windows.

The main app materializes Shot-aligned Episode windows and passes exact Shot boundaries.
This runner keeps the whole continuous video window as visual context, but deliberately limits
how many Shot objects Qwen must serialize in one response. Rapid-cut short dramas can contain
many Shots in 20-40 seconds; asking for every Shot in one giant JSON object caused truncation,
large KV-cache allocation and unstable Windows/CUDA runs.

Policy:
- <= 6 target Shots: one normal structured generation, then compact fallback on shape failure.
- > 6 target Shots: skip the giant response and directly use compact target batches.
- a compact batch that still fails structured validation is recursively split until stable.
- every batch still sees the SAME full continuous window and ALL Shot boundaries.

This is output batching, not isolated per-Shot visual analysis. The runner performs no ASR/OCR
and never produces Final Character/Scene/Prop/Binding IDs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import breakdown_vlm_prompt_zh_v1 as shot_language_profile
import run_breakdown_vlm_qwen3 as base

VLM_WINDOW_SCHEMA = "breakdown-p2-vlm-episode-window-v1"
_ALLOWED_STRICT_READERS = frozenset({"decord", "torchcodec", "torchvision"})
_DIRECT_TARGET_SHOT_LIMIT = 6
_FALLBACK_TARGET_BATCH_SHOTS = 6
_MIN_GENERATION_TOKENS = 2048
_MAX_GENERATION_TOKENS = 6144
_BASE_WINDOW_TOKENS = 768
_TOKENS_PER_TARGET_SHOT = 420


def _safe_error(exc: BaseException, *, max_len: int = 900) -> str:
    text = " ".join(str(exc).strip().split()) or type(exc).__name__
    return text[:max_len]


def _cleanup_cuda() -> None:
    """Best-effort cache cleanup between repeated full-window passes."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return


def _install_strict_reader() -> str | None:
    forced = os.getenv("FORCE_QWENVL_VIDEO_READER", "").strip().lower()
    if not forced:
        return None
    if forced not in _ALLOWED_STRICT_READERS:
        raise RuntimeError("FORCE_QWENVL_VIDEO_READER must be decord/torchcodec/torchvision")
    if forced == "torchvision":
        return forced

    import qwen_vl_utils.vision_process as vision_process

    backend = vision_process.VIDEO_READER_BACKENDS.get(forced)
    if backend is None:
        raise RuntimeError(f"qwen-vl-utils does not provide video backend: {forced}")
    vision_process.FORCE_QWENVL_VIDEO_READER = forced
    clear = getattr(vision_process.get_video_reader_backend, "cache_clear", None)
    if callable(clear):
        clear()
    # Do not let qwen-vl-utils silently mask a forced-backend failure with torchvision fallback.
    vision_process.VIDEO_READER_BACKENDS["torchvision"] = backend
    return forced


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != VLM_WINDOW_SCHEMA:
        raise ValueError("manifest is not a P2-E2 Episode-window manifest")
    if not isinstance(value.get("windows"), list):
        raise ValueError("manifest.windows must be a list")
    return value


def _video_reference(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved) if os.name == "nt" else resolved.as_uri()


def _validate_forced_reader(path: Path) -> None:
    if os.getenv("FORCE_QWENVL_VIDEO_READER", "").strip().lower() != "decord":
        return

    import decord

    try:
        reader = decord.VideoReader(str(path.resolve()))
        count = int(len(reader))
        fps = float(reader.get_avg_fps())
    except Exception as exc:
        raise RuntimeError(f"decord could not open Episode window: {_safe_error(exc)}") from exc
    if count < 2:
        raise RuntimeError(f"decord Episode window has too few frames: {count}")
    if not math.isfinite(fps) or fps <= 0:
        raise RuntimeError(f"decord Episode window FPS is invalid: {fps}")


def _window_shots(window: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = window.get("shots")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, Mapping))


def _shot_boundary_text(window: Mapping[str, Any]) -> str:
    return "\n".join(
        "- Shot {ordinal}: revision_item_id={item}; window {start:.3f}s → {end:.3f}s".format(
            ordinal=int(shot.get("ordinal") or 0),
            item=str(shot.get("revision_item_id") or ""),
            start=float(shot.get("window_start_seconds") or 0.0),
            end=float(shot.get("window_end_seconds") or 0.0),
        )
        for shot in _window_shots(window)
    )


def _target_shot_text(target_shots: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(
        "- Shot {ordinal}: revision_item_id={item}".format(
            ordinal=int(shot.get("ordinal") or 0),
            item=str(shot.get("revision_item_id") or ""),
        )
        for shot in target_shots
    )


def _generation_budget(requested: int, target_shot_count: int, *, compact: bool) -> int:
    """Bound generation memory while leaving enough room for a small structured batch."""
    requested = max(_MIN_GENERATION_TOKENS, int(requested))
    per_shot = 280 if compact else _TOKENS_PER_TARGET_SHOT
    estimated = _BASE_WINDOW_TOKENS + max(1, int(target_shot_count)) * per_shot
    return min(_MAX_GENERATION_TOKENS, max(requested, estimated))


def _prompt(
    source_language: str,
    window: Mapping[str, Any],
    *,
    target_shots: Sequence[Mapping[str, Any]],
    compact: bool,
) -> str:
    language = (source_language or "und").strip() or "und"
    compact_rule = (
        "每个目标 Shot 最多 3 个 subjects、2 个 events、3 个 props；"
        "描述尽量短，优先保证 JSON 完整闭合。"
        if compact
        else "描述简洁，优先保证 JSON 完整闭合。"
    )
    return f"""你是专业短剧连续视频拉片分析师。当前输入是一段连续视频窗口，不是孤立镜头。
项目原始语言：{language}。你生成的自然语言必须使用简体中文；JSON key、revision_item_id、subject_A 和指定英文枚举保持英文。

【整个窗口的 Shot 边界】
{_shot_boundary_text(window)}

【本次只需要写入 shots[] 的目标 Shot】
{_target_shot_text(target_shots)}

目标 Shot 之外的镜头仍是视觉上下文，必须继续用于判断场景、人物、动作和道具连续性，但不要写进 shots[]。

硬规则：
1. 切镜不等于换场。特写、虚化、背影、插入镜头可以借前后视觉上下文；证据不足写 UNCERTAIN。
2. 只有明确地点变化、明确 INT/EXT 变化或其他强视觉证据才写 NEW_SCENE。
3. 人物只用 subject_A/subject_B... 匿名标签；禁止真实姓名和 Final Character/Scene/Prop/Binding ID。
4. 不转录对白、字幕、招牌、手机/文件文字；这些属于 ASR/OCR。
5. 只保留剧情相关道具。
6. shots[] 必须严格且仅覆盖目标 Shot；revision_item_id 必须原样复制，不遗漏、不重复、不发明。
7. 只返回一个严格合法、完整闭合的 JSON object；不要 Markdown，不要 JSON 外解释。
8. {compact_rule}

稳定枚举：
- scene_continuity: SAME|NEW_SCENE|UNCERTAIN
- scene_basis: DIRECT|CONTEXT|MIXED|UNCERTAIN
- interior_exterior: INT|EXT|MIXED|UNKNOWN
- visibility: FULL|PARTIAL|OCCLUDED|UNKNOWN
- speaking_state: LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN
- event_type: VISUAL|ACTION
- importance: LOW|MEDIUM|HIGH

JSON schema:
{{
  "window_summary":"简体中文窗口摘要",
  "scene_change_candidates":[{{"at_seconds":12.3,"confidence":"LOW|MEDIUM|HIGH","description":"简体中文依据"}}],
  "subject_continuity_hints":[{{"appearance_summary":"简体中文外观","continuity_summary":"简体中文连续性","shot_ordinals":[1,2]}}],
  "prop_continuity_hints":[{{"label":"道具名","continuity_summary":"简体中文连续性","shot_ordinals":[1,2]}}],
  "shots":[{{
    "revision_item_id":"目标清单中的 ID",
    "ordinal":1,
    "scene_continuity":"SAME|NEW_SCENE|UNCERTAIN",
    "scene_basis":"DIRECT|CONTEXT|MIXED|UNCERTAIN",
    "context_note":"简体中文上下文依据",
    "semantic":{{
      "scene":{{"location_hint":"地点或空字符串","interior_exterior":"INT|EXT|MIXED|UNKNOWN","time_of_day":"白天/夜晚/未知","environment_description":"简体中文环境"}},
      "shot":{{"summary":"简体中文摘要","visual_description":"简体中文可见画面","shot_type_hint":"特写/近景/中景/全景","camera_motion_hint":"静止/推近/拉远/跟拍","narrative_function_hint":"简体中文叙事作用","composition_hint":"简体中文构图"}},
      "subjects":[{{"label":"subject_A","appearance_summary":"简体中文可见外观","activity_summary":"简体中文当前动作","screen_position":"左侧/中央/右侧/前景/背景","visibility":"FULL|PARTIAL|OCCLUDED|UNKNOWN","speaking_state":"LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN"}}],
      "events":[{{"event_type":"VISUAL|ACTION","start_ratio":0.0,"end_ratio":1.0,"content":"简体中文可见事件","subject_labels":["subject_A"]}}],
      "props":[{{"label":"简体中文道具名","importance":"LOW|MEDIUM|HIGH","narrative_reason":"简体中文可见原因","subject_labels":["subject_A"]}}]
    }}
  }}]
}}
"""


def _validate_output(
    value: Mapping[str, Any],
    window: Mapping[str, Any],
    *,
    target_shots: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    target = tuple(target_shots) if target_shots is not None else _window_shots(window)
    expected = {
        str(item.get("revision_item_id") or "")
        for item in target
        if str(item.get("revision_item_id") or "")
    }
    shots = value.get("shots")
    if not isinstance(shots, list):
        raise ValueError("window output.shots must be a list")

    seen: set[str] = set()
    for shot in shots:
        if not isinstance(shot, Mapping):
            continue
        item_id = str(shot.get("revision_item_id") or "").strip()
        if item_id not in expected or item_id in seen:
            raise ValueError("window output contains unknown/duplicate revision_item_id")
        seen.add(item_id)
        semantic = shot.get("semantic")
        if not isinstance(semantic, Mapping):
            raise ValueError(f"{item_id} semantic must be an object")
        shot_language_profile.validate_semantic_language(semantic)

    if seen != expected:
        raise ValueError("window output does not cover every target Shot")


def _generate_once(
    *,
    model: Any,
    processor: Any,
    window: Mapping[str, Any],
    target_shots: Sequence[Mapping[str, Any]],
    source_language: str,
    fps: float,
    max_new_tokens: int,
    max_pixels: int,
    compact: bool,
) -> Mapping[str, Any]:
    from qwen_vl_utils import process_vision_info

    video_path = Path(str(window.get("video_path") or ""))
    if not video_path.is_file():
        raise FileNotFoundError("Episode window clip is missing")
    _validate_forced_reader(video_path)

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "video",
                "video": _video_reference(video_path),
                "fps": fps,
                "max_pixels": max_pixels,
            },
            {
                "type": "text",
                "text": _prompt(
                    source_language,
                    window,
                    target_shots=target_shots,
                    compact=compact,
                ),
            },
        ],
    }]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs, video_kwargs = process_vision_info(
        messages,
        image_patch_size=16,
        return_video_kwargs=True,
        return_video_metadata=True,
    )
    if video_inputs is not None:
        videos, video_metadatas = zip(*video_inputs)
        videos = list(videos)
        video_metadatas = list(video_metadatas)
    else:
        videos = None
        video_metadatas = None

    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=videos,
        video_metadata=video_metadatas,
        padding=True,
        return_tensors="pt",
        do_resize=False,
        **video_kwargs,
    )
    inputs = inputs.to(model.device)
    budget = _generation_budget(max_new_tokens, len(target_shots), compact=compact)
    generated_ids = model.generate(**inputs, max_new_tokens=budget, do_sample=False)
    trimmed = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]

    try:
        semantic = base._first_json_object(output_text)
        _validate_output(semantic, window, target_shots=target_shots)
    except ValueError as exc:
        raise ValueError(
            "structured output invalid/truncated "
            f"(targets={len(target_shots)}, budget={budget}, chars={len(output_text)}): "
            f"{_safe_error(exc, max_len=350)}"
        ) from exc
    return semantic


def _append_unique_rows(target: list[Any], source: Any) -> None:
    if not isinstance(source, list):
        return
    known = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for item in target
    }
    for item in source:
        if not isinstance(item, Mapping):
            continue
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if marker not in known:
            known.add(marker)
            target.append(dict(item))


def _merge_batch_results(
    results: Sequence[Mapping[str, Any]],
    window: Mapping[str, Any],
    *,
    target_shots: Sequence[Mapping[str, Any]] | None = None,
) -> Mapping[str, Any]:
    merged: dict[str, Any] = {
        "window_summary": "",
        "scene_change_candidates": [],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
        "shots": [],
    }
    for result in results:
        if not merged["window_summary"]:
            summary = str(result.get("window_summary") or "").strip()
            if summary:
                merged["window_summary"] = summary
        _append_unique_rows(merged["scene_change_candidates"], result.get("scene_change_candidates"))
        _append_unique_rows(merged["subject_continuity_hints"], result.get("subject_continuity_hints"))
        _append_unique_rows(merged["prop_continuity_hints"], result.get("prop_continuity_hints"))
        shots = result.get("shots")
        if isinstance(shots, list):
            merged["shots"].extend(dict(item) for item in shots if isinstance(item, Mapping))

    target = tuple(target_shots) if target_shots is not None else _window_shots(window)
    order = {
        str(shot.get("revision_item_id") or ""): index
        for index, shot in enumerate(target)
    }
    merged["shots"].sort(
        key=lambda item: order.get(str(item.get("revision_item_id") or ""), len(order))
    )
    _validate_output(merged, window, target_shots=target)
    return merged


def _generate_compact_adaptive(
    *,
    model: Any,
    processor: Any,
    window: Mapping[str, Any],
    target_shots: Sequence[Mapping[str, Any]],
    source_language: str,
    fps: float,
    max_new_tokens: int,
    max_pixels: int,
) -> Mapping[str, Any]:
    """Generate one compact target batch; recursively split only on structured-output failure."""
    targets = tuple(target_shots)
    try:
        return _generate_once(
            model=model,
            processor=processor,
            window=window,
            target_shots=targets,
            source_language=source_language,
            fps=fps,
            max_new_tokens=max_new_tokens,
            max_pixels=max_pixels,
            compact=True,
        )
    except ValueError as exc:
        if len(targets) <= 1:
            raise ValueError(
                "single-target compact structured output failed: " + _safe_error(exc, max_len=700)
            ) from exc
        midpoint = max(1, len(targets) // 2)
        left = _generate_compact_adaptive(
            model=model,
            processor=processor,
            window=window,
            target_shots=targets[:midpoint],
            source_language=source_language,
            fps=fps,
            max_new_tokens=max_new_tokens,
            max_pixels=max_pixels,
        )
        _cleanup_cuda()
        right = _generate_compact_adaptive(
            model=model,
            processor=processor,
            window=window,
            target_shots=targets[midpoint:],
            source_language=source_language,
            fps=fps,
            max_new_tokens=max_new_tokens,
            max_pixels=max_pixels,
        )
        return _merge_batch_results((left, right), window, target_shots=targets)


def _analyze_window(
    *,
    model: Any,
    processor: Any,
    window: Mapping[str, Any],
    source_language: str,
    fps: float,
    max_new_tokens: int,
    max_pixels: int,
) -> Mapping[str, Any]:
    shots = _window_shots(window)
    if not shots:
        raise ValueError("Episode window contains no Shot manifest rows")

    # Small windows get one normal response. Rapid-cut windows skip the risky giant JSON entirely.
    if len(shots) <= _DIRECT_TARGET_SHOT_LIMIT:
        try:
            return _generate_once(
                model=model,
                processor=processor,
                window=window,
                target_shots=shots,
                source_language=source_language,
                fps=fps,
                max_new_tokens=max_new_tokens,
                max_pixels=max_pixels,
                compact=False,
            )
        except ValueError:
            _cleanup_cuda()
            return _generate_compact_adaptive(
                model=model,
                processor=processor,
                window=window,
                target_shots=shots,
                source_language=source_language,
                fps=fps,
                max_new_tokens=max_new_tokens,
                max_pixels=max_pixels,
            )

    results: list[Mapping[str, Any]] = []
    for index in range(0, len(shots), _FALLBACK_TARGET_BATCH_SHOTS):
        batch = shots[index:index + _FALLBACK_TARGET_BATCH_SHOTS]
        results.append(_generate_compact_adaptive(
            model=model,
            processor=processor,
            window=window,
            target_shots=batch,
            source_language=source_language,
            fps=fps,
            max_new_tokens=max_new_tokens,
            max_pixels=max_pixels,
        ))
        _cleanup_cuda()
    return _merge_batch_results(results, window)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen3-VL Episode-window Breakdown semantics")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--max-pixels", type=int, default=524288)
    args = parser.parse_args()

    try:
        manifest = _load_manifest(Path(args.manifest))
        source_language = str(manifest.get("source_language") or "und")
        _install_strict_reader()
        device = base._resolve_device(args.device)
        model, processor = base._load_model(Path(args.model_path), device)
    except Exception as exc:
        # The parent process captures stdout+stderr. Keep one sanitized fatal line so the UI can
        # surface model-load/runtime failures instead of only "P2-E2 VLM inference failed".
        print(f"P2-E2 FATAL {type(exc).__name__}: {_safe_error(exc)}", flush=True)
        return 2

    records: list[dict[str, Any]] = []
    for window in manifest["windows"]:
        if not isinstance(window, Mapping):
            continue
        window_id = str(window.get("window_id") or "").strip()
        if not window_id:
            continue
        try:
            semantic = _analyze_window(
                model=model,
                processor=processor,
                window=window,
                source_language=source_language,
                fps=float(args.fps),
                max_new_tokens=int(args.max_new_tokens),
                max_pixels=int(args.max_pixels),
            )
            records.append({
                "window_id": window_id,
                "status": "READY",
                "semantic": semantic,
            })
        except Exception as exc:
            records.append({
                "window_id": window_id,
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error_detail": _safe_error(exc),
            })
        finally:
            _cleanup_cuda()

    output = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    base._atomic_write_text(Path(args.output), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
