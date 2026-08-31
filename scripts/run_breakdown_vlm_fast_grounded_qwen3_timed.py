#!/usr/bin/env python3
"""Timed single-load Qwen3-VL runner for Fast Grounded Breakdown.

This runner preserves the existing Fast Grounded semantic behavior and only adds structured timing
records. It measures model load, every Window Context inference, every top-level Exact-Shot batch,
and aggregate runner time. CUDA is synchronized around measured inference stages when available so
GPU timings are meaningful. The final timing record contains no media/model filesystem paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Mapping

import run_breakdown_vlm_fast_grounded_qwen3 as fast
import run_breakdown_vlm_qwen3 as base

TIMING_PROFILE = "breakdown-p2-vlm-performance-timing-v1"


def _sync_cuda() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        return


def _elapsed(started: float) -> float:
    return round(max(0.0, time.perf_counter() - started), 6)


def _frame_count(batch: tuple[Mapping[str, Any], ...]) -> int:
    total = 0
    for shot in batch:
        frames = shot.get("frames")
        if isinstance(frames, list):
            total += len(frames)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run timed fast grounded Episode Breakdown with one Qwen3-VL load"
    )
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

    runner_started = time.perf_counter()
    manifest = fast._load_manifest(Path(args.manifest))
    source_language = str(manifest.get("source_language") or "und")
    windows = tuple(item for item in manifest["windows"] if isinstance(item, Mapping))
    grounding_shots = tuple(
        item for item in manifest["grounding_shots"] if isinstance(item, Mapping)
    )

    device = base._resolve_device(args.device)
    _sync_cuda()
    model_started = time.perf_counter()
    model, processor = base._load_model(Path(args.model_path), device)
    _sync_cuda()
    model_load_seconds = _elapsed(model_started)

    records: list[dict[str, Any]] = []
    window_results: dict[str, Mapping[str, Any]] = {}
    window_timings: list[dict[str, Any]] = []
    window_stage_started = time.perf_counter()
    for window in windows:
        window_id = str(window.get("window_id") or "").strip()
        if not window_id:
            continue
        _sync_cuda()
        started = time.perf_counter()
        status = "READY"
        try:
            semantic = fast._analyze_window(
                model=model,
                processor=processor,
                window=window,
                source_language=source_language,
                fps=float(args.window_fps),
                max_pixels=int(args.window_max_pixels),
                max_new_tokens=int(args.window_max_new_tokens),
            )
            _sync_cuda()
            window_results[window_id] = semantic
            records.append({
                "kind": "window_context",
                "window_id": window_id,
                "status": "READY",
                "semantic": semantic,
            })
        except Exception as exc:
            _sync_cuda()
            status = "FAILED"
            records.append({
                "kind": "window_context",
                "window_id": window_id,
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error_detail": fast._safe_error(exc),
            })
        window_timings.append({
            "window_id": window_id,
            "shot_count": len(fast._window_shots(window)),
            "elapsed_seconds": _elapsed(started),
            "status": status,
        })
        fast._cleanup_cuda()
    window_total_seconds = _elapsed(window_stage_started)

    grounding_timings: list[dict[str, Any]] = []
    grounding_stage_started = time.perf_counter()
    batch_size = max(1, min(12, int(args.grounding_batch_size)))
    batch_ordinal = 0
    for start in range(0, len(grounding_shots), batch_size):
        batch = grounding_shots[start:start + batch_size]
        batch_ordinal += 1
        _sync_cuda()
        started = time.perf_counter()
        status = "READY"
        try:
            results = fast._grounding_adaptive(
                model=model,
                processor=processor,
                batch=batch,
                source_language=source_language,
                windows=windows,
                window_results=window_results,
                max_pixels=int(args.grounding_max_pixels),
                max_new_tokens=int(args.grounding_max_new_tokens),
            )
            _sync_cuda()
            for result in results:
                item_id = str(result.get("revision_item_id") or "").strip()
                records.append({
                    "kind": "shot_grounding",
                    "revision_item_id": item_id,
                    "status": "READY",
                    "semantic": result.get("semantic"),
                })
        except Exception as exc:
            _sync_cuda()
            status = "FAILED"
            for shot in batch:
                records.append({
                    "kind": "shot_grounding",
                    "revision_item_id": str(shot.get("revision_item_id") or "").strip(),
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error_detail": fast._safe_error(exc),
                })
        ordinals = [fast._safe_int(shot.get("ordinal")) for shot in batch]
        grounding_timings.append({
            "batch_ordinal": batch_ordinal,
            "shot_count": len(batch),
            "frame_count": _frame_count(batch),
            "first_shot_ordinal": min(ordinals) if ordinals else None,
            "last_shot_ordinal": max(ordinals) if ordinals else None,
            "elapsed_seconds": _elapsed(started),
            "status": status,
        })
        fast._cleanup_cuda()
    grounding_total_seconds = _elapsed(grounding_stage_started)

    total_frame_count = sum(int(row["frame_count"]) for row in grounding_timings)
    timing = {
        "profile": TIMING_PROFILE,
        "timing_clock": "time.perf_counter",
        "gpu_sync_policy": "cuda-synchronize-around-measured-stages",
        "device_resolved": str(device),
        "model_load_seconds": model_load_seconds,
        "window_context_total_seconds": window_total_seconds,
        "window_count": len(window_timings),
        "window_timings": window_timings,
        "exact_shot_total_seconds": grounding_total_seconds,
        "grounding_batch_count": len(grounding_timings),
        "grounding_batch_size_requested": batch_size,
        "grounding_frame_count": total_frame_count,
        "grounding_batch_timings": grounding_timings,
        "runner_total_seconds": _elapsed(runner_started),
    }
    records.append({
        "kind": "runtime_timing",
        "status": "READY",
        "timing": timing,
    })

    output = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    base._atomic_write_text(Path(args.output), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
