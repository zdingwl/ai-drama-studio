from __future__ import annotations

from engine.app import breakdown_g1_fusion_replay_v4 as replay
from engine.app import breakdown_g1_subject_hint_resolver_v2 as resolver
from engine.app import breakdown_p2_fusion_episode_v4 as e4
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


def semantic(subjects: list[dict], location: str) -> dict:
    return {
        "scene": {
            "location_hint": location,
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "",
        },
        "shot": {"summary": "fixture"},
        "subjects": subjects,
        "events": [],
        "props": [],
    }


def hint(appearance: str, ordinals: list[int], window_id: str = "window") -> dict:
    return {
        "window_id": window_id,
        "appearance_summary": appearance,
        "continuity_summary": "",
        "shot_ordinals": ordinals,
        "members": [],
    }


def test_hint_resolver_does_not_auto_bind_only_visible_mismatch() -> None:
    observations = [
        e4.SubjectObservation("ITEM_14", 14, "subject_A", "黑发男子，灰卫衣"),
    ]
    indexes = {item.node_id: index for index, item in enumerate(observations)}

    resolved = resolver.resolve_hint_nodes(
        hint("穿白色露肩上衣的女性", [14]), observations, indexes
    )

    assert resolved == []


def test_hint_resolver_accepts_compact_gray_hoodie_aliases() -> None:
    observations = [
        e4.SubjectObservation("ITEM_14", 14, "subject_A", "黑发男子，灰卫衣"),
        e4.SubjectObservation("ITEM_16", 16, "subject_B", "灰衣，短发"),
        e4.SubjectObservation("ITEM_17", 17, "subject_A", "短发，灰连帽衫"),
    ]
    indexes = {item.node_id: index for index, item in enumerate(observations)}

    resolved = resolver.resolve_hint_nodes(
        hint("穿灰色连帽衫的男性", [14, 16, 17]), observations, indexes
    )

    assert resolved == [0, 1, 2]


def test_hint_resolver_picks_supported_person_in_two_person_shot() -> None:
    observations = [
        e4.SubjectObservation("ITEM_16", 16, "subject_A", "长发，白露肩上衣"),
        e4.SubjectObservation("ITEM_16", 16, "subject_B", "灰衣，短发"),
    ]
    indexes = {item.node_id: index for index, item in enumerate(observations)}

    female = resolver.resolve_hint_nodes(
        hint("穿白色露肩上衣的女性", [16]), observations, indexes
    )
    male = resolver.resolve_hint_nodes(
        hint("穿灰色连帽衫的男性", [16]), observations, indexes
    )

    assert female == [0]
    assert male == [1]


def test_replay_v4_compact_scene1_restores_two_women_without_cross_binding() -> None:
    rows: dict[int, list[dict]] = {
        1: [],
        2: [subject("subject_A", "深色长发，白衬衫")],
        3: [subject("subject_A", "灰发卷发，花衬衫"), subject("subject_B", "黑发，白上衣")],
        4: [subject("subject_A", "黑发，白上衣"), subject("subject_B", "灰发卷发，花衬衫")],
        5: [subject("subject_A", "灰发卷发，花衬衫"), subject("subject_B", "黑发，白上衣")],
        6: [subject("subject_A", "灰发卷曲，花衬衫")],
        7: [subject("subject_A", "黑发长直，白露肩装")],
        8: [subject("subject_A", "白露肩装")],
        9: [subject("subject_A", "黑发长直，白露肩装"), subject("subject_B", "灰发卷曲，花衬衫")],
        10: [subject("subject_A", "灰发卷曲，花衬衫")],
        11: [subject("subject_A", "灰发老妇，花衬衫，米色裤"), subject("subject_B", "黑发年轻女性，白上衣，白裤")],
        12: [subject("subject_A", "黑发，白露肩上衣，白裤")],
    }
    shots = [shot(index) for index in range(1, 13)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[semantic(rows[item.ordinal], "公寓走廊") for item in shots],
    )
    windows = [{
        "window_id": "window-0001",
        "subject_continuity_hints": [
            hint("穿白色上衣的年轻女性", list(range(1, 13)), "window-0001"),
            hint("穿花衬衫的老年女性", list(range(2, 13)), "window-0001"),
        ],
    }]

    clusters, conflicts = replay._candidate_clusters(plan, windows)

    assert conflicts == 0
    assert len(clusters) == 2
    shot_sets = [set(item["shot_ordinals"]) for item in clusters]
    assert {2, 3, 4, 5, 7, 8, 9, 11, 12} in shot_sets
    assert {3, 4, 5, 6, 9, 10, 11} in shot_sets


def test_replay_v4_compact_scene2_restores_woman_and_man_to_two() -> None:
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
        index=2,
        shots=shots,
        semantics=[semantic(rows[item.ordinal], "客厅") for item in shots],
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

    clusters, conflicts = replay._candidate_clusters(plan, windows)

    assert conflicts == 0
    assert len(clusters) == 2
    assert sorted(len(item["shot_ordinals"]) for item in clusters) == [15, 16]
    assert all(len(set(item["shot_ordinals"])) == len(item["shot_ordinals"]) for item in clusters)
