#!/usr/bin/env python3
"""Read-only Window Context diagnostic for one completed Breakdown Run.

This command reuses the completed Run's frozen ShotRevision and source/proxy media, materializes only
Episode windows, runs only the Window Context stage through the timed Qwen3-VL runner, and prints
failure/token diagnostics. It does NOT run Exact-Shot grounding and does NOT write DB/sidecar/Draft
or Final assets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime
from engine.app import breakdown_p2_vlm_v1 as legacy


def _seconds(value: Any) -> str:
    try:
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return "-"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _window_summary(payload: Mapping[str, Any]) -> str:
    timing = payload.get("timing")
    timing = timing if isinstance(timing, Mapping) else {}
    windows = timing.get("window_timings")
    windows = windows if isinstance(windows, list) else []
    lines = [
        "=== Fast Grounded Window-only 诊断 ===",
        f"Run: {payload.get('run_id')}",
        "Mode: completed frozen Run / Window Context only / no DB writes / no Exact-Shot",
        f"Video: {payload.get('video_kind')}",
        f"Host window materialization: {_seconds(payload.get('host_window_materialization_seconds'))}",
        f"Model load: {_seconds(timing.get('model_load_seconds'))}",
        f"Window Context total: {_seconds(timing.get('window_context_total_seconds'))}",
        f"Runner total: {_seconds(timing.get('runner_total_seconds'))}",
    ]
    for item in windows:
        if not isinstance(item, Mapping):
            continue
        tokens = item.get("output_token_count_total")
        max_tokens = item.get("max_new_tokens")
        maxed = int(item.get("maxed_out_attempt_count") or 0) > 0
        token_text = f"tokens={tokens}/{max_tokens}" if tokens is not None else "tokens=-"
        if maxed:
            token_text += " MAXED"
        lines.append(
            "{id}: shots={shots} | {elapsed} | {status} | {tokens}".format(
                id=item.get("window_id"),
                shots=item.get("shot_count"),
                elapsed=_seconds(item.get("elapsed_seconds")),
                status=item.get("status"),
                tokens=token_text,
            )
        )
        error_type = str(item.get("error_type") or "").strip()
        error_detail = " ".join(str(item.get("error_detail") or "").split())
        if error_type or error_detail:
            detail = error_type or "ERROR"
            if error_detail:
                detail += f": {error_detail[:500]}"
            lines.append(f"  -> {detail}")
    return "\n".join(lines)


def diagnose(run_id: str) -> dict[str, Any]:
    bundle = completed.load_completed_fusion_inputs(run_id)
    provider = runtime.Qwen3VLSemanticProvider()
    config = provider._runtime_config(bundle.context.source_language)
    missing = provider._runtime_missing(config)
    if missing:
        raise RuntimeError("VLM runtime unavailable: " + ", ".join(missing))

    windows = e2._plan_windows(
        bundle.context.shots,
        target_duration_us=int(round(provider.window_duration_seconds * 1_000_000)),
        overlap_ratio=provider.window_overlap_ratio,
    )
    video_path, video_kind = provider._resolve_episode_video(bundle.context)
    if video_path is None:
        raise FileNotFoundError("Episode proxy/source video is not available")

    with tempfile.TemporaryDirectory(prefix="ai-drama-vlm-window-diagnostic-") as temp_name:
        root = Path(temp_name)
        window_dir = root / "windows"
        window_dir.mkdir(parents=True, exist_ok=True)
        window_payloads: list[dict[str, Any]] = []
        host_started = time.perf_counter()
        for window in windows:
            clip = window_dir / f"{window.window_id}.mp4"
            provider._materialize_window(video_path, window, clip)
            window_payloads.append(provider._window_manifest(window, clip))
        host_seconds = max(0.0, time.perf_counter() - host_started)

        manifest_path = root / "manifest.json"
        output_path = root / "output.jsonl"
        manifest_path.write_text(json.dumps({
            "schema_version": runtime.VLM_WINDOW_SCHEMA,
            "profile": runtime.VLM_FAST_GROUNDED_PROFILE,
            "model": config.model_name,
            "source_language": config.source_language,
            "windows": window_payloads,
            "grounding_shots": [],
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        command = [
            str(config.python_executable), str(config.runner_script),
            "--model-path", str(config.model_path),
            "--manifest", str(manifest_path),
            "--output", str(output_path),
            "--device", config.device,
            "--window-fps", str(config.video_fps),
            "--window-max-pixels", str(config.max_pixels),
            "--window-max-new-tokens", str(config.max_new_tokens),
            "--grounding-max-pixels", str(provider.exact_shot_max_pixels),
            "--grounding-max-new-tokens", str(provider.grounding_max_new_tokens),
            "--grounding-batch-size", str(provider.grounding_batch_size),
        ]
        completed_process = subprocess.run(
            command,
            check=False,
            cwd=str(config.runner_script.parent),
            env=provider._subprocess_env(config),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=legacy.VLM_TIMEOUT_SECONDS,
        )
        if completed_process.returncode != 0:
            detail = provider._clean_subprocess_output(completed_process.stdout)
            raise RuntimeError(
                "Window-only timed runner failed"
                + (f": {detail}" if detail else "")
            )
        if not output_path.is_file():
            raise RuntimeError("Window-only timed runner produced no output")
        rows = _load_jsonl(output_path)

    runtime_row = next(
        (item for item in rows if str(item.get("kind") or "").lower() == "runtime_timing"),
        None,
    )
    timing = runtime_row.get("timing") if isinstance(runtime_row, Mapping) else {}
    return {
        "run_id": run_id,
        "video_kind": video_kind,
        "providers_executed": ["VLM_WINDOW_CONTEXT_DIAGNOSTIC"],
        "mutates_breakdown_run": False,
        "mutates_final_assets": False,
        "runs_exact_shot_grounding": False,
        "host_window_materialization_seconds": round(host_seconds, 6),
        "timing": dict(timing) if isinstance(timing, Mapping) else {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Window Context only against a completed frozen Breakdown Run"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = diagnose(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_window_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
