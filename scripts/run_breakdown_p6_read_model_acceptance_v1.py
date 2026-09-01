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
    except (LookupError, BreakdownReadModelError, SceneTimelineResultError, ValueError) as exc:
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

    # Rebuild the frozen G2 result independently and prove P6 did not rewrite it.
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
    except (LookupError, SceneTimelineResultError, ValueError) as exc:
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

    timeline_scenes = {scene.ordinal: scene for scene in payload.timeline.scenes}
    scenes: list[dict[str, object]] = []
    for scene_identity in payload.identity.scenes:
        timeline_scene = timeline_scenes.get(scene_identity.scene_ordinal)
        anonymous_by_ref = {
            person.ref: person.display_name
            for person in timeline_scene.people
        } if timeline_scene is not None else {}
        scenes.append({
            "scene": scene_identity.scene_ordinal,
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
            ],
        })

    result = {
        "status": "READY",
        "schema_version": payload.schema_version,
        "episode_id": payload.timeline.episode_id,
        "breakdown_run_id": payload.timeline.source_breakdown_run_id,
        "shot_revision_id": payload.timeline.source_shot_revision_id,
        "asset_revision_id": payload.identity.asset_revision_id,
        "scene_count": payload.timeline.scene_count,
        "shot_count": payload.timeline.shot_count,
        "resolved_count": payload.identity.resolved_count,
        "unresolved_count": payload.identity.unresolved_count,
        "timeline_preserved": timeline_preserved,
        "timeline_warnings": payload.timeline.warnings,
        "identity_warnings": payload.identity.warnings,
        "scenes": scenes,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
