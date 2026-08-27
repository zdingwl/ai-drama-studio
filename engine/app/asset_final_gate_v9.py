"""Character V9/V10 -> Final Asset Gate.

Formal rules:
- Final Character cardinality comes only from confirmed person identity classes;
- a confirmed class can materialize with no visible face;
- UNRESOLVED evidence never materializes and remains immutable AI Evidence;
- V9/V10 evidence fails closed unless resolver/provenance and >=3 supporting shots/images are present;
- historical pre-V9 runs keep their historical face-visible safety gate for compatibility;
- current V10.1 runs consume explicit Shot -> Character presence assignments; historical
  runs without that metadata keep the old Track-derived binding fallback.

Scene / Prop materialization keeps Asset Workspace V3 semantics unchanged.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app import asset_workspace_v3 as legacy
from engine.app.content_analysis_v2 import (
    CharacterCandidate,
    CharacterTrack,
    ContentAnalysisRun,
    PropCandidate,
    SceneCandidate,
    ShotPropEvidence,
    ShotSceneEvidence,
)

FORMAL_RESOLVERS = {
    "person-gallery-anchor-first-v9c",
    "person-gallery-progressive-v9.1",
    "person-evidence-model-classifier-v10",
}
FINAL_POLICY = "Confirmed Person Identity only; Person ReID model classification; Face optional"


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_formal_person_profile(profile: str | None) -> bool:
    value = str(profile or "").lower()
    return value.startswith("f05-assets-v9") or value.startswith("f05-assets-v10")


def _candidate_is_final_eligible(
    candidate: CharacterCandidate,
    *,
    run_profile: str | None,
    tracks: list[CharacterTrack],
) -> bool:
    evidence = _json(candidate.evidence_json)
    if str(evidence.get("identity_status") or "").upper() != "RESOLVED":
        return False
    if evidence.get("final_asset_eligible") is False:
        return False

    candidate_profile = str(evidence.get("profile") or run_profile or "")
    if _is_formal_person_profile(candidate_profile) or _is_formal_person_profile(run_profile):
        if str(evidence.get("resolver") or "") not in FORMAL_RESOLVERS:
            return False
        try:
            confirmed_shots = int(evidence.get("confirmed_gallery_shots") or 0)
            confirmed_images = int(evidence.get("confirmed_gallery_images") or 0)
        except (TypeError, ValueError):
            return False
        return confirmed_shots >= 3 and confirmed_images >= 3

    return any(bool(track.face_visible) for track in tracks)


def _track_identity_recovery(track: CharacterTrack) -> dict[str, Any]:
    """Read validated historical V10.1 Track recovery provenance."""

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
    return result


def _shot_binding_confidence(candidate: CharacterCandidate, tracks: list[CharacterTrack]) -> float | None:
    """Historical Track-derived Shot-presence confidence fallback."""

    recovery_scores: list[float] = []
    has_direct_track = False
    for track in tracks:
        recovery = _track_identity_recovery(track)
        if recovery:
            recovery_scores.append(float(recovery["score"]))
        else:
            has_direct_track = True
    if has_direct_track:
        return candidate.confidence
    if recovery_scores:
        return max(recovery_scores)
    return candidate.confidence


def _explicit_shot_presence_assignments(evidence: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return validated V10.1 explicit Shot assignments, or None for historical runs.

    The presence of ``shot_assignment_version`` is the switch.  Once a Run uses the new
    assignment engine, Final Binding must not silently fall back to candidate Track
    ownership, because that would recreate the original binding-recall defect.
    """

    if not str(evidence.get("shot_assignment_version") or ""):
        return None
    raw = evidence.get("shot_presence_assignments")
    if not isinstance(raw, list):
        return []

    by_shot: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("shot_id") or "")
        if not shot_id:
            continue
        confidence: float | None
        try:
            confidence = float(item.get("confidence")) if item.get("confidence") is not None else None
        except (TypeError, ValueError):
            continue
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            continue
        value = dict(item)
        value["shot_id"] = shot_id
        value["confidence"] = confidence
        previous = by_shot.get(shot_id)
        previous_confidence = float(previous.get("confidence") or 0.0) if previous else -1.0
        current_confidence = float(confidence or 0.0)
        if previous is None or current_confidence > previous_confidence:
            by_shot[shot_id] = value
    return list(by_shot.values())


