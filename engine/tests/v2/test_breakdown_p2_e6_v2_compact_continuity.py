from __future__ import annotations

from engine.app import breakdown_g1_fusion_replay_v5 as replay_v5
from engine.app import breakdown_p2_fusion_episode_v6 as e6
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_pipeline_v1 as pipeline
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


def hint(appearance: str, ordinals: list[int], window_id: str) -> dict:
    return {
        "window_id": window_id,
        "appearance_summary": appearance,
        "continuity_summary": "",
        "shot_ordinals": ordinals,
        "members": [],
    }


def test_e6_v2_routes_pipeline_to_replay_v5_policies() -> None:
    assert pipeline.fusion is e6
    assert e6.FUSION_PROFILE == "breakdown-p2-fusion-episode-context-e6-v2"
    assert e6.FUSION_VERSION == "2"
    assert e6.SUBJECT_CONTINUITY_POLICY == replay_v5.SUBJECT_POLICY
    assert e6.WINDOW_HINT_RESOLUTION_POLICY == replay_v5.WINDOW_HINT_RESOLUTION_POLICY
    assert e6.COMPACT_APPEARANCE_POLICY == replay_v5.COMPACT_APPEARANCE_POLICY


def test_e6_v2_compact_living_room_restores_two_people_without_same_shot_conflict() -> None:
    rows: dict[int, list[dict]] = {
        13: [subject("subject_A", "灰衣男子，手持手机"), subject("subject_B", "白衣女性，长发")],
        14: [subject("subject_A", "黑发男子，灰卫衣")],
        15: [subject("subject_A", "黑发女性，白露肩上衣")],
        16: [subject("subject_A", "长发，白露肩上衣"), subject("subject_B", "灰衣，短发")],
        17: [subject("subject_A", "短发，灰连帽衫")],
        18: [subject("subject_A", "长发，白露肩上衣"), subject("subject_B", "短发，灰连帽衫")],
        19: [subject("subject_A", "短发，灰连帽衫"), subject("subject_B", "长发，白露肩上衣")],
        20: [subject("subject_A", "长发，白露肩上衣"), subject("subject_B", "灰衣，短发")],
        21: [subject("subject_A", "灰连帽衫，黑发"), subject("subject_B", "白露肩上衣")],
        22: [subject("subject_A", "灰连帽衫，黑发"), subject("subject_B", "白露肩上衣")],
        23: [subject("subject_A", "白露肩上衣，长发"), subject("subject_B", "灰连帽衫，黑发")],
        24: [subject("subject_A", "灰连帽衫，黑发"), subject("subject_B", "白露肩上衣")],
        25: [subject("subject_A", "白露肩上衣，长发")],
        26: [subject("subject_A", "长发，白上衣")],
        27: [subject("subject_A", "长发，白上衣"), subject("subject_B", "短发，灰卫衣")],
        28: [subject("subject_A", "短发，灰卫衣"), subject("subject_B", "长发，白上衣")],
        29: [subject("subject_A", "短发，灰卫衣")],
        30: [subject("subject_A", "短发，灰卫衣"), subject("subject_B", "长发，白上衣")],
    }
    shots = [shot(index) for index in range(13, 31)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[semantic(rows[item.ordinal]) for item in shots],
    )
    windows = [
        {
            "window_id": "window-0002",
            "subject_continuity_hints": [
                hint("穿白色露肩上衣的女性", [9, 13, 14, 15, 16, 17, 18, 19, 20], "window-0002"),
                hint("穿灰色连帽衫的男性", [13, 14, 15, 16, 17, 18, 19, 20], "window-0002"),
            ],
        },
        {
            "window_id": "window-0003",
            "subject_continuity_hints": [
                hint("穿白色露肩上衣的女性", list(range(18, 27)), "window-0003"),
                hint("穿灰色连帽衫的男性", list(range(19, 27)), "window-0003"),
            ],
        },
        {
            "window_id": "window-0004",
            "subject_continuity_hints": [
                hint("穿灰色连帽衫的男子", [24, 25, 27, 28, 29], "window-0004"),
                hint("穿白色露肩上衣的女子", [24, 25, 26, 27, 28, 29, 30], "window-0004"),
            ],
        },
    ]

    keys, members, stats = e6._build_subject_cluster_keys([plan], windows)

    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.final_same_shot_conflict_count == 0
    assert keys[("ITEM_13", "subject_A")] == keys[("ITEM_30", "subject_A")]
    assert keys[("ITEM_13", "subject_B")] == keys[("ITEM_30", "subject_B")]
    assert keys[("ITEM_30", "subject_A")] != keys[("ITEM_30", "subject_B")]
