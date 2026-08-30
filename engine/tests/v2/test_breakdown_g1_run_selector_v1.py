from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from engine.app import breakdown_g1_run_selector_v1 as selector


def _run(
    run_id: str,
    *,
    completed_minutes: int,
    current: bool,
    profile: str | None = selector.FAST_GROUNDED_PROFILE,
) -> SimpleNamespace:
    started = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)
    metadata = {
        "p2_sidecar": {
            "VLM": {
                "provider": "qwen3-vl",
                "model": "Qwen3-VL-4B-Instruct",
                "metadata": {
                    "production_vlm_profile": profile,
                    "fast_grounded_schema": profile,
                    "exact_shot_grounding_profile": "breakdown-p2-vlm-exact-shot-frame-grounding-v1",
                    "visual_truth_policy": "exact-shot-frames-over-window-context-v1",
                },
            }
        }
    }
    return SimpleNamespace(
        id=run_id,
        project_id="PROJECT_1",
        episode_id="EPISODE_1",
        status="READY",
        is_current=current,
        started_at=started,
        completed_at=started + timedelta(minutes=completed_minutes),
        provider_metadata_json=json.dumps(metadata),
    )


def test_vlm_profile_snapshot_identifies_fast_grounded_run() -> None:
    snapshot = selector._vlm_profile_snapshot(
        _run("RUN_FG", completed_minutes=10, current=True)
    )

    assert snapshot["production_vlm_profile"] == selector.FAST_GROUNDED_PROFILE
    assert snapshot["is_fast_grounded"] is True
    assert snapshot["visual_truth_policy"] == "exact-shot-frames-over-window-context-v1"


def test_choose_candidate_prefers_current_for_episode_mode() -> None:
    newest_not_current = _run("RUN_NEW", completed_minutes=20, current=False)
    older_current = _run("RUN_CURRENT", completed_minutes=10, current=True)

    chosen = selector._choose_fast_grounded_candidate(
        [newest_not_current, older_current],
        prefer_current=True,
    )

    assert chosen.id == "RUN_CURRENT"


def test_choose_candidate_uses_newest_for_latest_mode_and_skips_legacy() -> None:
    legacy = _run(
        "RUN_LEGACY",
        completed_minutes=30,
        current=True,
        profile="breakdown-p2-vlm-episode-context-v2",
    )
    newest_fast = _run("RUN_FAST_NEW", completed_minutes=20, current=False)
    older_fast = _run("RUN_FAST_OLD", completed_minutes=10, current=True)

    chosen = selector._choose_fast_grounded_candidate(
        [legacy, newest_fast, older_fast],
        prefer_current=False,
    )

    assert chosen.id == "RUN_FAST_NEW"


def test_choose_candidate_returns_none_when_only_legacy_runs_exist() -> None:
    legacy = _run(
        "RUN_LEGACY",
        completed_minutes=10,
        current=True,
        profile="breakdown-p2-vlm-episode-context-v2",
    )

    assert selector._choose_fast_grounded_candidate(
        [legacy],
        prefer_current=False,
    ) is None
