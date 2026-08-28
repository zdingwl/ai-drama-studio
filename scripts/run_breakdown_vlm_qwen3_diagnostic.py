"""Diagnostic-preserving Qwen3-VL runner for Breakdown P2.4.

This runner reuses the frozen Qwen3-VL model loading/schema helpers from
``run_breakdown_vlm_qwen3.py`` but preserves a short per-Shot exception detail in
its private JSONL transport. The main provider still fail-closes; the detail exists
only so Windows/local acceptance can distinguish decode, CUDA, processor and model
failures instead of collapsing everything to ``Shot N VLM inference failed``.

Production Draft prose is generated with the Simplified-Chinese prompt profile and
validated before a Shot record is marked READY. If Qwen ignores the requested output
language, the Shot fails closed instead of publishing an English semantic Draft.

For the Windows production profile the parent Provider selects ``decord``. This runner
passes a native filesystem path to that backend and validates it before Qwen processing,
preventing a failed decoder from being masked by qwen-vl-utils' legacy torchvision
fallback (which may raise ``KeyError('video_fps')`` on Windows).
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import breakdown_vlm_prompt_zh_v1 as prompt_profile

# Install before importing/reusing the shared base module. install() imports that
# module once and replaces only its prompt builder; model/schema helpers stay frozen.
prompt_profile.install()
import run_breakdown_vlm_qwen3 as base


def _safe_error(exc: BaseException, *, max_len: int = 900) -> str:
    text = " ".join(str(exc).strip().split())
    if not text:
        text = type(exc).__name__
    return text[:max_len]


def _video_reference(video_path: Path) -> str:
    resolved = video_path.resolve()
    # decord/TorchCodec are happiest with native Windows paths; file:///D:/ URIs
    # can trigger a backend failure that qwen-vl-utils then masks via torchvision.
    if os.name == "nt":
        return str(resolved)
    return resolved.as_uri()


def _validate_forced_video_reader(video_path: Path) -> None:
    reader = os.getenv("FORCE_QWENVL_VIDEO_READER", "").strip().lower()
    if reader != "decord":
        return

    import decord

    resolved = video_path.resolve()
    try:
        vr = decord.VideoReader(str(resolved))
        frame_count = int(len(vr))
        raw_fps = float(vr.get_avg_fps())
    except Exception as exc:
        raise RuntimeError(f"decord could not open Reference Clip: {_safe_error(exc)}") from exc
    if frame_count < 2:
        raise RuntimeError(f"decord Reference Clip has too few frames: {frame_count}")
    if not math.isfinite(raw_fps) or raw_fps <= 0:
        raise RuntimeError(f"decord Reference Clip FPS is invalid: {raw_fps}")


def _analyze_shot_compat(
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

    _validate_forced_video_reader(video_path)
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "video",
                "video": _video_reference(video_path),
                "fps": fps,
                "max_pixels": max_pixels,
            },
            {"type": "text", "text": base._prompt(source_language)},
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
    semantic = base._first_json_object(output_text)
    prompt_profile.validate_semantic_language(semantic)
    return semantic


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen3-VL anonymous Breakdown semantics with diagnostics")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    parser.add_argument("--max-pixels", type=int, default=524288)
    args = parser.parse_args()

    manifest = base._load_manifest(Path(args.manifest))
    source_language = str(manifest.get("source_language") or "und")
    device = base._resolve_device(args.device)
    model, processor = base._load_model(Path(args.model_path), device)

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
            semantic = _analyze_shot_compat(
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
