from __future__ import annotations

from engine.app import breakdown_p2_fusion_episode_v5 as e5
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


def semantic(location: str, subjects: list[dict] | None = None) -> dict:
    return {
        "scene": {
            "location_hint": location,
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "",
        },
        "shot": {"summary": "fixture"},
        "subjects": subjects or [],
        "events": [],
        "props": [],
    }


def record(item: p2.P2ShotInput, location: str) -> p2.P2EvidenceRecord:
    return p2.P2EvidenceRecord(
        source_type="VLM_OUTPUT",
        source_id=f"VLM_{item.ordinal}",
        source_start_us=item.start_us,
        source_end_us=item.end_us,
        shot_revision_item_id=item.revision_item_id,
        payload={"semantic": semantic(location)},
    )


def test_pipeline_routes_to_e5_profile() -> None:
    assert pipeline.fusion.FUSION_PROFILE == e5.FUSION_PROFILE
    assert e5.BASE_FUSION_PROFILE == "breakdown-p2-fusion-episode-context-e4-v1"


def test_e5_corridor_qualifier_drift_stays_one_scene_without_direct_cut() -> None:
    shots = tuple(shot(index) for index in range(1, 4))
    records = {
        shots[0].revision_item_id: record(shots[0], "公寓走廊"),
        shots[1].revision_item_id: record(shots[1], "酒店走廊"),
        shots[2].revision_item_id: record(shots[2], "公寓楼道"),
    }

    details = e5._continuity_plan_details(shots, records, [])

    assert len(details) == 1
    assert [item.ordinal for item in details[0].plan.shots] == [1, 2, 3]
    assert details[0].anchor.location == "公寓走廊"


def test_e5_direct_window_new_scene_still_forces_corridor_cut() -> None:
    shots = (shot(1), shot(2), shot(3))
    records = {
        shots[0].revision_item_id: record(shots[0], "公寓走廊"),
        shots[1].revision_item_id: record(shots[1], "酒店走廊"),
        shots[2].revision_item_id: record(shots[2], "酒店走廊"),
    }
    windows = [{
        "shot_scene_hints": [{
            "ordinal": 2,
            "scene_continuity": "NEW_SCENE",
            "scene_basis": "DIRECT",
        }]
    }]

    details = e5._continuity_plan_details(shots, records, windows)

    assert len(details) == 2
    assert [item.ordinal for item in details[0].plan.shots] == [1]
    assert [item.ordinal for item in details[1].plan.shots] == [2, 3]


def test_e5_real_scene_shape_converges_six_fragments_to_two_anonymous_people() -> None:
    """Mirror the accepted real Scene02 evidence instead of weakening it into a generic fixture."""

    shots = [shot(index) for index in range(13, 31)]
    female_by_shot: dict[int, tuple[str, str]] = {
        13: ("subject_A", "黑发长发，穿白色露肩上衣和白色阔腿裤。"),
        15: ("subject_A", "黑色长发，身穿白色露肩上衣和白色裤子。"),
        16: ("subject_A", "长发女性，身穿白色露肩上衣，搭配白色裤子。"),
        18: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        19: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        20: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        21: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        22: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        23: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        24: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        25: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        26: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        27: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        28: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        29: ("subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),
        30: ("subject_B", "长发女性，身穿白色露肩上衣和白色裤子。"),
    }
    male_by_shot: dict[int, tuple[str, str]] = {
        13: ("subject_B", "黑发短发，穿灰色连帽衫，内搭白色T恤。"),
        14: ("subject_A", "短发，身穿灰色连帽衫，内搭白色T恤。"),
        16: ("subject_B", "短发男性，身穿灰色连帽衫，手持手机。"),
        17: ("subject_A", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        18: ("subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        19: ("subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        20: ("subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        21: ("subject_B", "短发，身穿灰色连帽衫，低头看手机。"),
        22: ("subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        23: ("subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        24: ("subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),
        27: ("subject_B", "短发，身穿灰色连帽衫，低头看手机。"),
        28: ("subject_B", "短发，身穿灰色连帽衫，专注操作手机。"),
        29: ("subject_B", "短发，身穿灰色连帽衫。"),
        30: ("subject_A", "短发，身穿灰色连帽衫，手指放在嘴边。"),
    }

    semantics: list[dict] = []
    for item in shots:
        subjects: list[dict] = []
        female = female_by_shot.get(item.ordinal)
        male = male_by_shot.get(item.ordinal)
        if female is not None:
            subjects.append(subject(*female))
        if male is not None:
            subjects.append(subject(*male))
        semantics.append(semantic("客厅", subjects))

    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=semantics)
    keys, members, stats = e5._build_subject_cluster_keys([plan], [])

    female_key = keys[("ITEM_13", "subject_A")]
    male_key = keys[("ITEM_13", "subject_B")]
    assert female_key != male_key
    assert female_key == keys[("ITEM_16", "subject_A")]
    assert female_key == keys[("ITEM_30", "subject_B")]
    assert male_key == keys[("ITEM_16", "subject_B")]
    assert male_key == keys[("ITEM_27", "subject_B")]
    assert male_key == keys[("ITEM_30", "subject_A")]
    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.cluster_bridge_union_count >= 1
    assert stats.final_same_shot_conflict_count == 0


def test_e5_does_not_bridge_explicit_long_hair_to_short_hair() -> None:
    shots = [shot(1), shot(2)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic("客厅", [subject("subject_A", "年轻女性，黑色长发，白色上衣，白色裤子")]),
            semantic("客厅", [subject("subject_A", "年轻女性，黑色短发，白色上衣，白色裤子")]),
        ],
    )

    keys, members, stats = e5._build_subject_cluster_keys([plan], [])

    assert keys[("ITEM_1", "subject_A")] != keys[("ITEM_2", "subject_A")]
    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.final_same_shot_conflict_count == 0
