"""Character V10.1 adapter for Asset Workspace shot evidence.

`asset_workspace_v3` still contains historical Character evidence semantics. Current
V10.1 separates three decisions:

- CharacterTrack = immutable visual/identity evidence;
- CharacterCandidate = project-level identity class;
- explicit Shot Character Assignment = known Character presence in one Shot.

The adapter therefore prefers explicit Shot assignments for RESOLVED Characters, while
keeping UNRESOLVED Track evidence in a separate diagnostics lane. Historical Runs that
predate explicit assignment continue to use Track-derived presence as a fallback.

Final Asset / Shot Binding consistency is also repaired here before the payload reaches
the frontend. The database `ShotCharacterBinding` rows are the canonical Final truth;
`characters[].shot_ids` and `bindings_by_shot[*].character_ids` must always be two views
of those same rows. This prevents the Asset Library from saying a Character is bound to
a Shot while the Shot matrix renders the Character column as empty.

Character coverage is a separate business invariant: if Breakdown understood N people
in a Shot, or V10.1 currently sees N distinct person candidates, the Shot cannot be
reported as automatically consistent until at least N distinct Final Characters are
bound and no unresolved person evidence remains. This keeps anonymous Breakdown people
separate from Character identity while still preventing missing people from disappearing
silently from the review queue.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app.asset_workspace_v3 import ShotCharacterBinding
from engine.app.breakdown_models_v1 import BreakdownRun, ShotLocalSubject, ShotSemanticDraft
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


def _current_breakdown_people_by_shot(session: Any, project_id: str) -> dict[str, set[str]]:
    """Return anonymous people understood by the current READY Breakdown, per Shot.

    LocalSubject is intentionally not treated as Character identity. We use only the
    cardinality/presence signal here: if the semantic pass says two people are visible,
    one Final Character binding is not enough to mark the Shot complete.
    """

    rows = session.execute(
        select(
            ShotSemanticDraft.source_shot_id_snapshot,
            ShotLocalSubject.local_subject_id,
        )
        .join(ShotLocalSubject, ShotLocalSubject.shot_draft_id == ShotSemanticDraft.id)
        .join(BreakdownRun, BreakdownRun.id == ShotSemanticDraft.run_id)
        .where(
            BreakdownRun.project_id == project_id,
            BreakdownRun.is_current.is_(True),
            BreakdownRun.status.in_(("READY", "READY_WITH_WARNINGS")),
        )
    ).all()
    result: dict[str, set[str]] = {}
    for shot_id, local_subject_id in rows:
        normalized_shot_id = str(shot_id or "")
        normalized_subject_id = str(local_subject_id or "")
        if not normalized_shot_id or not normalized_subject_id:
            continue
        result.setdefault(normalized_shot_id, set()).add(normalized_subject_id)
    return result


def _build_character_coverage(
    *,
    breakdown_person_count: int,
    visual_candidate_count: int,
    bound_person_count: int,
    unresolved_person_count: int,
) -> dict[str, Any]:
    """Build the Shot-level character completeness contract used by UI and ReviewIssue."""

    breakdown_count = max(0, int(breakdown_person_count))
    visual_count = max(0, int(visual_candidate_count))
    bound_count = max(0, int(bound_person_count))
    unresolved_count = max(0, int(unresolved_person_count))
    detected_count = max(breakdown_count, visual_count)
    missing_count = max(0, detected_count - bound_count, unresolved_count)

    if detected_count == 0:
        complete = unresolved_count == 0
        reason = "NONE" if complete else "UNRESOLVED_PERSON"
    elif unresolved_count > 0:
        complete = False
        reason = "UNRESOLVED_PERSON"
    elif bound_count == 0:
        complete = False
        reason = "NO_BINDING"
    elif bound_count < detected_count:
        complete = False
        reason = "PARTIAL_BINDING"
    else:
        complete = True
        reason = "COMPLETE"

    return {
        "breakdown_person_count": breakdown_count,
        "visual_candidate_count": visual_count,
        "detected_person_count": detected_count,
        "bound_person_count": bound_count,
        "unresolved_person_count": unresolved_count,
        "missing_person_count": missing_count,
        "complete": complete,
        "reason": reason,
    }


def _sync_final_character_bindings(
    workspace: dict[str, Any],
    bindings: list[ShotCharacterBinding],
) -> dict[str, Any]:
    """Make every Final Character Shot view follow current DB bindings exactly.

    `asset_workspace_v3` normally serializes both views from the same snapshot, but the
    UI must never be allowed to render contradictory Final truth even if a stale payload
    or a later adapter leaves them out of sync. Scene/Prop binding fields are preserved;
    only Character Final bindings are rebuilt from the canonical DB table.
    """

    result = dict(workspace)
    by_shot: dict[str, dict[str, Any]] = {}
    for shot_id, raw in (workspace.get("bindings_by_shot") or {}).items():
        bucket = dict(raw or {})
        by_shot[str(shot_id)] = {
            "character_ids": [],
            "scene_id": bucket.get("scene_id"),
            "prop_ids": list(bucket.get("prop_ids") or []),
        }

    shots_by_character: dict[str, set[str]] = {}
    for binding in bindings:
        shot_id = str(binding.shot_id)
        character_id = str(binding.character_id)
        if not shot_id or not character_id:
            continue
        bucket = by_shot.setdefault(shot_id, {"character_ids": [], "scene_id": None, "prop_ids": []})
        if character_id not in bucket["character_ids"]:
            bucket["character_ids"].append(character_id)
        shots_by_character.setdefault(character_id, set()).add(shot_id)

    characters: list[dict[str, Any]] = []
    for raw in workspace.get("characters") or []:
        item = dict(raw or {})
        character_id = str(item.get("id") or "")
        shot_ids = sorted(shots_by_character.get(character_id, set()))
        item["shot_ids"] = shot_ids
        item["shot_count"] = len(shot_ids)
        characters.append(item)

    for bucket in by_shot.values():
        bucket["character_ids"] = sorted(set(str(value) for value in bucket["character_ids"] if value))

    result["characters"] = characters
    result["bindings_by_shot"] = by_shot
    return result


def decorate_asset_workspace_character_evidence(workspace: dict[str, Any]) -> dict[str, Any]:
    """Return workspace payload with V10.1-correct Character presence and coverage per Shot."""

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
        final_bindings = list(session.scalars(
            select(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id)
        ).all())
        breakdown_people_by_shot = _current_breakdown_people_by_shot(session, project_id)

    result = _sync_final_character_bindings(workspace, final_bindings)
    candidate_to_asset = _candidate_to_asset(result)
    tracks_by_candidate_shot: dict[tuple[str, str], list[CharacterTrack]] = {}
    for track in tracks:
        tracks_by_candidate_shot.setdefault((track.candidate_id, track.shot_id), []).append(track)

    evidence_by_shot: dict[str, dict[str, Any]] = {}
    for shot_id, raw_bucket in (result.get("evidence_by_shot") or {}).items():
        bucket = dict(raw_bucket or {})
        evidence_by_shot[str(shot_id)] = _empty_bucket(
            scene=bucket.get("scene"),
            props=list(bucket.get("props") or []),
        )

    visual_candidates_by_shot: dict[str, set[str]] = {}
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
                source = str(
                    assignment.get("source")
                    or candidate_evidence.get("shot_assignment_source")
                    or "V10_1_SHOT_CHARACTER_ASSIGNMENT"
                )
                confidence_source = f"{source}:{mode}"
                recovered = mode != "DIRECT_IDENTITY"
            else:
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
                # For an explicit-assignment Run, a RESOLVED Track not present in the
                # assignment map must not silently recreate a Shot presence decision.
                if assignment_by_shot is None or assignment is not None:
                    bucket["characters"].append(item)
                    visual_candidates_by_shot.setdefault(shot_id, set()).add(candidate.id)
            else:
                bucket["character_diagnostics"].append(item)
                visual_candidates_by_shot.setdefault(shot_id, set()).add(candidate.id)

    valid_character_ids = {
        str(item.get("id"))
        for item in (result.get("characters") or [])
        if str(item.get("id") or "")
    }
    all_shot_ids = (
        set(evidence_by_shot)
        | set(result.get("bindings_by_shot") or {})
        | set(breakdown_people_by_shot)
        | set(visual_candidates_by_shot)
    )
    for shot_id in all_shot_ids:
        bucket = evidence_by_shot.setdefault(shot_id, _empty_bucket())
        binding = (result.get("bindings_by_shot") or {}).get(shot_id) or {}
        bound_ids = {
            str(value)
            for value in (binding.get("character_ids") or [])
            if str(value or "") in valid_character_ids
        }
        unresolved_ids = {
            str(item.get("candidate_id"))
            for item in (bucket.get("character_diagnostics") or [])
            if isinstance(item, dict) and str(item.get("candidate_id") or "")
        }
        bucket["character_coverage"] = _build_character_coverage(
            breakdown_person_count=len(breakdown_people_by_shot.get(shot_id, set())),
            visual_candidate_count=len(visual_candidates_by_shot.get(shot_id, set())),
            bound_person_count=len(bound_ids),
            unresolved_person_count=len(unresolved_ids),
        )

    result["evidence_by_shot"] = evidence_by_shot
    return result


__all__ = [
    "decorate_asset_workspace_character_evidence",
    "_build_character_coverage",
    "_sync_final_character_bindings",
]
