"""Instrumented Fast Grounded VLM provider.

This is a production-compatible layer on top of ``breakdown_p2_vlm_fast_grounded_v1``. Exact-Shot
semantic behavior stays unchanged. Window Context is executed by the timed runner with the
segment-based v3 contract after real acceptance proved both the prose-heavy v1 prompt and compact
per-Shot v2 shape could still hit the 1600-token limit.

The provider persists structured performance provenance and the active Window prompt profile.
No Character/Scene/Prop Final assets are touched by this module.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_fast_grounded_v1 as fast
from engine.app import breakdown_p2_vlm_v1 as legacy

PERFORMANCE_PROFILE = "breakdown-p2-vlm-performance-timing-v1"
WINDOW_PROMPT_PROFILE = "breakdown-p2-vlm-window-context-segment-zh-v3"


def _round_elapsed(started: float) -> float:
    return round(max(0.0, time.perf_counter() - started), 6)


class Qwen3VLSemanticProvider(fast.Qwen3VLSemanticProvider):
    """Fast Grounded provider with timing provenance and segment-v3 Window Context routing."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        if kwargs.get("runner_script") is None:
            kwargs["runner_script"] = str(
                repo_root / "scripts" / "run_breakdown_vlm_fast_grounded_qwen3_timed_v2.py"
            )
        self._last_host_timing: dict[str, Any] = {}
        self._last_runtime_timing: dict[str, Any] = {}
        self._last_runner_wall_seconds: float | None = None
        super().__init__(*args, **kwargs)

        original_runner = self._unified_inference_runner

        def capture_timing(
            config: legacy.VLMRuntimeConfig,
            video_path: Path,
            windows: Sequence[e2.EpisodeVLMWindow],
        ) -> Sequence[Mapping[str, Any]]:
            self._last_runtime_timing = {}
            self._last_runner_wall_seconds = None
            started = time.perf_counter()
            try:
                rows = tuple(original_runner(config, video_path, windows))
            finally:
                self._last_runner_wall_seconds = _round_elapsed(started)
            for row in rows:
                kind = str(row.get("kind") or "").strip().lower()
                timing = row.get("timing")
                if kind == "runtime_timing" and isinstance(timing, Mapping):
                    self._last_runtime_timing = dict(timing)
                elif kind == "host_preparation_timing" and isinstance(timing, Mapping):
                    self._last_host_timing = dict(timing)
            return rows

        self._unified_inference_runner = capture_timing

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        self._last_host_timing = {}
        self._last_runtime_timing = {}
        self._last_runner_wall_seconds = None
        return super().analyze(context)

    def _run_unified_subprocess(
        self,
        config: legacy.VLMRuntimeConfig,
        video_path: Path,
        windows: Sequence[e2.EpisodeVLMWindow],
    ) -> Sequence[Mapping[str, Any]]:
        unified_started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="ai-drama-p2-fast-grounded-") as temp_name:
            root = Path(temp_name)
            window_dir = root / "windows"
            frame_dir = root / "frames"
            window_dir.mkdir(parents=True, exist_ok=True)
            frame_dir.mkdir(parents=True, exist_ok=True)

            window_payloads: list[dict[str, Any]] = []
            window_materialization: list[dict[str, Any]] = []
            window_stage_started = time.perf_counter()
            for window in windows:
                started = time.perf_counter()
                clip = window_dir / f"{window.window_id}.mp4"
                self._materialize_window(video_path, window, clip)
                window_payloads.append(self._window_manifest(window, clip))
                window_materialization.append({
                    "window_id": window.window_id,
                    "shot_count": len(window.shots),
                    "duration_seconds": round(window.duration_us / 1_000_000.0, 6),
                    "elapsed_seconds": _round_elapsed(started),
                })
            window_materialization_total = _round_elapsed(window_stage_started)

            grounding_payloads: list[dict[str, Any]] = []
            shot_frame_materialization: list[dict[str, Any]] = []
            frame_stage_started = time.perf_counter()
            total_frame_count = 0
            for shot in self._unique_shots(windows):
                started = time.perf_counter()
                frames = self._materialize_grounding_frames(shot, frame_dir)
                total_frame_count += len(frames)
                grounding_payloads.append({
                    "revision_item_id": shot.revision_item_id,
                    "ordinal": shot.ordinal,
                    "source_start_us": shot.start_us,
                    "source_end_us": shot.end_us,
                    "frames": frames,
                })
                shot_frame_materialization.append({
                    "shot_ordinal": shot.ordinal,
                    "frame_count": len(frames),
                    "elapsed_seconds": _round_elapsed(started),
                })
            frame_materialization_total = _round_elapsed(frame_stage_started)

            manifest_path = root / "manifest.json"
            output_path = root / "output.jsonl"
            manifest_started = time.perf_counter()
            manifest_path.write_text(json.dumps({
                "schema_version": fast.FAST_GROUNDED_SCHEMA,
                "profile": fast.FAST_GROUNDED_PROFILE,
                "window_prompt_profile": WINDOW_PROMPT_PROFILE,
                "model": config.model_name,
                "source_language": config.source_language,
                "windows": window_payloads,
                "grounding_shots": grounding_payloads,
            }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            manifest_seconds = _round_elapsed(manifest_started)

            host_before_subprocess_seconds = _round_elapsed(unified_started)
            command = [
                str(config.python_executable), str(config.runner_script),
                "--model-path", str(config.model_path),
                "--manifest", str(manifest_path),
                "--output", str(output_path),
                "--device", config.device,
                "--window-fps", str(config.video_fps),
                "--window-max-pixels", str(config.max_pixels),
                "--window-max-new-tokens", str(config.max_new_tokens),
                "--grounding-max-pixels", str(self.exact_shot_max_pixels),
                "--grounding-max-new-tokens", str(self.grounding_max_new_tokens),
                "--grounding-batch-size", str(self.grounding_batch_size),
            ]
            subprocess_started = time.perf_counter()
            try:
                subprocess.run(
                    command,
                    check=True,
                    cwd=str(config.runner_script.parent),
                    env=self._subprocess_env(config),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=legacy.VLM_TIMEOUT_SECONDS,
                )
            except subprocess.CalledProcessError as exc:
                self._fast_subprocess_failure_detail = self._clean_subprocess_output(
                    exc.stdout or exc.output
                )
                self._last_host_timing = {
                    "profile": PERFORMANCE_PROFILE,
                    "window_prompt_profile": WINDOW_PROMPT_PROFILE,
                    "window_materialization_total_seconds": window_materialization_total,
                    "grounding_frame_materialization_total_seconds": frame_materialization_total,
                    "manifest_write_seconds": manifest_seconds,
                    "host_before_subprocess_seconds": host_before_subprocess_seconds,
                    "subprocess_wall_seconds": _round_elapsed(subprocess_started),
                    "grounding_frame_count": total_frame_count,
                    "window_materialization": window_materialization,
                    "shot_frame_materialization": shot_frame_materialization,
                }
                raise

            subprocess_wall_seconds = _round_elapsed(subprocess_started)
            if not output_path.is_file():
                raise RuntimeError("fast-grounded timed VLM runner produced no output")

            parse_started = time.perf_counter()
            rows: list[Mapping[str, Any]] = []
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, Mapping):
                    rows.append(value)
            output_parse_seconds = _round_elapsed(parse_started)
            unified_total_seconds = _round_elapsed(unified_started)
            host_timing = {
                "profile": PERFORMANCE_PROFILE,
                "window_prompt_profile": WINDOW_PROMPT_PROFILE,
                "window_materialization_total_seconds": window_materialization_total,
                "grounding_frame_materialization_total_seconds": frame_materialization_total,
                "manifest_write_seconds": manifest_seconds,
                "host_before_subprocess_seconds": host_before_subprocess_seconds,
                "subprocess_wall_seconds": subprocess_wall_seconds,
                "output_parse_seconds": output_parse_seconds,
                "unified_runner_total_seconds": unified_total_seconds,
                "grounding_frame_count": total_frame_count,
                "window_materialization": window_materialization,
                "shot_frame_materialization": shot_frame_materialization,
            }
            self._last_host_timing = dict(host_timing)
            rows.append({
                "kind": "host_preparation_timing",
                "status": "READY",
                "timing": host_timing,
            })
            return tuple(rows)

    def _metadata(
        self,
        *,
        config: legacy.VLMRuntimeConfig,
        video_kind: str,
        windows: Sequence[e2.EpisodeVLMWindow],
        window_summaries: Sequence[Mapping[str, Any]],
        shot_count: int,
        grounding_count: int,
        failed_window_count: int,
        failed_grounding_count: int,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        result = super()._metadata(
            config=config,
            video_kind=video_kind,
            windows=windows,
            window_summaries=window_summaries,
            shot_count=shot_count,
            grounding_count=grounding_count,
            failed_window_count=failed_window_count,
            failed_grounding_count=failed_grounding_count,
            error_type=error_type,
        )
        result["window_prompt_profile"] = WINDOW_PROMPT_PROFILE
        result["performance"] = {
            "profile": PERFORMANCE_PROFILE,
            "window_prompt_profile": WINDOW_PROMPT_PROFILE,
            "provider_runner_wall_seconds": self._last_runner_wall_seconds,
            "host": dict(self._last_host_timing),
            "model_runner": dict(self._last_runtime_timing),
        }
        return result


# Re-export stable semantic constants so the production runtime can switch imports without changing
# public compatibility surfaces.
DEFAULT_WINDOW_SECONDS = fast.DEFAULT_WINDOW_SECONDS
DEFAULT_WINDOW_OVERLAP_RATIO = fast.DEFAULT_WINDOW_OVERLAP_RATIO
DEFAULT_WINDOW_CONTEXT_FPS = fast.DEFAULT_WINDOW_CONTEXT_FPS
DEFAULT_WINDOW_MAX_PIXELS = fast.DEFAULT_WINDOW_MAX_PIXELS
DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS = fast.DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS
DEFAULT_EXACT_SHOT_MAX_PIXELS = fast.DEFAULT_EXACT_SHOT_MAX_PIXELS
DEFAULT_GROUNDING_MAX_NEW_TOKENS = fast.DEFAULT_GROUNDING_MAX_NEW_TOKENS
DEFAULT_GROUNDING_BATCH_SIZE = fast.DEFAULT_GROUNDING_BATCH_SIZE
FAST_GROUNDED_SCHEMA = fast.FAST_GROUNDED_SCHEMA
FAST_GROUNDED_PROFILE = fast.FAST_GROUNDED_PROFILE
WINDOW_CONTEXT_PROFILE = fast.WINDOW_CONTEXT_PROFILE
EXACT_SHOT_GROUNDING_PROFILE = fast.EXACT_SHOT_GROUNDING_PROFILE
VISUAL_TRUTH_POLICY = fast.VISUAL_TRUTH_POLICY
GroundingFramePlan = fast.GroundingFramePlan
frame_sample_ratios = fast.frame_sample_ratios


__all__ = [
    "DEFAULT_EXACT_SHOT_MAX_PIXELS",
    "DEFAULT_GROUNDING_BATCH_SIZE",
    "DEFAULT_GROUNDING_MAX_NEW_TOKENS",
    "DEFAULT_WINDOW_CONTEXT_FPS",
    "DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS",
    "DEFAULT_WINDOW_MAX_PIXELS",
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "EXACT_SHOT_GROUNDING_PROFILE",
    "FAST_GROUNDED_PROFILE",
    "FAST_GROUNDED_SCHEMA",
    "GroundingFramePlan",
    "PERFORMANCE_PROFILE",
    "Qwen3VLSemanticProvider",
    "VISUAL_TRUTH_POLICY",
    "WINDOW_CONTEXT_PROFILE",
    "WINDOW_PROMPT_PROFILE",
    "frame_sample_ratios",
]
