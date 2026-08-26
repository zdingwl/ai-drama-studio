from __future__ import annotations

import math

import numpy as np

from engine.app import character_gallery_v9 as gallery_v9
from engine.app import character_identity_v9c as identity
from engine.app import character_visual_v5 as v5
from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle


def unit(axis: int, size: int = 4) -> np.ndarray:
    value = np.zeros(size, dtype=np.float32)
    value[axis] = 1.0
    return value


def mixed(cosine_to_axis0: float) -> np.ndarray:
    value = np.asarray([
        cosine_to_axis0,
        math.sqrt(max(0.0, 1.0 - cosine_to_axis0 * cosine_to_axis0)),
        0.0,
        0.0,
    ], dtype=np.float32)
    return value / np.linalg.norm(value)


def make_observation(
    *,
    shot: int,
    vector: np.ndarray,
    face: np.ndarray | None = None,
    instance_class: str = "CLEAN",
    at_us: int | None = None,
    x: int = 100,
    instance_suffix: str = "P01",
) -> v5.Observation:
    source_time = int(at_us if at_us is not None else shot * 1_000_000)
    observation = v5.Observation(
        shot_id=f"SHOT_{shot:04d}",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot,
        source_time_us=source_time,
        local_time_us=100_000,
        bbox=(x, 80, 180, 620),
        face_bbox=(x + 55, 110, 64, 64) if face is not None else None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=face,
        reid_embedding=vector,
        body_hist=vector,
        face_visible=face is not None,
        detection_source="v9-test" if instance_class == "CLEAN" else "v9-test-partial",
        frame_width=1000,
        frame_height=1000,
        face_score=0.94 if face is not None else 0.0,
        clarity_score=0.93,
        body_completeness=0.92,
        interference_ratio=0.0,
        other_person_boxes=[],
    )
    observation.instance_id = f"{observation.shot_id}:{source_time}:{instance_suffix}"
    observation.instance_class = instance_class
    observation.gallery_eligible = instance_class == "CLEAN"
    observation.person_bbox = observation.bbox
    observation.person_crop_bbox = observation.bbox
    observation.cannot_link_instance_ids = []
    observation.person_feature_quality = 0.92 if instance_class == "CLEAN" else 0.55
    bundle = PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=observation.instance_id,
        instance_class=instance_class,
        gallery_eligible=instance_class == "CLEAN",
        quality=observation.person_feature_quality,
        person_reid=vector,
        clothing_upper=vector,
        clothing_lower=vector,
        body_hist=vector,
        body_structure=vector,
        face=face,
        face_score=observation.face_score,
    )
    observation.person_feature_bundle = bundle
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


def unresolved(candidates: list[v5.CandidateDraft]) -> list[v5.CandidateDraft]:
    return [item for item in candidates if item.identity_status != "RESOLVED"]


def test_three_real_people_many_tracks_resolve_to_three_person_galleries() -> None:
    tracks: list[v5.TrackDraft] = []
    for shot in (1, 2, 3, 4):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(0))))
    for shot in (5, 6, 7, 8):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(1))))
    for shot in (9, 10, 11, 12):
        tracks.append(make_track(make_observation(shot=shot, vector=unit(2))))

    # Extra body/partial fragments of person A must attach to A or remain unresolved; never create A2.
    tracks.append(make_track(make_observation(shot=13, vector=unit(0), instance_class="PARTIAL")))
    tracks.append(make_track(make_observation(shot=14, vector=unit(0), instance_class="PARTIAL")))

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 3
    assert all(
        getattr(item, "v9_metadata", {}).get("resolver") == "person-gallery-anchor-first-v9c"
        for item in resolved(candidates)
    )


def test_face_is_optional_for_confirmed_person_gallery() -> None:
    tracks = [
        make_track(make_observation(shot=shot, vector=unit(0), face=None))
        for shot in (1, 2, 3, 4)
    ]

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 1
    metadata = getattr(resolved(candidates)[0], "v9_metadata", {})
    assert metadata["confirmed_gallery_shots"] >= 3
    assert metadata["face_images"] == 0


def test_ambiguous_known_person_cannot_seed_duplicate_character() -> None:
    tracks = [
        *(make_track(make_observation(shot=shot, vector=unit(0))) for shot in (1, 2, 3, 4)),
        # Internally stable but only moderately similar to already-confirmed A: must stay unresolved, not A2.
        *(make_track(make_observation(shot=shot, vector=mixed(0.65))) for shot in (5, 6, 7)),
        *(make_track(make_observation(shot=shot, vector=unit(2))) for shot in (8, 9, 10, 11)),
    ]

    candidates = identity.resolve_global_identities(list(tracks))

    assert len(resolved(candidates)) == 2
    assert len(unresolved(candidates)) >= 1


def test_two_shot_group_cannot_create_automatic_character() -> None:
    tracks = [
        make_track(make_observation(shot=1, vector=unit(0))),
        make_track(make_observation(shot=2, vector=unit(0))),
    ]

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 0
    assert len(unresolved(candidates)) == 2


def test_partial_only_evidence_can_never_seed_character() -> None:
    tracks = [
        make_track(make_observation(shot=shot, vector=unit(0), instance_class="PARTIAL"))
        for shot in (1, 2, 3, 4)
    ]

    candidates = identity.resolve_global_identities(tracks)

    assert len(resolved(candidates)) == 0
    assert len(unresolved(candidates)) == 4


def test_face_similarity_alone_is_not_a_person_match() -> None:
    face = unit(3)
    left = make_observation(shot=1, vector=unit(0), face=face)
    right = make_observation(shot=2, vector=unit(1), face=face)
    a = identity.PersonEvidence(0, 0, left, left.person_feature_bundle, 0.92)
    b = identity.PersonEvidence(1, 1, right, right.person_feature_bundle, 0.92)

    decision = identity.compare_person_images(a, b)

    assert decision.status != "MATCH"
    assert decision.channels["face"] is not None and decision.channels["face"] > 0.99


def test_same_sample_cannot_link_overrides_identical_visual_features() -> None:
    at_us = 1_000_000
    left = make_observation(shot=1, vector=unit(0), at_us=at_us, x=80, instance_suffix="P01")
    right = make_observation(shot=1, vector=unit(0), at_us=at_us, x=700, instance_suffix="P02")
    left.cannot_link_instance_ids = [right.instance_id]
    right.cannot_link_instance_ids = [left.instance_id]
    a = identity.PersonEvidence(0, 0, left, left.person_feature_bundle, 0.92)
    b = identity.PersonEvidence(1, 1, right, right.person_feature_bundle, 0.92)

    decision = identity.compare_person_images(a, b)

    assert decision.status == "DIFFERENT"
    assert decision.hard_conflict is True
    assert "same-sample-cannot-link" in decision.reasons
