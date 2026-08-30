#!/usr/bin/env python3
"""Single-load Qwen3-VL runner for fast grounded Breakdown.

The model is loaded once for the complete Episode. It first reads each overlapping Episode window
once to obtain Scene/anonymous continuity context, then grounds exact frozen Shots from 1..3
sampled images in small batches. Window context is never allowed to create visible people/actions/
props in an exact Shot.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import run_breakdown_vlm_qwen3 as base

FAST_GROUNDED_SCHEMA = "breakdown-p2-vlm-fast-grounded-v1"


def _safe_error(exc: BaseException, *, max_len: int = 900) -> str:
    text = " ".join(str(exc).strip().split()) or type(exc).__name__
    return text[:max_len]


def _cleanup_cuda() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != FAST_GROUNDED_SCHEMA:
        raise ValueError("manifest is not fast-grounded VLM input")
    if not isinstance(value.get("windows"), list):
        raise ValueError("manifest.windows must be a list")
    if not isinstance(value.get("grounding_shots"), list):
        raise ValueError("manifest.grounding_shots must be a list")
    return value


def _media_ref(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved) if os.name == "nt" else resolved.as_uri()


def _window_shots(window: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = window.get("shots")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, Mapping))


def _shot_boundary_text(window: Mapping[str, Any]) -> str:
    return "\n".join(
        "- Shot {ordinal}: revision_item_id={item}; {start:.3f}s→{end:.3f}s".format(
            ordinal=int(shot.get("ordinal") or 0),
            item=str(shot.get("revision_item_id") or ""),
            start=float(shot.get("window_start_seconds") or 0.0),
            end=float(shot.get("window_end_seconds") or 0.0),
        )
        for shot in _window_shots(window)
    )


def _window_prompt(source_language: str, window: Mapping[str, Any]) -> str:
    language = (source_language or "und").strip() or "und"
    return f"""你是专业短剧的连续场景理解器。当前输入是一段连续视频窗口。
项目原始语言：{language}。生成说明文字使用简体中文；JSON key、revision_item_id、英文枚举保持英文。

【窗口内 Shot 边界】
{_shot_boundary_text(window)}

你的任务只做“跨镜上下文”，不要为每个 Shot 写完整画面描述。

硬规则：
1. 切镜不等于换场；人物特写、背景虚化、插入镜头不能因为看不到环境就自动换场。
2. 只有明确地点改变、明确 INT/EXT 改变或其他强视觉证据才判 NEW_SCENE。
3. 观察匿名人物跨镜连续性，但不要猜真实姓名、Character ID 或其他 Final ID。
4. 可以描述稳定外观用于连续性判断；表情、动作、姿态、屏幕左右位置不是人物身份。
5. 不转录对白、字幕、招牌、手机/文件文字；ASR/OCR 单独负责。
6. 道具连续性只保留剧情相关物体。
7. shot_scene_hints 必须引用给定 Shot；不发明 Shot。
8. 只返回一个完整 JSON object，不要 Markdown 或 JSON 外解释。

