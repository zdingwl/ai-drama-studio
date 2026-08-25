"""V2 拉片 Revision / Current / Restore。

职责：
- 把当前可生产 Shot Timeline 快照为不可变 Revision；
- 自动重跑只有在新 Shot 全部生成成功后才切换 Current；
- 人工修改后创建新的 MANUAL Revision；
- 支持查看历史 Revision、查看历史 Shot 和恢复历史版本。

不负责：
- 不运行 TransNetV2 / FFmpeg；
- 不修改自动模型 Evidence；
- 不把失败中的候选结果切成 Current。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.studio_v2 import Base, Episode, Shot, get_session, new_id, serialize_shot, utcnow


class ShotRevision(Base):
    __tablename__ = "v2_shot_revisions"
    __table_args__ = (UniqueConstraint("episode_id", "revision", name="uq_v2_shot_revision_episode_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # AUTO / MANUAL / RESTORE / BASELINE
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ShotRevisionItem(Base):
    __tablename__ = "v2_shot_revision_items"
    __table_args__ = (UniqueConstraint("revision_id", "ordinal", name="uq_v2_shot_revision_item_ordinal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("v2_shot_revisions.id", ondelete="CASCADE"), index=True)
    original_shot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_clip_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyframes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shot_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_motion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shot_status: Mapped[str] = mapped_column(String(32), nullable=False)


def _ordered_shots(session: Any, episode_id: str) -> list[Shot]:
    return list(session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.ordinal)).all())


def _next_revision_number(session: Any, episode_id: str) -> int:
    latest = session.scalar(select(func.max(ShotRevision.revision)).where(ShotRevision.episode_id == episode_id))
    return int(latest or 0) + 1


def _snapshot_items(session: Any, revision_id: str, shots: list[Shot]) -> None:
    for shot in shots:
        session.add(ShotRevisionItem(
            id=new_id("SHOTREVITEM"),
            revision_id=revision_id,
            original_shot_id=shot.id,
            ordinal=shot.ordinal,
            start_us=shot.start_us,
            end_us=shot.end_us,
            duration_us=shot.duration_us,
            reference_clip_path=shot.reference_clip_path,
            thumbnail_path=shot.thumbnail_path,
            keyframes_json=shot.keyframes_json,
            short_description=shot.short_description,
            shot_type=shot.shot_type,
            camera_motion=shot.camera_motion,
            shot_status=shot.status,
        ))


def _create_revision_from_current(
    session: Any,
    *,
    episode_id: str,
    kind: str,
    source_revision_id: str | None = None,
    note: str | None = None,
    make_current: bool = True,
) -> ShotRevision:
    shots = _ordered_shots(session, episode_id)
    if not shots:
        raise ValueError("当前剧集没有 Shot，无法创建 Revision")
    if make_current:
        current = session.scalars(select(ShotRevision).where(ShotRevision.episode_id == episode_id, ShotRevision.is_current.is_(True))).all()
        for item in current:
            item.is_current = False
    revision = ShotRevision(
        id=new_id("SHOTREV"),
        episode_id=episode_id,
        revision=_next_revision_number(session, episode_id),
        kind=kind,
        is_current=make_current,
        source_revision_id=source_revision_id,
        note=note,
    )
    session.add(revision)
    session.flush()
    _snapshot_items(session, revision.id, shots)
    return revision


def ensure_current_revision(episode_id: str) -> dict[str, Any] | None:
    """为已有旧数据补建 BASELINE Revision；已存在 Current 时幂等返回。"""

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        current = session.scalar(select(ShotRevision).where(ShotRevision.episode_id == episode_id, ShotRevision.is_current.is_(True)))
        if current is not None:
            return serialize_revision(current, session=session)
        if not _ordered_shots(session, episode_id):
            return None
        revision = _create_revision_from_current(session, episode_id=episode_id, kind="BASELINE", note="升级版本化前的当前 Shot")
        session.commit()
        return serialize_revision(revision, session=session)


def record_manual_revision(episode_id: str, *, note: str | None = None) -> dict[str, Any]:
    """人工修改成功后，把新的当前 Timeline 记录为一个 MANUAL Revision。"""

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        revision = _create_revision_from_current(session, episode_id=episode_id, kind="MANUAL", note=note or "人工镜头修正")
        session.commit()
        return serialize_revision(revision, session=session)


def commit_auto_shot_revision(episode_id: str, shot_payloads: list[dict[str, Any]], *, note: str | None = None) -> list[dict[str, Any]]:
    """把已经完整生成成功的自动 Shot 原子切换为新的 Current Revision。

    调用前媒体文件必须已经全部生成成功。数据库事务失败时旧 Current Shot 不变。
    """

    if not shot_payloads:
        raise ValueError("自动拉片结果不能为空")
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")

        existing = _ordered_shots(session, episode_id)
        current_revision = session.scalar(select(ShotRevision).where(ShotRevision.episode_id == episode_id, ShotRevision.is_current.is_(True)))
        if existing and current_revision is None:
            current_revision = _create_revision_from_current(
                session,
                episode_id=episode_id,
                kind="BASELINE",
                note="自动重跑前自动保存现有 Shot",
                make_current=True,
            )
            session.flush()

        # 先把旧 current 标为 historical；同一数据库事务内新 Shot / Revision 任一步失败都会整体回滚。
        if current_revision is not None:
            current_revision.is_current = False
        for item in existing:
            session.delete(item)
        session.flush()

        new_shots: list[Shot] = []
        for payload in shot_payloads:
            shot = Shot(id=new_id("SHOT"), episode_id=episode_id, **payload)
            session.add(shot)
            new_shots.append(shot)
        session.flush()

        revision = ShotRevision(
            id=new_id("SHOTREV"),
            episode_id=episode_id,
            revision=_next_revision_number(session, episode_id),
            kind="AUTO",
            is_current=True,
            source_revision_id=current_revision.id if current_revision is not None else None,
            note=note or "自动拉片",
        )
        session.add(revision)
        session.flush()
        _snapshot_items(session, revision.id, new_shots)

        episode.status = "SHOTS_READY"
        episode.updated_at = utcnow()
        session.commit()
        for shot in new_shots:
            session.refresh(shot)
        return [serialize_shot(item) for item in new_shots]


def list_shot_revisions(episode_id: str) -> list[dict[str, Any]]:
    ensure_current_revision(episode_id)
    with get_session() as session:
        revisions = session.scalars(select(ShotRevision).where(ShotRevision.episode_id == episode_id).order_by(ShotRevision.revision.desc())).all()
        return [serialize_revision(item, session=session) for item in revisions]


def get_shot_revision(revision_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        revision = session.get(ShotRevision, revision_id)
        if revision is None:
            return None
        return serialize_revision(revision, session=session, include_items=True)


def serialize_revision(revision: ShotRevision, *, session: Any, include_items: bool = False) -> dict[str, Any]:
    count = session.scalar(select(func.count(ShotRevisionItem.id)).where(ShotRevisionItem.revision_id == revision.id)) or 0
    payload: dict[str, Any] = {
        "id": revision.id,
        "episode_id": revision.episode_id,
        "revision": revision.revision,
        "kind": revision.kind,
        "is_current": revision.is_current,
        "source_revision_id": revision.source_revision_id,
        "note": revision.note,
        "shot_count": int(count),
        "created_at": revision.created_at.isoformat(),
    }
    if include_items:
        items = session.scalars(select(ShotRevisionItem).where(ShotRevisionItem.revision_id == revision.id).order_by(ShotRevisionItem.ordinal)).all()
        payload["shots"] = [serialize_revision_item(item) for item in items]
    return payload


def serialize_revision_item(item: ShotRevisionItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "revision_id": item.revision_id,
        "original_shot_id": item.original_shot_id,
        "ordinal": item.ordinal,
        "start_us": item.start_us,
        "end_us": item.end_us,
        "duration_us": item.duration_us,
        "reference_url": f"/api/shot-revision-items/{item.id}/reference",
        "thumbnail_url": f"/api/shot-revision-items/{item.id}/thumbnail" if item.thumbnail_path else None,
        "status": item.shot_status,
    }


def get_revision_item_path(item_id: str, kind: str) -> Any | None:
    from pathlib import Path
    with get_session() as session:
        item = session.get(ShotRevisionItem, item_id)
        if item is None:
            return None
        raw = item.reference_clip_path if kind == "reference" else item.thumbnail_path
        return Path(raw) if raw else None


def restore_shot_revision(revision_id: str) -> list[dict[str, Any]]:
    """把历史 Revision 恢复为一个新的 RESTORE Revision，不改写历史记录。"""

    with get_session() as session:
        source = session.get(ShotRevision, revision_id)
        if source is None:
            raise LookupError("Shot Revision 不存在")
        items = session.scalars(select(ShotRevisionItem).where(ShotRevisionItem.revision_id == revision_id).order_by(ShotRevisionItem.ordinal)).all()
        if not items:
            raise ValueError("Shot Revision 没有镜头")
        payloads = [
            {
                "ordinal": item.ordinal,
                "start_us": item.start_us,
                "end_us": item.end_us,
                "duration_us": item.duration_us,
                "reference_clip_path": item.reference_clip_path,
                "thumbnail_path": item.thumbnail_path,
                "keyframes_json": item.keyframes_json,
                "short_description": item.short_description,
                "shot_type": item.shot_type,
                "camera_motion": item.camera_motion,
                "status": "RESTORED",
            }
            for item in items
        ]
        episode_id = source.episode_id

    # 用与自动切换相同的原子替换逻辑，但随后把 AUTO Revision 改成 RESTORE，保留 source_revision_id。
    result = commit_auto_shot_revision(episode_id, payloads, note=f"恢复自 R{source.revision}")
    with get_session() as session:
        current = session.scalar(select(ShotRevision).where(ShotRevision.episode_id == episode_id, ShotRevision.is_current.is_(True)))
        if current is not None:
            current.kind = "RESTORE"
            current.source_revision_id = revision_id
            current.note = f"恢复自 R{source.revision}"
            session.commit()
    return result
