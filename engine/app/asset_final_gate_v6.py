"""Character V6 -> Final Asset Gate。

职责：
- CharacterCandidate / CharacterTrack 始终作为不可变 AI Evidence 读取；
- Final Character 采用严格 allow-list：只有 identity_status == RESOLVED 才能物化；
- UNRESOLVED / 缺失状态 / 非法状态都只保留 Evidence，不进入 Final Character 数量；
- body-only 即使错误标成 RESOLVED，也必须至少存在一条真实 face_visible Track 才能创建 Character；
- 不 monkeypatch legacy materializer，不临时修改 ORM Evidence 字段。

V6 仍复用 Asset Workspace V3 的 Revision / Snapshot / Manual protection contract，
只替换“AI Evidence -> Final Asset”的人物映射门槛。
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


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _candidate_is_final_eligible(candidate: CharacterCandidate) -> bool:
    """V6 Final Character 严格 allow-list。

    不能再采用“不是 UNRESOLVED 就放行”这种 deny-list，因为旧 Run、损坏 Evidence、
    或未来新增中间状态都可能绕过 Final Gate。只有明确 RESOLVED 才允许物化。
    """

    evidence = _json(candidate.evidence_json)
    return str(evidence.get("identity_status") or "").upper() == "RESOLVED"


def _rebuild_from_analysis(session: Any, project_id: str, run_id: str) -> None:
    """把 V6 AI Evidence 映射成新的可编辑 Final Asset 状态。

    注意：这个函数只读 Character Evidence；不会临时改 face_visible，也不会覆盖 Candidate / Track。
    """

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
        if not _candidate_is_final_eligible(candidate):
            continue

        members = tracks_by_candidate.get(candidate.id, [])
        # 第二道安全门：Global Resolver 即使状态写错，纯 body-only 也不能自己创造 Character。
        if not any(bool(track.face_visible) for track in members):
            continue

        asset_id = legacy.new_id("CHAR")
        metadata = {
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
            "evidence_cover_urls": [f"/api/content-analysis/characters/{candidate.id}/cover"] if candidate.cover_path else [],
            "confidence": candidate.confidence,
            "identity_status": "RESOLVED",
            "identity_policy": "Character V6 Global Identity Graph; RESOLVED only",
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

        # Track 是 Evidence 粒度；Final Binding 表达“人物是否出现在 Shot”，同一 Shot 只物化一次。
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

    # Scene / Prop 继续使用 V3 相同语义；V6 只改变人物身份 Gate。
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
    """把 V6 AI Run 应用成新的 AUTO Final Asset Revision。

    保留 V3 的 Manual/Restore 保护：新 AI Run 不会静默覆盖人工版本；只有 force=True 才显式采用。
    """

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
            note="基于最新 AI Evidence 自动形成资产；Character V6 仅发布 RESOLVED Identity",
        )
        session.commit()
        return legacy._serialize_workspace(session, project_id)
