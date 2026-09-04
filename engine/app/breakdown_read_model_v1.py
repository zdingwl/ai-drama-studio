"""P6：冻结 Scene Timeline + Final Asset display overlays 的最终用户阅读组合层。

本模块不做新的识别或资产推断：

Character:
    G2 Scene-local P* --(same run/revision + same scene/ref)--> P5 RESOLVED
        --> current AssetRevision --> existing Final Character

Scene / Prop:
    exact current ShotRevision mapping --> current Final ShotSceneBinding / ShotPropBinding
        --> existing Final Scene / Prop

人物 identity 与 Scene/Prop asset overlay 独立 fail-closed。任何 overlay 都不得改写冻结 G2 Timeline。
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from engine.app.asset_workspace_v3 import AssetRevision
from engine.app.breakdown_character_bridge_contract_v1 import BreakdownCharacterResolutionPayloadV1
from engine.app.breakdown_character_bridge_v1 import (
    BreakdownCharacterBridgeError,
    load_episode_character_resolution_v1,
)
from engine.app.breakdown_final_asset_overlay_v1 import (
    FINAL_ASSET_STALE_WARNING,
    empty_final_asset_overlay_v1,
    load_episode_final_asset_overlay_v1,
)
from engine.app.breakdown_read_model_contract_v1 import (
    BREAKDOWN_READ_MODEL_SCHEMA_VERSION,
    BreakdownReadAssetOverlayV1,
    BreakdownReadIdentityOverlayV1,
    BreakdownReadModelV1,
)
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.breakdown_scene_timeline_result_v1 import build_scene_timeline_result_v1
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.studio_v2 import Character, Episode, get_session


IDENTITY_PENDING_WARNING = "人物资产尚未完成最终身份确认，当前继续使用匿名人物显示。"
IDENTITY_PARTIAL_WARNING = "部分人物尚未完成最终身份确认，当前仍以匿名人物显示。"
IDENTITY_STALE_WARNING = "人物资产与当前拉片版本暂不一致，当前继续使用匿名人物显示。"


class BreakdownReadModelError(RuntimeError):
    """P6 自身 Contract 无法安全组合；不会用于放宽 G2/P5/Final Binding。"""


def _metadata(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _anonymous_identity(
    timeline: SceneTimelinePayloadV1,
    *,
    warning: str | None,
    asset_revision_id: str | None = None,
) -> BreakdownReadIdentityOverlayV1:
    scenes: list[dict[str, object]] = []
    person_count = 0
    for scene in timeline.scenes:
        people = [
            {"ref": person.ref, "display_name": person.display_name, "character": None}
            for person in scene.people
        ]
        person_count += len(people)
        scenes.append({"scene_ordinal": scene.ordinal, "people": people})
    return BreakdownReadIdentityOverlayV1(
        asset_revision_id=asset_revision_id,
        resolved_count=0,
        unresolved_count=person_count,
        warnings=[warning] if warning and person_count else [],
        scenes=scenes,
    )


def _asset_overlay(
    value: Mapping[str, Any] | BreakdownReadAssetOverlayV1 | None,
    timeline: SceneTimelinePayloadV1,
) -> BreakdownReadAssetOverlayV1 | None:
    if value is None:
        return None
    try:
        overlay = value if isinstance(value, BreakdownReadAssetOverlayV1) else BreakdownReadAssetOverlayV1.model_validate(value)
    except ValueError:
        return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)

    expected_scenes = {scene.ordinal for scene in timeline.scenes}
    actual_scenes = {item.scene_ordinal for item in overlay.scenes}
    expected_shots = {
        (scene.ordinal, shot.ordinal)
        for scene in timeline.scenes
        for shot in scene.shots
    }
    actual_shots = {(item.scene_ordinal, item.shot_ordinal) for item in overlay.shots}
    if expected_scenes != actual_scenes or expected_shots != actual_shots:
        return empty_final_asset_overlay_v1(timeline, warning=FINAL_ASSET_STALE_WARNING)
    return overlay


def _anonymous_result(
    timeline: SceneTimelinePayloadV1,
    *,
    warning: str,
    asset_overlay: BreakdownReadAssetOverlayV1 | None = None,
) -> dict[str, Any]:
    return BreakdownReadModelV1(
        timeline=timeline,
        identity=_anonymous_identity(timeline, warning=warning),
        assets=asset_overlay,
    ).model_dump(mode="json")


def _current_episode_asset_anchor(episode_id: str) -> tuple[str, str | None]:
    """Return project + current AssetRevision without depending on P5 Character resolution."""

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        current_revision = session.scalar(select(AssetRevision).where(
            AssetRevision.project_id == episode.project_id,
            AssetRevision.is_current.is_(True),
        ))
        return episode.project_id, current_revision.id if current_revision is not None else None


def _load_current_character_snapshots(
    *,
    project_id: str,
    expected_asset_revision_id: str | None,
    character_ids: set[str],
) -> tuple[bool, dict[str, dict[str, str | None]]]:
    """Verify P5 still points at current AssetRevision, then load display-only Character fields."""

    if expected_asset_revision_id is None:
        return False, {}

    with get_session() as session:
        current_revision = session.scalar(select(AssetRevision).where(
            AssetRevision.project_id == project_id,
            AssetRevision.is_current.is_(True),
        ))
        if current_revision is None or current_revision.id != expected_asset_revision_id:
            return False, {}

        if not character_ids:
            return True, {}

        rows = list(session.scalars(
            select(Character).where(
                Character.project_id == project_id,
                Character.id.in_(tuple(sorted(character_ids))),
            )
        ).all())
        snapshots: dict[str, dict[str, str | None]] = {}
        for character in rows:
            metadata = _metadata(character.metadata_json)
            cover = metadata.get("cover_url")
            snapshots[character.id] = {
                "id": character.id,
                "name": character.name,
                "cover_url": str(cover).strip() if isinstance(cover, str) and cover.strip() else None,
            }
        return True, snapshots


def compose_breakdown_read_model_v1(
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
    resolution_payload: Mapping[str, Any] | BreakdownCharacterResolutionPayloadV1 | None,
    *,
    current_asset_revision_matches: bool = True,
    character_snapshots: Mapping[str, Mapping[str, str | None]] | None = None,
    asset_overlay: Mapping[str, Any] | BreakdownReadAssetOverlayV1 | None = None,
    unavailable_warning: str = IDENTITY_PENDING_WARNING,
) -> dict[str, Any]:
    """Pure P6 Character composition plus independently validated Scene/Prop overlay."""

    timeline = (
        timeline_payload
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload)
    )
    normalized_timeline = timeline.model_dump(mode="json")
    assets = _asset_overlay(asset_overlay, timeline)

    if resolution_payload is None:
        identity = _anonymous_identity(timeline, warning=unavailable_warning)
        return BreakdownReadModelV1(
            schema_version=BREAKDOWN_READ_MODEL_SCHEMA_VERSION,
            timeline=timeline,
            identity=identity,
            assets=assets,
        ).model_dump(mode="json")

    resolution = (
        resolution_payload
        if isinstance(resolution_payload, BreakdownCharacterResolutionPayloadV1)
        else BreakdownCharacterResolutionPayloadV1.model_validate(resolution_payload)
    )

    anchors_match = (
        resolution.episode_id == timeline.episode_id
        and resolution.breakdown_run_id == timeline.source_breakdown_run_id
        and resolution.shot_revision_id == timeline.source_shot_revision_id
        and current_asset_revision_matches
        and resolution.asset_revision_id is not None
    )
    if not anchors_match:
        return _anonymous_result(timeline, warning=IDENTITY_STALE_WARNING, asset_overlay=assets)

    bridge_people_count = sum(len(scene.people) for scene in resolution.scenes)
    bridge_resolved_count = sum(
        1
        for scene in resolution.scenes
        for person in scene.people
        if person.status == "RESOLVED"
    )
    if (
        resolution.scene_count != len(resolution.scenes)
        or resolution.person_count != bridge_people_count
        or resolution.resolved_count != bridge_resolved_count
        or resolution.unresolved_count != bridge_people_count - bridge_resolved_count
    ):
        return _anonymous_result(timeline, warning=IDENTITY_STALE_WARNING, asset_overlay=assets)

    timeline_scenes = {scene.ordinal: scene for scene in timeline.scenes}
    resolution_scenes = {scene.scene_ordinal: scene for scene in resolution.scenes}
    if (
        len(timeline_scenes) != len(timeline.scenes)
        or len(resolution_scenes) != len(resolution.scenes)
        or set(timeline_scenes) != set(resolution_scenes)
    ):
        return _anonymous_result(timeline, warning=IDENTITY_STALE_WARNING, asset_overlay=assets)

    snapshots = character_snapshots or {}
    overlay_scenes: list[dict[str, object]] = []
    resolved_count = 0
    unresolved_count = 0

    for scene_ordinal, scene in timeline_scenes.items():
        bridge_scene = resolution_scenes[scene_ordinal]
        timeline_people = {person.ref: person for person in scene.people}
        bridge_people = {person.scene_person_ref: person for person in bridge_scene.people}
        bridge_scene_resolved = sum(person.status == "RESOLVED" for person in bridge_scene.people)
        if (
            len(timeline_people) != len(scene.people)
            or len(bridge_people) != len(bridge_scene.people)
            or bridge_scene.resolved_count != bridge_scene_resolved
            or bridge_scene.unresolved_count != len(bridge_scene.people) - bridge_scene_resolved
            or set(timeline_people) != set(bridge_people)
        ):
            return _anonymous_result(timeline, warning=IDENTITY_STALE_WARNING, asset_overlay=assets)
        for ref, person in timeline_people.items():
            bridge_person = bridge_people[ref]
            if bridge_person.local_display_name != person.display_name:
                return _anonymous_result(timeline, warning=IDENTITY_STALE_WARNING, asset_overlay=assets)
            if bridge_person.status == "RESOLVED":
                character_id = str(bridge_person.character_id or "")
                snapshot = snapshots.get(character_id)
                if (
                    not snapshot
                    or snapshot.get("id") != character_id
                    or snapshot.get("name") != bridge_person.character_name
                ):
                    return _anonymous_result(timeline, warning=IDENTITY_STALE_WARNING, asset_overlay=assets)

    for scene in timeline.scenes:
        bridge_people = {
            person.scene_person_ref: person
            for person in resolution_scenes[scene.ordinal].people
        }
        people: list[dict[str, object]] = []
        for person in scene.people:
            bridge_person = bridge_people[person.ref]
            if bridge_person.status == "RESOLVED":
                snapshot = snapshots[str(bridge_person.character_id)]
                character = {
                    "id": str(snapshot["id"]),
                    "name": str(snapshot["name"]),
                    "cover_url": snapshot.get("cover_url"),
                }
                people.append({
                    "ref": person.ref,
                    "display_name": character["name"],
                    "character": character,
                })
                resolved_count += 1
            else:
                people.append({
                    "ref": person.ref,
                    "display_name": person.display_name,
                    "character": None,
                })
                unresolved_count += 1
        overlay_scenes.append({"scene_ordinal": scene.ordinal, "people": people})

    warnings = [IDENTITY_PARTIAL_WARNING] if unresolved_count else []
    identity = BreakdownReadIdentityOverlayV1(
        asset_revision_id=resolution.asset_revision_id,
        resolved_count=resolved_count,
        unresolved_count=unresolved_count,
        warnings=warnings,
        scenes=overlay_scenes,
    )
    result = BreakdownReadModelV1(
        timeline=timeline,
        identity=identity,
        assets=assets,
    ).model_dump(mode="json")

    if result["timeline"] != normalized_timeline:
        raise BreakdownReadModelError("P6 不允许改写 Scene Timeline")
    return result


def _load_episode_breakdown_read_model_v1(episode_id: str) -> dict[str, Any] | None:
    """Read current G2 result and independently add current Final Character/Scene/Prop overlays."""

    draft = get_current_breakdown(episode_id)
    if draft is None:
        return None
    timeline = SceneTimelinePayloadV1.model_validate(build_scene_timeline_result_v1(draft))

    project_id, current_asset_revision_id = _current_episode_asset_anchor(episode_id)
    assets = load_episode_final_asset_overlay_v1(
        timeline,
        project_id=project_id,
        expected_asset_revision_id=current_asset_revision_id,
    )

    try:
        resolution = load_episode_character_resolution_v1(episode_id)
    except BreakdownCharacterBridgeError:
        return compose_breakdown_read_model_v1(
            timeline,
            None,
            asset_overlay=assets,
            unavailable_warning=IDENTITY_STALE_WARNING,
        )

    if resolution is None:
        return compose_breakdown_read_model_v1(timeline, None, asset_overlay=assets)

    resolved_character_ids = {
        str(person.character_id)
        for scene in resolution.scenes
        for person in scene.people
        if person.status == "RESOLVED" and person.character_id
    }
    revision_matches, snapshots = _load_current_character_snapshots(
        project_id=resolution.project_id,
        expected_asset_revision_id=resolution.asset_revision_id,
        character_ids=resolved_character_ids,
    )
    return compose_breakdown_read_model_v1(
        timeline,
        resolution,
        current_asset_revision_matches=revision_matches,
        character_snapshots=snapshots,
        asset_overlay=assets,
    )


__all__ = [
    "BreakdownReadModelError",
    "IDENTITY_PARTIAL_WARNING",
    "IDENTITY_PENDING_WARNING",
    "IDENTITY_STALE_WARNING",
    "compose_breakdown_read_model_v1",
    "load_episode_breakdown_read_model_v1",
]


def load_episode_breakdown_read_model_v1(episode_id: str):
    from engine.app.source_person_assets_v1 import apply_person_mapping
    return apply_person_mapping(episode_id, _load_episode_breakdown_read_model_v1(episode_id))
