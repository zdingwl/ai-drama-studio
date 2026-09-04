#!/usr/bin/env python3
"""Single-load Qwen3-VL runner for LocalSubject multi-person closed-set adjudication.

The main app prepares only V10.1 Person crops. This isolated runner loads the existing local
Qwen3-VL-4B-Instruct checkpoint once, processes all ambiguous LocalSubjects sequentially, and emits
only normalized JSON candidates. It never writes Character/Binding facts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import run_breakdown_vlm_fast_grounded_qwen3 as fast
import run_breakdown_vlm_qwen3 as base

SCHEMA_VERSION = "source-person-qwen3-vl-adjudication-v1"


def _atomic_write(path: Path, text: str) -> None:
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
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("manifest is not source-person-qwen3-vl-adjudication-v1")
    if not isinstance(value.get("requests"), list):
        raise ValueError("manifest.requests must be a list")
    return value


def _image_uri(path: str) -> str:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError("candidate crop is missing")
    return resolved.as_uri()


def _messages(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    system_prompt = str(request.get("system_prompt") or "").strip()
    user_prompt = str(request.get("user_prompt") or "").strip()
    if not system_prompt or not user_prompt:
        raise ValueError("person adjudication prompt is empty")
    content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    candidates = request.get("candidates")
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 6:
        raise ValueError("person adjudication candidates must contain 2..6 items")
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate is invalid")
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError("candidate_id is missing or duplicated")
        seen.add(candidate_id)
        crop_paths = candidate.get("crop_paths")
        if not isinstance(crop_paths, list) or not crop_paths:
            raise ValueError("candidate crop list is empty")
        content.append({"type": "text", "text": f"candidate_id={candidate_id}; visual crops follow:"})
        for crop_path in crop_paths[:2]:
            content.append({"type": "image", "image": _image_uri(str(crop_path))})
    return [
        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
        {"role": "user", "content": content},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen3-VL source-person closed-set adjudication")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()
    if not 64 <= args.max_new_tokens <= 1024:
        raise ValueError("max-new-tokens must be between 64 and 1024")

    manifest = _load_manifest(Path(args.manifest))
    device = base._resolve_device(args.device)
    model, processor = base._load_model(Path(args.model_path), device)
    records: list[dict[str, Any]] = []
    for request in manifest["requests"]:
        if not isinstance(request, Mapping):
            continue
        key = str(request.get("key") or "").strip()
        if not key:
            continue
        try:
            decision = fast._generate_json(
                model=model,
                processor=processor,
                messages=_messages(request),
                max_new_tokens=int(args.max_new_tokens),
            )
            records.append({"key": key, "status": "READY", "decision": dict(decision)})
        except Exception as exc:
            records.append({"key": key, "status": "FAILED", "error_type": type(exc).__name__[:120]})
        finally:
            fast._cleanup_cuda()

    text = "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in records)
    if text:
        text += "\n"
    _atomic_write(Path(args.output), text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
