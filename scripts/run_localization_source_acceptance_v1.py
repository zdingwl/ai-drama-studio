from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1  # noqa: E402
from engine.app.breakdown_read_model_v1 import load_episode_breakdown_read_model_v1  # noqa: E402
from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1  # noqa: E402
from engine.app.localization_source_v1 import LocalizationSourceError, load_episode_localization_source_v1  # noqa: E402


def _source_truth_matches(package: LocalizationSourcePackageV1, read_model: BreakdownReadModelV1) -> bool:
    if package.episode_id != read_model.timeline.episode_id:
        return False
    if package.source_breakdown_run_id != read_model.timeline.source_breakdown_run_id:
        return False
    if package.source_shot_revision_id != read_model.timeline.source_shot_revision_id:
        return False

    source_scenes = {scene.ordinal: scene for scene in read_model.timeline.scenes}
    if set(source_scenes) != {scene.ordinal for scene in package.scenes}:
        return False

    for packaged_scene in package.scenes:
        source_scene = source_scenes[packaged_scene.ordinal]
        source_shots = {shot.ordinal: shot for shot in source_scene.shots}
        if set(source_shots) != {shot.ordinal for shot in packaged_scene.shots}:
            return False
        for packaged_shot in packaged_scene.shots:
            source_shot = source_shots[packaged_shot.ordinal]
            if packaged_shot.visual_description != source_shot.visual_description:
                return False
            if len(packaged_shot.source_dialogue) != len(source_shot.dialogue):
                return False
            if len(packaged_shot.source_on_screen_text) != len(source_shot.on_screen_text):
                return False
            for packaged, source in zip(packaged_shot.source_dialogue, source_shot.dialogue, strict=True):
                if (
                    packaged.start_us != source.start_us
                    or packaged.end_us != source.end_us
                    or packaged.source_text != source.text
                ):
                    return False
            for packaged, source in zip(packaged_shot.source_on_screen_text, source_shot.on_screen_text, strict=True):
                if (
                    packaged.start_us != source.start_us
                    or packaged.end_us != source.end_us
                    or packaged.source_text != source.text
                ):
                    return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P7.1 localization-source acceptance on one real Episode.")
    parser.add_argument("episode_id")
    args = parser.parse_args()

    try:
        package_raw = load_episode_localization_source_v1(args.episode_id)
        read_model_raw = load_episode_breakdown_read_model_v1(args.episode_id)
    except (LookupError, LocalizationSourceError, ValueError) as exc:
        print(json.dumps({
            "status": "ERROR",
            "episode_id": args.episode_id,
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        return 2

    if package_raw is None or read_model_raw is None:
        print(json.dumps({
            "status": "NO_CURRENT_SOURCE",
            "episode_id": args.episode_id,
        }, ensure_ascii=False, indent=2))
        return 1

    package = LocalizationSourcePackageV1.model_validate(package_raw)
    read_model = BreakdownReadModelV1.model_validate(read_model_raw)
    source_truth_preserved = _source_truth_matches(package, read_model)
    if not source_truth_preserved:
        print(json.dumps({
            "status": "FAILED_SOURCE_MUTATION_GUARD",
            "episode_id": args.episode_id,
            "message": "P7 source dialogue/OCR/visual facts no longer match the independently loaded P6 source.",
        }, ensure_ascii=False, indent=2))
        return 3

    scenes = []
    for scene in package.scenes:
        scenes.append({
            "scene": scene.ordinal,
            "g2_title": scene.title,
            "final_scene": scene.final_scene.name if scene.final_scene else None,
            "people": [person.display_name for person in scene.people],
            "shots": [
                {
                    "shot": shot.ordinal,
                    "dialogue_count": len(shot.source_dialogue),
                    "ocr_count": len(shot.source_on_screen_text),
                    "final_props": [prop.name for prop in shot.final_props],
                    "reference_url": shot.reference_url,
                }
                for shot in scene.shots
            ],
        })

    print(json.dumps({
        "status": package.status,
        "schema_version": package.schema_version,
        "project_id": package.project_id,
        "episode_id": package.episode_id,
        "source_language": package.source_language,
        "target_language": package.target_language,
        "target_region": package.target_region,
        "breakdown_run_id": package.source_breakdown_run_id,
        "shot_revision_id": package.source_shot_revision_id,
        "asset_revision_id": package.source_asset_revision_id,
        "scene_count": package.scene_count,
        "shot_count": package.shot_count,
        "source_dialogue_count": package.source_dialogue_count,
        "source_on_screen_text_count": package.source_on_screen_text_count,
        "source_truth_preserved": source_truth_preserved,
        "warnings": package.warnings,
        "scenes": scenes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
