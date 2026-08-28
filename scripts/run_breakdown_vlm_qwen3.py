"""Isolated Qwen3-VL runner for Breakdown P2.4.

This script runs inside the already isolated Python 3.12 VLM runtime. It loads the base
Qwen3-VL content-understanding checkpoint exactly once, then analyzes historical Reference Clips
sequentially. The main Python 3.11 application only consumes the normalized JSONL output through
``breakdown_p2_vlm_v1``.

The runner deliberately does not perform ASR or OCR. Dialogue/text evidence belongs to the P2.2
and P2.3 providers and is fused later in P2.5.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

VLM_SEMANTIC_SCHEMA = "breakdown-p2-vlm-shot-semantics-v1"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    shots = value.get("shots")
    if not isinstance(shots, list):
        raise ValueError("manifest.shots must be a list")
    return value


def _first_json_object(text: str) -> Mapping[str, Any]:
    """Extract one JSON object without persisting surrounding model chatter."""

    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        value = json.loads(candidate)
        if isinstance(value, Mapping):
            return value
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    if start < 0:
        raise ValueError("model output contains no JSON object")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                value = json.loads(candidate[start:index + 1])
                if isinstance(value, Mapping):
                    return value
                break
    raise ValueError("model output JSON object is invalid")


def _prompt(source_language: str) -> str:
    language = (source_language or "und").strip() or "und"
    return f"""You are a professional short-drama shot analyst.
Analyze ONLY what is visually supported by this single Reference Clip.
The project source language is {language}; write descriptive text in that language when practical.

Hard rules:
1. Never guess a real person name, global identity, Character ID, Scene ID, Prop ID, or any business/database ID.
2. People are anonymous within this shot only. Label them subject_A, subject_B, subject_C... in stable visual order.
3. Do not transcribe dialogue, subtitles, signs, phone screens, documents, or other readable text. ASR/OCR are separate providers.
4. speaking_state is only a visual hint from mouth/body interaction; it is NOT speaker identity truth.
5. Only include plot-relevant props, not every background object.
6. Use normalized event start_ratio/end_ratio from 0 to 1 relative to this clip. Do not invent exact source timestamps.
7. If uncertain, use UNKNOWN or omit the detail. Do not fill gaps by imagination.
8. Return exactly one JSON object and no prose outside JSON.

JSON schema:
{{
  "scene": {{
    "location_hint": "string or empty",
    "interior_exterior": "INT|EXT|MIXED|UNKNOWN",
    "time_of_day": "string or empty",
    "environment_description": "string or empty"
  }},
  "shot": {{
    "summary": "concise visible action/content",
    "visual_description": "visible composition and action",
    "shot_type_hint": "string or empty",
    "camera_motion_hint": "string or empty",
    "narrative_function_hint": "string or empty",
    "composition_hint": "string or empty"
  }},
  "subjects": [
    {{
      "label": "subject_A",
      "appearance_summary": "visible appearance only",
      "activity_summary": "visible action only",
      "screen_position": "string or empty",
      "visibility": "FULL|PARTIAL|OCCLUDED|UNKNOWN",
      "speaking_state": "LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN"
    }}
  ],
  "events": [
    {{
      "event_type": "VISUAL|ACTION",
      "start_ratio": 0.0,
      "end_ratio": 1.0,
      "content": "visible event",
      "subject_labels": ["subject_A"]
    }}
  ],
  "props": [
    {{
      "label": "plot-relevant object hint",
      "importance": "LOW|MEDIUM|HIGH",
      "narrative_reason": "why it appears relevant from visible interaction",
      "subject_labels": ["subject_A"]
    }}
  ]
}}
"""


def _resolve_device(requested: str) -> str:
    import torch

    requested = requested.strip().lower()
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was explicitly requested but is unavailable")
        return "cuda"
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cpu":
        return "cpu"
    raise ValueError("device must be auto/cpu/cuda")


def _load_model(model_path: Path, device: str):
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else (
        torch.float16 if device == "cuda" else torch.float32
    )
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(model_path),
        torch_dtype=dtype,
        device_map="auto" if device == "cuda" else None,
        local_files_only=True,
    )
    if device == "cpu":
        model = model.to("cpu")
    model.eval()
    processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True)
    return model, processor


def _analyze_shot(
    *,
    model: Any,
    processor: Any,
    video_path: Path,
    source_language: str,
    fps: float,
    max_new_tokens: int,
    max_pixels: int,
) -> Mapping[str, Any]:
    from qwen_vl_utils import process_vision_info

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "video",
                "video": video_path.resolve().as_uri(),
                "fps": fps,
                "max_pixels": max_pixels,
            },
            {"type": "text", "text": _prompt(source_language)},
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
    generated_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
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
    return _first_json_object(output_text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen3-VL anonymous Breakdown semantics")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    parser.add_argument("--max-pixels", type=int, default=524288)
    args = parser.parse_args()

    manifest = _load_manifest(Path(args.manifest))
    source_language = str(manifest.get("source_language") or "und")
    device = _resolve_device(args.device)
    model, processor = _load_model(Path(args.model_path), device)

    records: list[dict[str, Any]] = []
    for shot in manifest["shots"]:
        if not isinstance(shot, Mapping):
            continue
        revision_item_id = str(shot.get("revision_item_id") or "").strip()
        clip = Path(str(shot.get("reference_clip_path") or ""))
        ordinal = int(shot.get("ordinal") or 0)
        if not revision_item_id:
            continue
        try:
            if not clip.is_file():
                raise FileNotFoundError("Reference Clip is missing")
            semantic = _analyze_shot(
                model=model,
                processor=processor,
                video_path=clip,
                source_language=source_language,
                fps=float(args.fps),
                max_new_tokens=int(args.max_new_tokens),
                max_pixels=int(args.max_pixels),
            )
            records.append({
                "revision_item_id": revision_item_id,
                "ordinal": ordinal,
                "status": "READY",
                "semantic": semantic,
            })
        except Exception as exc:
            records.append({
                "revision_item_id": revision_item_id,
                "ordinal": ordinal,
                "status": "FAILED",
                "error_type": type(exc).__name__,
            })

    output = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    _atomic_write_text(Path(args.output), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
