"""03「资产」最终工作层：Project Asset + Shot Binding + Revision。

职责边界：
- CharacterCandidate / SceneCandidate / PropCandidate / Track 是不可变 AI Evidence；
- Character / Scene / Prop 是 Project 级 Final Asset；
- ShotCharacterBinding / ShotSceneBinding / ShotPropBinding 是可人工修改的 Final Binding；
- 每个业务写操作都在同一个数据库事务中执行“修改 → flush → 完整快照 → Revision → commit”；
- 新 AI Run 不静默覆盖 MANUAL/RESTORE，旧人工版本只会变 STALE，用户可显式采用新 Evidence。
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Literal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.content_analysis_v2 import (
    CharacterCandidate,
    CharacterTrack,
    ContentAnalysisRun,
    PropCandidate,
    SceneCandidate,
    ShotPropEvidence,
    ShotSceneEvidence,
)
from engine.app.studio_v2 import Base, Character, Episode, Prop, Scene, Shot, get_session, new_id, utcnow

AssetType = Literal["character", "scene", "prop"]


class AssetWorkspaceError(RuntimeError):
    """资产工作台业务错误。"""


class AssetRevision(Base):
    __tablename__ = "v2_asset_revisions"
    __table_args__ = (UniqueConstraint("project_id", "revision", name="uq_v2_asset_revision_project_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ShotCharacterBinding(Base):
    __tablename__ = "v2_shot_character_bindings"
    __table_args__ = (UniqueConstraint("shot_id", "character_id", name="uq_v2_shot_character_binding"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("v2_characters.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTO")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ShotSceneBinding(Base):
    __tablename__ = "v2_shot_scene_bindings"
    __table_args__ = (UniqueConstraint("shot_id", name="uq_v2_shot_scene_binding"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("v2_scenes.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTO")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ShotPropBinding(Base):
    __tablename__ = "v2_shot_prop_bindings"
    __table_args__ = (UniqueConstraint("shot_id", "prop_id", name="uq_v2_shot_prop_binding"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    prop_id: Mapped[str] = mapped_column(ForeignKey("v2_props.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTO")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _asset_table(entity_type: AssetType):
    return {"character": Character, "scene": Scene, "prop": Prop}[entity_type]


def _current_analysis(session: Any, project_id: str) -> ContentAnalysisRun | None:
    return session.scalar(select(ContentAnalysisRun).where(
        ContentAnalysisRun.project_id == project_id,
        ContentAnalysisRun.is_current.is_(True),
    ).order_by(ContentAnalysisRun.completed_at.desc()))


def _current_revision(session: Any, project_id: str) -> AssetRevision | None:
    return session.scalar(select(AssetRevision).where(
        AssetRevision.project_id == project_id,
        AssetRevision.is_current.is_(True),
    ))


def _next_revision(session: Any, project_id: str) -> int:
    latest = session.scalar(select(func.max(AssetRevision.revision)).where(AssetRevision.project_id == project_id))
    return int(latest or 0) + 1


def _serialize_entity(entity_type: AssetType, item: Any, shot_ids: list[str]) -> dict[str, Any]:
    metadata = _json(item.metadata_json)
    status = item.status if entity_type in {"character", "scene"} else metadata.get("status", "AUTO")
    return {
        "id": item.id,
        "type": entity_type,
        "name": item.name,
        "status": status,
        "is_key_prop": bool(item.is_key_prop) if entity_type == "prop" else None,
        "cover_url": metadata.get("cover_url"),
        "source_candidate_ids": metadata.get("source_candidate_ids") or [],
        "confidence": metadata.get("confidence"),
        "shot_ids": sorted(set(shot_ids)),
        "shot_count": len(set(shot_ids)),
        "metadata": metadata,
    }


def _snapshot(session: Any, project_id: str) -> dict[str, Any]:
    """读取当前 Final Asset 完整状态；调用前必须 flush。"""

    char_bindings = list(session.scalars(select(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id)).all())
    scene_bindings = list(session.scalars(select(ShotSceneBinding).where(ShotSceneBinding.project_id == project_id)).all())
    prop_bindings = list(session.scalars(select(ShotPropBinding).where(ShotPropBinding.project_id == project_id)).all())
    char_shots: dict[str, list[str]] = {}
    scene_shots: dict[str, list[str]] = {}
    prop_shots: dict[str, list[str]] = {}
    for item in char_bindings:
        char_shots.setdefault(item.character_id, []).append(item.shot_id)
    for item in scene_bindings:
        scene_shots.setdefault(item.scene_id, []).append(item.shot_id)
    for item in prop_bindings:
        prop_shots.setdefault(item.prop_id, []).append(item.shot_id)

    characters = list(session.scalars(select(Character).where(Character.project_id == project_id).order_by(Character.name)).all())
    scenes = list(session.scalars(select(Scene).where(Scene.project_id == project_id).order_by(Scene.name)).all())
    props = list(session.scalars(select(Prop).where(Prop.project_id == project_id).order_by(Prop.name)).all())
    return {
        "characters": [_serialize_entity("character", item, char_shots.get(item.id, [])) for item in characters],
        "scenes": [_serialize_entity("scene", item, scene_shots.get(item.id, [])) for item in scenes],
        "props": [_serialize_entity("prop", item, prop_shots.get(item.id, [])) for item in props],
        "bindings": {
            "characters": [
                {"shot_id": item.shot_id, "entity_id": item.character_id, "source": item.source, "confidence": item.confidence, "source_run_id": item.source_run_id, "source_candidate_id": item.source_candidate_id}
                for item in char_bindings
            ],
            "scenes": [
                {"shot_id": item.shot_id, "entity_id": item.scene_id, "source": item.source, "confidence": item.confidence, "source_run_id": item.source_run_id, "source_candidate_id": item.source_candidate_id}
                for item in scene_bindings
            ],
            "props": [
                {"shot_id": item.shot_id, "entity_id": item.prop_id, "source": item.source, "confidence": item.confidence, "source_run_id": item.source_run_id, "source_candidate_id": item.source_candidate_id}
                for item in prop_bindings
            ],
        },
    }


def _create_revision(
    session: Any,
    *,
    project_id: str,
    kind: str,
    note: str,
    source_run_id: str | None,
    source_revision_id: str | None = None,
) -> AssetRevision:
    """把“本事务刚修改后的状态”保存成不可变 Revision。

    为什么这里必须主动 flush：V2 Session 使用 autoflush=False；如果不 flush，刚新增的 Binding / Asset
    不会进入 snapshot，历史版本会比实际业务状态慢一拍。
    """

    session.flush()
    snapshot = _snapshot(session, project_id)
    for previous in session.scalars(select(AssetRevision).where(
        AssetRevision.project_id == project_id,
        AssetRevision.is_current.is_(True),
    )).all():
        previous.is_current = False
    revision = AssetRevision(
        id=new_id("ASSETREV"),
        project_id=project_id,
        revision=_next_revision(session, project_id),
        kind=kind,
        is_current=True,
        source_run_id=source_run_id,
        source_revision_id=source_revision_id,
        note=note,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
    )
    session.add(revision)
    session.flush()
    return revision


def _clear_project_state(session: Any, project_id: str) -> None:
    session.execute(delete(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id))
    session.execute(delete(ShotSceneBinding).where(ShotSceneBinding.project_id == project_id))
    session.execute(delete(ShotPropBinding).where(ShotPropBinding.project_id == project_id))
    session.execute(delete(Character).where(Character.project_id == project_id))
    session.execute(delete(Scene).where(Scene.project_id == project_id))
    session.execute(delete(Prop).where(Prop.project_id == project_id))
    session.flush()


def _replace_from_snapshot(session: Any, project_id: str, snapshot: dict[str, Any]) -> None:
    _clear_project_state(session, project_id)
    for item in snapshot.get("characters") or []:
        session.add(Character(
            id=item["id"], project_id=project_id, name=item["name"], status=item.get("status") or "MANUAL",
            metadata_json=json.dumps(item.get("metadata") or {}, ensure_ascii=False),
        ))
    for item in snapshot.get("scenes") or []:
        session.add(Scene(
            id=item["id"], project_id=project_id, name=item["name"], status=item.get("status") or "MANUAL",
            metadata_json=json.dumps(item.get("metadata") or {}, ensure_ascii=False),
        ))
    for item in snapshot.get("props") or []:
        metadata = dict(item.get("metadata") or {})
        metadata.setdefault("status", item.get("status") or "MANUAL")
        session.add(Prop(
            id=item["id"], project_id=project_id, name=item["name"], is_key_prop=bool(item.get("is_key_prop", True)),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
    session.flush()
    bindings = snapshot.get("bindings") or {}
    for item in bindings.get("characters") or []:
        session.add(ShotCharacterBinding(
            id=new_id("SHOTCHAR"), project_id=project_id, shot_id=item["shot_id"], character_id=item["entity_id"],
            source=item.get("source") or "MANUAL", confidence=item.get("confidence"),
            source_run_id=item.get("source_run_id"), source_candidate_id=item.get("source_candidate_id"),
        ))
    for item in bindings.get("scenes") or []:
        session.add(ShotSceneBinding(
            id=new_id("SHOTSCENEFINAL"), project_id=project_id, shot_id=item["shot_id"], scene_id=item["entity_id"],
            source=item.get("source") or "MANUAL", confidence=item.get("confidence"),
            source_run_id=item.get("source_run_id"), source_candidate_id=item.get("source_candidate_id"),
        ))
    for item in bindings.get("props") or []:
        session.add(ShotPropBinding(
            id=new_id("SHOTPROPFINAL"), project_id=project_id, shot_id=item["shot_id"], prop_id=item["entity_id"],
            source=item.get("source") or "MANUAL", confidence=item.get("confidence"),
            source_run_id=item.get("source_run_id"), source_candidate_id=item.get("source_candidate_id"),
        ))
    session.flush()


def _rebuild_from_analysis(session: Any, project_id: str, run_id: str) -> None:
    """把不可变 AI Evidence 映射成新的可编辑 Final Asset 状态。"""

    run = session.get(ContentAnalysisRun, run_id)
    if run is None or run.project_id != project_id:
        raise AssetWorkspaceError("资产分析 Run 不存在")
    _clear_project_state(session, project_id)

    tracks = list(session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run_id)).all())
    tracks_by_candidate: dict[str, list[CharacterTrack]] = {}
    for track in tracks:
        tracks_by_candidate.setdefault(track.candidate_id, []).append(track)
    for candidate in session.scalars(select(CharacterCandidate).where(CharacterCandidate.run_id == run_id).order_by(CharacterCandidate.ordinal)).all():
        members = tracks_by_candidate.get(candidate.id, [])
        # 最终人物身份必须至少有 Face/SFace 锚点；body-only 不升级为 Character。
        if not any(track.face_visible for track in members):
            continue
        asset_id = new_id("CHAR")
        metadata = {
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
            "evidence_cover_urls": [f"/api/content-analysis/characters/{candidate.id}/cover"] if candidate.cover_path else [],
            "confidence": candidate.confidence,
            "identity_policy": "Face/SFace anchor + body/clothing auxiliary",
        }
        session.add(Character(id=asset_id, project_id=project_id, name=candidate.auto_label, status="AUTO", metadata_json=json.dumps(metadata, ensure_ascii=False)))

        # V5 的 Track 是 Evidence 粒度：同一人物在一个 Shot 内可能因遮挡/断轨产生多条 Track。
        # Final ShotCharacterBinding 表达的是“这个 Character 是否出现在该 Shot”，因此同一 Shot 只能物化一次。
        bound_shot_ids: set[str] = set()
        for track in members:
            if track.shot_id in bound_shot_ids:
                continue
            bound_shot_ids.add(track.shot_id)
            session.add(ShotCharacterBinding(
                id=new_id("SHOTCHAR"), project_id=project_id, shot_id=track.shot_id, character_id=asset_id,
                source="AUTO", confidence=candidate.confidence, source_run_id=run_id, source_candidate_id=candidate.id,
            ))

    scene_links = list(session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)).all())
    links_by_scene: dict[str, list[ShotSceneEvidence]] = {}
    for link in scene_links:
        links_by_scene.setdefault(link.scene_candidate_id, []).append(link)
    for candidate in session.scalars(select(SceneCandidate).where(SceneCandidate.run_id == run_id).order_by(SceneCandidate.ordinal)).all():
        asset_id = new_id("SCENE")
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
        session.add(Scene(id=asset_id, project_id=project_id, name=candidate.auto_label, status="AUTO", metadata_json=json.dumps(metadata, ensure_ascii=False)))
        for link in links:
            session.add(ShotSceneBinding(
                id=new_id("SHOTSCENEFINAL"), project_id=project_id, shot_id=link.shot_id, scene_id=asset_id,
                source="AUTO", confidence=link.confidence, source_run_id=run_id, source_candidate_id=candidate.id,
            ))

    prop_links = list(session.scalars(select(ShotPropEvidence).where(ShotPropEvidence.run_id == run_id)).all())
    links_by_prop: dict[str, list[ShotPropEvidence]] = {}
    for link in prop_links:
        links_by_prop.setdefault(link.prop_candidate_id, []).append(link)
    for candidate in session.scalars(select(PropCandidate).where(PropCandidate.run_id == run_id).order_by(PropCandidate.ordinal)).all():
        asset_id = new_id("PROP")
        metadata = {
            "status": "AUTO",
            "source_run_id": run_id,
            "source_candidate_ids": [candidate.id],
            "confidence": candidate.confidence,
        }
        session.add(Prop(id=asset_id, project_id=project_id, name=candidate.auto_label, is_key_prop=True, metadata_json=json.dumps(metadata, ensure_ascii=False)))
        for link in links_by_prop.get(candidate.id, []):
            session.add(ShotPropBinding(
                id=new_id("SHOTPROPFINAL"), project_id=project_id, shot_id=link.shot_id, prop_id=asset_id,
                source="AUTO", confidence=link.confidence, source_run_id=run_id, source_candidate_id=candidate.id,
            ))
    session.flush()


def apply_analysis_to_assets(project_id: str, run_id: str, *, force: bool = False) -> dict[str, Any]:
    """把 AI Run 应用成新的 AUTO Final Asset Revision。

    MANUAL/RESTORE 默认受保护；只有用户显式 force=True 才允许基于新 Evidence 建新版本。
    """

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None or run.project_id != project_id:
            raise LookupError("资产分析 Run 不存在")
        current = _current_revision(session, project_id)
        if current is not None and current.kind in {"MANUAL", "RESTORE"} and current.source_run_id != run_id and not force:
            return _serialize_workspace(session, project_id)
        source_revision_id = current.id if current else None
        _rebuild_from_analysis(session, project_id, run_id)
        _create_revision(
            session,
            project_id=project_id,
            kind="AUTO",
            source_run_id=run_id,
            source_revision_id=source_revision_id,
            note="基于最新 AI Evidence 自动形成资产",
        )
        session.commit()
        return _serialize_workspace(session, project_id)


def _validate_shot(session: Any, project_id: str, shot_id: str) -> Shot:
    shot = session.get(Shot, shot_id)
    if shot is None:
        raise AssetWorkspaceError("Shot 不存在")
    episode = session.get(Episode, shot.episode_id)
    if episode is None or episode.project_id != project_id:
        raise AssetWorkspaceError("Shot 不属于当前项目")
    return shot


def _validate_ids(session: Any, project_id: str, entity_type: AssetType, ids: list[str]) -> list[str]:
    clean = list(dict.fromkeys(ids))
    if not clean:
        return []
    table = _asset_table(entity_type)
    found = list(session.scalars(select(table.id).where(table.project_id == project_id, table.id.in_(clean))).all())
    if set(found) != set(clean):
        raise AssetWorkspaceError(f"存在不属于当前项目的{entity_type}资产")
    return clean


def _manual_revision(session: Any, project_id: str, note: str) -> None:
    run = _current_analysis(session, project_id)
    _create_revision(session, project_id=project_id, kind="MANUAL", source_run_id=run.id if run else None, note=note)


def set_shot_bindings(
    project_id: str,
    shot_id: str,
    *,
    character_ids: list[str],
    scene_id: str | None,
    prop_ids: list[str],
) -> dict[str, Any]:
    """一次原子保存当前 Shot 的人物、场景、道具 Final Binding。"""

    with get_session() as session:
        shot = _validate_shot(session, project_id, shot_id)
        character_ids = _validate_ids(session, project_id, "character", character_ids)
        prop_ids = _validate_ids(session, project_id, "prop", prop_ids)
        if scene_id:
            _validate_ids(session, project_id, "scene", [scene_id])
        session.execute(delete(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id, ShotCharacterBinding.shot_id == shot_id))
        session.execute(delete(ShotSceneBinding).where(ShotSceneBinding.project_id == project_id, ShotSceneBinding.shot_id == shot_id))
        session.execute(delete(ShotPropBinding).where(ShotPropBinding.project_id == project_id, ShotPropBinding.shot_id == shot_id))
        for asset_id in character_ids:
            session.add(ShotCharacterBinding(id=new_id("SHOTCHAR"), project_id=project_id, shot_id=shot_id, character_id=asset_id, source="MANUAL"))
        if scene_id:
            session.add(ShotSceneBinding(id=new_id("SHOTSCENEFINAL"), project_id=project_id, shot_id=shot_id, scene_id=scene_id, source="MANUAL"))
        for asset_id in prop_ids:
            session.add(ShotPropBinding(id=new_id("SHOTPROPFINAL"), project_id=project_id, shot_id=shot_id, prop_id=asset_id, source="MANUAL"))
        _manual_revision(session, project_id, f"修改 Shot {shot.ordinal:04d} 资产绑定")
        session.commit()
        return _serialize_workspace(session, project_id)


def create_asset(project_id: str, entity_type: AssetType, name: str, *, shot_id: str | None = None) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise AssetWorkspaceError("资产名称不能为空")
    with get_session() as session:
        if shot_id:
            _validate_shot(session, project_id, shot_id)
        if entity_type == "character":
            item = Character(id=new_id("CHAR"), project_id=project_id, name=name, status="MANUAL", metadata_json="{}")
        elif entity_type == "scene":
            item = Scene(id=new_id("SCENE"), project_id=project_id, name=name, status="MANUAL", metadata_json="{}")
        else:
            item = Prop(id=new_id("PROP"), project_id=project_id, name=name, is_key_prop=True, metadata_json=json.dumps({"status": "MANUAL"}, ensure_ascii=False))
        session.add(item)
        session.flush()
        if shot_id:
            if entity_type == "character":
                session.add(ShotCharacterBinding(id=new_id("SHOTCHAR"), project_id=project_id, shot_id=shot_id, character_id=item.id, source="MANUAL"))
            elif entity_type == "scene":
                session.execute(delete(ShotSceneBinding).where(ShotSceneBinding.project_id == project_id, ShotSceneBinding.shot_id == shot_id))
                session.add(ShotSceneBinding(id=new_id("SHOTSCENEFINAL"), project_id=project_id, shot_id=shot_id, scene_id=item.id, source="MANUAL"))
            else:
                session.add(ShotPropBinding(id=new_id("SHOTPROPFINAL"), project_id=project_id, shot_id=shot_id, prop_id=item.id, source="MANUAL"))
        _manual_revision(session, project_id, f"新建{entity_type}资产：{name}")
        session.commit()
        return _serialize_workspace(session, project_id)


def rename_asset(project_id: str, entity_type: AssetType, entity_id: str, name: str) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise AssetWorkspaceError("资产名称不能为空")
    with get_session() as session:
        table = _asset_table(entity_type)
        item = session.get(table, entity_id)
        if item is None or item.project_id != project_id:
            raise AssetWorkspaceError("资产不存在")
        item.name = name
        if entity_type in {"character", "scene"}:
            item.status = "MANUAL"
        else:
            metadata = _json(item.metadata_json)
            metadata["status"] = "MANUAL"
            item.metadata_json = json.dumps(metadata, ensure_ascii=False)
        _manual_revision(session, project_id, f"重命名{entity_type}资产：{name}")
        session.commit()
        return _serialize_workspace(session, project_id)


def delete_asset(project_id: str, entity_type: AssetType, entity_id: str) -> dict[str, Any]:
    with get_session() as session:
        table = _asset_table(entity_type)
        item = session.get(table, entity_id)
        if item is None or item.project_id != project_id:
            raise AssetWorkspaceError("资产不存在")
        if entity_type == "character":
            session.execute(delete(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id, ShotCharacterBinding.character_id == entity_id))
        elif entity_type == "scene":
            session.execute(delete(ShotSceneBinding).where(ShotSceneBinding.project_id == project_id, ShotSceneBinding.scene_id == entity_id))
        else:
            session.execute(delete(ShotPropBinding).where(ShotPropBinding.project_id == project_id, ShotPropBinding.prop_id == entity_id))
        session.delete(item)
        _manual_revision(session, project_id, f"删除{entity_type}资产")
        session.commit()
        return _serialize_workspace(session, project_id)


def _merge_metadata(target: Any, sources: list[Any]) -> None:
    metadata = _json(target.metadata_json)
    person_mappings = list(metadata.get("source_person_mappings_v1") or [])
    candidate_ids = list(metadata.get("source_candidate_ids") or [])
    covers = list(metadata.get("evidence_cover_urls") or [])
    if metadata.get("cover_url"):
        covers.append(str(metadata["cover_url"]))
    confidences: list[float] = []
    if metadata.get("confidence") is not None:
        confidences.append(float(metadata["confidence"]))
    for source in sources:
        other = _json(source.metadata_json)
        person_mappings.extend(other.get("source_person_mappings_v1") or [])
        candidate_ids.extend(other.get("source_candidate_ids") or [])
        covers.extend(other.get("evidence_cover_urls") or [])
        if other.get("cover_url"):
            covers.append(str(other["cover_url"]))
        if other.get("confidence") is not None:
            confidences.append(float(other["confidence"]))
    metadata["source_person_mappings_v1"] = list({(m.get("key"), m.get("anchor")): m for m in person_mappings}.values())
    metadata["source_candidate_ids"] = list(dict.fromkeys(candidate_ids))
    metadata["evidence_cover_urls"] = list(dict.fromkeys(covers))
    if covers:
        metadata.setdefault("cover_url", covers[0])
    if confidences:
        metadata["confidence"] = max(confidences)
    metadata["merged_manual"] = True
    metadata["status"] = "MANUAL"
    target.metadata_json = json.dumps(metadata, ensure_ascii=False)


def merge_assets(project_id: str, entity_type: AssetType, entity_ids: list[str], *, target_id: str | None = None) -> dict[str, Any]:
    ids = list(dict.fromkeys(entity_ids))
    if len(ids) < 2:
        raise AssetWorkspaceError("至少选择两个资产才能合并")
    with get_session() as session:
        ids = _validate_ids(session, project_id, entity_type, ids)
        target_id = target_id if target_id in ids else ids[0]
        table = _asset_table(entity_type)
        target = session.get(table, target_id)
        if target is None:
            raise AssetWorkspaceError("目标资产不存在")
        sources = [session.get(table, item_id) for item_id in ids if item_id != target_id]
        sources = [item for item in sources if item is not None]
        _merge_metadata(target, sources)
        if entity_type in {"character", "scene"}:
            target.status = "MANUAL"

        if entity_type == "character":
            existing = set(session.scalars(select(ShotCharacterBinding.shot_id).where(ShotCharacterBinding.character_id == target_id)).all())
            for source in sources:
                for binding in list(session.scalars(select(ShotCharacterBinding).where(ShotCharacterBinding.character_id == source.id)).all()):
                    if binding.shot_id not in existing:
                        session.add(ShotCharacterBinding(id=new_id("SHOTCHAR"), project_id=project_id, shot_id=binding.shot_id, character_id=target_id, source="MANUAL"))
                        existing.add(binding.shot_id)
                    session.delete(binding)
        elif entity_type == "scene":
            for source in sources:
                for binding in session.scalars(select(ShotSceneBinding).where(ShotSceneBinding.scene_id == source.id)).all():
                    binding.scene_id = target_id
                    binding.source = "MANUAL"
                    binding.confidence = None
                    binding.source_candidate_id = None
        else:
            existing = set(session.scalars(select(ShotPropBinding.shot_id).where(ShotPropBinding.prop_id == target_id)).all())
            for source in sources:
                for binding in list(session.scalars(select(ShotPropBinding).where(ShotPropBinding.prop_id == source.id)).all()):
                    if binding.shot_id not in existing:
                        session.add(ShotPropBinding(id=new_id("SHOTPROPFINAL"), project_id=project_id, shot_id=binding.shot_id, prop_id=target_id, source="MANUAL"))
                        existing.add(binding.shot_id)
                    session.delete(binding)
        for source in sources:
            session.delete(source)
        _manual_revision(session, project_id, f"合并 {len(ids)} 个{entity_type}资产")
        session.commit()
        return _serialize_workspace(session, project_id)


def split_asset(project_id: str, entity_type: AssetType, entity_id: str, shot_ids: list[str], *, new_name: str | None = None) -> dict[str, Any]:
    selected = list(dict.fromkeys(shot_ids))
    if not selected:
        raise AssetWorkspaceError("至少选择一个 Shot 进行拆分")
    with get_session() as session:
        table = _asset_table(entity_type)
        source = session.get(table, entity_id)
        if source is None or source.project_id != project_id:
            raise AssetWorkspaceError("资产不存在")
        if entity_type == "character":
            bindings = list(session.scalars(select(ShotCharacterBinding).where(ShotCharacterBinding.character_id == entity_id)).all())
        elif entity_type == "scene":
            bindings = list(session.scalars(select(ShotSceneBinding).where(ShotSceneBinding.scene_id == entity_id)).all())
        else:
            bindings = list(session.scalars(select(ShotPropBinding).where(ShotPropBinding.prop_id == entity_id)).all())
        bound_ids = {item.shot_id for item in bindings}
        if not set(selected) <= bound_ids:
            raise AssetWorkspaceError("拆分 Shot 不属于该资产")
        if set(selected) == bound_ids:
            raise AssetWorkspaceError("不能把该资产的全部 Shot 都拆走")
        name = (new_name or f"{source.name} · 拆分").strip()
        metadata = _json(source.metadata_json)
        metadata["split_from"] = source.id
        metadata["status"] = "MANUAL"
        if entity_type == "character":
            new_item = Character(id=new_id("CHAR"), project_id=project_id, name=name, status="MANUAL", metadata_json=json.dumps(metadata, ensure_ascii=False))
        elif entity_type == "scene":
            new_item = Scene(id=new_id("SCENE"), project_id=project_id, name=name, status="MANUAL", metadata_json=json.dumps(metadata, ensure_ascii=False))
        else:
            new_item = Prop(id=new_id("PROP"), project_id=project_id, name=name, is_key_prop=source.is_key_prop, metadata_json=json.dumps(metadata, ensure_ascii=False))
        session.add(new_item)
        session.flush()
        for binding in bindings:
            if binding.shot_id not in selected:
                continue
            if entity_type == "character":
                binding.character_id = new_item.id
            elif entity_type == "scene":
                binding.scene_id = new_item.id
            else:
                binding.prop_id = new_item.id
            binding.source = "MANUAL"
            binding.confidence = None
            binding.source_candidate_id = None
        _manual_revision(session, project_id, f"拆分{entity_type}资产：{source.name}")
        session.commit()
        return _serialize_workspace(session, project_id)


def set_asset_cover(project_id: str, entity_type: AssetType, entity_id: str, cover_url: str) -> dict[str, Any]:
    with get_session() as session:
        table = _asset_table(entity_type)
        item = session.get(table, entity_id)
        if item is None or item.project_id != project_id:
            raise AssetWorkspaceError("资产不存在")
        metadata = _json(item.metadata_json)
        allowed = set(metadata.get("evidence_cover_urls") or [])
        if metadata.get("cover_url"):
            allowed.add(str(metadata["cover_url"]))
        if cover_url not in allowed:
            raise AssetWorkspaceError("参考图必须来自该资产已有 Evidence")
        metadata["cover_url"] = cover_url
        metadata["status"] = "MANUAL"
        item.metadata_json = json.dumps(metadata, ensure_ascii=False)
        if entity_type in {"character", "scene"}:
            item.status = "MANUAL"
        _manual_revision(session, project_id, f"修改{entity_type}参考图")
        session.commit()
        return _serialize_workspace(session, project_id)


def restore_asset_revision(revision_id: str) -> dict[str, Any]:
    """恢复历史快照，并创建新的 RESTORE Revision；历史 Revision 永不被修改。"""

    with get_session() as session:
        source = session.get(AssetRevision, revision_id)
        if source is None:
            raise LookupError("资产 Revision 不存在")
        try:
            snapshot = json.loads(source.snapshot_json)
        except json.JSONDecodeError as exc:
            raise AssetWorkspaceError("资产 Revision 快照损坏") from exc
        _replace_from_snapshot(session, source.project_id, snapshot)
        run = _current_analysis(session, source.project_id)
        _create_revision(
            session,
            project_id=source.project_id,
            kind="RESTORE",
            source_run_id=run.id if run else source.source_run_id,
            source_revision_id=source.id,
            note=f"恢复自资产 R{source.revision}",
        )
        session.commit()
        return _serialize_workspace(session, source.project_id)


def _serialize_revision(item: AssetRevision) -> dict[str, Any]:
    try:
        snapshot = json.loads(item.snapshot_json)
    except json.JSONDecodeError:
        snapshot = {}
    return {
        "id": item.id,
        "project_id": item.project_id,
        "revision": item.revision,
        "kind": item.kind,
        "is_current": item.is_current,
        "source_run_id": item.source_run_id,
        "source_revision_id": item.source_revision_id,
        "note": item.note,
        "created_at": item.created_at.isoformat(),
        "counts": {
            "characters": len(snapshot.get("characters") or []),
            "scenes": len(snapshot.get("scenes") or []),
            "props": len(snapshot.get("props") or []),
        },
    }


def list_asset_revisions(project_id: str) -> list[dict[str, Any]]:
    with get_session() as session:
        items = session.scalars(select(AssetRevision).where(AssetRevision.project_id == project_id).order_by(AssetRevision.revision.desc())).all()
        return [_serialize_revision(item) for item in items]


def _evidence_by_shot(session: Any, run: ContentAnalysisRun | None, snapshot: dict[str, Any]) -> dict[str, Any]:
    if run is None:
        return {}
    candidate_to_asset: dict[str, str] = {}
    for collection in (snapshot.get("characters") or [], snapshot.get("scenes") or [], snapshot.get("props") or []):
        for item in collection:
            for candidate_id in item.get("source_candidate_ids") or []:
                candidate_to_asset[candidate_id] = item["id"]

    result: dict[str, dict[str, Any]] = {}
    characters = {item.id: item for item in session.scalars(select(CharacterCandidate).where(CharacterCandidate.run_id == run.id)).all()}
    for track in session.scalars(select(CharacterTrack).where(CharacterTrack.run_id == run.id)).all():
        candidate = characters.get(track.candidate_id)
        if candidate is None or not track.face_visible:
            continue
        bucket = result.setdefault(track.shot_id, {"characters": [], "scene": None, "props": []})
        if any(value["candidate_id"] == candidate.id for value in bucket["characters"]):
            continue
        bucket["characters"].append({
            "candidate_id": candidate.id,
            "label": candidate.auto_label,
            "confidence": candidate.confidence,
            "cover_url": f"/api/content-analysis/characters/{candidate.id}/cover" if candidate.cover_path else None,
            "final_asset_id": candidate_to_asset.get(candidate.id),
        })

    scenes = {item.id: item for item in session.scalars(select(SceneCandidate).where(SceneCandidate.run_id == run.id)).all()}
    for link in session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run.id)).all():
        candidate = scenes.get(link.scene_candidate_id)
        if candidate is None:
            continue
        bucket = result.setdefault(link.shot_id, {"characters": [], "scene": None, "props": []})
        bucket["scene"] = {
            "candidate_id": candidate.id,
            "label": candidate.auto_label,
            "confidence": link.confidence,
            "cover_url": f"/api/content-analysis/scenes/{candidate.id}/cover" if candidate.cover_path else None,
            "final_asset_id": candidate_to_asset.get(candidate.id),
        }

    props = {item.id: item for item in session.scalars(select(PropCandidate).where(PropCandidate.run_id == run.id)).all()}
    for link in session.scalars(select(ShotPropEvidence).where(ShotPropEvidence.run_id == run.id)).all():
        candidate = props.get(link.prop_candidate_id)
        if candidate is None:
            continue
        bucket = result.setdefault(link.shot_id, {"characters": [], "scene": None, "props": []})
        bucket["props"].append({
            "candidate_id": candidate.id,
            "label": candidate.auto_label,
            "confidence": link.confidence,
            "cover_url": None,
            "final_asset_id": candidate_to_asset.get(candidate.id),
        })
    return result


def _serialize_workspace(session: Any, project_id: str) -> dict[str, Any]:
    session.flush()
    snapshot = _snapshot(session, project_id)
    revision = _current_revision(session, project_id)
    run = _current_analysis(session, project_id)
    bindings_by_shot: dict[str, dict[str, Any]] = {}
    for item in snapshot["bindings"]["characters"]:
        bindings_by_shot.setdefault(item["shot_id"], {"character_ids": [], "scene_id": None, "prop_ids": []})["character_ids"].append(item["entity_id"])
    for item in snapshot["bindings"]["scenes"]:
        bindings_by_shot.setdefault(item["shot_id"], {"character_ids": [], "scene_id": None, "prop_ids": []})["scene_id"] = item["entity_id"]
    for item in snapshot["bindings"]["props"]:
        bindings_by_shot.setdefault(item["shot_id"], {"character_ids": [], "scene_id": None, "prop_ids": []})["prop_ids"].append(item["entity_id"])

    stale = bool(run and (run.status == "STALE" or revision is None or revision.source_run_id != run.id))
    revisions = session.scalars(select(AssetRevision).where(AssetRevision.project_id == project_id).order_by(AssetRevision.revision.desc())).all()
    return {
        "project_id": project_id,
        "status": "STALE" if stale else ("READY" if revision else "EMPTY"),
        "stale": stale,
        "revision": _serialize_revision(revision) if revision else None,
        "analysis": {
            "id": run.id,
            "status": run.status,
            "profile_version": run.profile_version,
            "component_status": _json(run.component_status_json),
            "counts": _json(run.counts_json),
        } if run else None,
        "characters": snapshot["characters"],
        "scenes": snapshot["scenes"],
        "props": snapshot["props"],
        "bindings_by_shot": bindings_by_shot,
        "evidence_by_shot": _evidence_by_shot(session, run, snapshot),
        "revisions": [_serialize_revision(item) for item in revisions],
    }


def get_asset_workspace(project_id: str, *, auto_bootstrap: bool = True) -> dict[str, Any]:
    """读取资产工作台；已有可用 AI Run 且没有人工保护版本时自动形成 AUTO Revision。"""

    if auto_bootstrap:
        with get_session() as session:
            run = _current_analysis(session, project_id)
            revision = _current_revision(session, project_id)
            should_apply = bool(
                run
                and run.status not in {"PROCESSING", "FAILED", "STALE"}
                and (revision is None or (revision.kind == "AUTO" and revision.source_run_id != run.id))
            )
            run_id = run.id if should_apply and run else None
        if run_id:
            return apply_analysis_to_assets(project_id, run_id)
    with get_session() as session:
        return _serialize_workspace(session, project_id)
