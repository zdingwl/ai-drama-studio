from __future__ import annotations

import math

import numpy as np

from engine.app import character_gallery_v10 as gallery_v10
from engine.app import character_identity_v10 as identity
from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import attach_v10_policy
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
    at_us: int | None = None,
    x: int = 100,
    suffix: str = "P01",
) -> v5.Observation:
    source_time = int(at_us if at_us is not None else shot * 1_000_000)
    observation = v5.Observation(
        shot_id=f"SHOT_{shot:04d}",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot,
        source_time_us=source_time,
        local_time_us=100_000,
        bbox=(x, 60, 220, 760),
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=None,
        reid_embedding=vector,
        body_hist=vector,
        face_visible=False,
        detection_source="v10-test",
        frame_width=1000,
        frame_height=1000,
        face_score=0.0,
        clarity_score=0.92,
        body_completeness=0.90,
        interference_ratio=0.0,
        other_person_boxes=[],
    )
    observation.instance_id = f"{observation.shot_id}:{source_time}:{suffix}"
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
    attach_v10_policy(observation)
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
    track.representatives = gallery_v10.select_track_representatives(track)
    return track


def resolved(candidates: list[v5.CandidateDraft]) -> list[v5.CandidateDraft]:
    return [item for item in candidates if item.identity_status == "RESOLVED"]


def test_front_side_back_and_occluded_views_classify_to_one_person() -> None:
    # Simulate one actor across progressively changing whole-person views.
    observations = [
        make_observation(shot=1, vector=angle_vector(0), instance_class="CLEAN"),
        make_observation(shot=2, vector=angle_vector(20), instance_class="CLEAN"),
        make_observation(shot=3, vector=angle_vector(40), instance_class="CLEAN"),
        make_observation(shot=4, vector=angle_vector(60), instance_class="OCCLUDED"),
        make_observation(shot=5, vector=angle_vector(80), instance_class="CONTAMINATED"),
    ]
    candidates = identity.resolve_global_identities([make_track(item) for item in observations])

    people = resolved(candidates)
    assert len(people) == 1
    assert {track.shot_id for track in people[0].tracks} == {
        "SHOT_0001", "SHOT_0002", "SHOT_0003", "SHOT_0004", "SHOT_0005"
    }
    metadata = getattr(people[0], "v10_metadata", {})
    assert metadata["resolver"] == "person-evidence-model-classifier-v10"
    assert metadata["classified_shots"] == 5
    assert "OCCLUDED" in metadata["instance_classes"]
    assert "CONTAMINATED" in metadata["instance_classes"]


def test_same_sample_different_people_are_hard_cannot_link() -> None:
    at_us = 1_000_000
    left = make_observation(shot=1, vector=unit(0), at_us=at_us, x=80, suffix="P01")
    right = make_observation(shot=1, vector=unit(0), at_us=at_us, x=650, suffix="P02")
    left.cannot_link_instance_ids = [right.instance_id]
    right.cannot_link_instance_ids = [left.instance_id]

    a = identity.PersonEvidence(0, 0, left, left.person_feature_bundle, 0.92, 1.0, True)
    b = identity.PersonEvidence(1, 1, right, right.person_feature_bundle, 0.92, 1.0, True)
    decision = identity.compare_person_model(a, b)

    assert decision.status == "DIFFERENT"
    assert decision.hard_conflict is True
    assert "same-sample-cannot-link" in decision.reasons


def test_partial_evidence_is_saved_for_classification_but_cannot_seed_identity() -> None:
    partials = [
        make_observation(shot=shot, vector=unit(0), instance_class="PARTIAL", quality=0.75)
        for shot in (1, 2, 3, 4)
    ]
    assert all(item.person_evidence_eligible for item in partials)
    assert all(not item.person_seed_eligible for item in partials)

    candidates = identity.resolve_global_identities([make_track(item) for item in partials])
    assert len(resolved(candidates)) == 0


def test_three_people_many_views_still_resolve_to_three_identity_classes() -> None:
    tracks: list[v5.TrackDraft] = []
    for shot, degrees in zip((1, 2, 3, 4), (0, 18, 36, 54)):
        tracks.append(make_track(make_observation(shot=shot, vector=angle_vector(degrees))))
    for shot in (5, 6, 7, 8):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(2))))
    for shot in (9, 10, 11, 12):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(3))))

    # Extra low-reliability content exists but cannot manufacture new people.
    tracks.append(make_track(make_observation(shot=13, vector=unit(2), instance_class="CONTAMINATED")))
    tracks.append(make_track(make_observation(shot=14, vector=unit(3), instance_class="PARTIAL")))

    candidates = identity.resolve_global_identities(tracks)
    assert len(resolved(candidates)) == 3
