"""P6：冻结 Scene Timeline + P5 Final Character 的最终用户阅读组合层。

本模块绝不做身份推断。唯一允许的链路是：

    G2 Scene-local P* --(same run/revision + same scene/ref)--> P5 RESOLVED
        --> current AssetRevision --> existing Final Character

任何锚点、人物编号或当前资产版本不一致时都 fail closed：保留完整 G2 Timeline，人物继续匿名。
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
from engine.app.breakdown_read_model_contract_v1 import (
    BREAKDOWN_READ_MODEL_SCHEMA_VERSION,
    BreakdownReadIdentityOverlayV1,
    BreakdownReadModelV1,
)
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.breakdown_scene_timeline_result_v1 import build_scene_timeline_result_v1
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.studio_v2 import Character, get_session


IDENTITY_PENDING_WARNING = "人物资产尚未完成最终身份确认，当前继续使用匿名人物显示。"
IDENTITY_PARTIAL_WARNING = "部分人物尚未完成最终身份确认，当前仍以匿名人物显示。"
IDENTITY_STALE_WARNING = "人物资产与当前拉片版本暂不一致，当前继续使用匿名人物显示。"


class BreakdownReadModelError(RuntimeError):
    """P6 自身 Contract 无法安全组合；不会用于放宽 G2/P5。"""


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


def _load_current_character_snapshots(
    *,
    project_id: str,
    expected_asset_revision_id: str | None,
    character_ids: set[str],
) -> tuple[bool, dict[str, dict[str, str | None]]]:
    """Verify P5 still points at the current asset revision, then load display-only Character fields."""

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

        rows = list(session.scalars(select(Character).where(
            Character.project_id == project_id,
            Character.id.in_(tuple(sorted(character_ids))),
        )).all())
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
) -> dict[str, Any]:
    """Pure P6 composition gate used by API and deterministic tests.

    ``timeline`` is validated then embedded unchanged. Identity overlay is accepted only when every
    version anchor and every Scene-local P* row agrees with frozen G2/P5.
    """

    timeline = (
        timeline_payload
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload)
    )
    normalized_timeline = timeline.model_dump(mode="json")

    if resolution_payload is None:
        identity = _anonymous_identity(timeline, warning=IDENTITY_PENDING_WARNING)
        return BreakdownReadModelV1(
            schema_version=BREAKDOWN_READ_MODEL_SCHEMA_VERSION,
            timeline=timeline,
            identity=identity,
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
        identity = _anonymous_identity(timeline, warning=IDENTITY_STALE_WARNING)
        return BreakdownReadModelV1(
            timeline=timeline,
            identity=identity,
        ).model_dump(mode="json")

    timeline_scenes = {scene.ordinal: scene for scene in timeline.scenes}
    resolution_scenes = {scene.scene_ordinal: scene for scene in resolution.scenes}
    if set(timeline_scenes) != set(resolution_scenes):
        identity = _anonymous_identity(timeline, warning=IDENTITY_STALE_WARNING)
        return BreakdownReadModelV1(timeline=timeline, identity=identity).model_dump(mode="json")

    snapshots = character_snapshots or {}
    overlay_scenes: list[dict[str, object]] = []
    resolved_count = 0
    unresolved_count = 0

    # First prove the whole Scene/P* numbering surface is identical before resolving a single person.
    for scene_ordinal, scene in timeline_scenes.items():
        bridge_scene = resolution_scenes[scene_ordinal]
        timeline_people = {person.ref: person for person in scene.people}
        bridge_people = {person.scene_person_ref: person for person in bridge_scene.people}
        if set(timeline_people) != set(bridge_people):
            identity = _anonymous_identity(timeline, warning=IDENTITY_STALE_WARNING)
            return BreakdownReadModelV1(timeline=timeline, identity=identity).model_dump(mode="json")
        for ref, person in timeline_people.items():
            bridge_person = bridge_people[ref]
            if bridge_person.local_display_name != person.display_name:
                identity = _anonymous_identity(timeline, warning=IDENTITY_STALE_WARNING)
                return BreakdownReadModelV1(timeline=timeline, identity=identity).model_dump(mode="json")
            if bridge_person.status == "RESOLVED":
                character_id = str(bridge_person.character_id or "")
                snapshot = snapshots.get(character_id)
                if (
                    not snapshot
                    or snapshot.get("id") != character_id
                    or snapshot.get("name") != bridge_person.character_name
                ):
                    identity = _anonymous_identity(timeline, warning=IDENTITY_STALE_WARNING)
                    return BreakdownReadModelV1(timeline=timeline, identity=identity).model_dump(mode="json")

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
    result = BreakdownReadModelV1(timeline=timeline, identity=identity).model_dump(mode="json")

    # Explicit leak/mutation guard: P6 may never rewrite any frozen Timeline value.
    if result["timeline"] != normalized_timeline:
        raise BreakdownReadModelError("P6 不允许改写 Scene Timeline")
    return result


def load_episode_breakdown_read_model_v1(episode_id: str) -> dict[str, Any] | None:
    """Read current user-facing G2 result and safely add current Final Character display identity."""

    draft = get_current_breakdown(episode_id)
    if draft is None:
        return None
    timeline = SceneTimelinePayloadV1.model_validate(build_scene_timeline_result_v1(draft))

    try:
        resolution = load_episode_character_resolution_v1(episode_id)
    except BreakdownCharacterBridgeError:
        return compose_breakdown_read_model_v1(
            timeline,
            None,
        )

    if resolution is None:
        return compose_breakdown_read_model_v1(timeline, None)

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
    )


__all__ = [
    "BreakdownReadModelError",
    "IDENTITY_PARTIAL_WARNING",
    "IDENTITY_PENDING_WARNING",
    "IDENTITY_STALE_WARNING",
    "compose_breakdown_read_model_v1",
    "load_episode_breakdown_read_model_v1",
]
