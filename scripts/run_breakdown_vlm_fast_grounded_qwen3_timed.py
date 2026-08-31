#!/usr/bin/env python3
"""Timed single-load Qwen3-VL runner for Fast Grounded Breakdown.

This runner keeps the existing Exact-Shot grounding semantics and adds structured timing/generation
diagnostics. Window Context now uses the compact v2 prompt proven necessary by the real 1600-token
truncation diagnostic. Exact-Shot visible truth remains unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Mapping

import run_breakdown_vlm_fast_grounded_qwen3 as fast
import run_breakdown_vlm_qwen3 as base
import run_breakdown_vlm_window_compact_v2 as compact

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


def _generation_rollup(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    output_tokens = 0
    input_tokens = 0
    maxed = 0
    for event in events:
        try:
            output_tokens += int(event.get("output_token_count") or 0)
        except (TypeError, ValueError):
            pass
        try:
            input_tokens += int(event.get("input_token_count") or 0)
        except (TypeError, ValueError):
            pass
        if bool(event.get("hit_max_new_tokens")):
            maxed += 1
    return {
        "generation_attempt_count": len(events),
        "input_token_count_total": input_tokens,
        "output_token_count_total": output_tokens,
        "maxed_out_attempt_count": maxed,
        "generation_events": [dict(item) for item in events],
    }


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

    generation_events: list[dict[str, Any]] = []
    generation_context: dict[str, Any] = {"stage": "unknown"}

    def instrumented_generate_json(
        *,
        model: Any,
        processor: Any,
        messages: Any,
        max_new_tokens: int,
    ) -> Mapping[str, Any]:
        started = time.perf_counter()
        input_token_count = 0
        output_token_count = 0
        event: dict[str, Any] = {
            **generation_context,
            "max_new_tokens": int(max_new_tokens),
            "status": "FAILED",
        }
        try:
            inputs = fast._prepare_inputs(model, processor, messages)
            try:
                input_token_count = int(inputs.input_ids.shape[-1])
            except Exception:
                input_token_count = 0
            _sync_cuda()
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=int(max_new_tokens),
                do_sample=False,
            )
            _sync_cuda()
            trimmed = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_token_count = sum(int(item.shape[-1]) for item in trimmed)
            output_text = processor.batch_decode(
                trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
            value = base._first_json_object(output_text)
            event["status"] = "READY"
            return value
        except Exception as exc:
            event["error_type"] = type(exc).__name__
            event["error_detail"] = fast._safe_error(exc)
            raise
        finally:
            event.update({
                "input_token_count": input_token_count,
                "output_token_count": output_token_count,
                "hit_max_new_tokens": bool(
                    int(max_new_tokens) > 0 and output_token_count >= int(max_new_tokens)
                ),
                "elapsed_seconds": _elapsed(started),
            })
            generation_events.append(event)

    original_generate_json = fast._generate_json
    fast._generate_json = instrumented_generate_json
    try:
        records: list[dict[str, Any]] = []
        window_results: dict[str, Mapping[str, Any]] = {}
        window_timings: list[dict[str, Any]] = []
        window_stage_started = time.perf_counter()
        for window in windows:
            window_id = str(window.get("window_id") or "").strip()
            if not window_id:
                continue
            generation_context.clear()
            generation_context.update({
                "stage": "window_context",
                "window_id": window_id,
                "prompt_profile": compact.WINDOW_CONTEXT_PROMPT_PROFILE,
            })
            generation_start = len(generation_events)
            _sync_cuda()
            started = time.perf_counter()
            status = "READY"
            error_type: str | None = None
            error_detail: str | None = None
            try:
                semantic = compact.analyze_window(
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
                error_type = type(exc).__name__
                error_detail = fast._safe_error(exc)
                records.append({
                    "kind": "window_context",
                    "window_id": window_id,
                    "status": "FAILED",
                    "error_type": error_type,
                    "error_detail": error_detail,
                })
            stage_events = generation_events[generation_start:]
            window_timings.append({
                "window_id": window_id,
                "shot_count": len(fast._window_shots(window)),
                "elapsed_seconds": _elapsed(started),
                "status": status,
                "error_type": error_type,
                "error_detail": error_detail,
                "prompt_profile": compact.WINDOW_CONTEXT_PROMPT_PROFILE,
                "max_new_tokens": int(args.window_max_new_tokens),
                **_generation_rollup(stage_events),
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
            ordinals = [fast._safe_int(shot.get("ordinal")) for shot in batch]
            generation_context.clear()
            generation_context.update({
                "stage": "exact_shot",
                "batch_ordinal": batch_ordinal,
                "first_shot_ordinal": min(ordinals) if ordinals else None,
                "last_shot_ordinal": max(ordinals) if ordinals else None,
            })
            generation_start = len(generation_events)
            _sync_cuda()
            started = time.perf_counter()
            status = "READY"
            error_type = None
            error_detail = None
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
                error_type = type(exc).__name__
                error_detail = fast._safe_error(exc)
                for shot in batch:
                    records.append({
                        "kind": "shot_grounding",
                        "revision_item_id": str(shot.get("revision_item_id") or "").strip(),
                        "status": "FAILED",
                        "error_type": error_type,
                        "error_detail": error_detail,
                    })
            stage_events = generation_events[generation_start:]
            grounding_timings.append({
                "batch_ordinal": batch_ordinal,
                "shot_count": len(batch),
                "frame_count": _frame_count(batch),
                "first_shot_ordinal": min(ordinals) if ordinals else None,
                "last_shot_ordinal": max(ordinals) if ordinals else None,
                "elapsed_seconds": _elapsed(started),
                "status": status,
                "error_type": error_type,
                "error_detail": error_detail,
                "max_new_tokens": int(args.grounding_max_new_tokens),
                **_generation_rollup(stage_events),
            })
            fast._cleanup_cuda()
        grounding_total_seconds = _elapsed(grounding_stage_started)

        total_frame_count = sum(int(row["frame_count"]) for row in grounding_timings)
        timing = {
            "profile": TIMING_PROFILE,
            "window_prompt_profile": compact.WINDOW_CONTEXT_PROMPT_PROFILE,
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
            "generation_attempt_count": len(generation_events),
            "generation_output_tokens_total": sum(
                int(item.get("output_token_count") or 0) for item in generation_events
            ),
            "generation_maxed_out_attempt_count": sum(
                1 for item in generation_events if bool(item.get("hit_max_new_tokens"))
            ),
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
    finally:
        fast._generate_json = original_generate_json


if __name__ == "__main__":
    raise SystemExit(main())
