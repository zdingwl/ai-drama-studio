from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_character_bridge_v1 import (  # noqa: E402
    BreakdownCharacterBridgeError,
    load_episode_character_resolution_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P5 Breakdown ↔ Character safe bridge acceptance.")
    parser.add_argument("episode_id")
    args = parser.parse_args()

    try:
        payload = load_episode_character_resolution_v1(args.episode_id)
    except (LookupError, BreakdownCharacterBridgeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    if payload is None:
        print(json.dumps({
            "status": "NO_CURRENT_BREAKDOWN",
            "episode_id": args.episode_id,
        }, ensure_ascii=False, indent=2))
        return 1

    result = {
        "status": "READY",
        "episode_id": payload.episode_id,
        "breakdown_run_id": payload.breakdown_run_id,
        "scene_count": payload.scene_count,
        "person_count": payload.person_count,
        "resolved_count": payload.resolved_count,
        "unresolved_count": payload.unresolved_count,
        "warnings": payload.warnings,
        "scenes": [
            {
                "scene": scene.scene_ordinal,
                "subject_aware_shot_count": scene.subject_aware_shot_count,
                "people": [
                    {
                        "person": person.scene_person_ref,
                        "display": person.local_display_name,
                        "status": person.status,
                        "character": person.character_name,
                        "support_shots": person.support_shot_ordinals,
                        "basis": person.resolution_basis,
                    }
                    for person in scene.people
                ],
            }
            for scene in payload.scenes
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
