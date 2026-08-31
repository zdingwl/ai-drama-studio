from __future__ import annotations

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


def semantic(location: str, subjects: list[dict]) -> dict:
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


def test_pipeline_routes_to_e6_profile() -> None:
    assert pipeline.fusion.FUSION_PROFILE == e6.FUSION_PROFILE
    assert e6.BASE_FUSION_PROFILE == "breakdown-p2-fusion-episode-context-e5-v1"


def test_e6_real_corridor_scene_converges_to_two_anonymous_people() -> None:
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
        semantics=[semantic("公寓走廊", rows[item.ordinal]) for item in shots],
    )

    keys, members, stats = e6._build_subject_cluster_keys([plan], [])

    white_key = keys[("ITEM_2", "subject_A")]
    floral_key = keys[("ITEM_3", "subject_B")]
    assert white_key != floral_key
    assert white_key == keys[("ITEM_12", "subject_B")]
    assert floral_key == keys[("ITEM_11", "subject_A")]
    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.component_bridge_union_count >= 1
    assert stats.final_same_shot_conflict_count == 0


def test_e6_real_living_room_scene_stays_two_anonymous_people() -> None:
    shots = [shot(index) for index in range(13, 31)]
    female_shots = {13, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30}
    male_shots = {13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24, 27, 28, 29, 30}
    semantics: list[dict] = []
    for item in shots:
        subjects: list[dict] = []
        if item.ordinal in female_shots:
            label = "subject_B" if item.ordinal == 30 else "subject_A"
            subjects.append(subject(label, "长发女性，身穿白色露肩上衣和白色裤子。"))
        if item.ordinal in male_shots:
            label = "subject_A" if item.ordinal in {14, 17, 30} else "subject_B"
            subjects.append(subject(label, "短发男性，身穿灰色连帽衫，内搭白色T恤。"))
        semantics.append(semantic("客厅", subjects))

    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=semantics)
    keys, members, stats = e6._build_subject_cluster_keys([plan], [])

    female_key = keys[("ITEM_13", "subject_A")]
    male_key = keys[("ITEM_13", "subject_B")]
    assert female_key != male_key
    assert female_key == keys[("ITEM_30", "subject_B")]
    assert male_key == keys[("ITEM_30", "subject_A")]
    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.final_same_shot_conflict_count == 0


def test_e6_preserves_explicit_long_short_hair_guard() -> None:
    shots = [shot(1), shot(2)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic("客厅", [subject("subject_A", "年轻女性，黑色长发，白色上衣，白色裤子")]),
            semantic("客厅", [subject("subject_A", "年轻女性，黑色短发，白色上衣，白色裤子")]),
        ],
    )

    keys, members, stats = e6._build_subject_cluster_keys([plan], [])

    assert keys[("ITEM_1", "subject_A")] != keys[("ITEM_2", "subject_A")]
    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.final_same_shot_conflict_count == 0
