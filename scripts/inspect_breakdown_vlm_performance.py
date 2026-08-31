#!/usr/bin/env python3
"""Print persisted Fast Grounded VLM performance timing for one completed Breakdown Run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed
from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _seconds(value: Any) -> str:
    try:
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return "-"


def _tokens(item: Mapping[str, Any]) -> str:
    output = item.get("output_token_count_total")
    maximum = item.get("max_new_tokens")
    if output is None:
        return ""
    suffix = ""
    try:
        if int(item.get("maxed_out_attempt_count") or 0) > 0:
            suffix = " MAXED"
    except (TypeError, ValueError):
        pass
    return f" | tokens={output}/{maximum or '-'}{suffix}"


def _error(item: Mapping[str, Any]) -> str:
    error_type = str(item.get("error_type") or "").strip()
    detail = " ".join(str(item.get("error_detail") or "").split())
    if not error_type and not detail:
        events = item.get("generation_events")
        if isinstance(events, list):
            for raw in reversed(events):
                if not isinstance(raw, Mapping):
                    continue
                error_type = str(raw.get("error_type") or "").strip()
                detail = " ".join(str(raw.get("error_detail") or "").split())
                if error_type or detail:
                    break
    if not error_type and not detail:
        return ""
    text = error_type or "ERROR"
    if detail:
        text += f": {detail[:260]}"
    return "\n    -> " + text


def _performance(run_id: str) -> dict[str, Any]:
    bundle = completed.load_completed_fusion_inputs(run_id)
    vlm = bundle.components["VLM"].result
    metadata = vlm.metadata if isinstance(vlm.metadata, Mapping) else {}
    performance = metadata.get("performance")
    perf = dict(performance) if isinstance(performance, Mapping) else {}

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        provider_meta = _json_object(run.provider_metadata_json)
        pipeline = provider_meta.get("p2_pipeline")
        pipeline = dict(pipeline) if isinstance(pipeline, Mapping) else {}
        timings = pipeline.get("timings_seconds")
        timings = dict(timings) if isinstance(timings, Mapping) else {}
        whole_run_seconds = None
        if run.completed_at is not None and run.started_at is not None:
            whole_run_seconds = max(0.0, (run.completed_at - run.started_at).total_seconds())

    return {
        "run_id": run_id,
        "whole_run_seconds": whole_run_seconds,
        "pipeline_provider_seconds": timings,
        "performance": perf,
    }


def _summary(payload: Mapping[str, Any]) -> str:
    perf = payload.get("performance")
    perf = perf if isinstance(perf, Mapping) else {}
    host = perf.get("host")
    host = host if isinstance(host, Mapping) else {}
    model = perf.get("model_runner")
    model = model if isinstance(model, Mapping) else {}
    pipeline = payload.get("pipeline_provider_seconds")
    pipeline = pipeline if isinstance(pipeline, Mapping) else {}

    lines = [
        "=== Fast Grounded VLM 性能摘要 ===",
        f"Run: {payload.get('run_id')}",
        f"Whole Run: {_seconds(payload.get('whole_run_seconds'))}",
        "Providers: ASR={asr} | OCR={ocr} | VLM={vlm}".format(
            asr=_seconds(pipeline.get("ASR")),
            ocr=_seconds(pipeline.get("OCR")),
            vlm=_seconds(pipeline.get("VLM")),
        ),
    ]
    if not perf:
        lines.append("performance metadata not found; this Run predates timing instrumentation")
        return "\n".join(lines)

    lines.extend([
        "",
        "[Host preparation]",
        f"Window clip materialization: {_seconds(host.get('window_materialization_total_seconds'))}",
        f"Exact-Shot frame extraction: {_seconds(host.get('grounding_frame_materialization_total_seconds'))}",
        f"Manifest write: {_seconds(host.get('manifest_write_seconds'))}",
        f"Subprocess wall: {_seconds(host.get('subprocess_wall_seconds'))}",
        f"Grounding frames: {host.get('grounding_frame_count', '-')}",
        "",
        "[Qwen runner]",
        f"Model load: {_seconds(model.get('model_load_seconds'))}",
        f"Window Context total: {_seconds(model.get('window_context_total_seconds'))}",
        f"Exact-Shot total: {_seconds(model.get('exact_shot_total_seconds'))}",
        f"Runner total: {_seconds(model.get('runner_total_seconds'))}",
        f"Windows: {model.get('window_count', '-')} | Grounding batches: {model.get('grounding_batch_count', '-')} | Frames: {model.get('grounding_frame_count', '-')}",
    ])
    if model.get("generation_attempt_count") is not None:
        lines.append(
            "Generation: attempts={attempts} | output_tokens={tokens} | maxed={maxed}".format(
                attempts=model.get("generation_attempt_count"),
                tokens=model.get("generation_output_tokens_total"),
                maxed=model.get("generation_maxed_out_attempt_count"),
            )
        )

    windows = model.get("window_timings")
    if isinstance(windows, list) and windows:
        lines.append("\n[Per Window]")
        for item in windows:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                "{id}: shots={shots} | {elapsed} | {status}{tokens}{error}".format(
                    id=item.get("window_id"),
                    shots=item.get("shot_count"),
                    elapsed=_seconds(item.get("elapsed_seconds")),
                    status=item.get("status"),
                    tokens=_tokens(item),
                    error=_error(item),
                )
            )

    batches = model.get("grounding_batch_timings")
    if isinstance(batches, list) and batches:
        lines.append("\n[Per Exact-Shot batch]")
        for item in batches:
            if not isinstance(item, Mapping):
                continue
            attempts = item.get("generation_attempt_count")
            attempt_text = f" | attempts={attempts}" if attempts is not None else ""
            lines.append(
                "batch {batch}: shots={shots} ({first}-{last}) | frames={frames} | {elapsed} | {status}{tokens}{attempts}{error}".format(
                    batch=item.get("batch_ordinal"),
                    shots=item.get("shot_count"),
                    first=item.get("first_shot_ordinal"),
                    last=item.get("last_shot_ordinal"),
                    frames=item.get("frame_count"),
                    elapsed=_seconds(item.get("elapsed_seconds")),
                    status=item.get("status"),
                    tokens=_tokens(item),
                    attempts=attempt_text,
                    error=_error(item),
                )
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect persisted Fast Grounded VLM timing")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = _performance(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
