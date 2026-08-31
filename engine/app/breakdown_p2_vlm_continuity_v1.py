"""Production continuity wrapper on top of Fast Grounded VLM.

The stable Breakdown pipeline imports this module so Episode-context Fusion keeps a dedicated
continuity-preservation surface. Production visual truth now uses the accepted Window-v4 +
reconstruction-safe Exact-Shot compact-v3 provider in one Qwen3-VL model load. The old text-only
per-Shot E3 stage is retired from production.

This wrapper keeps window-level subject/prop continuity hints normalized for the anonymous
continuity graph. Those hints remain soft Draft evidence only: they never create Final
Character/Scene/Prop IDs and never make Shot-local ``subject_A`` labels global identities.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v3 as production
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime

VLM_CONTINUITY_PRESERVATION_PROFILE = "breakdown-p2-vlm-window-continuity-preservation-e4-v1"


def _clean_text(value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_len] if text else None


def _valid_shot_maps(window: e2.EpisodeVLMWindow) -> tuple[dict[int, str], dict[str, int]]:
    by_ordinal = {int(shot.ordinal): str(shot.revision_item_id) for shot in window.shots}
    by_id = {str(shot.revision_item_id): int(shot.ordinal) for shot in window.shots}
    return by_ordinal, by_id


def _normalize_ordinals(value: Any, *, valid: set[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for raw in value:
        try:
            ordinal = int(raw)
        except (TypeError, ValueError):
            continue
        if ordinal in valid and ordinal not in result:
            result.append(ordinal)
    return result


def _normalize_members(
    value: Any,
    *,
    by_ordinal: Mapping[int, str],
    by_id: Mapping[str, int],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value[:48]:
        if not isinstance(raw, Mapping):
            continue
        item_id = str(raw.get("revision_item_id") or "").strip()
        ordinal_raw = raw.get("ordinal")
        try:
            ordinal = int(ordinal_raw) if ordinal_raw is not None else None
        except (TypeError, ValueError):
            ordinal = None
        if item_id and item_id in by_id:
            ordinal = by_id[item_id]
        elif ordinal is not None and ordinal in by_ordinal:
            item_id = by_ordinal[ordinal]
        else:
            continue
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        key = (item_id, label)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "revision_item_id": item_id,
            "ordinal": int(ordinal),
            "label": label,
        })
    return result


def _normalize_subject_hints(raw: Any, window: e2.EpisodeVLMWindow) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    by_ordinal, by_id = _valid_shot_maps(window)
    valid_ordinals = set(by_ordinal)
    result: list[dict[str, Any]] = []
    for item in raw[:32]:
        if not isinstance(item, Mapping):
            continue
        appearance = _clean_text(item.get("appearance_summary"), max_len=1200)
        continuity = _clean_text(item.get("continuity_summary"), max_len=1200)
        members = _normalize_members(item.get("members"), by_ordinal=by_ordinal, by_id=by_id)
        ordinals = _normalize_ordinals(item.get("shot_ordinals"), valid=valid_ordinals)
        for member in members:
            ordinal = int(member["ordinal"])
            if ordinal not in ordinals:
                ordinals.append(ordinal)
        if not appearance and not continuity:
            continue
        if len(ordinals) < 2 and len(members) < 2:
            continue
        result.append({
            "appearance_summary": appearance,
            "continuity_summary": continuity,
            "shot_ordinals": sorted(ordinals),
            "members": members,
        })
    return result


def _normalize_prop_hints(raw: Any, window: e2.EpisodeVLMWindow) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    by_ordinal, _by_id = _valid_shot_maps(window)
    valid_ordinals = set(by_ordinal)
    result: list[dict[str, Any]] = []
    for item in raw[:32]:
        if not isinstance(item, Mapping):
            continue
        label = _clean_text(item.get("label"), max_len=255)
        continuity = _clean_text(item.get("continuity_summary"), max_len=1200)
        ordinals = _normalize_ordinals(item.get("shot_ordinals"), valid=valid_ordinals)
        if not label or len(ordinals) < 2:
            continue
        result.append({
            "label": label,
            "continuity_summary": continuity,
            "shot_ordinals": sorted(ordinals),
        })
    return result


class Qwen3VLSemanticProvider(production.Qwen3VLSemanticProvider):
    """Production provider: Window v4 + Exact-Shot compact v3 + continuity normalization."""

    def _normalize_window_summary(
        self,
        raw: Mapping[str, Any],
        window: e2.EpisodeVLMWindow,
    ) -> dict[str, Any]:
        normalized = dict(super()._normalize_window_summary(raw, window))
        normalized["subject_continuity_hints"] = _normalize_subject_hints(
            raw.get("subject_continuity_hints"), window
        )
        normalized["prop_continuity_hints"] = _normalize_prop_hints(
            raw.get("prop_continuity_hints"), window
        )
        normalized["continuity_preservation_profile"] = VLM_CONTINUITY_PRESERVATION_PROFILE
        return normalized


DEFAULT_WINDOW_OVERLAP_RATIO = production.DEFAULT_WINDOW_OVERLAP_RATIO
DEFAULT_WINDOW_SECONDS = production.DEFAULT_WINDOW_SECONDS
DEFAULT_WINDOW_CONTEXT_FPS = production.DEFAULT_WINDOW_CONTEXT_FPS
DEFAULT_WINDOW_MAX_PIXELS = production.DEFAULT_WINDOW_MAX_PIXELS
DEFAULT_EXACT_SHOT_MAX_PIXELS = production.DEFAULT_EXACT_SHOT_MAX_PIXELS
DEFAULT_GROUNDING_BATCH_SIZE = production.DEFAULT_GROUNDING_BATCH_SIZE
VLM_WINDOW_PROMPT_PROFILE = production.WINDOW_PROMPT_PROFILE
VLM_EXACT_SHOT_PROMPT_PROFILE = production.EXACT_SHOT_PROMPT_PROFILE
VLM_DRAFT_TEXT_LANGUAGE = runtime.VLM_DRAFT_TEXT_LANGUAGE
VLM_EPISODE_WINDOW_PROFILE = production.WINDOW_CONTEXT_PROFILE
VLM_FAST_GROUNDED_PROFILE = production.FAST_GROUNDED_PROFILE
VLM_EXACT_SHOT_GROUNDING_PROFILE = production.EXACT_SHOT_GROUNDING_PROFILE
VLM_PROMPT_PROFILE = runtime.VLM_PROMPT_PROFILE
VLM_WINDOW_SCHEMA = production.FAST_GROUNDED_SCHEMA
VLM_CONTEXTUAL_REFINEMENT_PROFILE = runtime.VLM_CONTEXTUAL_REFINEMENT_PROFILE
VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE = runtime.VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE
VLM_CONTEXTUAL_GROUNDING_POLICY = production.VISUAL_TRUTH_POLICY
VLM_CONTEXTUAL_FAILURE_POLICY = runtime.VLM_CONTEXTUAL_FAILURE_POLICY
VLMRuntimeConfig = runtime.VLMRuntimeConfig


__all__ = [
    "DEFAULT_EXACT_SHOT_MAX_PIXELS",
    "DEFAULT_GROUNDING_BATCH_SIZE",
    "DEFAULT_WINDOW_CONTEXT_FPS",
    "DEFAULT_WINDOW_MAX_PIXELS",
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "Qwen3VLSemanticProvider",
    "VLM_CONTINUITY_PRESERVATION_PROFILE",
    "VLM_CONTEXTUAL_FAILURE_POLICY",
    "VLM_CONTEXTUAL_GROUNDING_POLICY",
    "VLM_CONTEXTUAL_REFINEMENT_PROFILE",
    "VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE",
    "VLM_DRAFT_TEXT_LANGUAGE",
    "VLM_EPISODE_WINDOW_PROFILE",
    "VLM_EXACT_SHOT_GROUNDING_PROFILE",
    "VLM_EXACT_SHOT_PROMPT_PROFILE",
    "VLM_FAST_GROUNDED_PROFILE",
    "VLM_PROMPT_PROFILE",
    "VLM_WINDOW_PROMPT_PROFILE",
    "VLM_WINDOW_SCHEMA",
    "VLMRuntimeConfig",
]
