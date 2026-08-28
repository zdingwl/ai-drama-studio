"""Isolated Qwen3-VL runner for Breakdown P2-E2 overlapping Episode windows.

The main app materializes shot-aligned Episode windows and passes an exact Shot boundary
manifest. This runner loads Qwen once, analyzes windows sequentially, and returns one JSONL
record per window. It performs no ASR/OCR and never produces Final asset IDs.

Real short-drama windows may contain many rapid cuts. A single strict JSON object for every
Shot can therefore hit the generation limit before the closing brace. The runner first uses a
shot-count-aware token budget; if strict JSON/contract validation still fails, it retries the
same continuous video as compact target-Shot batches. Every retry still sees the whole window
and all Shot boundaries, so batching limits output size without turning visual understanding
back into isolated per-Shot clips.
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
_FALLBACK_TARGET_BATCH_SHOTS = 6
_MIN_GENERATION_TOKENS = 2048
_MAX_GENERATION_TOKENS = 12288
_BASE_WINDOW_TOKENS = 1024
_TOKENS_PER_TARGET_SHOT = 420


def _safe_error(exc: BaseException, *, max_len: int = 900) -> str:
    text = " ".join(str(exc).strip().split()) or type(exc).__name__
    return text[:max_len]


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
    # Prevent qwen-vl-utils from masking the real forced-backend error with torchvision fallback.
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
    lines: list[str] = []
    for shot in _window_shots(window):
        lines.append(
            "- Shot {ordinal}: revision_item_id={item}; window {start:.3f}s → {end:.3f}s".format(
                ordinal=int(shot.get("ordinal") or 0),
                item=str(shot.get("revision_item_id") or ""),
                start=float(shot.get("window_start_seconds") or 0.0),
                end=float(shot.get("window_end_seconds") or 0.0),
            )
        )
    return "\n".join(lines)


def _target_shot_text(target_shots: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(
        "- Shot {ordinal}: revision_item_id={item}".format(
            ordinal=int(shot.get("ordinal") or 0),
            item=str(shot.get("revision_item_id") or ""),
        )
        for shot in target_shots
    )


def _generation_budget(requested: int, target_shot_count: int, *, compact: bool) -> int:
    """Treat configured max_new_tokens as a floor for multi-Shot structured output.

    E2 originally used a fixed 4096-token cap. A 20-40s short-drama window can contain enough
    rapid cuts that valid JSON is deterministically truncated. This budget grows with the number
    of requested Shot objects while keeping a hard ceiling so a bad generation cannot run away.
    Compact retries need less prose but still receive at least the configured floor.
    """

    requested = max(_MIN_GENERATION_TOKENS, int(requested))
    per_shot = 300 if compact else _TOKENS_PER_TARGET_SHOT
    estimated = _BASE_WINDOW_TOKENS + max(1, int(target_shot_count)) * per_shot
    return min(_MAX_GENERATION_TOKENS, max(requested, estimated))


def _prompt(
    source_language: str,
    window: Mapping[str, Any],
    *,
    target_shots: Sequence[Mapping[str, Any]] | None = None,
    compact: bool = False,
) -> str:
    language = (source_language or "und").strip() or "und"
    all_shots = _window_shots(window)
    targets = tuple(target_shots) if target_shots is not None else all_shots
    boundaries = _shot_boundary_text(window)
    target_text = _target_shot_text(targets)
    compact_rules = """
