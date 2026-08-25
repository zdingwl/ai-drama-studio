from __future__ import annotations

import numpy as np

from engine.app.character_visual_v2 import TrackDraft, cluster_candidates, sample_ratios


def normalized(vector: list[float]):
    values = np.asarray(vector, dtype=np.float32)
    return values / np.linalg.norm(values)


def body_track(*, shot_id: str, shot_ordinal: int, vector: list[float]) -> TrackDraft:
    track = TrackDraft(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
    )
    track.body_hist = normalized(vector)
    track.reid_embedding = normalized(vector)
    track.face_embedding = None
    return track


def face_track(
    *,
    shot_id: str,
    shot_ordinal: int,
    face_vector: list[float],
    body_vector: list[float],
) -> TrackDraft:
    track = TrackDraft(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
    )
    track.face_embedding = normalized(face_vector)
    track.reid_embedding = normalized(body_vector)
    track.body_hist = normalized(body_vector)
    return track


def test_body_only_tracks_become_unresolved_person_evidence_not_resolved_identity() -> None:
    left = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.0, 0.0])
    right = body_track(shot_id="SHOT_2", shot_ordinal=2, vector=[1.0, 0.01, 0.0])

    candidates = cluster_candidates([left, right])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "UNRESOLVED"
    assert candidates[0].has_face_anchor is False
    assert candidates[0].tracks == [left, right]


def test_same_shot_face_tracks_never_auto_merge_even_with_identical_identity_evidence() -> None:
    left = face_track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.0, 0.0],
    )
    right = face_track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.0, 0.0],
    )

    candidates = cluster_candidates([left, right])

    assert len(candidates) == 2
    assert candidates[0].tracks == [left]
    assert candidates[1].tracks == [right]
    assert all(item.identity_status == "RESOLVED" for item in candidates)


def test_cross_shot_face_angle_change_can_merge_when_reid_supports_same_actor() -> None:
    """脸角度使 SFace 变弱时，专用 ReID 应避免把同一演员拆成两个 Final Character。"""

    frontal = face_track(
        shot_id="SHOT_2",
        shot_ordinal=2,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.04, 0.0],
    )
    profile = face_track(
        shot_id="SHOT_7",
        shot_ordinal=7,
        face_vector=[0.42, 0.9075, 0.0],
        body_vector=[1.0, 0.05, 0.0],
    )

    candidates = cluster_candidates([frontal, profile])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "RESOLVED"
    assert set(item.shot_id for item in candidates[0].tracks) == {"SHOT_2", "SHOT_7"}


def test_adjacent_body_only_track_can_extend_existing_face_anchored_identity() -> None:
    anchor = face_track(
        shot_id="SHOT_2",
        shot_ordinal=2,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.05, 0.0],
    )
    back_view = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.04, 0.0])

    candidates = cluster_candidates([back_view, anchor])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "RESOLVED"
    assert anchor in candidates[0].tracks
    assert back_view in candidates[0].tracks
    assert len(candidates[0].tracks) == 2


def test_distant_body_only_track_remains_unresolved_instead_of_silent_drop() -> None:
    anchor = face_track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.0, 0.0],
    )
    distant = body_track(shot_id="SHOT_8", shot_ordinal=8, vector=[1.0, 0.0, 0.0])

    candidates = cluster_candidates([anchor, distant])

    assert len(candidates) == 2
    resolved = next(item for item in candidates if item.identity_status == "RESOLVED")
    unresolved = next(item for item in candidates if item.identity_status == "UNRESOLVED")
    assert resolved.tracks == [anchor]
    assert unresolved.tracks == [distant]


def test_v5_tracking_sampling_is_denser_than_old_three_five_seven_frame_strategy() -> None:
    assert len(sample_ratios(300_000)) == 3
    assert len(sample_ratios(700_000)) >= 5
    assert len(sample_ratios(1_600_000)) >= 10
    assert len(sample_ratios(4_000_000)) >= 20