def _rebuild_from_analysis(session: Any, project_id: str, run_id: str) -> None:
    run = session.get(ContentAnalysisRun, run_id)
    if run is None or run.project_id != project_id:
        raise legacy.AssetWorkspaceError("资产分析 Run 不存在")

    legacy._clear_project_state(session, project_id)

    tracks = list(session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run_id)).all())
    tracks_by_candidate: dict[str, list[CharacterTrack]] = {}
    for track in tracks:
        tracks_by_candidate.setdefault(track.candidate_id, []).append(track)

    candidates = session.scalars(
        select(CharacterCandidate)
        .where(CharacterCandidate.run_id == run_id)
        .order_by(CharacterCandidate.ordinal)
    ).all()
    for candidate in candidates:
        members = tracks_by_candidate.get(candidate.id, [])
        if not _candidate_is_final_eligible(candidate, run_profile=run.profile_version, tracks=members):
            continue

        evidence = _json(candidate.evidence_json)
        explicit_assignments = _explicit_shot_presence_assignments(evidence)
        asset_id = legacy.new_id("CHAR")
        metadata = {
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
            "evidence_cover_urls": [f"/api/content-analysis/characters/{candidate.id}/cover"] if candidate.cover_path else [],
            "confidence": candidate.confidence,
            "identity_status": "RESOLVED",
            "identity_policy": FINAL_POLICY if _is_formal_person_profile(run.profile_version) else "Historical resolved identity",
            "resolver": evidence.get("resolver"),
            "classifier_model": evidence.get("classifier_model"),
            "confirmed_gallery_images": evidence.get("confirmed_gallery_images"),
            "confirmed_gallery_shots": evidence.get("confirmed_gallery_shots"),
            "captured_classified_images": evidence.get("captured_classified_images"),
            "classified_shots": evidence.get("classified_shots"),
            "instance_classes": evidence.get("instance_classes"),
            "face_images": evidence.get("face_images"),
            "shot_assignment_version": evidence.get("shot_assignment_version"),
            "shot_assignment_source": evidence.get("shot_assignment_source"),
            "shot_assignment_policy": evidence.get("shot_assignment_policy"),
            "shot_presence_count": evidence.get("shot_presence_count"),
            "shot_presence_recovered_count": evidence.get("shot_presence_recovered_count"),
            "shot_presence_shot_ids": evidence.get("shot_presence_shot_ids"),
            # Historical provenance remains readable for old Runs.
            "track_recovery_count": evidence.get("track_recovery_count"),
            "track_recovery_shot_ids": evidence.get("track_recovery_shot_ids"),
            "track_recovery_scores": evidence.get("track_recovery_scores"),
            "track_recovery_source": evidence.get("track_recovery_source"),
            "track_recovery_policy": evidence.get("track_recovery_policy"),
        }
        session.add(
            legacy.Character(
                id=asset_id,
                project_id=project_id,
                name=candidate.auto_label,
                status="AUTO",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
        )

        if explicit_assignments is not None:
            # Current V10.1 contract: Final Binding consumes the explicit Shot assignment
            # engine output.  Candidate Track ownership is identity evidence only.
            for assignment in explicit_assignments:
                session.add(
                    legacy.ShotCharacterBinding(
                        id=legacy.new_id("SHOTCHAR"),
                        project_id=project_id,
                        shot_id=str(assignment["shot_id"]),
                        character_id=asset_id,
                        source="AUTO",
                        confidence=assignment.get("confidence"),
                        source_run_id=run_id,
                        source_candidate_id=candidate.id,
                    )
                )
        else:
            # Historical fallback for old persisted V9/V10/V10.1 Runs.
            tracks_by_shot: dict[str, list[CharacterTrack]] = {}
            for track in members:
                tracks_by_shot.setdefault(track.shot_id, []).append(track)
            for shot_id, shot_tracks in tracks_by_shot.items():
                session.add(
                    legacy.ShotCharacterBinding(
                        id=legacy.new_id("SHOTCHAR"),
                        project_id=project_id,
                        shot_id=shot_id,
                        character_id=asset_id,
                        source="AUTO",
                        confidence=_shot_binding_confidence(candidate, shot_tracks),
                        source_run_id=run_id,
                        source_candidate_id=candidate.id,
                    )
                )

    scene_links = list(session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)).all())
    links_by_scene: dict[str, list[ShotSceneEvidence]] = {}
    for link in scene_links:
        links_by_scene.setdefault(link.scene_candidate_id, []).append(link)

    scene_candidates = session.scalars(
        select(SceneCandidate).where(SceneCandidate.run_id == run_id).order_by(SceneCandidate.ordinal)
    ).all()
    for candidate in scene_candidates:
        asset_id = legacy.new_id("SCENE")
        links = links_by_scene.get(candidate.id, [])
        scores = [item.confidence for item in links if item.confidence is not None]
        value = sum(scores) / len(scores) if scores else None
        cover = f"/api/content-analysis/scenes/{candidate.id}/cover" if candidate.cover_path else None
        metadata = {
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "cover_url": cover,
            "evidence_cover_urls": [cover] if cover else [],
            "confidence": value,
        }
        session.add(legacy.Scene(
            id=asset_id,
            project_id=project_id,
            name=candidate.auto_label,
            status="AUTO",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        for link in links:
            session.add(legacy.ShotSceneBinding(
                id=legacy.new_id("SHOTSCENEFINAL"),
                project_id=project_id,
                shot_id=link.shot_id,
                scene_id=asset_id,
                source="AUTO",
                confidence=link.confidence,
                source_run_id=run_id,
                source_candidate_id=candidate.id,
            ))

    prop_links = list(session.scalars(select(ShotPropEvidence).where(ShotPropEvidence.run_id == run_id)).all())
    links_by_prop: dict[str, list[ShotPropEvidence]] = {}
    for link in prop_links:
        links_by_prop.setdefault(link.prop_candidate_id, []).append(link)

    prop_candidates = session.scalars(
        select(PropCandidate).where(PropCandidate.run_id == run_id).order_by(PropCandidate.ordinal)
    ).all()
    for candidate in prop_candidates:
        asset_id = legacy.new_id("PROP")
        metadata = {
            "status": "AUTO",
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "confidence": candidate.confidence,
        }
        session.add(legacy.Prop(
            id=asset_id,
            project_id=project_id,
            name=candidate.auto_label,
            is_key_prop=True,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        for link in links_by_prop.get(candidate.id, []):
            session.add(legacy.ShotPropBinding(
                id=legacy.new_id("SHOTPROPFINAL"),
                project_id=project_id,
                shot_id=link.shot_id,
                prop_id=asset_id,
                source="AUTO",
                confidence=candidate.confidence,
                source_run_id=run_id,
                source_candidate_id=candidate.id,
            ))

    session.flush()


def apply_analysis_to_assets(project_id: str, run_id: str, *, force: bool = False) -> dict[str, Any]:
    with legacy.get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None or run.project_id != project_id:
            raise LookupError("资产分析 Run 不存在")

        current = legacy._current_revision(session, project_id)
        if (
            current is not None
            and current.kind in {"MANUAL", "RESTORE"}
            and current.source_run_id != run_id
            and not force
        ):
            return legacy._serialize_workspace(session, project_id)

        source_revision_id = current.id if current else None
        _rebuild_from_analysis(session, project_id, run_id)
        legacy._create_revision(
            session,
            project_id=project_id,
            kind="AUTO",
            source_run_id=run_id,
            source_revision_id=source_revision_id,
            note="基于最新 AI Evidence 自动形成资产；Character V10.1 使用确认身份 + 独立 Shot Character Assignment，Face 为可选证据",
        )
        session.commit()
        return legacy._serialize_workspace(session, project_id)
