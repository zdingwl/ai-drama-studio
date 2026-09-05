"""Production Fast Grounded VLM provider after Window-v4 + Exact-Shot compact-v3 acceptance.

This version keeps the v2 timing/host-preparation implementation intact and changes only the
production runner entry plus provenance metadata. The active visual contracts are:

- Window Context: local-index Segment Contract v4;
- Exact-Shot: reconstruction-safe compact Contract v3.

Exact-Shot frame selection, image resolution, generation cap and top-level batch size remain owned
by the stable Fast Grounded base provider. Character V10.1 and P2-E6 Fusion are untouched.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence, Mapping

from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v2 as v2
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_v1 as legacy

PERFORMANCE_PROFILE = v2.PERFORMANCE_PROFILE
WINDOW_PROMPT_PROFILE = v2.WINDOW_PROMPT_PROFILE
EXACT_SHOT_PROMPT_PROFILE = "breakdown-p2-vlm-exact-shot-detector-recheck-zh-v5"


class Qwen3VLSemanticProvider(v2.Qwen3VLSemanticProvider):
    """Stable production provider using accepted Window v4 + Exact-Shot compact v3."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        if kwargs.get("runner_script") is None:
            kwargs["runner_script"] = str(
                repo_root / "scripts" / "run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py"
            )
        super().__init__(*args, **kwargs)

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
        result["exact_shot_prompt_profile"] = EXACT_SHOT_PROMPT_PROFILE
        performance = result.get("performance")
        if isinstance(performance, dict):
            performance["exact_shot_prompt_profile"] = EXACT_SHOT_PROMPT_PROFILE
        return result


# Re-export the stable public surface.
DEFAULT_WINDOW_SECONDS = v2.DEFAULT_WINDOW_SECONDS
DEFAULT_WINDOW_OVERLAP_RATIO = v2.DEFAULT_WINDOW_OVERLAP_RATIO
DEFAULT_WINDOW_CONTEXT_FPS = v2.DEFAULT_WINDOW_CONTEXT_FPS
DEFAULT_WINDOW_MAX_PIXELS = v2.DEFAULT_WINDOW_MAX_PIXELS
DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS = v2.DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS
DEFAULT_EXACT_SHOT_MAX_PIXELS = v2.DEFAULT_EXACT_SHOT_MAX_PIXELS
DEFAULT_GROUNDING_MAX_NEW_TOKENS = v2.DEFAULT_GROUNDING_MAX_NEW_TOKENS
DEFAULT_GROUNDING_BATCH_SIZE = v2.DEFAULT_GROUNDING_BATCH_SIZE
FAST_GROUNDED_SCHEMA = v2.FAST_GROUNDED_SCHEMA
FAST_GROUNDED_PROFILE = v2.FAST_GROUNDED_PROFILE
WINDOW_CONTEXT_PROFILE = v2.WINDOW_CONTEXT_PROFILE
EXACT_SHOT_GROUNDING_PROFILE = v2.EXACT_SHOT_GROUNDING_PROFILE
VISUAL_TRUTH_POLICY = v2.VISUAL_TRUTH_POLICY
GroundingFramePlan = v2.GroundingFramePlan
frame_sample_ratios = v2.frame_sample_ratios


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
    "EXACT_SHOT_PROMPT_PROFILE",
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
