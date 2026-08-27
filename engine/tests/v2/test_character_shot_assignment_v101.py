from __future__ import annotations

import math

import numpy as np

from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle
from engine.app.character_shot_assignment_v101 import ASSIGNMENT_SOURCE, ASSIGNMENT_VERSION, assign_shot_characters
from engine.app.character_visual_v5 import CandidateDraft, Observation, TrackDraft, TrackRepresentative


def _unit(values: tuple[float, ...]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    return array / np.linalg.norm(array)


def _observation(
    *,
    shot_id: str,
    shot_ordinal: int,
    source_time_us: int,
    instance_id: str,
    reid: tuple[float, ...] | None,
    face: tuple[float, ...] | None = None,
    face_score: float = 0.0,
    cannot_link: tuple[str, ...] = (),
) -> Observation:
    reid_vector = _unit(reid) if reid is not None else None
    face_vector = _unit(face) if face is not None else None
    item = Observation(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=source_time_us,
        local_time_us=source_time_us,
        bbox=(0, 0, 120, 240),
        face_bbox=(20, 20, 70, 70) if face_vector is not None else None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=face_vector,
        reid_embedding=reid_vector,
        body_hist=reid_vector,
        face_visible=face_vector is not None,
        detection_source="TEST",
        frame_width=1080,
        frame_height=1920,
        face_score=face_score,
        clarity_score=0.95,
        body_completeness=1.0,
        interference_ratio=0.0,
    )
    item.instance_id = instance_id
    item.instance_class = "CLEAN"
    item.cannot_link_instance_ids = list(cannot_link)
    item.person_evidence_eligible = True
    item.person_evidence_reliability = 0.95
    item.person_feature_quality = 0.95
    item.person_feature_bundle = PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=instance_id,
        instance_class="CLEAN",
        gallery_eligible=True,
        quality=0.95,
        person_reid=reid_vector,
        clothing_upper=reid_vector,
        clothing_lower=reid_vector,
        body_hist=reid_vector,
        body_structure=reid_vector,
        face=face_vector,
        face_score=face_score,
    )
    return item


def _track(shot_id: str, shot_ordinal: int, observations: list[Observation]) -> TrackDraft:
    reids = [item.reid_embedding for item in observations if item.reid_embedding is not None]
    faces = [item.face_embedding for item in observations if item.face_embedding is not None]
    return TrackDraft(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        observations=observations,
        reid_embedding=np.mean(reids, axis=0) if reids else None,
        face_embedding=np.mean(faces, axis=0) if faces else None,
        body_hist=np.mean(reids, axis=0) if reids else None,
    )


def _resolved_candidate(
    candidate_id: str,
    *,
    prefix: str,
    reid: tuple[float, ...],
    face: tuple[float, ...],
    start_ordinal: int,
) -> CandidateDraft:
    tracks: list[TrackDraft] = []
    gallery: list[TrackRepresentative] = []
    for offset in range(3):
        ordinal = start_ordinal + offset
        observation = _observation(
            shot_id=f"{prefix}_SHOT_{ordinal}",
            shot_ordinal=ordinal,
            source_time_us=100_000,
            instance_id=f"{prefix}_I_{ordinal}",
            reid=reid,
            face=face,
            face_score=0.95,
        )
        track = _track(observation.shot_id, ordinal, [observation])
        tracks.append(track)
        gallery.append(TrackRepresentative(observation=observation, quality_score=0.95, clean=True))
    candidate = CandidateDraft(
        id=candidate_id,
        tracks=tracks,
        reid_embedding=_unit(reid),
        face_embedding=_unit(face),
        body_hist=_unit(reid),
        identity_status="RESOLVED",
        gallery=gallery,
        scores=[0.92, 0.91],
    )
    candidate.v10_metadata = {
        "confirmed_gallery_images": 3,
        "confirmed_gallery_shots": 3,
        "captured_classified_images": 3,
        "classified_shots": 3,
    }
    return candidate


def _assignment(candidate: CandidateDraft, shot_id: str) -> dict[str, object] | None:
    for item in candidate.v10_metadata["shot_presence_assignments"]:
        if item["shot_id"] == shot_id:
            return item
    return None


def test_direct_identity_tracks_become_explicit_shot_assignments() -> None:
    person = _resolved_candidate(
        "A",
        prefix="A",
        reid=(1.0, 0.0, 0.0),
        face=(1.0, 0.0, 0.0),
        start_ordinal=1,
    )

    result = assign_shot_characters(list(person.tracks), [person])

    assert result == [person]
    assert person.v10_metadata["shot_assignment_version"] == ASSIGNMENT_VERSION
    assert person.v10_metadata["shot_assignment_source"] == ASSIGNMENT_SOURCE
    assert person.v10_metadata["shot_presence_count"] == 3
    assert person.v10_metadata["shot_presence_recovered_count"] == 0
    assert {item["mode"] for item in person.v10_metadata["shot_presence_assignments"]} == {"DIRECT_IDENTITY"}