JSON schema：
{{
  "window_summary":"简体中文，概括这段连续剧情与主要场景",
  "scene_change_candidates":[{{"at_seconds":12.3,"confidence":"LOW|MEDIUM|HIGH","description":"换场依据"}}],
  "subject_continuity_hints":[{{
    "appearance_summary":"稳定外观摘要",
    "continuity_summary":"为什么认为是同一匿名人物",
    "shot_ordinals":[1,2,3]
  }}],
  "prop_continuity_hints":[{{
    "label":"道具名",
    "continuity_summary":"连续性说明",
    "shot_ordinals":[1,2]
  }}],
  "shot_scene_hints":[{{
    "revision_item_id":"必须原样复制",
    "ordinal":1,
    "scene_continuity":"SAME|NEW_SCENE|UNCERTAIN",
    "scene_basis":"DIRECT|CONTEXT|MIXED|UNCERTAIN",
    "context_note":"简短依据",
    "scene":{{
      "location_hint":"稳定地点或空字符串",
      "interior_exterior":"INT|EXT|MIXED|UNKNOWN",
      "time_of_day":"白天/夜晚/未知",
      "environment_description":"场景环境概述或空字符串"
    }}
  }}]
}}
"""


def _grounding_scene_contexts(
    batch: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for shot in batch:
        item_id = str(shot.get("revision_item_id") or "").strip()
        try:
            ordinal = int(shot.get("ordinal") or 0)
        except (TypeError, ValueError):
            ordinal = 0
        contexts: list[dict[str, Any]] = []
        for window in windows:
            if not any(
                int(candidate.get("ordinal") or 0) == ordinal
                for candidate in _window_shots(window)
            ):
                continue
            window_id = str(window.get("window_id") or "").strip()
            semantic = window_results.get(window_id)
            if not isinstance(semantic, Mapping):
                continue
            matched_hint = None
            raw_hints = semantic.get("shot_scene_hints")
            if isinstance(raw_hints, list):
                for hint in raw_hints:
                    if not isinstance(hint, Mapping):
                        continue
                    if (
                        str(hint.get("revision_item_id") or "").strip() == item_id
                        or int(hint.get("ordinal") or 0) == ordinal
                    ):
                        matched_hint = dict(hint)
                        break
            contexts.append({
                "window_id": window_id,
                "window_summary": semantic.get("window_summary"),
                "shot_scene_hint": matched_hint,
            })
        result[item_id] = contexts[:3]
    return result


def _grounding_prompt(
    source_language: str,
    batch: Sequence[Mapping[str, Any]],
    scene_contexts: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    language = (source_language or "und").strip() or "und"
    target_text = "\n".join(
        f"- Shot {int(shot.get('ordinal') or 0)}: revision_item_id={str(shot.get('revision_item_id') or '')}; "
        f"frames={len(shot.get('frames') or [])}"
        for shot in batch
    )
    context_json = json.dumps(scene_contexts, ensure_ascii=False, separators=(",", ":"))
    return f"""你是专业短剧的“Exact-Shot 视觉事实校验器”。
项目原始语言：{language}。生成描述使用简体中文；JSON key、revision_item_id、subject_* 与英文枚举保持英文。

【目标 Shot】
{target_text}

【允许借用的 Scene 上下文】
{context_json}

你随后会看到按 Shot 分组的 1~3 张采样图片。这些图片来自各自 exact frozen Shot。

最重要的硬规则：
1. subjects / events / props / shot.visual_description / shot.summary 的“可见内容”只能来自当前 Shot 自己的图片。
2. Scene 上下文只能帮助填写 scene.location_hint / interior_exterior / time_of_day / environment_description，不能把邻镜的人、动作、道具搬进当前 Shot。
3. 如果当前 Shot 图片只有花束，就必须 subjects=[]；不能因为上下文有人物而写人物。
4. 如果当前 Shot 图片没有某个道具，就不能因为前后镜出现该道具而写进 props。
5. 人物仅用当前 Shot 内匿名 subject_A/subject_B...；按当前 Shot 的稳定视觉顺序标记，不代表跨镜身份。
6. 不转录对白、字幕、招牌、手机/文件文字；ASR/OCR 单独负责。
7. 不猜真实姓名、Character/Scene/Prop/Asset/Binding ID。
8. camera_motion_hint 在静态采样图无法确认时写空字符串或 UNKNOWN，不要猜。
9. 每个目标 Shot 必须且只能输出一次；revision_item_id 原样复制。
10. 描述简洁，优先保证严格合法、完整闭合 JSON；JSON 外不要解释。

