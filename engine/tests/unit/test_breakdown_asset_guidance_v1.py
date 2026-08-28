from __future__ import annotations

from pathlib import Path

from engine.app.breakdown_asset_guidance_v1 import (
    GUIDANCE_PROFILE,
    ProjectAssetGuidance,
)


def test_guidance_profile_is_explicitly_p4_and_non_final() -> None:
    guidance = ProjectAssetGuidance(
        project_id="PROJECT_1",
        profile=GUIDANCE_PROFILE,
        shots={},
        breakdown_run_ids=(),
        skipped_episode_ids=("EP_1",),
        warnings=(),
    )

    assert guidance.profile == "breakdown-asset-guidance-p4-v1"
    assert guidance.guided_shot_count == 0
    assert guidance.prop_target_count == 0


def test_guidance_loader_requires_current_ready_exact_revision() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "engine" / "app" / "breakdown_asset_guidance_v1.py").read_text(
        encoding="utf-8"
    )

    assert 'BreakdownRun.is_current.is_(True)' in source
    assert 'BreakdownRun.status.in_(_CONSUMABLE_RUN_STATUSES)' in source
    assert 'BreakdownRun.source_shot_revision_id == revision_id' in source
    assert 'ShotRevision.is_current.is_(True)' in source
    assert 'ShotRevisionItem.revision_id == revision.id' in source
    assert 'draft.source_shot_id_snapshot != item.original_shot_id' in source
    assert 'current_shots.get(item.original_shot_id)' in source


def test_guidance_loader_never_maps_history_by_ordinal_or_timestamp() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "engine" / "app" / "breakdown_asset_guidance_v1.py").read_text(
        encoding="utf-8"
    )

    # Ordinal is allowed only for ordering. There must be no fallback lookup such as
    # shots_by_ordinal[...] or timestamp-nearest remapping for a stale BreakdownRun.
    assert "shots_by_ordinal" not in source
    assert "nearest" not in source.lower()
    assert "source_shot_revision_item_id" in source
