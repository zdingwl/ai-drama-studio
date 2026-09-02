"""Read-only ShotRevision query service.

Legacy ``list_shot_revisions`` upgrades old projects by creating a BASELINE revision.
That behavior is valid only in an explicit write path, never in HTTP GET.  This module
exposes the persisted history exactly as it exists.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from engine.app.shot_revision_v2 import ShotRevision, serialize_revision
from engine.app.studio_v2 import Episode, get_session


def list_shot_revisions_read_only_v2(episode_id: str) -> list[dict[str, Any]]:
    """List persisted ShotRevision rows without auto-creating a BASELINE revision."""

    with get_session() as session:
        if session.get(Episode, episode_id) is None:
            raise LookupError("剧集不存在")
        revisions = list(
            session.scalars(
                select(ShotRevision)
                .where(ShotRevision.episode_id == episode_id)
                .order_by(ShotRevision.revision.desc(), ShotRevision.id.desc())
            ).all()
        )
        return [serialize_revision(item, session=session) for item in revisions]


__all__ = ["list_shot_revisions_read_only_v2"]
