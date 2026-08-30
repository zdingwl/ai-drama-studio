"""Read-only diagnostics for Fast Grounded G1 real-video acceptance.

This module never reruns ASR/OCR/VLM, never rewrites Breakdown Draft rows and never creates Final
assets. It reads one completed BreakdownRun and exposes the facts needed for the current local-real
acceptance gate:

- total Run elapsed time plus persisted ASR/OCR/VLM provider timings;
- SceneSegmentDraft boundaries and per-Scene anonymous LocalSubject continuity members;
- E4 subject-continuity counters and same-Shot cluster conflict inspection;
- Shot 0001 final grounded Draft facts for the blue-rose regression;
- short OCR text samples, recorded only as a later cleanup signal.

LocalSubject remains anonymous Scene-scoped Draft truth and is never treated as Character identity.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from engine.app import studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownRun,
    DraftPropHint,
    DraftPropOccurrence,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
    TimelineEvent,
)

G1_DIAGNOSTIC_SCHEMA = "breakdown-g1-real-acceptance-diagnostics-v1"
G1_DIAGNOSTIC_VERSION = "1"


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _elapsed_seconds(run: Any) -> float | None:
    started = getattr(run, "started_at", None)
    completed = getattr(run, "completed_at", None)
    if started is None or completed is None:
        return None
    return round(max(0.0, float((completed - started).total_seconds())), 6)


def _runtime_snapshot(run: Any) -> dict[str, Any]:
    providers = _json_object(getattr(run, "provider_metadata_json", None))
    pipeline = providers.get("p2_pipeline") if isinstance(providers.get("p2_pipeline"), Mapping) else {}
    timings = pipeline.get("timings_seconds") if isinstance(pipeline.get("timings_seconds"), Mapping) else {}
    elapsed = _elapsed_seconds(run)
    return {
        "started_at": run.started_at.isoformat() if getattr(run, "started_at", None) else None,
        "completed_at": run.completed_at.isoformat() if getattr(run, "completed_at", None) else None,
        "total_elapsed_seconds": elapsed,
        "total_elapsed_minutes": round(elapsed / 60.0, 3) if elapsed is not None else None,
        "provider_timings_seconds": {
            str(key): round(float(value), 6)
            for key, value in timings.items()
            if isinstance(value, (int, float))
        },
        "targets": {
            "under_30_minutes": bool(elapsed is not None and elapsed < 30 * 60),
            "at_or_below_20_minutes": bool(elapsed is not None and elapsed <= 20 * 60),
        },
        "note": "Provider timings currently persist ASR/OCR/VLM only; total Run elapsed is started_at -> completed_at and includes Fusion/validation/IO.",
    }


def _normalize_source_members(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        item_id = str(raw.get("shot_revision_item_id") or "").strip()
        label = str(raw.get("source_label") or raw.get("label") or "").strip()
        try:
            ordinal = int(raw.get("shot_ordinal"))
        except (TypeError, ValueError):
            ordinal = None
        if not item_id:
            continue
        result.append({
            "shot_revision_item_id": item_id,
            "shot_ordinal": ordinal,
            "source_label": label or None,
            "appearance_summary": str(raw.get("appearance_summary") or "").strip() or None,
        })
    result.sort(key=lambda item: (
        item["shot_ordinal"] if item["shot_ordinal"] is not None else 10**9,
        item["shot_revision_item_id"],
        item["source_label"] or "",
    ))
    return result


def _same_shot_conflicts(members: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    ordinals: dict[str, int | None] = {}
    for item in members:
        item_id = str(item.get("shot_revision_item_id") or "").strip()
        if not item_id:
            continue
        label = str(item.get("source_label") or "").strip() or "UNKNOWN"
        grouped.setdefault(item_id, []).append(label)
        raw_ordinal = item.get("shot_ordinal")
        ordinals[item_id] = int(raw_ordinal) if isinstance(raw_ordinal, int) else None
    return [
        {
            "shot_revision_item_id": item_id,
            "shot_ordinal": ordinals.get(item_id),
            "source_labels": labels,
        }
        for item_id, labels in grouped.items()
        if len(labels) > 1
    ]


def _short_ocr_noise_samples(texts: Sequence[str], *, limit: int = 20) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in texts:
        text = " ".join(str(raw or "").strip().split())
        compact = "".join(ch for ch in text if not ch.isspace())
        if not text or len(compact) > 2 or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def build_g1_acceptance_snapshot(run_id: str) -> dict[str, Any]:
    """Build a read-only local-real acceptance snapshot for one existing Breakdown Run."""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")

        segments = list(session.scalars(
            select(SceneSegmentDraft)
            .where(SceneSegmentDraft.run_id == run_id)
            .order_by(SceneSegmentDraft.ordinal)
        ).all())
        shots = list(session.scalars(
            select(ShotSemanticDraft)
            .where(ShotSemanticDraft.run_id == run_id)
            .order_by(ShotSemanticDraft.shot_ordinal_snapshot)
        ).all())
        locals_ = list(session.scalars(
            select(LocalSubject)
            .where(LocalSubject.run_id == run_id)
            .order_by(LocalSubject.scene_segment_id, LocalSubject.ordinal)
        ).all())
        presences = list(session.scalars(
            select(ShotLocalSubject).where(ShotLocalSubject.run_id == run_id)
        ).all())
        props = list(session.scalars(
            select(DraftPropHint)
            .where(DraftPropHint.run_id == run_id)
            .order_by(DraftPropHint.scene_segment_id, DraftPropHint.ordinal)
        ).all())
        events = list(session.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.run_id == run_id)
            .order_by(TimelineEvent.source_start_us, TimelineEvent.id)
        ).all())

        shot_ids = [item.id for item in shots]
        occurrences = list(session.scalars(
            select(DraftPropOccurrence).where(DraftPropOccurrence.shot_draft_id.in_(shot_ids))
        ).all()) if shot_ids else []

        shot_by_id = {item.id: item for item in shots}
        local_by_id = {item.id: item for item in locals_}
        prop_by_id = {item.id: item for item in props}
        presences_by_shot: dict[str, list[ShotLocalSubject]] = {}
        presences_by_local: dict[str, list[ShotLocalSubject]] = {}
        for presence in presences:
            presences_by_shot.setdefault(presence.shot_draft_id, []).append(presence)
            presences_by_local.setdefault(presence.local_subject_id, []).append(presence)
        occurrences_by_shot: dict[str, list[DraftPropOccurrence]] = {}
        for occurrence in occurrences:
            occurrences_by_shot.setdefault(occurrence.shot_draft_id, []).append(occurrence)

        scene_payloads: list[dict[str, Any]] = []
        all_conflicts: list[dict[str, Any]] = []
        for segment in segments:
            scene_shots = [item for item in shots if item.scene_segment_id == segment.id]
            scene_locals = [item for item in locals_ if item.scene_segment_id == segment.id]
            subject_payloads: list[dict[str, Any]] = []
            for local in scene_locals:
                metadata = _json_object(local.appearance_json)
                members = _normalize_source_members(metadata.get("source_members"))
                if not members:
                    for presence in presences_by_local.get(local.id, []):
                        shot = shot_by_id.get(presence.shot_draft_id)
                        if shot is None:
                            continue
                        search_hint = _json_object(presence.search_hint_json)
                        members.append({
                            "shot_revision_item_id": shot.source_shot_revision_item_id,
                            "shot_ordinal": int(shot.shot_ordinal_snapshot),
                            "source_label": str(search_hint.get("source_vlm_label") or "").strip() or None,
                            "appearance_summary": None,
                        })
                    members.sort(key=lambda item: (item["shot_ordinal"], item["shot_revision_item_id"]))
                conflicts = _same_shot_conflicts(members)
                for conflict in conflicts:
                    all_conflicts.append({
                        "scene_ordinal": int(segment.ordinal),
                        "local_subject_id": local.id,
                        "display_label": local.display_label,
                        **conflict,
                    })
                subject_payloads.append({
                    "local_subject_id": local.id,
                    "ordinal": int(local.ordinal),
                    "display_label": local.display_label,
                    "appearance_summary": local.appearance_summary,
                    "first_seen_us": int(local.first_seen_us),
                    "last_seen_us": int(local.last_seen_us),
                    "cluster_key": metadata.get("cluster_key"),
                    "source_members": members,
                    "shot_ordinals": sorted({
                        int(item["shot_ordinal"])
                        for item in members
                        if isinstance(item.get("shot_ordinal"), int)
                    }),
                    "same_shot_conflicts": conflicts,
                })
            scene_payloads.append({
                "scene_segment_id": segment.id,
                "ordinal": int(segment.ordinal),
                "source_start_us": int(segment.source_start_us),
                "source_end_us": int(segment.source_end_us),
                "location_hint": segment.location_hint,
                "interior_exterior": segment.interior_exterior,
                "time_of_day": segment.time_of_day,
                "shot_count": len(scene_shots),
                "shot_ordinals": [int(item.shot_ordinal_snapshot) for item in scene_shots],
                "local_subject_count": len(scene_locals),
                "local_subjects": subject_payloads,
            })

        shot_0001 = next((item for item in shots if int(item.shot_ordinal_snapshot) == 1), None)
        shot_0001_payload: dict[str, Any] | None = None
        if shot_0001 is not None:
            shot_subjects = []
            for presence in presences_by_shot.get(shot_0001.id, []):
                local = local_by_id.get(presence.local_subject_id)
                search_hint = _json_object(presence.search_hint_json)
                shot_subjects.append({
                    "local_subject_id": presence.local_subject_id,
                    "display_label": local.display_label if local is not None else None,
                    "source_vlm_label": str(search_hint.get("source_vlm_label") or "").strip() or None,
                    "activity_summary": presence.activity_summary,
                })
            prop_labels: list[str] = []
            for occurrence in occurrences_by_shot.get(shot_0001.id, []):
                prop = prop_by_id.get(occurrence.prop_hint_id)
                if prop is not None and prop.label_hint not in prop_labels:
                    prop_labels.append(prop.label_hint)
            shot_0001_payload = {
                "shot_revision_item_id": shot_0001.source_shot_revision_item_id,
                "source_start_us": int(shot_0001.source_start_us),
                "source_end_us": int(shot_0001.source_end_us),
                "summary": shot_0001.summary,
                "visual_description": shot_0001.visual_description,
                "subject_count": len(shot_subjects),
                "subjects": shot_subjects,
                "prop_labels": prop_labels,
            }

        statuses = _json_object(run.component_status_json)
        fusion_status = statuses.get("FUSION") if isinstance(statuses.get("FUSION"), Mapping) else {}
        subject_continuity = (
            dict(fusion_status.get("subject_continuity"))
            if isinstance(fusion_status.get("subject_continuity"), Mapping)
            else {}
        )
        scene_04 = next((item for item in scene_payloads if item["ordinal"] == 4), None)
        ocr_texts = [item.content_text for item in events if item.event_type == "OCR"]

        return {
            "schema_version": G1_DIAGNOSTIC_SCHEMA,
            "version": G1_DIAGNOSTIC_VERSION,
            "generated_at": studio_v2.utcnow().isoformat(),
            "run": {
                "run_id": run.id,
                "project_id": run.project_id,
                "episode_id": run.episode_id,
                "status": run.status,
                "pipeline_profile": run.pipeline_profile,
                "source_shot_revision_id": run.source_shot_revision_id,
            },
            "runtime": _runtime_snapshot(run),
            "e4_subject_continuity": subject_continuity,
            "scene_count": len(scene_payloads),
            "scenes": scene_payloads,
            "scene_04_focus": {
                "present": scene_04 is not None,
                "shot_count": scene_04["shot_count"] if scene_04 else None,
                "local_subject_count": scene_04["local_subject_count"] if scene_04 else None,
                "shot_ordinals": scene_04["shot_ordinals"] if scene_04 else [],
            },
            "same_shot_cluster_conflicts": all_conflicts,
            "shot_0001": shot_0001_payload,
            "ocr_record_only": {
                "ocr_event_count": len(ocr_texts),
                "short_text_samples": _short_ocr_noise_samples(ocr_texts),
                "note": "Recorded for later OCR dedupe/noise filtering; do not use this section to block G1 unless it corrupts core visual/scene/subject truth.",
            },
            "acceptance_note": "This snapshot is diagnostic evidence only. G1/P2.6 still requires human review and must not be auto-promoted to PASS from counters alone.",
        }


def default_g1_snapshot_path(snapshot: Mapping[str, Any]) -> Path:
    run = snapshot.get("run") if isinstance(snapshot.get("run"), Mapping) else {}
    project_id = str(run.get("project_id") or "").strip()
    episode_id = str(run.get("episode_id") or "").strip()
    run_id = str(run.get("run_id") or "").strip()
    if not project_id or not episode_id or not run_id:
        raise ValueError("G1 acceptance snapshot 缺少 run metadata")
    return (
        studio_v2.episode_dir(project_id, episode_id)
        / "breakdown"
        / run_id
        / "acceptance"
        / f"g1-real-acceptance-{run_id}.json"
    )


def write_g1_acceptance_snapshot(
    snapshot: Mapping[str, Any],
    *,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(output_path).expanduser() if output_path else default_g1_snapshot_path(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(snapshot), ensure_ascii=False, indent=2, sort_keys=True, default=str)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(serialized, encoding="utf-8")
    os.replace(temp, path)
    return path
