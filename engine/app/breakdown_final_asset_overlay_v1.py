"""P6 Final Scene / Prop display overlay from current Final Shot bindings.

Authority is deliberately one-way and independent from Character identity:

    current ShotRevision exact Shot mapping
      + current AssetRevision
      + Final ShotSceneBinding / ShotPropBinding
      -> display-only Final Scene / Prop overlay

No Draft prose or G2 label is used to choose a Final Scene/Prop. Scene fill-back is
conservative: every Shot inside one G2 Scene must have the same Final Scene binding.
Prop fill-back is Shot-local and only lists Final Props explicitly bound to that Shot.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from engine.app.asset_workspace_v3 import (
    AssetRevision,
    ShotPropBinding,
    ShotSceneBinding,
)
from engine.app.breakdown_read_model_contract_v1 import BreakdownReadAssetOverlayV1
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem
from engine.app.studio_v2 import Prop, Scene, Shot, get_session


FINAL_ASSET_STALE_WARNING = "场景/道具资产与当前拉片版本暂不一致，当前保留拉片原结果。"


class BreakdownFinalAssetOverlayError(RuntimeError):
    """Current Final Scene/Prop binding surface cannot be safely projected."""


def _metadata(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _display_snapshot(item: Scene | Prop) -> dict[str, str | None]:
    metadata = _metadata(item.metadata_json)
    cover = metadata.get("cover_url")
    return {
        "id": item.id,
        "name": item.name,
        "cover_url": str(cover).strip() if isinstance(cover, str) and cover.strip() else None,
    }


def empty_final_asset_overlay_v1(
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
    *,
    asset_revision_id: str | None = None,
    warning: str | None = None,
) -> BreakdownReadAssetOverlayV1:
    """Return the exact G2 Scene/Shot surface with no Final Scene/Prop projection."""

    timeline = (
        timeline_payload
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload)
    )
    return BreakdownReadAssetOverlayV1(
        asset_revision_id=asset_revision_id,
        warnings=[warning] if warning else [],
        scenes=[{"scene_ordinal": scene.ordinal, "scene": None} for scene in timeline.scenes],
        shots=[
            {"scene_ordinal": scene.ordinal, "shot_ordinal": shot.ordinal, "props": []}
            for scene in timeline.scenes
            for shot in scene.shots
        ],
    )


def compose_final_asset_overlay_v1(
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
    *,
    asset_revision_id: str | None,
    shot_id_by_ordinal: Mapping[int, str],
    scene_binding_by_shot: Mapping[str, str],
    prop_bindings_by_shot: Mapping[str, list[str] | tuple[str, ...]],
    scene_snapshots: Mapping[str, Mapping[str, str | None]],
    prop_snapshots: Mapping[str, Mapping[str, str | None]],
) -> BreakdownReadAssetOverlayV1:
    """Pure deterministic Scene/Prop display composition used by loader and tests."""

    timeline = (
        timeline_payload
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload)
    )
    if not asset_revision_id:
        return empty_final_asset_overlay_v1(timeline)

    timeline_shots = [shot for scene in timeline.scenes for shot in scene.shots]
    ordinals = [shot.ordinal for shot in timeline_shots]
    if len(set(ordinals)) != len(ordinals):
        return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)
    if set(ordinals) != set(shot_id_by_ordinal):
        return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

    shot_ids = [str(shot_id_by_ordinal[ordinal]) for ordinal in ordinals]
    if any(not item for item in shot_ids) or len(set(shot_ids)) != len(shot_ids):
        return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)
    valid_shot_ids = set(shot_ids)

    # Any binding that points to a missing Final asset means the current overlay surface is corrupt.
    for shot_id, scene_id in scene_binding_by_shot.items():
        if shot_id in valid_shot_ids and scene_id not in scene_snapshots:
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)
    for shot_id, prop_ids in prop_bindings_by_shot.items():
        if shot_id not in valid_shot_ids:
            continue
        normalized = [str(item) for item in prop_ids]
        if len(set(normalized)) != len(normalized):
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)
        if any(prop_id not in prop_snapshots for prop_id in normalized):
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

    scenes: list[dict[str, object]] = []
    shots: list[dict[str, object]] = []
    for scene in timeline.scenes:
        scene_shot_ids = [str(shot_id_by_ordinal[shot.ordinal]) for shot in scene.shots]
        bound_scene_ids = [scene_binding_by_shot.get(shot_id) for shot_id in scene_shot_ids]
        final_scene: Mapping[str, str | None] | None = None
        if bound_scene_ids and all(bound_scene_ids) and len(set(bound_scene_ids)) == 1:
            final_scene = scene_snapshots.get(str(bound_scene_ids[0]))
        scenes.append({
            "scene_ordinal": scene.ordinal,
            "scene": dict(final_scene) if final_scene is not None else None,
        })

        for shot in scene.shots:
            shot_id = str(shot_id_by_ordinal[shot.ordinal])
            prop_ids = [str(item) for item in prop_bindings_by_shot.get(shot_id, ())]
            prop_rows = [dict(prop_snapshots[prop_id]) for prop_id in prop_ids]
            prop_rows.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("id") or "")))
            shots.append({
                "scene_ordinal": scene.ordinal,
                "shot_ordinal": shot.ordinal,
                "props": prop_rows,
            })

    return BreakdownReadAssetOverlayV1(
        asset_revision_id=asset_revision_id,
        warnings=[],
        scenes=scenes,
        shots=shots,
    )


def load_episode_final_asset_overlay_v1(
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
    *,
    project_id: str,
    expected_asset_revision_id: str | None,
) -> BreakdownReadAssetOverlayV1:
    """Load current Final Scene/Prop bindings for the exact ShotRevision behind G2."""

    timeline = (
        timeline_payload
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload)
    )
    if expected_asset_revision_id is None:
        return empty_final_asset_overlay_v1(timeline)

    with get_session() as session:
        current_asset_revision = session.scalar(select(AssetRevision).where(
            AssetRevision.project_id == project_id,
            AssetRevision.is_current.is_(True),
        ))
        if current_asset_revision is None or current_asset_revision.id != expected_asset_revision_id:
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

        revision = session.get(ShotRevision, timeline.source_shot_revision_id)
        if (
            revision is None
            or revision.episode_id != timeline.episode_id
            or not revision.is_current
        ):
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

        revision_items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == revision.id)
            .order_by(ShotRevisionItem.ordinal, ShotRevisionItem.id)
        ).all())
        item_by_ordinal = {int(item.ordinal): item for item in revision_items}
        if len(item_by_ordinal) != len(revision_items):
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

        timeline_ordinals = {
            shot.ordinal
            for scene in timeline.scenes
            for shot in scene.shots
        }
        if set(item_by_ordinal) != timeline_ordinals:
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

        current_shots = {
            shot.id: shot
            for shot in session.scalars(select(Shot).where(Shot.episode_id == timeline.episode_id)).all()
        }
        shot_id_by_ordinal: dict[int, str] = {}
        for ordinal, item in item_by_ordinal.items():
            shot = current_shots.get(item.original_shot_id)
            if shot is None:
                return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)
            shot_id_by_ordinal[ordinal] = shot.id

        shot_ids = tuple(shot_id_by_ordinal.values())
        scene_bindings = list(session.scalars(select(ShotSceneBinding).where(
            ShotSceneBinding.project_id == project_id,
            ShotSceneBinding.shot_id.in_(shot_ids),
        )).all()) if shot_ids else []
        scene_binding_by_shot = {item.shot_id: item.scene_id for item in scene_bindings}
        if len(scene_binding_by_shot) != len(scene_bindings):
            return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

        prop_bindings = list(session.scalars(select(ShotPropBinding).where(
            ShotPropBinding.project_id == project_id,
            ShotPropBinding.shot_id.in_(shot_ids),
        )).all()) if shot_ids else []
        prop_bindings_by_shot: dict[str, list[str]] = defaultdict(list)
        for item in prop_bindings:
            prop_bindings_by_shot[item.shot_id].append(item.prop_id)

        scene_ids = tuple(sorted({item.scene_id for item in scene_bindings}))
        prop_ids = tuple(sorted({item.prop_id for item in prop_bindings}))
        scene_snapshots = {
            item.id: _display_snapshot(item)
            for item in session.scalars(select(Scene).where(
                Scene.project_id == project_id,
                Scene.id.in_(scene_ids),
            )).all()
        } if scene_ids else {}
        prop_snapshots = {
            item.id: _display_snapshot(item)
            for item in session.scalars(select(Prop).where(
                Prop.project_id == project_id,
                Prop.id.in_(prop_ids),
            )).all()
        } if prop_ids else {}

    return compose_final_asset_overlay_v1(
        timeline,
        asset_revision_id=expected_asset_revision_id,
        shot_id_by_ordinal=shot_id_by_ordinal,
        scene_binding_by_shot=scene_binding_by_shot,
        prop_bindings_by_shot=prop_bindings_by_shot,
        scene_snapshots=scene_snapshots,
        prop_snapshots=prop_snapshots,
    )


__all__ = [
    "BreakdownFinalAssetOverlayError",
    "FINAL_ASSET_STALE_WARNING",
    "compose_final_asset_overlay_v1",
    "empty_final_asset_overlay_v1",
    "load_episode_final_asset_overlay_v1",
]
