#!/usr/bin/env python3
"""G2.3 local text-only Qwen3-VL runner.

The runner reuses the already-installed isolated Qwen3-VL-4B-Instruct runtime, but it never opens a
video/image. One process loads the model once, then handles all Scene narrative requests in ordinal
order. This file is independent from the frozen G1 Window/Exact-Shot runners.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import run_breakdown_vlm_fast_grounded_qwen3 as fast
import run_breakdown_vlm_qwen3 as base


RUNNER_SCHEMA_VERSION = "scene-narrative-runner-v1"


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
    if not isinstance(value, dict) or value.get("schema_version") != RUNNER_SCHEMA_VERSION:
        raise ValueError("manifest is not scene-narrative-runner-v1")
    requests = value.get("requests")
    if not isinstance(requests, list):
        raise ValueError("manifest.requests must be a list")
    return value


def _safe_error_type(exc: BaseException) -> str:
    """Output only the exception class; never serialize prompts, paths, tokens or secrets."""

    return type(exc).__name__[:120]


def _generate_candidate(
    *,
    model: Any,
    processor: Any,
    system_prompt: str,
    user_prompt: str,
    max_new_tokens: int,
) -> Mapping[str, Any]:
    messages = [
        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
    ]
    return fast._generate_json(
        model=model,
        processor=processor,
        messages=messages,
        max_new_tokens=max_new_tokens,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run G2 Scene narrative with one local Qwen3-VL load")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    args = parser.parse_args()

    if args.max_new_tokens < 64 or args.max_new_tokens > 2048:
        raise ValueError("max-new-tokens must be between 64 and 2048")

    manifest = _load_manifest(Path(args.manifest))
    requests = [item for item in manifest["requests"] if isinstance(item, Mapping)]
    device = base._resolve_device(args.device)
    model, processor = base._load_model(Path(args.model_path), device)

    records: list[dict[str, Any]] = []
    for item in sorted(requests, key=lambda row: int(row.get("scene_ordinal") or 0)):
        try:
            scene_ordinal = int(item.get("scene_ordinal") or 0)
        except (TypeError, ValueError):
            scene_ordinal = 0
        if scene_ordinal < 1:
            continue
        system_prompt = str(item.get("system_prompt") or "")
        user_prompt = str(item.get("user_prompt") or "")
        if not system_prompt.strip() or not user_prompt.strip():
            records.append({
                "scene_ordinal": scene_ordinal,
                "status": "FAILED",
                "error_type": "InvalidPrompt",
            })
            continue
        try:
            candidate = _generate_candidate(
                model=model,
                processor=processor,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=int(args.max_new_tokens),
            )
            records.append({
                "scene_ordinal": scene_ordinal,
                "status": "READY",
                "candidate": dict(candidate),
            })
        except Exception as exc:
            records.append({
                "scene_ordinal": scene_ordinal,
                "status": "FAILED",
                "error_type": _safe_error_type(exc),
            })
        finally:
            fast._cleanup_cuda()

    serialized = "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in records)
    if serialized:
        serialized += "\n"
    _atomic_write_text(Path(args.output), serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
