from __future__ import annotations

import numpy as np

from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle
from engine.app.character_shot_binding_v101 import recover_unresolved_tracks
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
    cannot_link: tuple[str, ...] = (),
) -> Observation:
    vector = _unit(reid)
    item = Observation(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=source_time_us,
        local_time_us=source_time_us,
        bbox=(0, 0, 100, 200),
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=None,
        reid_embedding=vector,
        body_hist=vector,
        face_visible=False,
        detection_source="TEST",
        frame_width=1080,
        frame_height=1920,
        face_score=0.0,
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
        person_reid=vector,
        clothing_upper=vector,
        clothing_lower=vector,
        body_hist=vector,
        body_structure=vector,
        face=None,
        face_score=0.0,
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


def _resolved_candidate(candidate_id: str, prefix: str, reid: tuple[float, float], start_ordinal: int) -> CandidateDraft:
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


def _unresolved_candidate(
    *,
    reid: tuple[float, float],
    cannot_link: tuple[str, ...] = (),
) -> CandidateDraft:
    observations = [
        _observation(
            shot_id="TARGET_SHOT",
            shot_ordinal=20,
            source_time_us=100_000 + index * 120_000,
            instance_id=f"U_{index}",
            reid=reid,
            cannot_link=cannot_link,
        )
        for index in range(3)
    ]
    return CandidateDraft(
        id="UNRESOLVED",
        tracks=[_track("TARGET_SHOT", 20, observations)],
        identity_status="UNRESOLVED",
    )


def test_repeated_track_evidence_recovers_known_identity_for_shot_binding() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), 10)
    unresolved = _unresolved_candidate(reid=(0.8, 0.6))

    result = recover_unresolved_tracks([person_a, person_b, unresolved])

    assert [item.id for item in result] == ["A", "B"]
    assert "TARGET_SHOT" in {track.shot_id for track in person_a.tracks}
    assert "TARGET_SHOT" not in {track.shot_id for track in person_b.tracks}
    assert person_a.v10_metadata["track_recovery_count"] == 1
    assert person_a.v10_metadata["track_recovery_shot_ids"] == ["TARGET_SHOT"]


def test_ambiguous_track_stays_unresolved() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), 10)
    unresolved = _unresolved_candidate(reid=(1.0, 1.0))

    result = recover_unresolved_tracks([person_a, person_b, unresolved])

    assert [item.id for item in result] == ["A", "B", "UNRESOLVED"]
    assert "TARGET_SHOT" not in {track.shot_id for track in person_a.tracks}
    assert "TARGET_SHOT" not in {track.shot_id for track in person_b.tracks}


def test_cannot_link_blocks_recovery_even_with_strong_reid() -> None:
    person_a = _resolved_candidate("A", "A", (1.0, 0.0), 1)
    person_b = _resolved_candidate("B", "B", (0.0, 1.0), 10)
    unresolved = _unresolved_candidate(reid=(1.0, 0.0), cannot_link=("A_I_1",))

    result = recover_unresolved_tracks([person_a, person_b, unresolved])

    assert [item.id for item in result] == ["A", "B", "UNRESOLVED"]
    assert "TARGET_SHOT" not in {track.shot_id for track in person_a.tracks}
