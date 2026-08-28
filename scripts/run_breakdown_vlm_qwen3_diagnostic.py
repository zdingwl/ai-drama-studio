"""Diagnostic-preserving Qwen3-VL runner for Breakdown P2.4.

This runner reuses the frozen Qwen3-VL loading/inference implementation from
``run_breakdown_vlm_qwen3.py`` but preserves a short per-Shot exception detail in
its private JSONL transport. The main provider still fail-closes; the detail exists
only so Windows/local acceptance can distinguish decode, CUDA, processor and model
failures instead of collapsing everything to ``Shot N VLM inference failed``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import run_breakdown_vlm_qwen3 as base


def _safe_error(exc: BaseException, *, max_len: int = 900) -> str:
    text = " ".join(str(exc).strip().split())
    if not text:
        text = type(exc).__name__
    return text[:max_len]


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
            semantic = base._analyze_shot(
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
