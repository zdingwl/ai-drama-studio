"""Stable production Qwen3-VL runtime entry for Episode-context Breakdown.

Production visual understanding is now composite:
P2-E2 overlapping Episode windows -> P2-E3 contextual Shot refinement.
The final frozen VLM sidecar keeps E2 semantics in ``payload.e2_semantic`` and exposes the E3
refined semantic in ``payload.semantic`` for the existing Episode-context Fusion.

The legacy single-Reference-Clip provider remains in ``breakdown_p2_vlm_v1`` for historical
contract tests; the pure E2 provider remains in ``breakdown_p2_vlm_episode_v2`` for E2 tests.
"""
from __future__ import annotations

from typing import Any

from engine.app import breakdown_p2_refinement_v1 as refinement
from engine.app import breakdown_p2_vlm_episode_v2 as episode_window
from engine.app.breakdown_p2_vlm_v1 import VLMRuntimeConfig

DEFAULT_WINDOW_OVERLAP_RATIO = episode_window.DEFAULT_WINDOW_OVERLAP_RATIO
DEFAULT_WINDOW_SECONDS = episode_window.DEFAULT_WINDOW_SECONDS
VLM_DRAFT_TEXT_LANGUAGE = episode_window.VLM_DRAFT_TEXT_LANGUAGE
VLM_EPISODE_WINDOW_PROFILE = episode_window.VLM_EPISODE_WINDOW_PROFILE
VLM_PROMPT_PROFILE = episode_window.VLM_PROMPT_PROFILE
VLM_WINDOW_SCHEMA = episode_window.VLM_WINDOW_SCHEMA
VLM_CONTEXTUAL_REFINEMENT_PROFILE = refinement.REFINEMENT_PROFILE
VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE = refinement.REFINEMENT_PROMPT_PROFILE


class Qwen3VLSemanticProvider(episode_window.Qwen3VLSemanticProvider):
    """Production E2+E3 provider while preserving the formal VLM Provider contract."""

    def __init__(
        self,
        *args: Any,
        contextual_refiner: refinement.ContextualShotRefiner | None = None,
        enable_contextual_refinement: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._contextual_refiner = contextual_refiner
        self.enable_contextual_refinement = bool(enable_contextual_refinement)

    def analyze(self, context):
        e2_result = super().analyze(context)
        if not self.enable_contextual_refinement or e2_result.status != "READY":
            return e2_result
        active = self._contextual_refiner or refinement.ContextualShotRefiner.from_vlm_provider(self)
        return refinement.refine_e2_provider_result(context, e2_result, refiner=active)


def run_qwen3_vl_episode_window_semantics(run_id: str, *, provider: Qwen3VLSemanticProvider | None = None):
    """Compatibility entry; production call now persists the composite E2+E3 VLM result."""

    from engine.app import breakdown_p2_sidecar_v1 as p2

    return p2.run_local_provider(run_id, provider or Qwen3VLSemanticProvider())


__all__ = [
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "Qwen3VLSemanticProvider",
    "VLM_CONTEXTUAL_REFINEMENT_PROFILE",
    "VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE",
    "VLM_DRAFT_TEXT_LANGUAGE",
    "VLM_EPISODE_WINDOW_PROFILE",
    "VLM_PROMPT_PROFILE",
    "VLM_WINDOW_SCHEMA",
    "VLMRuntimeConfig",
    "run_qwen3_vl_episode_window_semantics",
]
