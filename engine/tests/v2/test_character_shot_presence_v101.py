from __future__ import annotations

import numpy as np

from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle
from engine.app.character_shot_presence_v101 import RECOVERY_SOURCE, recover_fragmented_shot_presence
from engine.app.character_visual_v5 import CandidateDraft, Observation, TrackDraft, TrackRepresentative


def _unit(values: tuple[float, float]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    return array / np.linalg.norm(array)


def _observation(
    *,
    shot_id: str,
    shot_ordinal: int,
    source_time_us: int,
    instance_id: str,
    reid: tuple[float, float],
    face: tuple[float, float] | None = None,
    face_score: float = 0.0,
    cannot_link: tuple[str, ...] = (),
) -> Observation:
    reid_vector = _unit(reid)
    face_vector = _unit(face) if face is not None else None
    item = Observation(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=source_time_us,
        local_time_us=source_time_us,
        bbox=(0, 0, 100, 200),
        face_bbox=(10, 10, 50, 50) if face_vector is not None else None,
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
        clarity_score=0.9,
        body_completeness=1.0,
        interference_ratio=0.0,
    )
    item.instance_id = instance_id
    item.instance_class = "CLEAN"
    item.cannot_link_instance_ids = list(cannot_link)
    item.person_evidence_eligible = True
    item.person_evidence_reliability = 0.95
    item.person_feature_quality = 0.9
    item.person_feature_bundle = PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=instance_id,
        instance_class="CLEAN",
        gallery_eligible=True,
        quality=0.9,
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
    return TrackDraft(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        observations=observations,
        reid_embedding=np.mean([item.reid_embedding for item in observations], axis=0),
        body_hist=np.mean([item.body_hist for item in observations], axis=0),
    )


def _resolved_candidate(
    candidate_id: str,
    prefix: str,
    reid: tuple[float, float],
    face: tuple[float, float] | None,
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
            face_score=0.95 if face is not None else 0.0,
        )
        track = _track(observation.shot_id, ordinal, [observation])
        tracks.append(track)
        gallery.append(TrackRepresentative(observation=observation, quality_score=0.95, clean=True))
    candidate = CandidateDraft(
        id=candidate_id,
        tracks=tracks,
        reid_embedding=_unit(reid),
        body_hist=_unit(reid),
        identity_status="RESOLVED",
        gallery=gallery,
    )
    candidate.v10_metadata = {
        "confirmed_gallery_images": 3,
        "confirmed_gallery_shots": 3,
        "captured_classified_images": 3,
        "classified_shots": 3,
    }
    return candidate


def _unresolved_fragment(
    fragment_id: str,
    *,
    source_time_us: int,
    reid: tuple[float, float],
    face: tuple[float, float] | None = None,
    face_score: float = 0.0,
    cannot_link: tuple[str, ...] = (),
) -> CandidateDraft:
    observation = _observation(
        shot_id="TARGET_SHOT",
        shot_ordinal=20,
        source_time_us=source_time_us,
        instance_id=f"{fragment_id}_I",
        reid=reid,
        face=face,
        face_score=face_score,
        cannot_link=cannot_link,
    )
    return CandidateDraft(
        id=fragment_id,
        tracks=[_track("TARGET_SHOT", 20, [observation])],
        identity_status="UNRESOLVED",
    )


def test_three_singleton_fragments_can_recover_one_known_character_in_same_shot() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), None, 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), None, 10)
    fragments = [
        _unresolved_fragment(f"U_{index}", source_time_us=100_000 + index * 120_000, reid=(0.8, 0.6))
        for index in range(3)
    ]

    result = recover_fragmented_shot_presence([person_a, person_b, *fragments])

    assert [item.id for item in result] == ["A", "B"]
    recovered = [track for track in person_a.tracks if track.shot_id == "TARGET_SHOT"]
    assert len(recovered) == 3
    assert all(track.identity_recovery["source"] == RECOVERY_SOURCE for track in recovered)
    assert "TARGET_SHOT" not in {track.shot_id for track in person_b.tracks}
    assert person_a.v10_metadata["shot_fragment_recovery_count"] == 3


def test_one_strong_face_fragment_can_confirm_presence_of_existing_identity() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), (1.0, 0.0), 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), (0.0, 1.0), 10)
    fragment = _unresolved_fragment(
        "U_FACE",
        source_time_us=100_000,
        reid=(0.7, 0.714),
        face=(1.0, 0.0),
        face_score=0.95,
    )

    result = recover_fragmented_shot_presence([person_a, person_b, fragment])

    assert [item.id for item in result] == ["A", "B"]
    recovered = next(track for track in person_a.tracks if track.shot_id == "TARGET_SHOT")
    assert recovered.identity_recovery["source"] == RECOVERY_SOURCE
    assert recovered.identity_recovery["strong_face_support"] is True


def test_single_weak_body_fragment_stays_unresolved() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), None, 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), None, 10)
    fragment = _unresolved_fragment("U_WEAK", source_time_us=100_000, reid=(0.8, 0.6))

    result = recover_fragmented_shot_presence([person_a, person_b, fragment])

    assert [item.id for item in result] == ["A", "B", "U_WEAK"]
    assert not hasattr(fragment.tracks[0], "identity_recovery")


def test_same_sample_cannot_link_prevents_duplicate_fragment_support() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), None, 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), None, 10)
    first = _unresolved_fragment("U_1", source_time_us=100_000, reid=(0.8, 0.6), cannot_link=("U_2_I",))
    second = _unresolved_fragment("U_2", source_time_us=100_000, reid=(0.8, 0.6), cannot_link=("U_1_I",))
    third = _unresolved_fragment("U_3", source_time_us=220_000, reid=(0.8, 0.6))

    result = recover_fragmented_shot_presence([person_a, person_b, first, second, third])

    # One simultaneous fragment is discarded by cannot-link, leaving fewer than the
    # three independent timestamps required for body-only Shot presence recovery.
    assert [item.id for item in result] == ["A", "B", "U_1", "U_2", "U_3"]
    assert "TARGET_SHOT" not in {track.shot_id for track in person_a.tracks}