JSON schema：
{{
  "shots":[{{
    "revision_item_id":"目标ID",
    "semantic":{{
      "scene":{{
        "location_hint":"地点或空字符串",
        "interior_exterior":"INT|EXT|MIXED|UNKNOWN",
        "time_of_day":"白天/夜晚/未知",
        "environment_description":"环境描述或空字符串"
      }},
      "shot":{{
        "summary":"当前 Shot 核心可见内容",
        "visual_description":"只写当前 Shot 图片直接支持的画面事实",
        "shot_type_hint":"特写/近景/中景/全景或空字符串",
        "camera_motion_hint":"静止/UNKNOWN/空字符串",
        "narrative_function_hint":"基于画面与 Scene 上下文的简短叙事作用",
        "composition_hint":"当前 Shot 构图或空字符串"
      }},
      "subjects":[{{
        "label":"subject_A",
        "appearance_summary":"当前 Shot 可见稳定外观",
        "activity_summary":"当前 Shot 可见动作",
        "screen_position":"左侧/中央/右侧/前景/背景",
        "visibility":"FULL|PARTIAL|OCCLUDED|UNKNOWN",
        "speaking_state":"LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN"
      }}],
      "events":[{{
        "event_type":"VISUAL|ACTION",
        "start_ratio":0.0,
        "end_ratio":1.0,
        "content":"当前 Shot 可见事件",
        "subject_labels":["subject_A"]
      }}],
      "props":[{{
        "label":"剧情相关可见道具",
        "importance":"LOW|MEDIUM|HIGH",
        "narrative_reason":"仅基于当前画面可见关系",
        "subject_labels":["subject_A"]
      }}]
    }}
  }}]
}}
"""


def _prepare_inputs(model: Any, processor: Any, messages: Sequence[Mapping[str, Any]]):
    from qwen_vl_utils import process_vision_info

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
    return inputs.to(model.device)


def _generate_json(
    *,
    model: Any,
    processor: Any,
    messages: Sequence[Mapping[str, Any]],
    max_new_tokens: int,
) -> Mapping[str, Any]:
    inputs = _prepare_inputs(model, processor, messages)
    generated_ids = model.generate(
        **inputs,
        max_new_tokens=int(max_new_tokens),
        do_sample=False,
    )
    trimmed = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    return base._first_json_object(output_text)


def _analyze_window(
    *,
    model: Any,
    processor: Any,
    window: Mapping[str, Any],
    source_language: str,
    fps: float,
    max_pixels: int,
    max_new_tokens: int,
) -> Mapping[str, Any]:
    video_path = Path(str(window.get("video_path") or ""))
    if not video_path.is_file():
        raise FileNotFoundError("Episode window clip missing")
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "video",
                "video": _media_ref(video_path),
                "fps": float(fps),
                "max_pixels": int(max_pixels),
            },
            {"type": "text", "text": _window_prompt(source_language, window)},
        ],
    }]
    value = _generate_json(
        model=model,
        processor=processor,
        messages=messages,
        max_new_tokens=max_new_tokens,
    )
    raw_hints = value.get("shot_scene_hints")
    if raw_hints is not None and not isinstance(raw_hints, list):
        raise ValueError("window shot_scene_hints must be a list")
    return value


def _grounding_messages(
    *,
    source_language: str,
    batch: Sequence[Mapping[str, Any]],
    scene_contexts: Mapping[str, Sequence[Mapping[str, Any]]],
    max_pixels: int,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": _grounding_prompt(source_language, batch, scene_contexts),
    }]
    for shot in batch:
        item_id = str(shot.get("revision_item_id") or "").strip()
        ordinal = int(shot.get("ordinal") or 0)
        content.append({
            "type": "text",
            "text": f"下面图片只属于 Shot {ordinal} / revision_item_id={item_id}。",
        })
        raw_frames = shot.get("frames")
        if not isinstance(raw_frames, list) or not raw_frames:
            raise ValueError(f"Shot {ordinal} has no grounding frames")
        for index, raw in enumerate(raw_frames, start=1):
            if not isinstance(raw, Mapping):
                continue
            path = Path(str(raw.get("path") or ""))
            if not path.is_file():
                raise FileNotFoundError(f"Shot {ordinal} frame missing")
            ratio = float(raw.get("ratio") or 0.5)
            content.append({"type": "text", "text": f"Shot {ordinal} frame {index}, ratio={ratio:.2f}"})
            content.append({
                "type": "image",
                "image": _media_ref(path),
                "max_pixels": int(max_pixels),
            })
    return [{"role": "user", "content": content}]


def _validate_grounding_output(
    value: Mapping[str, Any],
    batch: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    expected = {
        str(item.get("revision_item_id") or "").strip()
        for item in batch
        if str(item.get("revision_item_id") or "").strip()
    }
    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list):
        raise ValueError("grounding output.shots must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_shots:
        if not isinstance(raw, Mapping):
            continue
        item_id = str(raw.get("revision_item_id") or "").strip()
        if item_id not in expected or item_id in seen:
            raise ValueError("grounding output has unknown/duplicate Shot")
        semantic = raw.get("semantic")
        if not isinstance(semantic, Mapping):
            raise ValueError(f"{item_id} semantic must be an object")
        seen.add(item_id)
        result.append({"revision_item_id": item_id, "semantic": dict(semantic)})
    if seen != expected:
        raise ValueError("grounding output does not cover every target Shot")
    return result


def _analyze_grounding_batch(
    *,
    model: Any,
    processor: Any,
    batch: Sequence[Mapping[str, Any]],
    source_language: str,
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
    max_pixels: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    contexts = _grounding_scene_contexts(batch, windows, window_results)
    value = _generate_json(
        model=model,
        processor=processor,
        messages=_grounding_messages(
            source_language=source_language,
            batch=batch,
            scene_contexts=contexts,
            max_pixels=max_pixels,
        ),
        max_new_tokens=max_new_tokens,
    )
    return _validate_grounding_output(value, batch)


def _grounding_adaptive(
    *,
    model: Any,
    processor: Any,
    batch: Sequence[Mapping[str, Any]],
    source_language: str,
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
    max_pixels: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    targets = tuple(batch)
    try:
        return _analyze_grounding_batch(
            model=model,
            processor=processor,
            batch=targets,
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
    except Exception:
        if len(targets) <= 1:
            raise
        midpoint = max(1, len(targets) // 2)
        left = _grounding_adaptive(
            model=model,
            processor=processor,
            batch=targets[:midpoint],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        _cleanup_cuda()
        right = _grounding_adaptive(
            model=model,
            processor=processor,
            batch=targets[midpoint:],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        return [*left, *right]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fast grounded Episode Breakdown with one Qwen3-VL load")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--window-fps", type=float, default=1.0)
    parser.add_argument("--window-max-pixels", type=int, default=262144)
    parser.add_argument("--window-max-new-tokens", type=int, default=1600)
    parser.add_argument("--grounding-max-pixels", type=int, default=524288)
    parser.add_argument("--grounding-max-new-tokens", type=int, default=4096)
    parser.add_argument("--grounding-batch-size", type=int, default=5)
    args = parser.parse_args()

    manifest = _load_manifest(Path(args.manifest))
    source_language = str(manifest.get("source_language") or "und")
    windows = tuple(item for item in manifest["windows"] if isinstance(item, Mapping))
    grounding_shots = tuple(item for item in manifest["grounding_shots"] if isinstance(item, Mapping))

    device = base._resolve_device(args.device)
    model, processor = base._load_model(Path(args.model_path), device)

    records: list[dict[str, Any]] = []
    window_results: dict[str, Mapping[str, Any]] = {}
    for window in windows:
        window_id = str(window.get("window_id") or "").strip()
        if not window_id:
            continue
        try:
            semantic = _analyze_window(
                model=model,
                processor=processor,
                window=window,
                source_language=source_language,
                fps=float(args.window_fps),
                max_pixels=int(args.window_max_pixels),
                max_new_tokens=int(args.window_max_new_tokens),
            )
            window_results[window_id] = semantic
            records.append({
                "kind": "window_context",
                "window_id": window_id,
                "status": "READY",
                "semantic": semantic,
            })
        except Exception as exc:
            records.append({
                "kind": "window_context",
                "window_id": window_id,
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error_detail": _safe_error(exc),
            })
        _cleanup_cuda()

    batch_size = max(1, min(12, int(args.grounding_batch_size)))
    for start in range(0, len(grounding_shots), batch_size):
        batch = grounding_shots[start:start + batch_size]
        try:
            results = _grounding_adaptive(
                model=model,
                processor=processor,
                batch=batch,
                source_language=source_language,
                windows=windows,
                window_results=window_results,
                max_pixels=int(args.grounding_max_pixels),
                max_new_tokens=int(args.grounding_max_new_tokens),
            )
            for result in results:
                item_id = str(result.get("revision_item_id") or "").strip()
                records.append({
                    "kind": "shot_grounding",
                    "revision_item_id": item_id,
                    "status": "READY",
                    "semantic": result.get("semantic"),
                })
        except Exception as exc:
            for shot in batch:
                records.append({
                    "kind": "shot_grounding",
                    "revision_item_id": str(shot.get("revision_item_id") or "").strip(),
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error_detail": _safe_error(exc),
                })
        _cleanup_cuda()

    output = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    base._atomic_write_text(Path(args.output), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
