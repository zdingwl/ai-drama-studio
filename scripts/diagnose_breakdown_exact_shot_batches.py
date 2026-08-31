#!/usr/bin/env python3
"""Read-only selected Exact-Shot batch diagnostic for a completed Breakdown Run.

This command reuses the completed Run's frozen ShotRevision and media, runs the accepted production
Window Context once, then runs only selected top-level Exact-Shot batches through the configured
timed Qwen3-VL runner. It writes no DB rows, no sidecars, no Draft/Final assets.

Use it to measure real generation token counts, adaptive retry/split behavior, frame counts, elapsed
time, and a compact quality summary before changing Exact-Shot prompt shape, resolution or batch
size.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime
from engine.app import breakdown_p2_vlm_v1 as legacy


def _seconds(value: Any) -> str:
    try:
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return "-"


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


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


def _parse_batch_numbers(value: str) -> tuple[int, ...]:
    result: list[int] = []
    for raw in str(value or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            number = int(raw)
        except ValueError as exc:
            raise ValueError(f"invalid batch number: {raw}") from exc
        if number <= 0:
            raise ValueError("batch numbers must be >= 1")
        if number not in result:
            result.append(number)
    if not result:
        raise ValueError("at least one batch number is required")
    return tuple(result)


def _top_level_batches(shots: Sequence[Any], batch_size: int) -> tuple[tuple[Any, ...], ...]:
    size = max(1, int(batch_size))
    return tuple(tuple(shots[start:start + size]) for start in range(0, len(shots), size))


def _selected_batches(
    shots: Sequence[Any],
    *,
    batch_size: int,
    requested: Sequence[int],
) -> tuple[tuple[int, tuple[Any, ...]], ...]:
    batches = _top_level_batches(shots, batch_size)
    result: list[tuple[int, tuple[Any, ...]]] = []
    for number in requested:
        if number < 1 or number > len(batches):
            raise ValueError(f"batch {number} outside valid range 1..{len(batches)}")
        result.append((number, batches[number - 1]))
    return tuple(result)


def _selected_shot_quality(
    rows: Sequence[Mapping[str, Any]],
    ordinal_by_id: Mapping[str, int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("kind") or "").strip().lower() != "shot_grounding":
            continue
        item_id = str(row.get("revision_item_id") or "").strip()
        if item_id not in ordinal_by_id:
            continue
        semantic = row.get("semantic") if isinstance(row.get("semantic"), Mapping) else {}
        shot = semantic.get("shot") if isinstance(semantic.get("shot"), Mapping) else {}
        subjects = semantic.get("subjects") if isinstance(semantic.get("subjects"), list) else []
        props = semantic.get("props") if isinstance(semantic.get("props"), list) else []
        subject_rows: list[dict[str, Any]] = []
        for subject in subjects:
            if not isinstance(subject, Mapping):
                continue
            subject_rows.append({
                "label": _clean(subject.get("label"), 48),
                "appearance_summary": _clean(subject.get("appearance_summary"), 160),
                "activity_summary": _clean(subject.get("activity_summary"), 160),
            })
        prop_labels = [
            _clean(prop.get("label"), 120)
            for prop in props
            if isinstance(prop, Mapping) and _clean(prop.get("label"), 120)
        ]
        result.append({
            "revision_item_id": item_id,
            "shot_ordinal": ordinal_by_id[item_id],
            "status": row.get("status"),
            "summary": _clean(shot.get("summary"), 320),
            "visual_description": _clean(shot.get("visual_description"), 500),
            "shot_type_hint": _clean(shot.get("shot_type_hint"), 80),
            "subject_count": len(subject_rows),
            "subjects": subject_rows,
            "props": prop_labels,
        })
    return sorted(result, key=lambda item: int(item["shot_ordinal"]))


def diagnose(run_id: str, batch_numbers: Sequence[int]) -> dict[str, Any]:
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

    all_shots = provider._unique_shots(windows)
    selected = _selected_batches(
        all_shots,
        batch_size=provider.grounding_batch_size,
        requested=batch_numbers,
    )

    with tempfile.TemporaryDirectory(prefix="ai-drama-exact-shot-diagnostic-") as temp_name:
        root = Path(temp_name)
        window_dir = root / "windows"
        frame_dir = root / "frames"
        window_dir.mkdir(parents=True, exist_ok=True)
        frame_dir.mkdir(parents=True, exist_ok=True)

        window_payloads: list[dict[str, Any]] = []
        host_window_started = time.perf_counter()
        for window in windows:
            clip = window_dir / f"{window.window_id}.mp4"
            provider._materialize_window(video_path, window, clip)
            window_payloads.append(provider._window_manifest(window, clip))
        host_window_seconds = max(0.0, time.perf_counter() - host_window_started)

        grounding_payloads: list[dict[str, Any]] = []
        selected_meta: list[dict[str, Any]] = []
        host_frame_started = time.perf_counter()
        for original_batch_number, batch in selected:
            ordinals: list[int] = []
            frame_count = 0
            for shot in batch:
                frames = provider._materialize_grounding_frames(shot, frame_dir)
                ordinals.append(int(shot.ordinal))
                frame_count += len(frames)
                grounding_payloads.append({
                    "revision_item_id": shot.revision_item_id,
                    "ordinal": shot.ordinal,
                    "source_start_us": shot.start_us,
                    "source_end_us": shot.end_us,
                    "frames": frames,
                })
            selected_meta.append({
                "original_batch_number": original_batch_number,
                "shot_ordinals": ordinals,
                "shot_count": len(batch),
                "frame_count": frame_count,
            })
        host_frame_seconds = max(0.0, time.perf_counter() - host_frame_started)
        ordinal_by_id = {
            str(item.get("revision_item_id") or "").strip(): int(item.get("ordinal") or 0)
            for item in grounding_payloads
            if str(item.get("revision_item_id") or "").strip()
        }

        manifest_path = root / "manifest.json"
        output_path = root / "output.jsonl"
        manifest_path.write_text(json.dumps({
            "schema_version": runtime.VLM_WINDOW_SCHEMA,
            "profile": runtime.VLM_FAST_GROUNDED_PROFILE,
            "window_prompt_profile": getattr(runtime, "VLM_WINDOW_PROMPT_PROFILE", None),
            "model": config.model_name,
            "source_language": config.source_language,
            "windows": window_payloads,
            "grounding_shots": grounding_payloads,
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
                "Exact-Shot diagnostic timed runner failed" + (f": {detail}" if detail else "")
            )
        if not output_path.is_file():
            raise RuntimeError("Exact-Shot diagnostic runner produced no output")
        rows = _load_jsonl(output_path)

    runtime_row = next(
        (item for item in rows if str(item.get("kind") or "").lower() == "runtime_timing"),
        None,
    )
    timing = runtime_row.get("timing") if isinstance(runtime_row, Mapping) else {}
    timing = dict(timing) if isinstance(timing, Mapping) else {}
    grounding_timings = timing.get("grounding_batch_timings")
    grounding_timings = grounding_timings if isinstance(grounding_timings, list) else []

    mapped_batches: list[dict[str, Any]] = []
    for index, meta in enumerate(selected_meta):
        row = grounding_timings[index] if index < len(grounding_timings) else {}
        row = dict(row) if isinstance(row, Mapping) else {}
        row["original_batch_number"] = meta["original_batch_number"]
        row["selected_shot_ordinals"] = list(meta["shot_ordinals"])
        row["selected_frame_count"] = meta["frame_count"]
        mapped_batches.append(row)

    return {
        "run_id": run_id,
        "video_kind": video_kind,
        "window_prompt_profile": timing.get("window_prompt_profile"),
        "providers_executed": ["VLM_WINDOW_CONTEXT_DIAGNOSTIC", "VLM_EXACT_SHOT_SELECTED_BATCHES"],
        "mutates_breakdown_run": False,
        "mutates_final_assets": False,
        "host_window_materialization_seconds": round(host_window_seconds, 6),
        "host_selected_frame_materialization_seconds": round(host_frame_seconds, 6),
        "model_load_seconds": timing.get("model_load_seconds"),
        "window_context_total_seconds": timing.get("window_context_total_seconds"),
        "exact_shot_total_seconds": timing.get("exact_shot_total_seconds"),
        "selected_batches": mapped_batches,
        "selected_shots": _selected_shot_quality(rows, ordinal_by_id),
    }


def _summary(payload: Mapping[str, Any]) -> str:
    lines = [
        "=== Exact-Shot 选定 Batch 只读诊断 ===",
        f"Run: {payload.get('run_id')}",
        f"Window profile: {payload.get('window_prompt_profile')}",
        "Mode: completed frozen Run / selected Exact-Shot batches / no DB writes",
        f"Host Window materialization: {_seconds(payload.get('host_window_materialization_seconds'))}",
        f"Host selected frame extraction: {_seconds(payload.get('host_selected_frame_materialization_seconds'))}",
        f"Model load: {_seconds(payload.get('model_load_seconds'))}",
        f"Window Context total: {_seconds(payload.get('window_context_total_seconds'))}",
        f"Selected Exact-Shot total: {_seconds(payload.get('exact_shot_total_seconds'))}",
    ]
    batches = payload.get("selected_batches")
    if isinstance(batches, list):
        for row in batches:
            if not isinstance(row, Mapping):
                continue
            out_tokens = row.get("output_token_count_total")
            max_tokens = row.get("max_new_tokens")
            maxed = int(row.get("maxed_out_attempt_count") or 0) > 0
            attempts = int(row.get("generation_attempt_count") or 0)
            ordinals = row.get("selected_shot_ordinals") or []
            token_text = f"tokens={out_tokens}/{max_tokens}" if out_tokens is not None else "tokens=-"
            if maxed:
                token_text += " MAXED"
            if attempts > 1:
                token_text += f" attempts={attempts}"
            lines.append(
                "batch {batch}: shots={shots} | frames={frames} | {elapsed} | {status} | {tokens}".format(
                    batch=row.get("original_batch_number"),
                    shots=",".join(str(item) for item in ordinals),
                    frames=row.get("selected_frame_count"),
                    elapsed=_seconds(row.get("elapsed_seconds")),
                    status=row.get("status"),
                    tokens=token_text,
                )
            )
            error_type = str(row.get("error_type") or "").strip()
            error_detail = " ".join(str(row.get("error_detail") or "").split())
            if error_type or error_detail:
                detail = error_type or "ERROR"
                if error_detail:
                    detail += f": {error_detail[:500]}"
                lines.append(f"  -> {detail}")

    shots = payload.get("selected_shots")
    if isinstance(shots, list) and shots:
        lines.append("")
        lines.append("[Selected Shot quality]")
        for row in shots:
            if not isinstance(row, Mapping):
                continue
            subject_text = "; ".join(
                f"{item.get('label')}={item.get('appearance_summary')} / {item.get('activity_summary')}"
                for item in (row.get("subjects") or [])
                if isinstance(item, Mapping)
            ) or "-"
            prop_text = ", ".join(str(item) for item in (row.get("props") or [])) or "-"
            lines.append(
                f"Shot {row.get('shot_ordinal')}: subjects={row.get('subject_count')} | props={prop_text} | "
                f"summary={row.get('summary')}"
            )
            if subject_text != "-":
                lines.append(f"  people: {subject_text}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run selected Exact-Shot top-level batches against a completed frozen Breakdown Run"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--batches",
        default="1,4,6",
        help="Comma-separated original top-level batch numbers; default: 1,4,6",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = diagnose(args.run_id, _parse_batch_numbers(args.batches))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
