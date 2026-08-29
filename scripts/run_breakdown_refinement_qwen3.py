#!/usr/bin/env python3
"""Isolated text-only Qwen3-VL runner for Breakdown P2-E3 contextual Shot refinement.

E3 is an optional semantic refinement layer on top of already-valid E2 visual semantics. Runtime
setup failures therefore must be serialized as per-Shot FAILED records so the main process can
fall back to E2 instead of losing the whole BreakdownRun. Item-level failures follow the same
rule. The runner still never creates Final Character/Scene/Prop/Binding truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import breakdown_vlm_prompt_zh_v1 as language_profile
import run_breakdown_vlm_qwen3 as base

REFINEMENT_INPUT_SCHEMA = "breakdown-p2-contextual-refinement-input-v1"


def _safe_error(exc: BaseException, *, max_len: int = 900) -> str:
    text = " ".join(str(exc).strip().split()) or type(exc).__name__
    return text[:max_len]


def _cleanup_cuda() -> None:
    """Best-effort cleanup after a failed text-generation call."""

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != REFINEMENT_INPUT_SCHEMA:
        raise ValueError("manifest is not a P2-E3 refinement manifest")
    if not isinstance(value.get("items"), list):
        raise ValueError("manifest.items must be a list")
    return value


def _manifest_items(manifest: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = manifest.get("items")
    if not isinstance(raw, list):
        return ()
    return tuple(
        item for item in raw
        if isinstance(item, Mapping) and str(item.get("revision_item_id") or "").strip()
    )


def _failure_records(
    items: Sequence[Mapping[str, Any]],
    exc: BaseException,
    *,
    stage: str,
) -> list[dict[str, Any]]:
    error_type = type(exc).__name__
    detail = _safe_error(exc)
    return [
        {
            "revision_item_id": str(item.get("revision_item_id") or "").strip(),
            "status": "FAILED",
            "error_type": error_type,
            "error_detail": detail,
            "failure_stage": stage,
            "refinement_note": f"E3 {stage} 失败，保留 E2 结果：{error_type}: {detail}",
        }
        for item in items
    ]


def _write_records(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    output = "".join(
        json.dumps(dict(record), ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    base._atomic_write_text(path, output)


def _prompt(source_language: str, item: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(item), ensure_ascii=False, separators=(",", ":"))
    return f"""你是一名专业短剧拉片的“镜头上下文精修器”。当前阶段是 P2-E3。
项目原始语言：{source_language or 'und'}。你不会直接看到原视频；视觉事实只能来自 E2 已经看过连续视频窗口后给出的结构化视觉观察。

你的输入同时包含：当前 Scene 的保守上下文、Previous/Current/Next Shot 的 E2 视觉语义、选中/支持窗口摘要、邻域 ASR、邻域 OCR。

硬规则：
1. 只精修 current_shot；previous/next/window 只能提供上下文，不能把邻镜头里独有的物体或人物搬进当前镜头。
2. ASR_SEGMENT 是对白文本真值。你可以用对白理解剧情语境，但不要在 semantic 中转录、改写、翻译或猜 speaker 身份。
3. OCR 是画面文字观察。可以用来理解当前动作/叙事作用，但不要篡改 OCR 文本，也不要把 OCR 当人物身份。
4. current_shot.semantic.subjects 中已有的 subject_A/subject_B... 是本镜头允许使用的唯一匿名人物标签；禁止新增、改名或猜真实姓名。
5. LocalSubject != Character；禁止输出 Character ID、Scene ID、Prop ID、Asset ID、Binding ID 或任何 Final 业务身份。
6. 场景特写/虚化背景可根据 scene_context 和前后镜头消除 UNKNOWN，但只有上下文真的支持时才补全；明确冲突时保留当前镜头直接视觉事实。
7. 只保留剧情相关道具。不要把背景杂物因为 ASR/OCR 提到就强行写进当前画面。
8. 景别、运镜、构图等视觉字段优先相信 current_shot 的 E2 视觉观察；不要从对白推断摄影事实。
9. 所有新生成自然语言描述使用简体中文；JSON key、revision_item_id、subject_* 和指定英文枚举保持原样。
10. 只返回一个 JSON object，JSON 外不要输出解释。

