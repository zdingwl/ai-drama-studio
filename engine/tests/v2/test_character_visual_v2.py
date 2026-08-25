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


def test_body_only_tracks_never_create_global_character_identity() -> None:
    """V6 body-only 只能挂已有 Face Identity；不能互相抱团制造人物。"""

    left = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.0, 0.0])
    right = body_track(shot_id="SHOT_2", shot_ordinal=2, vector=[1.0, 0.01, 0.0])

    candidates = cluster_candidates([left, right])

    assert len(candidates) == 2
    assert all(item.identity_status == "UNRESOLVED" for item in candidates)
    assert all(item.has_face_anchor is False for item in candidates)


def test_same_shot_face_tracks_never_auto_merge_even_with_identical_embedding() -> None:
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
    # 这里只有历史聚合 embedding、没有连续人脸 samples；V6 不允许它们直接升级 Final。
    assert all(item.identity_status == "UNRESOLVED" for item in candidates)


def test_weak_face_match_cannot_merge_across_distant_shots_even_when_reid_is_similar() -> None:
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

    assert len(candidates) == 2


def test_adjacent_body_only_track_can_attach_to_face_cluster_but_not_make_it_resolved_by_itself() -> None:
    """历史无 samples 的 Face Track 本身不足以通过 Final Gate；Body 只能附着，不能提高 Face 证据等级。"""

    anchor = face_track(
        shot_id="SHOT_2",
        shot_ordinal=2,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.05, 0.0],
    )
    back_view = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.04, 0.0])

    candidates = cluster_candidates([back_view, anchor])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "UNRESOLVED"
    assert anchor in candidates[0].tracks
    assert back_view in candidates[0].tracks


def test_distant_body_only_track_remains_separate_unresolved_evidence() -> None:
    anchor = face_track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face_vector=[1.0, 0.0, 0.0],
        body_vector=[1.0, 0.0, 0.0],
    )
    distant = body_track(shot_id="SHOT_8", shot_ordinal=8, vector=[1.0, 0.0, 0.0])

    candidates = cluster_candidates([anchor, distant])

    assert len(candidates) == 2
    assert all(item.identity_status == "UNRESOLVED" for item in candidates)


def test_v6_tracking_sampling_is_dense_enough_for_mature_mot() -> None:
    assert len(sample_ratios(300_000)) >= 4
    assert len(sample_ratios(700_000)) >= 9
    assert len(sample_ratios(1_600_000)) >= 20
    assert len(sample_ratios(4_000_000)) >= 40
