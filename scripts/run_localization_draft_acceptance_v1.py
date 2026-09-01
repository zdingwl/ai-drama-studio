from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.localization_draft_contract_v1 import LocalizationDraftViewV1  # noqa: E402
from engine.app.localization_draft_v1 import (  # noqa: E402
    get_current_localization_draft,
    list_localization_revisions,
    localization_source_fingerprint_v1,
)
from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1  # noqa: E402
from engine.app.localization_source_v1 import load_episode_localization_source_v1  # noqa: E402


def _entries(view: LocalizationDraftViewV1):
    for scene in view.scenes:
        for shot in scene.shots:
            yield from shot.entries


def _source_rows(source: LocalizationSourcePackageV1) -> dict[str, tuple[str, int, int, str]]:
    rows: dict[str, tuple[str, int, int, str]] = {}
    for scene in source.scenes:
        for shot in scene.shots:
            for item in shot.source_dialogue:
                rows[item.source_key] = ("dialogue", item.start_us, item.end_us, item.source_text)
            for item in shot.source_on_screen_text:
                rows[item.source_key] = ("on_screen_text", item.start_us, item.end_us, item.source_text)
    return rows


def _current_source_truth_matches(view: LocalizationDraftViewV1, source: LocalizationSourcePackageV1) -> bool:
    expected = _source_rows(source)
    actual = {
        item.source_key: (item.kind, item.start_us, item.end_us, item.source_text)
        for item in _entries(view)
    }
    return actual == expected


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only P7.2 Localization Draft acceptance for one real Episode.")
    parser.add_argument("episode_id")
    args = parser.parse_args()

    try:
        source_raw = load_episode_localization_source_v1(args.episode_id)
        draft_raw = get_current_localization_draft(args.episode_id)
        revisions = list_localization_revisions(args.episode_id)
    except Exception as exc:
        print(json.dumps({
            "status": "ERROR",
            "episode_id": args.episode_id,
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        return 2

    if source_raw is None:
        print(json.dumps({
            "status": "NO_CURRENT_SOURCE",
            "episode_id": args.episode_id,
            "message": "先完成并确认当前 P7.1 本土化源包。",
        }, ensure_ascii=False, indent=2))
        return 1

    source = LocalizationSourcePackageV1.model_validate(source_raw)
    if draft_raw is None:
        print(json.dumps({
            "status": "NOT_STARTED",
            "episode_id": args.episode_id,
            "source_schema_version": source.schema_version,
            "source_ready": True,
            "message": "当前剧集还没有 Localization Draft；runner 不会自动创建或修改正式稿件。",
        }, ensure_ascii=False, indent=2))
        return 1

    view = LocalizationDraftViewV1.model_validate(draft_raw)
    current_fingerprint = localization_source_fingerprint_v1(source)
    source_anchor_current = view.source_fingerprint == current_fingerprint and not view.stale
    source_truth_preserved = _current_source_truth_matches(view, source) if source_anchor_current else None

    current_revisions = [item for item in revisions if item.get("is_current")]
    numbers = [int(item["revision"]) for item in revisions]
    revision_history_valid = (
        len(current_revisions) == 1
        and bool(revisions)
        and revisions[0].get("id") == view.revision_id
        and numbers == sorted(set(numbers), reverse=True)
    )

    entries = list(_entries(view))
    pending = sum(item.decision == "PENDING" for item in entries)
    localize_missing_final = sum(
        item.decision == "LOCALIZE" and not (item.final_text or "").strip()
        for item in entries
    )
    final_state_valid = True
    if view.status in {"IN_REVIEW", "FINAL"}:
        final_state_valid = pending == 0 and localize_missing_final == 0

    acceptance_ready = (
        source_anchor_current
        and source_truth_preserved is True
        and revision_history_valid
        and final_state_valid
    )

    print(json.dumps({
        "status": "READY" if acceptance_ready else "NEEDS_ATTENTION",
        "schema_version": view.schema_version,
        "project_id": view.project_id,
        "episode_id": view.episode_id,
        "draft_status": view.status,
        "revision_id": view.revision_id,
        "revision": view.revision,
        "revision_count": len(revisions),
        "current_revision_count": len(current_revisions),
        "source_breakdown_run_id": view.source_breakdown_run_id,
        "source_shot_revision_id": view.source_shot_revision_id,
        "source_asset_revision_id": view.source_asset_revision_id,
        "source_anchor_current": source_anchor_current,
        "source_truth_preserved": source_truth_preserved,
        "revision_history_valid": revision_history_valid,
        "progress": view.progress.model_dump(mode="json"),
        "localize_missing_final": localize_missing_final,
        "review_or_final_state_valid": final_state_valid,
        "warnings": view.warnings,
    }, ensure_ascii=False, indent=2))
    return 0 if acceptance_ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
