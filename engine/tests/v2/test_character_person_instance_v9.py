from __future__ import annotations

from engine.app import character_gallery_v9 as gallery
from engine.app import character_observation_v9 as observation_v9
from engine.app import character_visual_v5 as v5
from engine.app.character_person_instance_v9 import classify_person_instance


def obs(
    *,
    bbox: tuple[int, int, int, int],
    at_us: int = 1_000_000,
    source: str = "v6.3-yolox",
) -> v5.Observation:
    return v5.Observation(
        shot_id="SHOT_1",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=1,
        source_time_us=at_us,
        local_time_us=at_us,
        bbox=bbox,
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.91,
        face_embedding=None,
        reid_embedding=None,
        body_hist=None,
        face_visible=False,
        detection_source=source,
        frame_width=1000,
        frame_height=1000,
        clarity_score=0.8,
        body_completeness=0.9,
        interference_ratio=0.0,
        other_person_boxes=[],
    )


def test_clean_person_instance_is_gallery_eligible() -> None:
    safety = classify_person_instance(
        person_bbox=(100, 100, 180, 650),
        other_person_boxes=[(650, 100, 180, 650)],
        frame_width=1000,
        frame_height=1000,
        proposal_source="v6.3-yolox",
    )

    assert safety.instance_class == "CLEAN"
    assert safety.gallery_eligible is True
    assert safety.crop_bbox != (0, 0, 1000, 1000)


def test_multi_person_overlap_blocks_gallery_admission() -> None:
    safety = classify_person_instance(
        person_bbox=(100, 100, 300, 700),
        other_person_boxes=[(220, 120, 300, 700)],
        frame_width=1000,
        frame_height=1000,
        proposal_source="v6.3-yolox",
    )

    assert safety.instance_class == "CONTAMINATED"
    assert safety.gallery_eligible is False
    assert safety.contamination_ratio > 0.15


def test_partial_and_face_fallback_can_never_seed_gallery() -> None:
    partial = classify_person_instance(
        person_bbox=(0, 80, 180, 820),
        other_person_boxes=[],
        frame_width=1000,
        frame_height=1000,
        proposal_source="v6.3-yolox-edge-partial",
    )
    fallback = classify_person_instance(
        person_bbox=(300, 120, 240, 700),
        other_person_boxes=[],
        frame_width=1000,
        frame_height=1000,
        proposal_source="v6.3-face-fallback",
        force_partial=True,
    )

    assert partial.instance_class == "PARTIAL"
    assert partial.gallery_eligible is False
    assert fallback.instance_class == "PARTIAL"
    assert fallback.gallery_eligible is False


def test_same_sample_multiple_people_get_separate_ids_and_cannot_links() -> None:
    left = obs(bbox=(40, 100, 180, 700))
    middle = obs(bbox=(400, 100, 180, 700))
    right = obs(bbox=(760, 100, 180, 700))

    result = observation_v9.annotate_person_instances([right, left, middle])

    ids = {getattr(item, "instance_id") for item in result}
    assert len(ids) == 3
    for item in result:
        cannot_links = set(getattr(item, "cannot_link_instance_ids"))
        assert len(cannot_links) == 2
        assert getattr(item, "instance_id") not in cannot_links
        assert getattr(item, "person_crop_bbox") != (0, 0, 1000, 1000)


def test_gallery_representative_clean_flag_comes_from_v9_instance_safety() -> None:
    clean = obs(bbox=(100, 100, 180, 650), at_us=1_000_000)
    dirty = obs(bbox=(200, 100, 300, 700), at_us=1_600_000)
    overlapping_person = obs(bbox=(320, 120, 300, 700), at_us=1_600_000)

    observation_v9.annotate_person_instances([clean, dirty, overlapping_person])

    track = v5.TrackDraft(
        shot_id="SHOT_1",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=1,
        observations=[clean, dirty],
    )
    representatives = gallery.select_track_representatives(track)
    by_time = {item.observation.source_time_us: item for item in representatives}

    assert by_time[1_000_000].clean is True
    assert by_time[1_600_000].clean is False
