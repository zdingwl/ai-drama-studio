"""Stable production VLM entry for fast grounded Episode Breakdown.

Production no longer runs the old text-only per-Shot E3 pass. The active visual chain is:

Episode-window context (cheap, low FPS)
→ exact frozen Shot frame grounding (1..3 frames, small batches)
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ E6 Episode Fusion.

Both visual passes execute in one isolated Qwen3-VL subprocess/model load. Window context may
help Scene fields only; exact-Shot frames are authoritative for visible people/actions/props and
shot photographic facts. The stable runtime now routes through the instrumented Fast Grounded
provider so the next real acceptance Run persists model/window/batch timings without changing
semantic behavior. The old E2/E3 modules remain for historical tests and comparison only.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v2 as fast
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
VLM_PERFORMANCE_PROFILE = fast.PERFORMANCE_PROFILE

# Historical E3 exports remain import-compatible for old tests/reports. Production does not call
# E3 anymore; these constants/helpers only preserve read/compare compatibility for old artifacts.
VLM_CONTEXTUAL_REFINEMENT_PROFILE = "breakdown-p2-contextual-shot-refinement-e3-v1"
VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE = "breakdown-p2-contextual-shot-refinement-zh-v1"
VLM_CONTEXTUAL_FAILURE_POLICY = "retired-from-production-fast-grounded-v1"


def _semantic(record: p2.P2EvidenceRecord) -> Mapping[str, Any]:
    value = record.payload.get("semantic") if isinstance(record.payload, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def _label_key(value: Any) -> str:
    text = " ".join(str(value or "").strip().split()).lower()
    return "".join(char for char in text if char.isalnum())


def _compatible_label(left: Any, right: Any) -> bool:
    left_key = _label_key(left)
    right_key = _label_key(right)
    return bool(left_key and right_key) and (
        left_key == right_key or left_key in right_key or right_key in left_key
    )


def _ground_contextual_semantic(
    e2_semantic: Mapping[str, Any],
    refined_semantic: Mapping[str, Any],
) -> dict[str, Any]:
    """Historical E3 grounding helper kept for artifact/test compatibility only."""

    scene = dict(e2_semantic.get("scene") or {})
    refined_scene = refined_semantic.get("scene") if isinstance(refined_semantic.get("scene"), Mapping) else {}
    for key in ("location_hint", "interior_exterior", "time_of_day", "environment_description"):
        value = refined_scene.get(key)
        if value not in (None, "", "UNKNOWN"):
            scene[key] = value

    shot = dict(e2_semantic.get("shot") or {})
    refined_shot = refined_semantic.get("shot") if isinstance(refined_semantic.get("shot"), Mapping) else {}
    for key in ("summary", "narrative_function_hint"):
        value = refined_shot.get(key)
        if value:
            shot[key] = value

    subjects = [dict(item) for item in e2_semantic.get("subjects", []) if isinstance(item, Mapping)]
    events = [dict(item) for item in e2_semantic.get("events", []) if isinstance(item, Mapping)]
    refined_props = [dict(item) for item in refined_semantic.get("props", []) if isinstance(item, Mapping)]
    props: list[dict[str, Any]] = []
    for raw_prop in e2_semantic.get("props", []):
        if not isinstance(raw_prop, Mapping):
            continue
        prop = dict(raw_prop)
        match = next((
            item for item in refined_props
            if _compatible_label(raw_prop.get("label"), item.get("label"))
        ), None)
        if match is not None:
            if match.get("importance"):
                prop["importance"] = match["importance"]
            if match.get("narrative_reason"):
                prop["narrative_reason"] = match["narrative_reason"]
        props.append(prop)
    return {"scene": scene, "shot": shot, "subjects": subjects, "events": events, "props": props}


def _with_e2_runtime_diagnostics(result: p2.P2ProviderResult) -> p2.P2ProviderResult:
    """Historical diagnostic adapter retained for old E2 reports/tests."""

    if result.status == "READY":
        return result
    metadata = result.metadata if isinstance(result.metadata, Mapping) else {}
    details: list[str] = []
    subprocess_detail = " ".join(str(metadata.get("subprocess_failure_detail") or "").split())
    if subprocess_detail:
        details.append(subprocess_detail[:1200])
    raw_window_details = metadata.get("window_failure_details")
    if isinstance(raw_window_details, list):
        for item in raw_window_details[:3]:
            text = " ".join(str(item or "").split())
            if text and text not in details:
                details.append(text[:900])
    if not details:
        return result
    diagnostic = "P2-E2 runtime detail: " + " | ".join(details)
    return p2.P2ProviderResult(
        component=result.component,
        provider=result.provider,
        model=result.model,
        status=result.status,
        evidence=result.evidence,
        metadata=result.metadata,
        warnings=tuple(dict.fromkeys((diagnostic, *result.warnings))),
    )


def _fallback_to_e2(
    context: p2.P2RunContext,
    e2_result: p2.P2ProviderResult,
    *,
    failed_result: p2.P2ProviderResult | None = None,
    exc: BaseException | None = None,
) -> p2.P2ProviderResult:
    """Historical E3 fallback serializer. Fast-grounded production does not invoke it."""

    detail_parts: list[str] = []
    error_type: str | None = None
    failed_metadata: Mapping[str, Any] = {}
    if failed_result is not None:
        failed_metadata = failed_result.metadata if isinstance(failed_result.metadata, Mapping) else {}
        nested = failed_metadata.get("contextual_refinement_metadata")
        if isinstance(nested, Mapping):
            error_type = str(nested.get("error_type") or "").strip() or None
        for warning in failed_result.warnings:
            text = " ".join(str(warning or "").split())
            if text and text not in detail_parts:
                detail_parts.append(text[:900])
    if exc is not None:
        error_type = error_type or type(exc).__name__
        text = " ".join(str(exc).strip().split())
        if text:
            detail_parts.append(text[:900])

    evidence: list[p2.P2EvidenceRecord] = []
    for raw in e2_result.evidence:
        semantic = dict(_semantic(raw))
        payload = dict(raw.payload)
        payload["e2_semantic"] = semantic
        payload["semantic"] = semantic
        payload["contextual_refinement"] = {
            "profile": VLM_CONTEXTUAL_REFINEMENT_PROFILE,
            "prompt_profile": VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE,
            "status": "FALLBACK_E2",
            "failure_policy": VLM_CONTEXTUAL_FAILURE_POLICY,
            "error_type": error_type,
        }
        evidence.append(p2.P2EvidenceRecord(
            source_type=raw.source_type,
            source_id=raw.source_id,
            source_start_us=raw.source_start_us,
            source_end_us=raw.source_end_us,
            shot_revision_item_id=raw.shot_revision_item_id,
            text=raw.text,
            language=raw.language,
            confidence=raw.confidence,
            payload=payload,
        ))

    metadata = dict(e2_result.metadata)
    metadata.update({
        "contextual_refinement_profile": VLM_CONTEXTUAL_REFINEMENT_PROFILE,
        "contextual_refinement_prompt_profile": VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE,
        "contextual_refinement_status": "FALLBACK_E2",
        "contextual_refinement_failure_policy": VLM_CONTEXTUAL_FAILURE_POLICY,
        "contextual_refinement_error_type": error_type,
        "contextual_refinement_failure_metadata": dict(failed_metadata),
    })
    diagnostic = "P2-E3 unavailable; using validated E2 semantics"
    if error_type:
        diagnostic += f" ({error_type})"
    result = p2.P2ProviderResult(
        component=e2_result.component,
        provider=e2_result.provider,
        model=e2_result.model,
        status="READY",
        evidence=tuple(evidence),
        metadata=metadata,
        warnings=tuple(dict.fromkeys((*e2_result.warnings, diagnostic, *detail_parts))),
    )
    p2.validate_provider_result(context, result)
    return result


class Qwen3VLSemanticProvider(fast.Qwen3VLSemanticProvider):
    """Stable production class name backed by the instrumented fast-grounded provider."""


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
    "VLM_PERFORMANCE_PROFILE",
    "VLM_PROMPT_PROFILE",
    "VLM_WINDOW_SCHEMA",
    "VLMRuntimeConfig",
    "_fallback_to_e2",
    "_ground_contextual_semantic",
    "_with_e2_runtime_diagnostics",
    "run_qwen3_vl_episode_window_semantics",
]
