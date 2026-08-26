from __future__ import annotations

import math

import numpy as np

from engine.app import character_gallery_v9 as gallery_v9
from engine.app import character_identity_v91 as identity
from engine.app import character_visual_v5 as v5
from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle


def angle_vector(degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    value = np.asarray([math.cos(radians), math.sin(radians), 0.0, 0.0], dtype=np.float32)
    return value / np.linalg.norm(value)


def unit(axis: int, size: int = 4) -> np.ndarray:
    value = np.zeros(size, dtype=np.float32)
    value[axis] = 1.0
    return value


def make_observation(
    *,
    shot: int,
    vector: np.ndarray,
    instance_class: str = "CLEAN",
    quality: float = 0.92,
) -> v5.Observation:
    source_time = shot * 1_000_000
    observation = v5.Observation(
        shot_id=f"SHOT_{shot:04d}",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot,
        source_time_us=source_time,
        local_time_us=100_000,
        bbox=(100, 80, 180, 620),
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=None,
        reid_embedding=vector,
        body_hist=vector,
        face_visible=False,
        detection_source="v91-test" if instance_class == "CLEAN" else "v91-test-partial",
        frame_width=1000,
        frame_height=1000,
        face_score=0.0,
        clarity_score=0.93,
        body_completeness=0.92,
        interference_ratio=0.0,
        other_person_boxes=[],
    )
    observation.instance_id = f"{observation.shot_id}:{source_time}:P01"
    observation.instance_class = instance_class
    observation.gallery_eligible = instance_class == "CLEAN"
    observation.person_bbox = observation.bbox
    observation.person_crop_bbox = observation.bbox
    observation.cannot_link_instance_ids = []
    observation.person_feature_quality = quality
    observation.person_feature_bundle = PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=observation.instance_id,
        instance_class=instance_class,
        gallery_eligible=instance_class == "CLEAN",
        quality=quality,
        person_reid=vector,
        clothing_upper=vector,
        clothing_lower=vector,
        body_hist=vector,
        body_structure=vector,
        face=None,
        face_score=0.0,
    )
    return observation


def make_track(observation: v5.Observation) -> v5.TrackDraft:
    track = v5.TrackDraft(
        shot_id=observation.shot_id,
        episode_id=observation.episode_id,
        episode_order=observation.episode_order,
        shot_ordinal=observation.shot_ordinal,
        observations=[observation],
    )
    v5._refresh_track(track)
    track.representatives = gallery_v9.select_track_representatives(track)
    return track


def resolved(candidates: list[v5.CandidateDraft]) -> list[v5.CandidateDraft]:
    return [item for item in candidates if item.identity_status == "RESOLVED"]


def test_progressive_gallery_bridges_realistic_view_changes() -> None:
    tracks = [
        make_track(make_observation(shot=1, vector=angle_vector(0))),
        make_track(make_observation(shot=2, vector=angle_vector(25))),
        make_track(make_observation(shot=3, vector=angle_vector(50))),
        make_track(make_observation(shot=4, vector=angle_vector(75))),
    ]

    candidates = identity.resolve_global_identities(tracks)

    people = resolved(candidates)
    assert len(people) == 1
    metadata = getattr(people[0], "v9_metadata", {})
    assert metadata["resolver"] == "person-gallery-progressive-v9.1"
    assert metadata["gallery_builder"] == "progressive-proto-gallery"
    assert metadata["confirmed_gallery_shots"] >= 3


def test_confirmed_gallery_absorbs_a_later_view_through_multiview_support() -> None:
    observations = [
        make_observation(shot=1, vector=angle_vector(0)),
        make_observation(shot=2, vector=angle_vector(25)),
        make_observation(shot=3, vector=angle_vector(50)),
        # 77° has only one MATCH to the Gallery and is below the old 0.90 single-match exception.
        make_observation(shot=4, vector=angle_vector(77)),
    ]
    evidence = [
        identity.PersonEvidence(index, index, observation, observation.person_feature_bundle, 0.92)
        for index, observation in enumerate(observations)
    ]
    gallery = identity.ConfirmedGallery(ordinal=0, evidence_indices={0, 1, 2}, seed_index=0)

    decision = identity._progressive_gallery_decision(evidence[3], gallery, evidence)

    assert decision.status == "MATCH"
    assert "progressive-multiview-gallery-support" in decision.reasons


def test_one_ambiguous_image_does_not_hide_a_clearly_novel_third_person() -> None:
    tracks: list[v5.TrackDraft] = []

    for shot in (1, 2, 3, 4):
        tracks.append(make_track(make_observation(shot=shot, vector=angle_vector(0))))

    for shot in (5, 6, 7, 8):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(2))))

    tracks.extend([
        make_track(make_observation(shot=9, vector=angle_vector(49.5))),
        make_track(make_observation(shot=10, vector=angle_vector(72.5))),
        make_track(make_observation(shot=11, vector=angle_vector(95.0))),
        make_track(make_observation(shot=12, vector=angle_vector(96.0))),
    ])

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 3


def test_partial_fragments_still_cannot_seed_a_character() -> None:
    tracks = [
        make_track(make_observation(shot=shot, vector=angle_vector(20), instance_class="PARTIAL"))
        for shot in (1, 2, 3, 4, 5)
    ]

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 0


def test_three_people_many_fragments_still_have_three_final_identities() -> None:
    tracks: list[v5.TrackDraft] = []
    for shot, degrees in zip((1, 2, 3, 4), (0, 20, 40, 60)):
        tracks.append(make_track(make_observation(shot=shot, vector=angle_vector(degrees))))
    for shot in (5, 6, 7, 8):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(2))))
    for shot in (9, 10, 11, 12):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(3))))

    for shot in range(13, 25):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(2), instance_class="PARTIAL")))

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 3
