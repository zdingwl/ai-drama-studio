"""Character V10.1 adapter for Asset Workspace shot evidence.

`asset_workspace_v3` still contains historical Character evidence semantics.  Current
V10.1 separates three decisions:

- CharacterTrack = immutable visual/identity evidence;
- CharacterCandidate = project-level identity class;
- explicit Shot Character Assignment = known Character presence in one Shot.

The adapter therefore prefers explicit Shot assignments for RESOLVED Characters, while
keeping UNRESOLVED Track evidence in a separate diagnostics lane.  Historical Runs that
predate explicit assignment continue to use Track-derived presence as a fallback.
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
    """Historical Track-derived confidence fallback for pre-assignment Runs."""

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


def _explicit_assignments(evidence: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    if not str(evidence.get("shot_assignment_version") or ""):
        return None
    raw = evidence.get("shot_presence_assignments")
    if not isinstance(raw, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("shot_id") or "")
        if not shot_id:
            continue
        try:
            confidence = float(item.get("confidence")) if item.get("confidence") is not None else None
        except (TypeError, ValueError):
            continue
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            continue
        value = dict(item)
        value["confidence"] = confidence
        result[shot_id] = value
    return result


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
    """Return workspace payload with V10.1-correct Character presence per Shot."""

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
        assignment_by_shot = _explicit_assignments(candidate_evidence) if identity_status == "RESOLVED" else None
        track_shots = {
            shot_id
            for candidate_id, shot_id in tracks_by_candidate_shot
            if candidate_id == candidate.id
        }
        candidate_shots = sorted(
            set(track_shots) | (set(assignment_by_shot) if assignment_by_shot is not None else set())
        )

        for shot_id in candidate_shots:
            shot_tracks = tracks_by_candidate_shot.get((candidate.id, shot_id), [])
            assignment = assignment_by_shot.get(shot_id) if assignment_by_shot is not None else None
            if assignment is not None:
                confidence = assignment.get("confidence")
                mode = str(assignment.get("mode") or "SHOT_ASSIGNMENT")
                source = str(assignment.get("source") or candidate_evidence.get("shot_assignment_source") or "V10_1_SHOT_CHARACTER_ASSIGNMENT")
                confidence_source = f"{source}:{mode}"
                recovered = mode != "DIRECT_IDENTITY"
            else:
                confidence, confidence_source = _shot_presence_confidence(candidate, shot_tracks)
                recoveries = [value for value in (_track_recovery(track) for track in shot_tracks) if value]
                recovered = bool(recoveries) and len(recoveries) == len(shot_tracks)
                mode = "TRACK_FALLBACK"

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
                "assignment_mode": mode if identity_status == "RESOLVED" else None,
            }
            if identity_status == "RESOLVED":
                # For an explicit-assignment Run, a RESOLVED Track not present in the
                # assignment map must not silently recreate a Shot presence decision.
                if assignment_by_shot is None or assignment is not None:
                    bucket["characters"].append(item)
            else:
                bucket["character_diagnostics"].append(item)

    result["evidence_by_shot"] = evidence_by_shot
    return result


__all__ = ["decorate_asset_workspace_character_evidence"]
