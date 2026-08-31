from __future__ import annotations

from engine.app import breakdown_g1_fusion_replay_v3 as replay
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
            "location_hint": "公寓走廊",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "",
        },
        "shot": {"summary": "fixture"},
        "subjects": subjects,
        "events": [],
        "props": [],
    }


def test_v3_scene01_shape_converges_white_long_hair_and_floral_curly_hair_to_two() -> None:
    shots = [shot(index) for index in range(1, 13)]
    rows: dict[int, list[dict]] = {
        1: [],
        2: [subject("subject_A", "深色长发，面部妆容精致，身穿白色上衣。")],
        3: [
            subject("subject_A", "深色长发，身穿白色露肩上衣，背对镜头。"),
            subject("subject_B", "灰白色卷发，身穿橙色花卉图案衬衫，手提黑色塑料袋。"),
        ],
        4: [
            subject("subject_A", "深色长发，身穿白色露肩上衣和白色长裤。"),
            subject("subject_B", "灰白卷发，穿橙色花卉图案衬衫。"),
        ],
        5: [
            subject("subject_A", "深色长发，身穿白色露肩上衣，侧脸可见。"),
            subject("subject_B", "灰白卷发，穿橙色花卉图案衬衫。"),
        ],
        6: [subject("subject_A", "灰白卷发，穿橙色花卉图案衬衫，面部有皱纹")],
        7: [subject("subject_B", "黑长发，穿白色露肩上衣，高腰裤")],
        8: [subject("subject_B", "黑长发，穿白色露肩上衣，高腰裤")],
        9: [
            subject("subject_B", "黑长发，穿白色露肩上衣，高腰裤"),
            subject("subject_A", "灰白卷发，穿橙色花卉图案衬衫，穿浅色裤子"),
        ],
        10: [subject("subject_A", "灰白卷发，穿橙色花卉图案衬衫，穿浅色裤子")],
        11: [
            subject("subject_A", "灰发卷发，穿橙色花卉图案衬衫和米色长裤，脚穿黑色凉鞋。"),
            subject("subject_B", "黑发长发，穿白色露肩上衣和白色阔腿裤，脚穿浅色高跟鞋。"),
        ],
        12: [subject("subject_B", "黑发长发，穿白色露肩上衣和白色阔腿裤。")],
    }
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[semantic(rows[item.ordinal]) for item in shots],
    )

    clusters, conflicts = replay._candidate_clusters(plan, [])

    assert conflicts == 0
    assert len(clusters) == 2
    shot_sets = [set(item["shot_ordinals"]) for item in clusters]
    assert {2, 3, 4, 5, 7, 8, 9, 11, 12} in shot_sets
    assert {3, 4, 5, 6, 9, 10, 11} in shot_sets


def test_v3_does_not_merge_two_cooccurring_people_after_component_phase() -> None:
    shots = [shot(index) for index in range(1, 5)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic([
                subject("subject_A", "长发女性，白色露肩上衣，白色裤子"),
                subject("subject_B", "短发男性，灰色连帽衫，白色T恤"),
            ])
            for _item in shots
        ],
    )

    clusters, conflicts = replay._candidate_clusters(plan, [])

    assert conflicts == 0
    assert len(clusters) == 2
    assert all(item["shot_ordinals"] == [1, 2, 3, 4] for item in clusters)


def test_v3_preserves_explicit_long_short_conflict_guard() -> None:
    shots = [shot(1), shot(2)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic([subject("subject_A", "年轻女性，黑色长发，白色上衣，白色裤子")]),
            semantic([subject("subject_A", "年轻女性，黑色短发，白色上衣，白色裤子")]),
        ],
    )

    clusters, conflicts = replay._candidate_clusters(plan, [])

    assert conflicts == 0
    assert len(clusters) == 2
