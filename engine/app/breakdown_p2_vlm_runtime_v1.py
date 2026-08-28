"""Production Qwen3-VL runtime compatibility entry.

P2-E2 is now the production visual semantics provider. This module intentionally remains the
stable import path used by the pipeline/CLI while re-exporting the Episode-window provider.
The legacy single-Reference-Clip provider remains available in ``breakdown_p2_vlm_v1`` for
historical contract tests and old immutable BreakdownRuns.
"""
from engine.app.breakdown_p2_vlm_episode_v2 import (
    DEFAULT_WINDOW_OVERLAP_RATIO,
    DEFAULT_WINDOW_SECONDS,
    Qwen3VLSemanticProvider,
    VLM_DRAFT_TEXT_LANGUAGE,
    VLM_EPISODE_WINDOW_PROFILE,
    VLM_PROMPT_PROFILE,
    VLM_WINDOW_SCHEMA,
    run_qwen3_vl_episode_window_semantics,
)
from engine.app.breakdown_p2_vlm_v1 import VLMRuntimeConfig

__all__ = [
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "Qwen3VLSemanticProvider",
    "VLM_DRAFT_TEXT_LANGUAGE",
    "VLM_EPISODE_WINDOW_PROFILE",
    "VLM_PROMPT_PROFILE",
    "VLM_WINDOW_SCHEMA",
    "VLMRuntimeConfig",
    "run_qwen3_vl_episode_window_semantics",
]
