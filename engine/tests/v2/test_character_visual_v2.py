from __future__ import annotations

import numpy as np

from engine.app.character_visual_v2 import TrackDraft, cluster_candidates


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
    track.body_hist = normalized(body_vector)
    return track


def test_body_only_tracks_never_create_character_identity_by_themselves() -> None:
    left = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.0, 0.0])
    right = body_track(shot_id="SHOT_2", shot_ordinal=2, vector=[1.0, 0.0, 0.0])

    candidates = cluster_candidates([left, right])

    assert candidates == []


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
    assert anchor in candidates[0].tracks
    assert back_view in candidates[0].tracks
    assert len(candidates[0].tracks) == 2


def test_distant_body_only_track_does_not_attach_to_face_identity() -> None:
    anchor = face_track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.0, 0.0],
    )
    distant = body_track(shot_id="SHOT_8", shot_ordinal=8, vector=[1.0, 0.0, 0.0])

    candidates = cluster_candidates([anchor, distant])

    assert len(candidates) == 1
    assert candidates[0].tracks == [anchor]
