"""Character V9 Phase D -> Final Asset Gate.

Formal rules:
- V9 Character cardinality comes only from V9C confirmed Person Galleries;
- a V9C RESOLVED gallery can materialize even when none of its Track samples has a visible face;
- UNRESOLVED evidence never materializes and remains immutable AI Evidence;
- V9C evidence fails closed unless resolver/provenance and >=3 confirmed Gallery shots are present;
- historical pre-V9 runs keep their historical face-visible safety gate for compatibility.

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

V9_RESOLVER = "person-gallery-anchor-first-v9c"
V9_FINAL_POLICY = "Character V9D: confirmed Person Gallery only; Face optional"


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_v9_profile(profile: str | None) -> bool:
    return str(profile or "").lower().startswith("f05-assets-v9")


def _candidate_is_final_eligible(
    candidate: CharacterCandidate,
    *,
    run_profile: str | None,
    tracks: list[CharacterTrack],
) -> bool:
    """Fail-closed Final Character admission.

    V9 does not require face visibility.  It requires the stronger thing we actually
    want: a confirmed, multi-shot Person Gallery produced by the V9C resolver.
    Historical runs keep the previous face-visible guard instead of being silently
    reinterpreted under V9 rules.
    """

    evidence = _json(candidate.evidence_json)
    if str(evidence.get("identity_status") or "").upper() != "RESOLVED":
        return False
    if evidence.get("final_asset_eligible") is False:
        return False

    candidate_profile = str(evidence.get("profile") or run_profile or "")
    if _is_v9_profile(candidate_profile) or _is_v9_profile(run_profile):
        if str(evidence.get("resolver") or "") != V9_RESOLVER:
            return False
        try:
            confirmed_shots = int(evidence.get("confirmed_gallery_shots") or 0)
            confirmed_images = int(evidence.get("confirmed_gallery_images") or 0)
        except (TypeError, ValueError):
            return False
        return confirmed_shots >= 3 and confirmed_images >= 3

    # Historical compatibility only. V9 formal runs never use Face as the Final gate.
    return any(bool(track.face_visible) for track in tracks)


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
        asset_id = legacy.new_id("CHAR")
        metadata = {
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
            "evidence_cover_urls": [f"/api/content-analysis/characters/{candidate.id}/cover"] if candidate.cover_path else [],
            "confidence": candidate.confidence,
            "identity_status": "RESOLVED",
            "identity_policy": V9_FINAL_POLICY if _is_v9_profile(run.profile_version) else "Historical resolved identity",
            "resolver": evidence.get("resolver"),
            "confirmed_gallery_images": evidence.get("confirmed_gallery_images"),
            "confirmed_gallery_shots": evidence.get("confirmed_gallery_shots"),
            "face_images": evidence.get("face_images"),
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

        # A Character may have multiple Track fragments in one Shot. Final presence is once per Shot.
        bound_shot_ids: set[str] = set()
        for track in members:
            if track.shot_id in bound_shot_ids:
                continue
            bound_shot_ids.add(track.shot_id)
            session.add(
                legacy.ShotCharacterBinding(
                    id=legacy.new_id("SHOTCHAR"),
                    project_id=project_id,
                    shot_id=track.shot_id,
                    character_id=asset_id,
                    source="AUTO",
                    confidence=candidate.confidence,
                    source_run_id=run_id,
                    source_candidate_id=candidate.id,
                )
            )

    # Scene keeps V3 semantics.
    scene_links = list(
        session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)).all()
    )
    links_by_scene: dict[str, list[ShotSceneEvidence]] = {}
    for link in scene_links:
        links_by_scene.setdefault(link.scene_candidate_id, []).append(link)

    scene_candidates = session.scalars(
        select(SceneCandidate)
        .where(SceneCandidate.run_id == run_id)
        .order_by(SceneCandidate.ordinal)
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
        session.add(
            legacy.Scene(
                id=asset_id,
                project_id=project_id,
                name=candidate.auto_label,
                status="AUTO",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
        )
        for link in links:
            session.add(
                legacy.ShotSceneBinding(
                    id=legacy.new_id("SHOTSCENEFINAL"),
                    project_id=project_id,
                    shot_id=link.shot_id,
                    scene_id=asset_id,
                    source="AUTO",
                    confidence=link.confidence,
                    source_run_id=run_id,
                    source_candidate_id=candidate.id,
                )
            )

    # Prop keeps V3 semantics.
    prop_links = list(
        session.scalars(select(ShotPropEvidence).where(ShotPropEvidence.run_id == run_id)).all()
    )
    links_by_prop: dict[str, list[ShotPropEvidence]] = {}
    for link in prop_links:
        links_by_prop.setdefault(link.prop_candidate_id, []).append(link)

    prop_candidates = session.scalars(
        select(PropCandidate)
        .where(PropCandidate.run_id == run_id)
        .order_by(PropCandidate.ordinal)
    ).all()
    for candidate in prop_candidates:
        asset_id = legacy.new_id("PROP")
        metadata = {
            "status": "AUTO",
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "confidence": candidate.confidence,
        }
        session.add(
            legacy.Prop(
                id=asset_id,
                project_id=project_id,
                name=candidate.auto_label,
                is_key_prop=True,
                status="AUTO",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
        )
        for link in links_by_prop.get(candidate.id, []):
            session.add(
                legacy.ShotPropBinding(
                    id=legacy.new_id("SHOTPROPFINAL"),
                    project_id=project_id,
                    shot_id=link.shot_id,
                    prop_id=asset_id,
                    source="AUTO",
                    confidence=link.confidence,
                    source_run_id=run_id,
                    source_candidate_id=candidate.id,
                )
            )

    session.flush()


def apply_analysis_to_assets(project_id: str, run_id: str, *, force: bool = False) -> dict[str, Any]:
    """Materialize a new AUTO Final Asset revision from immutable AI Evidence."""

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
            note="基于最新 AI Evidence 自动形成资产；Character V9D 仅发布 Confirmed Person Gallery，Face 为可选证据",
        )
        session.commit()
        return legacy._serialize_workspace(session, project_id)
