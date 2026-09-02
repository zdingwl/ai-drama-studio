"""Normalize Asset Workspace read shape without creating any business data.

A Shot with zero Final bindings is still a real Shot and must remain visible to Review Center.
Historically ``asset_workspace_v3._serialize_workspace`` only created ``bindings_by_shot``
entries after seeing at least one binding, which made unresolved/empty Shots disappear from the
read model.  This helper fills the read-model shape only; it never creates ShotBinding rows.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from sqlalchemy import select

from engine.app import asset_workspace_v3 as legacy
from engine.app.studio_v2 import Episode, Shot


_EMPTY_BINDINGS = {"character_ids": [], "scene_id": None, "prop_ids": []}


def complete_asset_workspace_shot_bindings_v1(
    project_id: str,
    workspace: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a copy whose ``bindings_by_shot`` contains every current Project Shot."""

    payload = deepcopy(dict(workspace))
    current = payload.get("bindings_by_shot")
    bindings_by_shot: dict[str, dict[str, Any]] = {}
    if isinstance(current, Mapping):
        for shot_id, raw in current.items():
            value = raw if isinstance(raw, Mapping) else {}
            bindings_by_shot[str(shot_id)] = {
                "character_ids": list(dict.fromkeys(str(item) for item in (value.get("character_ids") or []) if item)),
                "scene_id": str(value.get("scene_id")) if value.get("scene_id") else None,
                "prop_ids": list(dict.fromkeys(str(item) for item in (value.get("prop_ids") or []) if item)),
            }

    # Resolve through the module attribute so existing isolated tests that monkeypatch
    # ``asset_workspace_v3.get_session`` continue to use their temporary database.
    with legacy.get_session() as session:
        episode_ids = tuple(session.scalars(
            select(Episode.id).where(Episode.project_id == project_id)
        ).all())
        shot_ids = list(session.scalars(
            select(Shot.id)
            .where(Shot.episode_id.in_(episode_ids))
            .order_by(Shot.episode_id, Shot.ordinal, Shot.id)
        ).all()) if episode_ids else []

    for shot_id in shot_ids:
        bindings_by_shot.setdefault(str(shot_id), deepcopy(_EMPTY_BINDINGS))

    payload["bindings_by_shot"] = bindings_by_shot
    return payload


__all__ = ["complete_asset_workspace_shot_bindings_v1"]