【紧凑输出规则】
- 这是 JSON 完整性重试。必须优先保证 JSON 闭合和目标 Shot 全覆盖。
- window_summary/context_note/summary/visual_description/environment_description 每项尽量不超过 40 个汉字。
- 每个 Shot 最多 3 个 subjects、2 个 events、3 个 props；没有就输出 []。
- 不重复同一句描述，不输出 Markdown，不输出解释，不输出 null 占位说明。
""" if compact else """

    return f"""你是一名专业的短剧连续视频拉片分析师。你现在看到的是同一集短剧中连续的一段视频窗口，而不是一个孤立镜头。
项目原始语言是 {language}。所有由你生成的自然语言描述必须使用简体中文；JSON key、revision_item_id、subject_A 等匿名标签和指定英文枚举保持原样。

【整个连续窗口的已知 Shot 边界】
{boundaries}

【本次必须写入 shots[] 的目标 Shot】
{target_text}

目标 Shot 之外的其它 Shot 仍然是连续视觉上下文，可以帮助判断场景、人物和道具连续性，但不要把它们写入 shots[]。

【核心任务】
1. 先理解整个连续窗口的场景、人物出入画、动作和关键道具连续性，再分别描述本次目标 Shot。
2. Shot 边界只是展示坐标，不等于场景边界、人物上下文边界或对白断句点。
3. 特写、背影、插入镜头、虚化背景如果自身看不清环境，可以利用窗口前后画面判断它是否延续同一场景；但没有连续性证据时必须写 UNCERTAIN，不得想象。
4. 只有明确地点变化、明显 INT/EXT 变化或其他强视觉证据才给出 NEW_SCENE。普通切镜不能自动判为换场。
5. 人物仍然是匿名视觉主体。每个目标 Shot 内用 subject_A、subject_B...；不要猜真实姓名、Character ID 或跨项目身份。
6. 不要转录对白、字幕、招牌、手机屏幕或文件文字。ASR/OCR 是独立 Provider。
7. 只保留剧情相关道具，不罗列背景杂物。
8. shots[] 必须严格且仅使用“本次目标 Shot”清单中的 revision_item_id；不要遗漏、重复或发明 Shot。
9. 只返回一个严格合法、完整闭合的 JSON object，JSON 外不要输出解释或 Markdown 代码块。
{compact_rules}
【稳定中文规则】
- location_hint 使用简短稳定地点词，例如“客厅”“医院病房”“走廊”；不要无证据加具体店名或房间号。
- appearance_summary 按发型/头部特征 → 上衣 → 下装 → 显著配饰/手持物，客观简洁。
- shot_type_hint 使用“特写/近景/中景/全景”等短词；camera_motion_hint 使用“静止/推近/拉远/跟拍”等短词。
- scene_continuity 枚举：SAME|NEW_SCENE|UNCERTAIN。
- scene_basis 枚举：DIRECT（当前 Shot 自己看得出）|CONTEXT（主要借前后镜头）|MIXED|UNCERTAIN。
- scene_change_candidates.confidence：LOW|MEDIUM|HIGH。

JSON schema:
{{
  "window_summary": "简体中文连续窗口摘要",
  "scene_change_candidates": [
    {{"at_seconds": 12.3, "confidence": "LOW|MEDIUM|HIGH", "description": "简体中文换场依据"}}
  ],
  "subject_continuity_hints": [
    {{"appearance_summary": "简体中文稳定外观", "continuity_summary": "简体中文连续性提示", "shot_ordinals": [1,2]}}
  ],
  "prop_continuity_hints": [
    {{"label": "简体中文道具名", "continuity_summary": "简体中文连续性提示", "shot_ordinals": [1,2]}}
  ],
  "shots": [
    {{
      "revision_item_id": "必须原样复制目标清单中的 ID",
      "ordinal": 1,
      "scene_continuity": "SAME|NEW_SCENE|UNCERTAIN",
      "scene_basis": "DIRECT|CONTEXT|MIXED|UNCERTAIN",
      "context_note": "简体中文连续上下文依据",
      "semantic": {{
        "scene": {{
          "location_hint": "简体中文稳定地点短语或空字符串",
          "interior_exterior": "INT|EXT|MIXED|UNKNOWN",
          "time_of_day": "简体中文时间提示或空字符串",
          "environment_description": "简体中文环境描述或空字符串"
        }},
        "shot": {{
          "summary": "简体中文镜头核心内容摘要",
          "visual_description": "简体中文可见构图与动作描述",
          "shot_type_hint": "简体中文短景别术语或空字符串",
          "camera_motion_hint": "简体中文短运镜术语或空字符串",
          "narrative_function_hint": "简体中文叙事功能提示或空字符串",
          "composition_hint": "简体中文构图提示或空字符串"
        }},
        "subjects": [
          {{
            "label": "subject_A",
            "appearance_summary": "简体中文可见外观",
            "activity_summary": "简体中文当前动作",
            "screen_position": "简体中文位置或空字符串",
            "visibility": "FULL|PARTIAL|OCCLUDED|UNKNOWN",
            "speaking_state": "LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN"
          }}
        ],
        "events": [
          {{
            "event_type": "VISUAL|ACTION",
            "start_ratio": 0.0,
            "end_ratio": 1.0,
            "content": "简体中文可见事件",
            "subject_labels": ["subject_A"]
          }}
        ],
        "props": [
          {{
            "label": "简体中文稳定道具名",
            "importance": "LOW|MEDIUM|HIGH",
            "narrative_reason": "简体中文可见剧情相关原因",
            "subject_labels": ["subject_A"]
          }}
        ]
      }}
    }}
  ]
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
    except ValueError as exc:
        raise ValueError(
            f"model output JSON object is invalid or truncated "
            f"(targets={len(target_shots)}, budget={budget}, chars={len(output_text)})"
        ) from exc
    _validate_output(semantic, window, target_shots=target_shots)
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


def _merge_compact_batches(
    results: Sequence[Mapping[str, Any]],
    window: Mapping[str, Any],
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

    order = {
        str(shot.get("revision_item_id") or ""): index
        for index, shot in enumerate(_window_shots(window))
    }
    merged["shots"].sort(
        key=lambda item: order.get(str(item.get("revision_item_id") or ""), len(order))
    )
    _validate_output(merged, window)
    return merged


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
    except ValueError as first_error:
        # Strict JSON/coverage/language failures are usually output-shape failures, not video
        # decoding/model-runtime failures. Retry compactly while preserving the full video window.
        batches = [
            shots[index:index + _FALLBACK_TARGET_BATCH_SHOTS]
            for index in range(0, len(shots), _FALLBACK_TARGET_BATCH_SHOTS)
        ]
        compact_results: list[Mapping[str, Any]] = []
        for batch_index, batch in enumerate(batches, start=1):
            try:
                compact_results.append(_generate_once(
                    model=model,
                    processor=processor,
                    window=window,
                    target_shots=batch,
                    source_language=source_language,
                    fps=fps,
                    max_new_tokens=max_new_tokens,
                    max_pixels=max_pixels,
                    compact=True,
                ))
            except Exception as retry_error:
                raise ValueError(
                    "full-window structured output failed and compact retry failed: "
                    f"batch={batch_index}/{len(batches)}, "
                    f"first={_safe_error(first_error, max_len=350)}, "
                    f"retry={_safe_error(retry_error, max_len=350)}"
                ) from retry_error
        return _merge_compact_batches(compact_results, window)


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

    manifest = _load_manifest(Path(args.manifest))
    source_language = str(manifest.get("source_language") or "und")
    _install_strict_reader()
    device = base._resolve_device(args.device)
    model, processor = base._load_model(Path(args.model_path), device)

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

    output = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    base._atomic_write_text(Path(args.output), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
