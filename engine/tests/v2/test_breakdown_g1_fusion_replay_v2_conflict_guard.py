from __future__ import annotations

from engine.app import breakdown_g1_fusion_replay_v2 as replay
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2


def shot(ordinal: int) -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id=f"ITEM_{ordinal}",
        original_shot_id=f"SHOT_{ordinal}",
        ordinal=ordinal,
        start_us=(ordinal - 1) * 1_000_000,
        end_us=ordinal * 1_000_000,
        duration_us=1_000_000,
        reference_clip_path=f"unused-{ordinal}.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def subject(label: str, appearance: str) -> dict:
    return {
        "label": label,
        "appearance_summary": appearance,
        "activity_summary": "",
        "screen_position": "",
        "visibility": "FULL",
        "speaking_state": "UNKNOWN",
    }


def semantic(subjects: list[dict]) -> dict:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "",
        },
        "shot": {"summary": "fixture"},
        "subjects": subjects,
        "events": [],
        "props": [],
    }


def plan_with_long_then_short() -> legacy._SegmentPlan:
    shots = [shot(1), shot(2)]
    return legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic([subject("subject_A", "年轻女性，黑色长发，白色上衣，白色裤子")]),
            semantic([subject("subject_A", "年轻女性，黑色短发，白色上衣，白色裤子")]),
        ],
    )


def test_observation_fallback_does_not_override_explicit_long_short_conflict() -> None:
    clusters, conflicts = replay._candidate_clusters(plan_with_long_then_short(), [])

    assert len(clusters) == 2
    assert conflicts == 0
    assert clusters[0]["shot_ordinals"] == [1]
    assert clusters[1]["shot_ordinals"] == [2]


def test_window_hint_does_not_override_exact_shot_long_short_conflict() -> None:
    windows = [{
        "window_id": "window-0001",
        "subject_continuity_hints": [{
            "appearance_summary": "年轻女性，白色上衣，白色裤子",
            "continuity_summary": "故意错误的连续性提示",
            "shot_ordinals": [1, 2],
            "members": [
                {"revision_item_id": "ITEM_1", "ordinal": 1, "label": "subject_A"},
                {"revision_item_id": "ITEM_2", "ordinal": 2, "label": "subject_A"},
            ],
        }],
    }]

    clusters, conflicts = replay._candidate_clusters(plan_with_long_then_short(), windows)

    assert len(clusters) == 2
    assert conflicts == 0
    assert clusters[0]["shot_ordinals"] == [1]
    assert clusters[1]["shot_ordinals"] == [2]
