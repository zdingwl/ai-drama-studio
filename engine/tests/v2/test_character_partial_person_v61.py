from __future__ import annotations

import numpy as np

from engine.app import character_observation_v6 as observation_v61
from engine.app import character_tracking_v6 as tracking
from engine.app import character_visual_v5 as v5


def partial(
    *,
    at_us: int,
    local_us: int,
    bbox: tuple[int, int, int, int] = (600, 120, 120, 720),
    score: float = 0.18,
    reid: tuple[float, ...] = (1.0, 0.0, 0.0),
    face_visible: bool = False,
    detection_source: str = "v6.2-yolox-partial",
) -> v5.Observation:
    return v5.Observation(
        shot_id="SHOT_1",
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=1,
        source_time_us=at_us,
        local_time_us=local_us,
        bbox=bbox,
        face_bbox=(620, 140, 50, 50) if face_visible else None,
        reference_path="unused.mp4",
        detection_score=score,
        face_embedding=np.asarray([1.0, 0.0, 0.0], dtype=np.float32) if face_visible else None,
        reid_embedding=np.asarray(reid, dtype=np.float32),
        body_hist=None,
        face_visible=face_visible,
        detection_source=detection_source,
        frame_width=720,
        frame_height=1280,
        face_score=0.95 if face_visible else 0.0,
        clarity_score=0.7,
        body_completeness=0.4,
        interference_ratio=0.0,
        other_person_boxes=[],
    )


def test_edge_cropped_large_body_is_allowed_as_partial_proposal() -> None:
    assert observation_v61._partial_person_box_plausible(
        (610, 100, 110, 900),
        720,
        1280,
    ) is True


def test_tiny_center_low_score_box_is_rejected_before_mot() -> None:
    assert observation_v61._partial_person_box_plausible(
        (340, 600, 20, 35),
        720,
        1280,
    ) is False


def test_right_edge_retry_box_maps_back_to_full_frame_coordinates() -> None:
    mapped = observation_v61._offset_box(
        (300, 100, 150, 700),
        230,
        0,
        720,
        1280,
    )
    assert mapped == (530, 100, 150, 700)


def test_edge_retry_duplicate_does_not_create_second_person_observation() -> None:
    values = [
        ((520, 100, 180, 800), 0.28, "v6.2-yolox-partial"),
        ((525, 105, 175, 795), 0.46, "v6.2-yolox-edge-partial"),
    ]

    deduped = observation_v61._dedupe_person_proposals(values)

    assert len(deduped) == 1
    assert deduped[0][1] == 0.46
    assert deduped[0][2] == "v6.2-yolox-edge-partial"


def test_dedupe_suppresses_weak_partial_fragments_mostly_covered_by_strong_person() -> None:
    values = [
        ((1, 543, 1055, 1353), 0.87, "v6.2-yolox"),
        ((0, 0, 207, 1714), 0.16, "v6.2-yolox-partial"),
        ((829, 1440, 251, 478), 0.19, "v6.2-yolox-partial"),
        ((10, 22, 566, 1893), 0.19, "v6.2-yolox-partial"),
    ]

    result = observation_v61._dedupe_person_proposals(values)

    assert result == [((1, 543, 1055, 1353), 0.87, "v6.2-yolox")]


def test_dedupe_preserves_strong_overlapping_people_and_distinct_partial() -> None:
    strong_left = ((40, 100, 420, 800), 0.91, "v6.2-yolox")
    strong_right = ((330, 110, 430, 790), 0.88, "v6.2-yolox")
    distinct_partial = ((810, 120, 170, 760), 0.17, "v6.2-yolox-partial")

    result = observation_v61._dedupe_person_proposals([
        strong_left,
        strong_right,
        distinct_partial,
    ])

    assert strong_left in result
    assert strong_right in result
    assert distinct_partial in result


def test_face_does_not_erase_partial_provenance() -> None:
    assert observation_v61._source_with_face("v6.2-yolox-partial") == "v6.2-yolox-partial+face"
    assert observation_v61._source_with_face("v6.2-yolox-edge-partial") == "v6.2-yolox-edge-partial+face"
    assert observation_v61._source_with_face("v6.2-yolox") == "v6.2-yolox+face"


def test_tracking_still_treats_partial_with_face_as_partial() -> None:
    value = partial(
        at_us=900_000,
        local_us=100_000,
        face_visible=True,
        detection_source="v6.2-yolox-edge-partial+face",
    )
    assert tracking._is_partial(value) is True


def test_isolated_partial_detection_cannot_survive_as_person_track() -> None:
    value = partial(at_us=1_000_000, local_us=100_000)
    assert tracking._partial_track_is_supported([value]) is False


def test_three_consistent_partial_detections_survive_as_unresolved_track_evidence() -> None:
    values = [
        partial(at_us=1_000_000, local_us=100_000, bbox=(605, 120, 115, 700)),
        partial(at_us=1_100_000, local_us=200_000, bbox=(600, 122, 120, 702)),
        partial(at_us=1_200_000, local_us=300_000, bbox=(596, 126, 124, 700)),
    ]

    assert tracking._partial_track_is_supported(values) is True


def test_unassigned_partial_singletons_are_coalesced_by_temporal_reid_support() -> None:
    values = [
        partial(at_us=2_000_000, local_us=0, bbox=(600, 100, 120, 740)),
        partial(at_us=2_100_000, local_us=100_000, bbox=(596, 105, 124, 735)),
        partial(at_us=2_200_000, local_us=200_000, bbox=(590, 110, 130, 730)),
    ]
    raw = {-1: [values[0]], -2: [values[1]], -3: [values[2]]}

    recovered = tracking._coalesce_partial_fallbacks(raw)

    assert len(recovered) == 1
    group = next(iter(recovered.values()))
    assert [item.source_time_us for item in group] == [2_000_000, 2_100_000, 2_200_000]
    assert tracking._partial_track_is_supported(group) is True


def test_partial_with_unrelated_reid_and_no_overlap_does_not_merge() -> None:
    first = partial(
        at_us=3_000_000,
        local_us=0,
        bbox=(0, 80, 100, 700),
        reid=(1.0, 0.0, 0.0),
    )
    second = partial(
        at_us=3_100_000,
        local_us=100_000,
        bbox=(620, 120, 100, 680),
        reid=(0.0, 1.0, 0.0),
    )

    recovered = tracking._coalesce_partial_fallbacks({-1: [first], -2: [second]})

    assert len(recovered) == 2
    assert all(tracking._partial_track_is_supported(items) is False for items in recovered.values())
