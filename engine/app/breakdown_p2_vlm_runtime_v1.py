"""Stable production Qwen3-VL runtime entry for Episode-context Breakdown.

Production visual understanding is composite:
P2-E2 overlapping Episode windows -> P2-E3 contextual Shot refinement -> deterministic
current-Shot grounding guard. The final frozen VLM sidecar keeps E2 semantics in
``payload.e2_semantic`` and exposes the grounded E3 semantic in ``payload.semantic`` for the
existing Episode-context Fusion.

The legacy single-Reference-Clip provider remains in ``breakdown_p2_vlm_v1`` for historical
contract tests; the pure E2 provider remains in ``breakdown_p2_vlm_episode_v2`` for E2 tests.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.app import breakdown_p2_refinement_v1 as refinement
from engine.app import breakdown_p2_sidecar_v1 as p2
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
VLM_CONTEXTUAL_GROUNDING_POLICY = "e3-text-only-preserve-e2-visual-facts-v1"


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
    """Keep E3 contextual prose but prevent text-only E3 from inventing visual presence."""

    scene = dict(e2_semantic.get("scene") or {})
    refined_scene = refined_semantic.get("scene") if isinstance(refined_semantic.get("scene"), Mapping) else {}
    # E3 is allowed to resolve Scene context because that is the purpose of the contextual pass.
    for key in ("location_hint", "interior_exterior", "time_of_day", "environment_description"):
        value = refined_scene.get(key)
        if value not in (None, "", "UNKNOWN"):
            scene[key] = value

    shot = dict(e2_semantic.get("shot") or {})
    refined_shot = refined_semantic.get("shot") if isinstance(refined_semantic.get("shot"), Mapping) else {}
    # Summary/narrative purpose may use context; photographic facts stay E2-grounded.
    for key in ("summary", "narrative_function_hint"):
        value = refined_shot.get(key)
        if value:
            shot[key] = value

    subjects = [
        dict(item) for item in e2_semantic.get("subjects", []) if isinstance(item, Mapping)
    ]
    events = [
        dict(item) for item in e2_semantic.get("events", []) if isinstance(item, Mapping)
    ]

    refined_props = [
        dict(item) for item in refined_semantic.get("props", []) if isinstance(item, Mapping)
    ]
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
            # E3 may contextualize importance/reason for an already-visible E2 prop, but never add one.
            if match.get("importance"):
                prop["importance"] = match["importance"]
            if match.get("narrative_reason"):
                prop["narrative_reason"] = match["narrative_reason"]
        props.append(prop)

    return {
        "scene": scene,
        "shot": shot,
        "subjects": subjects,
        "events": events,
        "props": props,
    }


def _apply_contextual_grounding(
    context: p2.P2RunContext,
    e2_result: p2.P2ProviderResult,
    refined_result: p2.P2ProviderResult,
) -> p2.P2ProviderResult:
    if refined_result.status != "READY":
        return refined_result
    e2_by_shot = {
        str(item.shot_revision_item_id): item
        for item in e2_result.evidence
        if item.shot_revision_item_id
    }
    evidence: list[p2.P2EvidenceRecord] = []
    for item in refined_result.evidence:
        raw = e2_by_shot.get(str(item.shot_revision_item_id or ""))
        if raw is None:
            raise refinement.BreakdownP2RefinementError(
                "E3 grounding guard 无法映射 exact E2 Shot"
            )
        payload = dict(item.payload)
        e2_semantic = payload.get("e2_semantic")
        if not isinstance(e2_semantic, Mapping):
            e2_semantic = _semantic(raw)
        refined_semantic = payload.get("semantic")
        if not isinstance(refined_semantic, Mapping):
            refined_semantic = e2_semantic
        grounded = _ground_contextual_semantic(e2_semantic, refined_semantic)
        payload["e2_semantic"] = dict(e2_semantic)
        payload["semantic"] = grounded
        contextual = payload.get("contextual_refinement")
        if isinstance(contextual, Mapping):
            payload["contextual_refinement"] = {
                **dict(contextual),
                "grounding_policy": VLM_CONTEXTUAL_GROUNDING_POLICY,
            }
        evidence.append(p2.P2EvidenceRecord(
            source_type=item.source_type,
            source_id=item.source_id,
            source_start_us=item.source_start_us,
            source_end_us=item.source_end_us,
            shot_revision_item_id=item.shot_revision_item_id,
            text=str((grounded.get("shot") or {}).get("summary") or item.text or "").strip() or None,
            language=item.language,
            confidence=item.confidence,
            payload=payload,
        ))

    metadata = dict(refined_result.metadata)
    metadata["contextual_grounding_policy"] = VLM_CONTEXTUAL_GROUNDING_POLICY
    metadata["contextual_grounding_rule"] = (
        "E3 may refine Scene, Shot summary/narrative purpose, and existing-prop importance/reason; "
        "subjects/events/photographic facts/new prop presence remain E2-grounded"
    )
    result = p2.P2ProviderResult(
        component=refined_result.component,
        provider=refined_result.provider,
        model=refined_result.model,
        status=refined_result.status,
        evidence=tuple(evidence),
        metadata=metadata,
        warnings=refined_result.warnings,
    )
    p2.validate_provider_result(context, result)
    return result


def _with_e2_runtime_diagnostics(result: p2.P2ProviderResult) -> p2.P2ProviderResult:
    """Promote sanitized E2 subprocess/window diagnostics into the first warning.

    The production pipeline intentionally surfaces the first Provider warning to the user. E2
    already stored subprocess_failure_detail/window_failure_details in metadata, but the old
    wrapper returned only the generic warning. That made model-load/CUDA/runner crashes appear as
    just "P2-E2 VLM inference failed". Keep metadata and prepend a bounded readable detail.
    """

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
    warnings = tuple(dict.fromkeys((diagnostic, *result.warnings)))
    return p2.P2ProviderResult(
        component=result.component,
        provider=result.provider,
        model=result.model,
        status=result.status,
        evidence=result.evidence,
        metadata=result.metadata,
        warnings=warnings,
    )


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

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        e2_result = super().analyze(context)
        if e2_result.status != "READY":
            return _with_e2_runtime_diagnostics(e2_result)
        if not self.enable_contextual_refinement:
            return e2_result
        active = self._contextual_refiner or refinement.ContextualShotRefiner.from_vlm_provider(self)
        refined = refinement.refine_e2_provider_result(context, e2_result, refiner=active)
        return _apply_contextual_grounding(context, e2_result, refined)


def run_qwen3_vl_episode_window_semantics(
    run_id: str,
    *,
    provider: Qwen3VLSemanticProvider | None = None,
):
    """Compatibility entry; production call persists the composite grounded E2+E3 result."""

    return p2.run_local_provider(run_id, provider or Qwen3VLSemanticProvider())


__all__ = [
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "Qwen3VLSemanticProvider",
    "VLM_CONTEXTUAL_GROUNDING_POLICY",
    "VLM_CONTEXTUAL_REFINEMENT_PROFILE",
    "VLM_CONTEXTUAL_REFINEMENT_PROMPT_PROFILE",
    "VLM_DRAFT_TEXT_LANGUAGE",
    "VLM_EPISODE_WINDOW_PROFILE",
    "VLM_PROMPT_PROFILE",
    "VLM_WINDOW_SCHEMA",
    "VLMRuntimeConfig",
    "run_qwen3_vl_episode_window_semantics",
]