输出 JSON schema：
{{
  "revision_item_id": "必须原样复制输入 revision_item_id",
  "refinement_note": "简体中文，简要说明主要利用了哪些上下文进行精修，不写推理过程",
  "semantic": {{
    "scene": {{
      "location_hint": "简体中文稳定地点短语或空字符串",
      "interior_exterior": "INT|EXT|MIXED|UNKNOWN",
      "time_of_day": "简体中文时间提示或空字符串",
      "environment_description": "简体中文环境描述或空字符串"
    }},
    "shot": {{
      "summary": "简体中文镜头核心内容",
      "visual_description": "简体中文当前镜头可见构图与动作",
      "shot_type_hint": "简体中文景别短词或空字符串",
      "camera_motion_hint": "简体中文运镜短词或空字符串",
      "narrative_function_hint": "简体中文叙事作用",
      "composition_hint": "简体中文构图提示或空字符串"
    }},
    "subjects": [
      {{
        "label": "仅允许 current_shot 中已存在的 subject_*",
        "appearance_summary": "简体中文当前镜头可见外观",
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
        "content": "简体中文当前镜头可见事件",
        "subject_labels": ["subject_A"]
      }}
    ],
    "props": [
      {{
        "label": "简体中文剧情相关道具",
        "importance": "LOW|MEDIUM|HIGH",
        "narrative_reason": "简体中文剧情相关原因",
        "subject_labels": ["subject_A"]
      }}
    ]
  }}
}}

输入：
{payload}
"""


def _analyze_item(
    *,
    model: Any,
    processor: Any,
    item: Mapping[str, Any],
    source_language: str,
    max_new_tokens: int,
) -> Mapping[str, Any]:
    messages = [{
        "role": "user",
        "content": [{"type": "text", "text": _prompt(source_language, item)}],
    }]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], padding=True, return_tensors="pt")
    inputs = inputs.to(model.device)
    generated_ids = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    trimmed = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    value = base._first_json_object(output_text)
    expected_id = str(item.get("revision_item_id") or "").strip()
    if str(value.get("revision_item_id") or "").strip() != expected_id:
        raise ValueError("refinement output revision_item_id mismatch")
    semantic = value.get("semantic")
    if not isinstance(semantic, Mapping):
        raise ValueError("refinement output semantic must be an object")
    language_profile.validate_semantic_language(semantic)
    allowed_labels = {
        str(subject.get("label") or "")
        for subject in (
            ((item.get("current_shot") or {}).get("semantic") or {}).get("subjects") or []
        )
        if isinstance(subject, Mapping) and str(subject.get("label") or "")
    }
    output_labels = {
        str(subject.get("label") or "")
        for subject in (semantic.get("subjects") or [])
        if isinstance(subject, Mapping) and str(subject.get("label") or "")
    }
    if not output_labels.issubset(allowed_labels):
        raise ValueError("refinement output introduced unknown subject labels")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen3-VL contextual Shot refinement")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    args = parser.parse_args()

    output_path = Path(args.output)
    manifest = _load_manifest(Path(args.manifest))
    source_language = str(manifest.get("source_language") or "und")
    items = _manifest_items(manifest)

    try:
        device = base._resolve_device(args.device)
        model, processor = base._load_model(Path(args.model_path), device)
    except Exception as exc:
        # E2 already contains the validated visual truth. Serialize setup failure per Shot so the
        # main E3 adapter can fall back instead of failing the complete Breakdown pipeline.
        _write_records(output_path, _failure_records(items, exc, stage="runtime_setup"))
        return 0

    records: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("revision_item_id") or "").strip()
        try:
            value = _analyze_item(
                model=model,
                processor=processor,
                item=item,
                source_language=source_language,
                max_new_tokens=int(args.max_new_tokens),
            )
            records.append({
                "revision_item_id": item_id,
                "status": "READY",
                "refinement_note": value.get("refinement_note"),
                "semantic": value.get("semantic"),
            })
        except Exception as exc:
            records.extend(_failure_records((item,), exc, stage="item_inference"))
            _cleanup_cuda()

    _write_records(output_path, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
