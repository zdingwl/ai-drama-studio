"""Episode-context Fusion E1 for Breakdown P2.

This module is the first safe migration away from "one Shot == one semantic context".
It deliberately keeps the frozen P1 Draft schema and immutable P2 Evidence sidecars, while
changing two derived-Fusion policies that were causing visible product errors:

1. Scene continuity is Episode/sequence scoped. Missing, weak, close-up or background-poor
   scene hints inherit the current SceneSegmentDraft. A new segment is created only when
   there is a strong location or interior/exterior contradiction.
2. ASR_SEGMENT remains the dialogue text truth. A sentence crossing a cut is projected onto
   each intersecting Shot without splitting its text. All projections carry the same
   ``dialogue_group_id`` / ``asr_segment_id`` and the full Episode-source dialogue range.

Raw ASR_WORD / VLM_OUTPUT evidence is never rewritten. This module derives a temporary
Fusion-consumption view and then writes the same P1 tables, so historical sidecars and the
Character V10.1 / Final Asset gates remain untouched.

E1 is intentionally not the final continuous-window VLM implementation. P2-E2 will replace
single-Reference-Clip visual inference with overlapping Episode windows. Until then, E1 makes
the current Shot-level visual evidence fuse conservatively instead of treating uncertainty as
a scene change.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from threading import Lock
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownEvidenceLink,
    BreakdownRun,
    SceneSegmentDraft,
    ShotSemanticDraft,
    TimelineEvent,
)

FUSION_PROFILE = "breakdown-p2-fusion-episode-context-e1-v2"
FUSION_VERSION = "2"
SCENE_SEGMENTATION_POLICY = "episode-continuity-inherit-unknown-v2"
ASR_DIALOGUE_POLICY = "episode-segment-projection-v2"
BASE_FUSION_PROFILE = legacy.FUSION_PROFILE

# Production heavy jobs are already globally serialized. This lock additionally prevents two
# E1 Fusion calls in the same process from overlapping while the legacy private segment planner
# is temporarily replaced by the continuity planner.
_FUSION_PATCH_LOCK = Lock()

_GENERIC_LOCATION_HINTS = frozenset({
    "",
    "unknown",
    "未知",
    "不明",
    "室内",
    "室外",
    "内景",
    "外景",
    "房间",
    "房间内",
    "空间",
    "室内空间",
    "室外空间",
    "indoors",
    "outdoors",
    "interior",
    "exterior",
    "room",
})


@dataclass(frozen=True)
class _SceneHint:
    location: str | None
    location_key: str
    interior_exterior: str
    time_of_day: str | None


@dataclass(frozen=True)
class _ScenePlanDetail:
    plan: Any
    anchor: _SceneHint


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_location_key(value: Any) -> str:
    text = legacy._clean_text(value, max_len=255) or ""
    # Ignore punctuation/spacing differences such as "客厅（室内）" vs "客厅".
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _normalize_ie(value: Any) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    if normalized in {"INT", "INTERIOR"}:
        return "INT"
    if normalized in {"EXT", "EXTERIOR"}:
        return "EXT"
    if normalized == "MIXED":
        return "MIXED"
    return "UNKNOWN"


def _scene_hint(semantic: Mapping[str, Any] | None) -> _SceneHint:
    scene = semantic.get("scene") if isinstance(semantic, Mapping) else None
    if not isinstance(scene, Mapping):
        return _SceneHint(None, "", "UNKNOWN", None)
    location = legacy._clean_text(scene.get("location_hint"), max_len=255)
    time_of_day = legacy._clean_text(scene.get("time_of_day"), max_len=64)
    return _SceneHint(
        location=location,
        location_key=_clean_location_key(location),
        interior_exterior=_normalize_ie(scene.get("interior_exterior")),
        time_of_day=time_of_day,
    )


def _weak_location(hint: _SceneHint) -> bool:
    key = hint.location_key
    if not key or key in _GENERIC_LOCATION_HINTS:
        return True
    if key.startswith("unknown") or key.startswith("未知"):
        return True
    return False


def _locations_compatible(left: _SceneHint, right: _SceneHint) -> bool:
    if _weak_location(left) or _weak_location(right):
        return True
    if left.location_key == right.location_key:
        return True
    shorter, longer = sorted((left.location_key, right.location_key), key=len)
    # "客厅" / "家中客厅", "病房" / "医院病房" are treated as the same place hint.
    return len(shorter) >= 2 and shorter in longer


def _strong_scene_change(current: _SceneHint, candidate: _SceneHint) -> bool:
    """Return True only for evidence strong enough to cut a Scene Segment.

    Missing/generic location and time-of-day changes alone never cut a scene in E1. Close-ups,
    inserts and blurred backgrounds therefore inherit the current scene. Location contradiction
    or a clear INT<->EXT contradiction is treated as strong evidence.
    """

    if (
        not _weak_location(current)
        and not _weak_location(candidate)
        and not _locations_compatible(current, candidate)
    ):
        return True
    if (
        current.interior_exterior in {"INT", "EXT"}
        and candidate.interior_exterior in {"INT", "EXT"}
        and current.interior_exterior != candidate.interior_exterior
    ):
        return True
    return False


def _merge_anchor(current: _SceneHint, candidate: _SceneHint) -> _SceneHint:
    location = current.location
    location_key = current.location_key
    if _weak_location(current) and not _weak_location(candidate):
        location, location_key = candidate.location, candidate.location_key
    elif (
        not _weak_location(candidate)
        and _locations_compatible(current, candidate)
        and len(candidate.location_key) > len(current.location_key)
    ):
        # Prefer the more specific compatible hint, e.g. "医院病房" over "病房".
        location, location_key = candidate.location, candidate.location_key

    interior = current.interior_exterior
    if interior == "UNKNOWN" and candidate.interior_exterior != "UNKNOWN":
        interior = candidate.interior_exterior

    time_of_day = current.time_of_day
    if not time_of_day and candidate.time_of_day:
        time_of_day = candidate.time_of_day

    return _SceneHint(location, location_key, interior, time_of_day)


def _continuity_plan_details(
    shots: Sequence[p2.P2ShotInput],
    vlm_by_shot: Mapping[str, p2.P2EvidenceRecord],
) -> list[_ScenePlanDetail]:
    details: list[_ScenePlanDetail] = []
    current_plan: Any | None = None
    current_anchor = _SceneHint(None, "", "UNKNOWN", None)

    for shot in shots:
        semantic = legacy._semantic(vlm_by_shot.get(shot.revision_item_id))
        hint = _scene_hint(semantic)
        if current_plan is None or _strong_scene_change(current_anchor, hint):
            current_plan = legacy._SegmentPlan(index=len(details) + 1)
            current_anchor = hint
            details.append(_ScenePlanDetail(plan=current_plan, anchor=current_anchor))
        else:
            current_anchor = _merge_anchor(current_anchor, hint)
            details[-1] = _ScenePlanDetail(plan=current_plan, anchor=current_anchor)

        current_plan.shots.append(shot)
        current_plan.semantics.append(semantic)

    return details


def _continuity_segment_plans(
    shots: Sequence[p2.P2ShotInput],
    vlm_by_shot: Mapping[str, p2.P2EvidenceRecord],
) -> list[Any]:
    return [item.plan for item in _continuity_plan_details(shots, vlm_by_shot)]


def _episode_projection_bundle(bundle: legacy.FusionInputBundle) -> legacy.FusionInputBundle:
    """Create a derived Fusion view that treats ASR_SEGMENT as dialogue text truth.

    The immutable ASR sidecar still contains all ASR_WORD evidence. Words are excluded only from
    the first legacy write pass so it cannot split sentence text at Shot boundaries; they are
    reattached as SUPPORT provenance and confidence evidence in ``_rewrite_dialogue_events``.
    """

    components = dict(bundle.components)
    loaded = components["ASR"]
    result = loaded.result
    filtered = tuple(
        item for item in result.evidence
        if item.source_type.strip().upper() != "ASR_WORD"
    )
    metadata = dict(result.metadata)
    metadata["fusion_consumption_policy"] = ASR_DIALOGUE_POLICY
    projected_result = p2.P2ProviderResult(
        component=result.component,
        provider=result.provider,
        model=result.model,
        status=result.status,
        evidence=filtered,
        metadata=metadata,
        warnings=tuple(result.warnings),
    )
    components["ASR"] = legacy.LoadedComponent(
        component=loaded.component,
        artifact_uri=loaded.artifact_uri,
        fingerprint=loaded.fingerprint,
        result=projected_result,
    )
    return legacy.FusionInputBundle(
        context=bundle.context,
        components=components,
        warnings=bundle.warnings,
    )


def _asr_indexes(
    bundle: legacy.FusionInputBundle,
) -> tuple[dict[str, p2.P2EvidenceRecord], dict[str, list[p2.P2EvidenceRecord]]]:
    segments: dict[str, p2.P2EvidenceRecord] = {}
    words: dict[str, list[p2.P2EvidenceRecord]] = {}
    for record in bundle.components["ASR"].result.evidence:
        source_type = record.source_type.strip().upper()
        if source_type == "ASR_SEGMENT":
            segments[record.source_id] = record
        elif source_type == "ASR_WORD":
            payload = record.payload if isinstance(record.payload, Mapping) else {}
            segment_id = str(payload.get("segment_id") or "").strip()
            if segment_id:
                words.setdefault(segment_id, []).append(record)
    for segment_words in words.values():
        segment_words.sort(key=lambda item: (item.source_start_us or 0, item.source_id))
    return segments, words


def _overlapping_words(
    words: Sequence[p2.P2EvidenceRecord],
    start_us: int,
    end_us: int,
) -> list[p2.P2EvidenceRecord]:
    return [
        word for word in words
        if word.source_start_us is not None
        and word.source_end_us is not None
        and min(int(word.source_end_us), end_us) > max(int(word.source_start_us), start_us)
    ]


def _rewrite_dialogue_events(
    session: Any,
    *,
    run_id: str,
    source_bundle: legacy.FusionInputBundle,
) -> None:
    segments, words_by_segment = _asr_indexes(source_bundle)
    events = list(session.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.run_id == run_id, TimelineEvent.event_type == "DIALOGUE")
        .order_by(TimelineEvent.source_start_us, TimelineEvent.id)
    ).all())

    grouped: dict[str, list[TimelineEvent]] = {}
    for event in events:
        metadata = _json_object(event.metadata_json)
        segment_id = str(metadata.get("asr_segment_id") or "").strip()
        if segment_id:
            grouped.setdefault(segment_id, []).append(event)

    existing_word_links = {
        (row.owner_id, row.source_id)
        for row in session.scalars(
            select(BreakdownEvidenceLink).where(
                BreakdownEvidenceLink.run_id == run_id,
                BreakdownEvidenceLink.owner_type == "TIMELINE_EVENT",
                BreakdownEvidenceLink.source_type == "ASR_WORD",
            )
        ).all()
    }
    asr_uri = source_bundle.components["ASR"].artifact_uri

    for segment_id, group in grouped.items():
        segment = segments.get(segment_id)
        if segment is None or segment.source_start_us is None or segment.source_end_us is None:
            continue
        ordered = sorted(group, key=lambda item: (item.source_start_us, item.id))
        full_text = legacy._clean_text(segment.text, max_len=4000)
        group_words = words_by_segment.get(segment_id, [])
        for projection_index, event in enumerate(ordered, start=1):
            overlap_words = _overlapping_words(group_words, event.source_start_us, event.source_end_us)
            if full_text:
                event.content_text = full_text
            if overlap_words:
                event.confidence = legacy._mean_confidence(overlap_words)

            metadata = _json_object(event.metadata_json)
            metadata.update({
                "fusion_profile": FUSION_PROFILE,
                "asr_segment_id": segment_id,
                "dialogue_group_id": segment_id,
                "text_policy": ASR_DIALOGUE_POLICY,
                "dialogue_source_start_us": int(segment.source_start_us),
                "dialogue_source_end_us": int(segment.source_end_us),
                "projection_start_us": int(event.source_start_us),
                "projection_end_us": int(event.source_end_us),
                "projection_index": projection_index,
                "projection_count": len(ordered),
                "continues_from_previous_shot": event.source_start_us > int(segment.source_start_us),
                "continues_to_next_shot": event.source_end_us < int(segment.source_end_us),
                "word_ids": [item.source_id for item in overlap_words],
            })
            event.metadata_json = _json_text(metadata)

            for word in overlap_words:
                link_key = (event.id, word.source_id)
                if link_key in existing_word_links:
                    continue
                existing_word_links.add(link_key)
                session.add(BreakdownEvidenceLink(
                    id=studio_v2.new_id("EVIDENCE"),
                    run_id=run_id,
                    owner_type="TIMELINE_EVENT",
                    owner_id=event.id,
                    source_type=word.source_type,
                    source_id=word.source_id,
                    source_uri=asr_uri,
                    role="SUPPORT",
                    confidence=word.confidence,
                    metadata_json=_json_text({
                        "dialogue_group_id": segment_id,
                        "projection_support": True,
                    }),
                ))


def _rewrite_scene_rows(
    session: Any,
    *,
    run_id: str,
    source_bundle: legacy.FusionInputBundle,
) -> None:
    shots_by_id = {shot.revision_item_id: shot for shot in source_bundle.context.shots}
    vlm_by_shot = {
        item.shot_revision_item_id: item
        for item in source_bundle.components["VLM"].result.evidence
        if item.source_type.strip().upper() == "VLM_OUTPUT"
        and item.shot_revision_item_id in shots_by_id
    }
    details = _continuity_plan_details(source_bundle.context.shots, vlm_by_shot)
    segments = list(session.scalars(
        select(SceneSegmentDraft)
        .where(SceneSegmentDraft.run_id == run_id)
        .order_by(SceneSegmentDraft.ordinal)
    ).all())

    for segment, detail in zip(segments, details):
        anchor = detail.anchor
        if not _weak_location(anchor) and anchor.location:
            segment.location_hint = anchor.location
        mapped_ie = legacy._map_interior_exterior(anchor.interior_exterior)
        if mapped_ie != "UNKNOWN":
            segment.interior_exterior = mapped_ie
        mapped_tod = legacy._map_time_of_day(anchor.time_of_day)
        if mapped_tod != "UNKNOWN":
            segment.time_of_day = mapped_tod
        metadata = _json_object(segment.metadata_json)
        metadata.update({
            "fusion_profile": FUSION_PROFILE,
            "segmentation_policy": SCENE_SEGMENTATION_POLICY,
            "continuity_rule": "inherit-weak-or-missing-until-strong-location-or-int-ext-change",
            "anchor_location": anchor.location,
        })
        segment.metadata_json = _json_text(metadata)

    drafts = list(session.scalars(
        select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run_id)
    ).all())
    for draft in drafts:
        metadata = _json_object(draft.model_metadata_json)
        metadata["fusion_profile"] = FUSION_PROFILE
        metadata["scene_context_policy"] = SCENE_SEGMENTATION_POLICY
        draft.model_metadata_json = _json_text(metadata)


def _rewrite_run_metadata(
    session: Any,
    *,
    run: BreakdownRun,
    warnings: Sequence[Mapping[str, Any]],
) -> None:
    # Dialogue rewrite can add ASR_WORD provenance links after the legacy generated-count snapshot.
    # Flush first, then make the reported Evidence count match the actual stored rows.
    session.flush()
    evidence_link_count = len(session.scalars(
        select(BreakdownEvidenceLink.id).where(BreakdownEvidenceLink.run_id == run.id)
    ).all())

    statuses = _json_object(run.component_status_json)
    fusion_status = statuses.get("FUSION")
    if not isinstance(fusion_status, dict):
        fusion_status = {}
    generated_counts = fusion_status.get("generated_counts")
    if isinstance(generated_counts, dict):
        generated_counts["evidence_link"] = evidence_link_count
    fusion_status.update({
        "status": "READY_WITH_WARNINGS" if warnings else "READY",
        "profile": FUSION_PROFILE,
        "version": FUSION_VERSION,
        "base_profile": BASE_FUSION_PROFILE,
        "warnings": [dict(item) for item in warnings],
    })
    statuses["FUSION"] = fusion_status

    providers = _json_object(run.provider_metadata_json)
    previous = providers.get("p2_fusion")
    p2_fusion = dict(previous) if isinstance(previous, Mapping) else {}
    p2_fusion.update({
        "profile": FUSION_PROFILE,
        "version": FUSION_VERSION,
        "base_profile": BASE_FUSION_PROFILE,
        "scene_segmentation_policy": SCENE_SEGMENTATION_POLICY,
        "asr_policy": ASR_DIALOGUE_POLICY,
        "dialogue_truth": "ASR_SEGMENT",
        "shot_dialogue_role": "projection-not-text-truth",
    })
    providers["p2_fusion"] = p2_fusion

    run.component_status_json = _json_text(statuses)
    run.provider_metadata_json = _json_text(providers)


def fuse_breakdown_run(run_id: str) -> BreakdownRun:
    """E1 production Fusion entry: immutable sidecars -> Episode-context P1 Draft -> publish."""

    try:
        source_bundle = legacy.load_fusion_inputs(run_id)
        projection_bundle = _episode_projection_bundle(source_bundle)

        # Reuse the mature P1 writing/validator-compatible implementation, changing only the
        # segmentation planner. The lock makes the short-lived private-function swap fail-safe
        # for production's already-serialized heavy-job model.
        with _FUSION_PATCH_LOCK:
            original_segment_plans = legacy._segment_plans
            legacy._segment_plans = _continuity_segment_plans
            try:
                raw_warnings, _generated_counts = legacy._write_fused_draft(projection_bundle)
            finally:
                legacy._segment_plans = original_segment_plans

        # ASR_CROSS_SHOT_TEXT_FALLBACK was a warning in the old split-text policy. Under E1 the
        # exact Segment-overlap projection is intentional and no longer an error condition.
        warnings = [
            dict(item) for item in raw_warnings
            if str(item.get("code") or "") != "ASR_CROSS_SHOT_TEXT_FALLBACK"
        ]

        with studio_v2.get_session() as session:
            run = session.get(BreakdownRun, run_id)
            if run is None:
                raise LookupError("Breakdown Run 不存在")
            if run.status != "PROCESSING":
                raise legacy.BreakdownP2FusionError(
                    f"E1 post-Fusion 只允许处理 PROCESSING Run，当前状态为 {run.status}"
                )
            _rewrite_dialogue_events(session, run_id=run_id, source_bundle=source_bundle)
            _rewrite_scene_rows(session, run_id=run_id, source_bundle=source_bundle)
            _rewrite_run_metadata(session, run=run, warnings=warnings)
            session.commit()

        return breakdown_service_v1.publish_breakdown_run(
            run_id,
            warnings=warnings or None,
        )
    except Exception as exc:
        legacy._safe_fail_run(run_id, exc)
        raise
