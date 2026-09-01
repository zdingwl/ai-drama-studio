from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1  # noqa: E402
from engine.app.breakdown_read_model_v1 import (  # noqa: E402
    BreakdownReadModelError,
    load_episode_breakdown_read_model_v1,
)
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError  # noqa: E402
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1  # noqa: E402
from engine.app.breakdown_scene_timeline_result_v1 import (  # noqa: E402
    SceneTimelineResultError,
    build_scene_timeline_result_v1,
)
from engine.app.breakdown_serializer_v1 import get_current_breakdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run P6 final Breakdown read-model acceptance on one real Episode."
    )
    parser.add_argument("episode_id")
    args = parser.parse_args()

    try:
        payload_raw = load_episode_breakdown_read_model_v1(args.episode_id)
    except (
        LookupError,
        BreakdownReadModelError,
        SceneTimelineAssemblyError,
        SceneTimelineResultError,
        ValueError,
    ) as exc:
        print(json.dumps({
            "status": "ERROR",
            "episode_id": args.episode_id,
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        return 2

    if payload_raw is None:
        print(json.dumps({
            "status": "NO_CURRENT_BREAKDOWN",
            "episode_id": args.episode_id,
        }, ensure_ascii=False, indent=2))
        return 1

    payload = BreakdownReadModelV1.model_validate(payload_raw)

    # Rebuild frozen G2 independently and prove P6 never rewrites Timeline truth.
    try:
        draft = get_current_breakdown(args.episode_id)
        if draft is None:
            print(json.dumps({
                "status": "SOURCE_CHANGED_DURING_ACCEPTANCE",
                "episode_id": args.episode_id,
                "message": "P6 读取后 Current Breakdown 已变化，请在任务稳定后重跑。",
            }, ensure_ascii=False, indent=2))
            return 3
        frozen_timeline = SceneTimelinePayloadV1.model_validate(
            build_scene_timeline_result_v1(draft)
        ).model_dump(mode="json")
    except (LookupError, SceneTimelineAssemblyError, SceneTimelineResultError, ValueError) as exc:
        print(json.dumps({
            "status": "SOURCE_READ_ERROR",
            "episode_id": args.episode_id,
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        return 3

    rendered_timeline = payload.timeline.model_dump(mode="json")
    timeline_preserved = rendered_timeline == frozen_timeline
    if not timeline_preserved:
        print(json.dumps({
            "status": "FAILED_TIMELINE_MUTATION_GUARD",
            "episode_id": args.episode_id,
            "message": "P6 返回的 timeline 与独立重建的冻结 G2 Timeline 不一致。",
        }, ensure_ascii=False, indent=2))
        return 4

    identity_by_scene = {scene.scene_ordinal: scene for scene in payload.identity.scenes}
    final_scene_by_ordinal = {
        item.scene_ordinal: item.scene
        for item in payload.assets.scenes
    } if payload.assets is not None else {}
    final_props_by_shot = {
        (item.scene_ordinal, item.shot_ordinal): item.props
        for item in payload.assets.shots
    } if payload.assets is not None else {}

    scenes: list[dict[str, object]] = []
    for timeline_scene in payload.timeline.scenes:
        scene_identity = identity_by_scene.get(timeline_scene.ordinal)
        anonymous_by_ref = {person.ref: person.display_name for person in timeline_scene.people}
        final_scene = final_scene_by_ordinal.get(timeline_scene.ordinal)
        scenes.append({
            "scene": timeline_scene.ordinal,
            "g2_title": timeline_scene.title,
            "final_scene": {
                "id": final_scene.id,
                "name": final_scene.name,
                "cover_url": final_scene.cover_url,
            } if final_scene is not None else None,
            "people": [
                {
                    "ref": person.ref,
                    "anonymous_display": anonymous_by_ref.get(person.ref),
                    "final_display": person.display_name,
                    "status": "RESOLVED" if person.character is not None else "ANONYMOUS",
                    "character_id": person.character.id if person.character is not None else None,
                    "character_name": person.character.name if person.character is not None else None,
                    "cover_url": person.character.cover_url if person.character is not None else None,
                }
                for person in scene_identity.people
            ] if scene_identity is not None else [],
            "shots": [
                {
                    "shot": shot.ordinal,
                    "g2_props": [prop.label for prop in shot.props],
                    "final_props": [
                        {
                            "id": prop.id,
                            "name": prop.name,
                            "cover_url": prop.cover_url,
                        }
                        for prop in final_props_by_shot.get((timeline_scene.ordinal, shot.ordinal), [])
                    ],
                }
                for shot in timeline_scene.shots
            ],
        })

    result = {
        "status": "READY",
        "schema_version": payload.schema_version,
        "episode_id": payload.timeline.episode_id,
        "breakdown_run_id": payload.timeline.source_breakdown_run_id,
        "shot_revision_id": payload.timeline.source_shot_revision_id,
        "identity_asset_revision_id": payload.identity.asset_revision_id,
        "final_asset_revision_id": payload.assets.asset_revision_id if payload.assets is not None else None,
        "scene_count": payload.timeline.scene_count,
        "shot_count": payload.timeline.shot_count,
        "resolved_count": payload.identity.resolved_count,
        "unresolved_count": payload.identity.unresolved_count,
        "final_scene_count": sum(
            1 for item in (payload.assets.scenes if payload.assets is not None else []) if item.scene is not None
        ),
        "final_prop_binding_count": sum(
            len(item.props) for item in (payload.assets.shots if payload.assets is not None else [])
        ),
        "timeline_preserved": timeline_preserved,
        "timeline_warnings": payload.timeline.warnings,
        "identity_warnings": payload.identity.warnings,
        "asset_warnings": payload.assets.warnings if payload.assets is not None else [],
        "scenes": scenes,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
