"""Stable production VLM entry for fast grounded Episode Breakdown.

Production no longer runs the old text-only per-Shot E3 pass. The active visual chain is:

Episode-window context (cheap, low FPS)
→ exact frozen Shot frame grounding (1..3 frames, small batches)
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ E4 Episode Fusion.

Both visual passes execute in one isolated Qwen3-VL subprocess/model load. Window context may
help Scene fields only; exact-Shot frames are authoritative for visible people/actions/props and
shot photographic facts. The old E2/E3 modules remain in the repository for historical tests and
comparison, but they are no longer production truth through this stable runtime entry.
"""
from __future__ import annotations

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_fast_grounded_v1 as fast
from engine.app.breakdown_p2_vlm_v1 import VLMRuntimeConfig

DEFAULT_WINDOW_OVERLAP_RATIO = fast.DEFAULT_WINDOW_OVERLAP_RATIO
DEFAULT_WINDOW_SECONDS = fast.DEFAULT_WINDOW_SECONDS
DEFAULT_WINDOW_CONTEXT_FPS = fast.DEFAULT_WINDOW_CONTEXT_FPS
DEFAULT_WINDOW_MAX_PIXELS = fast.DEFAULT_WINDOW_MAX_PIXELS
DEFAULT_EXACT_SHOT_MAX_PIXELS = fast.DEFAULT_EXACT_SHOT_MAX_PIXELS
DEFAULT_GROUNDING_BATCH_SIZE = fast.DEFAULT_GROUNDING_BATCH_SIZE

VLM_DRAFT_TEXT_LANGUAGE = "zh-CN"
VLM_EPISODE_WINDOW_PROFILE = fast.WINDOW_CONTEXT_PROFILE
VLM_PROMPT_PROFILE = "breakdown-p2-vlm-fast-grounded-zh-v1"
VLM_WINDOW_SCHEMA = fast.FAST_GROUNDED_SCHEMA
VLM_FAST_GROUNDED_PROFILE = fast.FAST_GROUNDED_PROFILE
VLM_EXACT_SHOT_GROUNDING_PROFILE = fast.EXACT_SHOT_GROUNDING_PROFILE
VLM_CONTEXTUAL_GROUNDING_POLICY = fast.VISUAL_TRUTH_POLICY

# Compatibility exports for code/tests that still import the old E3 names. They now explicitly
# describe a retired production stage rather than pretending E3 ran.
VLM_CONTEXTUAL_REFINEMENT_PROFILE = "breakdown-p2-contextual-shot-refinement-e3-v1"
VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE = "breakdown-p2-contextual-shot-refinement-zh-v1"
VLM_CONTEXTUAL_FAILURE_POLICY = "retired-from-production-fast-grounded-v1"


class Qwen3VLSemanticProvider(fast.Qwen3VLSemanticProvider):
    """Stable production class name backed by the fast-grounded visual provider."""


def run_qwen3_vl_episode_window_semantics(
    run_id: str,
    *,
    provider: Qwen3VLSemanticProvider | None = None,
):
    """Compatibility entry; persists the current fast-grounded VLM result."""

    return p2.run_local_provider(run_id, provider or Qwen3VLSemanticProvider())


__all__ = [
    "DEFAULT_EXACT_SHOT_MAX_PIXELS",
    "DEFAULT_GROUNDING_BATCH_SIZE",
    "DEFAULT_WINDOW_CONTEXT_FPS",
    "DEFAULT_WINDOW_MAX_PIXELS",
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "Qwen3VLSemanticProvider",
    "VLM_CONTEXTUAL_FAILURE_POLICY",
    "VLM_CONTEXTUAL_GROUNDING_POLICY",
    "VLM_CONTEXTUAL_REFINEMENT_PROFILE",
    "VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE",
    "VLM_DRAFT_TEXT_LANGUAGE",
    "VLM_EPISODE_WINDOW_PROFILE",
    "VLM_EXACT_SHOT_GROUNDING_PROFILE",
    "VLM_FAST_GROUNDED_PROFILE",
    "VLM_PROMPT_PROFILE",
    "VLM_WINDOW_SCHEMA",
    "VLMRuntimeConfig",
    "run_qwen3_vl_episode_window_semantics",
]
