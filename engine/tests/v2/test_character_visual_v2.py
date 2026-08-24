from __future__ import annotations

import numpy as np

from engine.app.character_visual_v2 import CandidateDraft, TrackDraft, cluster_candidates


def body_track(*, shot_id: str, shot_ordinal: int, vector: list[float]) -> TrackDraft:
    track = TrackDraft(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
    )
    values = np.asarray(vector, dtype=np.float32)
    track.body_hist = values / np.linalg.norm(values)
    track.face_embedding = None
    return track


def test_same_shot_tracks_never_auto_merge_even_with_identical_body_evidence() -> None:
    left = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.0, 0.0])
    right = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.0, 0.0])

    candidates = cluster_candidates([left, right])

    assert len(candidates) == 2
    assert candidates[0].tracks == [left]
    assert candidates[1].tracks == [right]


def test_body_only_tracks_can_link_across_adjacent_shots_when_extremely_similar() -> None:
    first = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.05, 0.0])
    second = body_track(shot_id="SHOT_2", shot_ordinal=2, vector=[1.0, 0.04, 0.0])

    candidates = cluster_candidates([first, second])

    assert len(candidates) == 1
    assert candidates[0].tracks == [first, second]


def test_body_only_tracks_do_not_link_across_distant_shots() -> None:
    first = body_track(shot_id="SHOT_1", shot_ordinal=1, vector=[1.0, 0.0, 0.0])
    distant = body_track(shot_id="SHOT_8", shot_ordinal=8, vector=[1.0, 0.0, 0.0])

    candidates = cluster_candidates([first, distant])

    assert len(candidates) == 2