def test_one_strong_face_closeup_can_assign_known_character_without_moving_track() -> None:
    person_a = _resolved_candidate(
        "A",
        prefix="A",
        reid=(1.0, 0.0, 0.0),
        face=(0.0, 1.0, 0.0),
        start_ordinal=1,
    )
    person_b = _resolved_candidate(
        "B",
        prefix="B",
        reid=(0.0, 1.0, 0.0),
        face=(1.0, 0.0, 0.0),
        start_ordinal=10,
    )
    # SFace cosine to B is 0.52, while A is only 0.10.  There is no usable body ReID.
    z = math.sqrt(1.0 - 0.52**2 - 0.10**2)
    closeup = _observation(
        shot_id="TARGET_CLOSEUP",
        shot_ordinal=20,
        source_time_us=500_000,
        instance_id="CLOSEUP_1",
        reid=None,
        face=(0.52, 0.10, z),
        face_score=0.95,
    )
    source_track = _track("TARGET_CLOSEUP", 20, [closeup])
    original_track_count = len(person_b.tracks)

    assign_shot_characters([*person_a.tracks, *person_b.tracks, source_track], [person_a, person_b])

    value = _assignment(person_b, "TARGET_CLOSEUP")
    assert value is not None
    assert value["mode"] == "FACE_STRONG"
    assert float(value["confidence"]) >= 0.88
    assert _assignment(person_a, "TARGET_CLOSEUP") is None
    # Shot assignment is independent; the unresolved source Track is not moved into B.
    assert len(person_b.tracks) == original_track_count


def test_two_person_shot_uses_current_shot_cannot_link_to_keep_both_characters() -> None:
    person_a = _resolved_candidate(
        "A",
        prefix="A",
        reid=(1.0, 0.0, 0.0),
        face=(1.0, 0.0, 0.0),
        start_ordinal=1,
    )
    person_b = _resolved_candidate(
        "B",
        prefix="B",
        reid=(0.8, 0.6, 0.0),
        face=(0.0, 1.0, 0.0),
        start_ordinal=10,
    )

    direct_a: list[Observation] = []
    unresolved_b: list[Observation] = []
    for index, source_time_us in enumerate((100_000, 220_000, 340_000)):
        a_id = f"A_CUR_{index}"
        u_id = f"U_CUR_{index}"
        direct_a.append(_observation(
            shot_id="TWO_PERSON",
            shot_ordinal=30,
            source_time_us=source_time_us,
            instance_id=a_id,
            reid=(1.0, 0.0, 0.0),
            cannot_link=(u_id,),
        ))
        unresolved_b.append(_observation(
            shot_id="TWO_PERSON",
            shot_ordinal=30,
            source_time_us=source_time_us,
            instance_id=u_id,
            # Nearly equidistant to A/B.  Without the same-frame cannot-link constraint
            # this is ambiguous; because A already occupies the other Person Instance,
            # the fragment may resolve to B at Shot-presence level.
            reid=(0.95, 0.3122499, 0.0),
            cannot_link=(a_id,),
        ))

    direct_track = _track("TWO_PERSON", 30, direct_a)
    person_a.tracks.append(direct_track)
    source_track = _track("TWO_PERSON", 30, unresolved_b)

    assign_shot_characters([*person_a.tracks, *person_b.tracks, source_track], [person_a, person_b])

    a_value = _assignment(person_a, "TWO_PERSON")
    b_value = _assignment(person_b, "TWO_PERSON")
    assert a_value is not None and a_value["mode"] == "DIRECT_IDENTITY"
    assert b_value is not None and b_value["mode"] == "BODY_REID"


def test_ambiguous_body_fragment_stays_unassigned() -> None:
    person_a = _resolved_candidate(
        "A",
        prefix="A",
        reid=(1.0, 0.0, 0.0),
        face=(1.0, 0.0, 0.0),
        start_ordinal=1,
    )
    person_b = _resolved_candidate(
        "B",
        prefix="B",
        reid=(0.8, 0.6, 0.0),
        face=(0.0, 1.0, 0.0),
        start_ordinal=10,
    )
    observations = [
        _observation(
            shot_id="AMBIGUOUS",
            shot_ordinal=40,
            source_time_us=100_000 + index * 120_000,
            instance_id=f"AMB_{index}",
            reid=(0.9486833, 0.3162278, 0.0),
        )
        for index in range(3)
    ]
    source_track = _track("AMBIGUOUS", 40, observations)

    assign_shot_characters([*person_a.tracks, *person_b.tracks, source_track], [person_a, person_b])

    assert _assignment(person_a, "AMBIGUOUS") is None
    assert _assignment(person_b, "AMBIGUOUS") is None
