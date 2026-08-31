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
    shots = [shot(index) for index in range(13, 31)]
    semantics: list[dict] = []
    for item in shots:
        ordinal = item.ordinal
        subjects: list[dict] = []
        if ordinal in {13, 15}:
            subjects.append(subject("subject_A", "黑发长发，穿白色上衣和白色裤子。"))
        if ordinal in {13, 14}:
            subjects.append(subject("subject_B", "黑发短发，穿灰色T恤。"))
        if ordinal in {16, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30}:
            subjects.append(subject("subject_A", "长发女性，身穿白色上衣和白色裤子。"))
        if ordinal in {16, 17, 18, 19, 20, 21, 22, 23, 24}:
            subjects.append(subject("subject_B", "短发男性，身穿灰色T恤。"))
        if ordinal in {27, 28, 29}:
            subjects.append(subject("subject_B", "短发，身穿灰色T恤。"))
        if ordinal == 30:
            subjects.append(subject("subject_B", "短发，身穿灰色T恤。"))
        semantics.append(semantic("客厅", subjects))

    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=semantics)
    keys, members, stats = e5._build_subject_cluster_keys([plan], [])

    female_key = keys[("ITEM_13", "subject_A")]
    male_key = keys[("ITEM_13", "subject_B")]
    assert female_key != male_key
    assert female_key == keys[("ITEM_16", "subject_A")]
    assert female_key == keys[("ITEM_30", "subject_A")]
    assert male_key == keys[("ITEM_16", "subject_B")]
    assert male_key == keys[("ITEM_27", "subject_B")]
    assert male_key == keys[("ITEM_30", "subject_B")]
    assert len(members) == 2
    assert stats.cluster_count == 2
    assert stats.cluster_bridge_union_count >= 1
    assert stats.final_same_shot_conflict_count == 0
