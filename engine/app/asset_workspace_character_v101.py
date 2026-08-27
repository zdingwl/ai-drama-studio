"""Character V10.1 adapter for Asset Workspace shot evidence.

`asset_workspace_v3` still contains a historical face-visible filter in its diagnostic
`evidence_by_shot` serializer. That filter predates the V10/V10.1 contract where Face is
optional and can therefore hide a correctly classified body/side/back/recovered Track
from the Shot review table.

This adapter rebuilds only the Character portion of `evidence_by_shot` from immutable
CharacterCandidate/CharacterTrack evidence. Scene/Prop evidence and all Final Bindings
remain owned by the existing Asset Workspace.

Resolved Character evidence and unresolved diagnostics are intentionally separated:
- `characters`: RESOLVED identity evidence that may map to a Final Character;
- `character_diagnostics`: UNRESOLVED evidence, never treated as a Final binding.

It intentionally does not change DB schema or identity decisions.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun
from engine.app.studio_v2 import get_session



def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _track_recovery(track: CharacterTrack) -> dict[str, Any]:
    value = _json(track.evidence_json).get("identity_recovery")
    if not isinstance(value, dict):
        return {}
    try:
        score = float(value.get("score"))
    except (TypeError, ValueError):
        return {}
    if not 0.0 <= score <= 1.0:
        return {}
    result = dict(value)
    result["score"] = score
    result["source"] = str(value.get("source") or "V10_1_RECOVERED_TRACK")
    return result


def _shot_presence_confidence(candidate: CharacterCandidate, tracks: list[CharacterTrack]) -> tuple[float | None, str]:
    """Separate global identity confidence from recovered Shot-presence confidence.

    Recovery source is read from the exact Track instead of being hard-coded. This keeps
    the Workspace diagnostic truthful for both the original per-Track recovery and the
    newer same-Shot fragmented-presence aggregation.
    """

    recoveries: list[dict[str, Any]] = []
    has_direct_track = False
    for track in tracks:
        recovery = _track_recovery(track)
        if recovery:
            recoveries.append(recovery)
        else:
            has_direct_track = True
    if has_direct_track:
        return candidate.confidence, "IDENTITY_CLASSIFICATION"
    if recoveries:
        strongest = max(recoveries, key=lambda value: float(value["score"]))
        return float(strongest["score"]), str(strongest["source"])
    return candidate.confidence, "IDENTITY_CLASSIFICATION"


def _candidate_to_asset(workspace: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in workspace.get("characters") or []:
        asset_id = str(item.get("id") or "")
        if not asset_id:
            continue
        for candidate_id in item.get("source_candidate_ids") or []:
            result[str(candidate_id)] = asset_id
    return result


def _empty_bucket(*, scene: Any = None, props: list[Any] | None = None) -> dict[str, Any]:
    return {
        "characters": [],
        "character_diagnostics": [],
        "scene": scene,
        "props": list(props or []),
    }


def decorate_asset_workspace_character_evidence(workspace: dict[str, Any]) -> dict[str, Any]:
    """Return workspace payload with V10.1-correct Character evidence per Shot.

    RESOLVED Track evidence is visible even when `face_visible=False`. UNRESOLVED evidence
    is moved to `character_diagnostics`, so it cannot appear as a final Character suggestion,
    create an unbound/conflict state, or pollute Final Shot confidence.
    """

    analysis = workspace.get("analysis") or {}
    run_id = str(analysis.get("id") or "")
    project_id = str(workspace.get("project_id") or "")
    if not run_id or not project_id:
        return workspace

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None or run.project_id != project_id:
            return workspace
        candidates = list(session.scalars(
            select(CharacterCandidate)
            .where(CharacterCandidate.run_id == run_id)
            .order_by(CharacterCandidate.ordinal)
        ).all())
        tracks = list(session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run_id)).all())

    candidate_to_asset = _candidate_to_asset(workspace)
    tracks_by_candidate_shot: dict[tuple[str, str], list[CharacterTrack]] = {}
    for track in tracks:
        tracks_by_candidate_shot.setdefault((track.candidate_id, track.shot_id), []).append(track)

    result = dict(workspace)
    evidence_by_shot: dict[str, dict[str, Any]] = {}
    for shot_id, raw_bucket in (workspace.get("evidence_by_shot") or {}).items():
        bucket = dict(raw_bucket or {})
        evidence_by_shot[str(shot_id)] = _empty_bucket(
            scene=bucket.get("scene"),
            props=list(bucket.get("props") or []),
        )

    for candidate in candidates:
        candidate_evidence = _json(candidate.evidence_json)
        identity_status = str(candidate_evidence.get("identity_status") or "UNRESOLVED").upper()
        final_asset_id = candidate_to_asset.get(candidate.id) if identity_status == "RESOLVED" else None
        candidate_shots = sorted({
            shot_id
            for candidate_id, shot_id in tracks_by_candidate_shot
            if candidate_id == candidate.id
        })
        for shot_id in candidate_shots:
            shot_tracks = tracks_by_candidate_shot[(candidate.id, shot_id)]
            confidence, confidence_source = _shot_presence_confidence(candidate, shot_tracks)
            recoveries = [value for value in (_track_recovery(track) for track in shot_tracks) if value]
            recovered = bool(recoveries) and len(recoveries) == len(shot_tracks)
            bucket = evidence_by_shot.setdefault(shot_id, _empty_bucket())
            item = {
                "candidate_id": candidate.id,
                "label": candidate.auto_label,
                "confidence": confidence if identity_status == "RESOLVED" else None,
                "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
                "final_asset_id": final_asset_id,
                "identity_status": identity_status,
                "face_required": False,
                "recovered_track": recovered,
                "confidence_source": confidence_source if identity_status == "RESOLVED" else "UNRESOLVED_DIAGNOSTIC",
                "recovery_source": confidence_source if recovered else None,
            }
            if identity_status == "RESOLVED":
                bucket["characters"].append(item)
            else:
                bucket["character_diagnostics"].append(item)

    result["evidence_by_shot"] = evidence_by_shot
    return result


__all__ = ["decorate_asset_workspace_character_evidence"]
