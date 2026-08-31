from __future__ import annotations

from engine.app import breakdown_g1_compact_appearance_normalizer_v1 as normalizer
from engine.app import breakdown_g1_fusion_replay_v1 as v1
from engine.app import breakdown_g1_fusion_replay_v5 as replay
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


def hint(appearance: str, ordinals: list[int]) -> dict:
    return {
        "window_id": "window-0004",
        "appearance_summary": appearance,
        "continuity_summary": "",
        "shot_ordinals": ordinals,
        "members": [],
    }


def test_compact_alias_normalizer_recovers_stable_gray_hoodie_tokens() -> None:
    assert normalizer.normalize_appearance("短发，灰卫衣") == "短发，灰色连帽衫"
    assert normalizer.normalize_appearance("白露肩装") == "白色露肩上衣"
    assert normalizer.normalize_appearance("白露 肩上衣") == "白露肩上衣"


def test_normalized_compact_adjacent_male_observations_reenter_existing_fallback() -> None:
    observations = [
        e4.SubjectObservation("ITEM_29", 29, "subject_A", "短发，灰卫衣"),
        e4.SubjectObservation("ITEM_30", 30, "subject_A", "短发，灰卫衣"),
        e4.SubjectObservation("ITEM_30", 30, "subject_B", "长发，白上衣"),
    ]
    normalized = normalizer.normalize_observations(observations)

    pairs = v1._candidate_fallback_pairs(normalized)

    assert (0, 1) in pairs
    assert (0, 2) not in pairs


def test_replay_v5_recovers_shot30_male_singleton_without_same_shot_merge() -> None:
    shots = [shot(index) for index in range(27, 31)]
    rows = {
        27: [subject("subject_A", "长发，白上衣"), subject("subject_B", "短发，灰卫衣")],
        28: [subject("subject_A", "短发，灰卫衣"), subject("subject_B", "长发，白上衣")],
        29: [subject("subject_A", "短发，灰卫衣")],
        30: [subject("subject_A", "短发，灰卫衣"), subject("subject_B", "长发，白上衣")],
    }
    plan = legacy._SegmentPlan(
        index=2,
        shots=shots,
        semantics=[semantic(rows[item.ordinal]) for item in shots],
    )
    windows = [{
        "window_id": "window-0004",
        "subject_continuity_hints": [
            hint("穿灰色连帽衫的男子", [27, 28, 29]),
            hint("穿白色露肩上衣的女子", [27, 28, 29, 30]),
        ],
    }]

    clusters, conflicts = replay._candidate_clusters(plan, windows)

    assert conflicts == 0
    assert len(clusters) == 2
    shot_sets = sorted((set(item["shot_ordinals"]) for item in clusters), key=lambda item: (len(item), sorted(item)))
    assert {27, 28, 30} in shot_sets
    assert {27, 28, 29, 30} in shot_sets
    assert all(len(item["shot_ordinals"]) == len(set(item["shot_ordinals"])) for item in clusters)
