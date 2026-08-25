from __future__ import annotations

import numpy as np

from engine.app.character_visual_v2 import (
    Observation,
    TrackDraft,
    build_tracks,
    cluster_candidates,
    select_track_representatives,
)


def normalized(vector: list[float]):
    values = np.asarray(vector, dtype=np.float32)
    return values / np.linalg.norm(values)


def observation(
    *,
    shot_id: str,
    shot_ordinal: int,
    source_time_us: int,
    bbox: tuple[int, int, int, int],
    face: list[float] | None,
    reid: list[float],
    interference: float,
    clarity: float = 0.9,
) -> Observation:
    return Observation(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=source_time_us,
        local_time_us=source_time_us,
        bbox=bbox,
        face_bbox=(bbox[0] + 10, bbox[1] + 10, 40, 40) if face else None,
        reference_path="dummy.mp4",
        detection_score=0.95,
        face_embedding=normalized(face) if face else None,
        reid_embedding=normalized(reid),
        body_hist=normalized(reid),
        face_visible=face is not None,
        detection_source="test",
        frame_width=640,
        frame_height=360,
        face_score=0.95 if face else 0.0,
        clarity_score=clarity,
        body_completeness=0.95,
        interference_ratio=interference,
        other_person_boxes=[],
    )


def test_track_representatives_use_only_clean_frames_when_clean_evidence_exists() -> None:
    track = TrackDraft(
        shot_id="SHOT_1",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=1,
        observations=[
            observation(
                shot_id="SHOT_1", shot_ordinal=1, source_time_us=100_000,
                bbox=(30, 30, 180, 300), face=[1.0, 0.0], reid=[1.0, 0.0],
                interference=0.35, clarity=1.0,
            ),
            observation(
                shot_id="SHOT_1", shot_ordinal=1, source_time_us=500_000,
                bbox=(40, 28, 170, 300), face=[1.0, 0.02], reid=[1.0, 0.02],
                interference=0.0, clarity=0.85,
            ),
        ],
    )

    reps = select_track_representatives(track)

    assert reps
    assert all(rep.clean for rep in reps)
    assert reps[0].observation.source_time_us == 500_000


def test_character_gallery_never_absorbs_dirty_multi_person_representative() -> None:
    clean_track = TrackDraft(
        shot_id="SHOT_1",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=1,
        observations=[
            observation(
                shot_id="SHOT_1", shot_ordinal=1, source_time_us=100_000,
                bbox=(20, 20, 180, 300), face=[1.0, 0.0], reid=[1.0, 0.0], interference=0.0,
            )
        ],
    )
    dirty_track = TrackDraft(
        shot_id="SHOT_2",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=2,
        observations=[
            observation(
                shot_id="SHOT_2", shot_ordinal=2, source_time_us=1_000_000,
                bbox=(20, 20, 180, 300), face=[1.0, 0.01], reid=[1.0, 0.01], interference=0.30,
            )
        ],
    )

    for track in (clean_track, dirty_track):
        built = build_tracks(track.observations)
        track.face_embedding = built[0].face_embedding
        track.reid_embedding = built[0].reid_embedding
        track.body_hist = built[0].body_hist
        track.representatives = built[0].representatives

    candidates = cluster_candidates([clean_track, dirty_track])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert len(candidate.tracks) == 2
    assert candidate.gallery
    assert all(rep.clean for rep in candidate.gallery)
    assert all(rep.observation.shot_id == "SHOT_1" for rep in candidate.gallery)


def test_character_gallery_grows_when_later_clean_track_matches_same_person() -> None:
    first = [
        observation(
            shot_id="SHOT_1", shot_ordinal=1, source_time_us=100_000,
            bbox=(20, 20, 180, 300), face=[1.0, 0.0, 0.0], reid=[1.0, 0.0, 0.0], interference=0.0,
        )
    ]
    second = [
        observation(
            shot_id="SHOT_3", shot_ordinal=3, source_time_us=2_000_000,
            bbox=(260, 20, 180, 300), face=[0.98, 0.10, 0.0], reid=[0.99, 0.08, 0.0], interference=0.0,
        )
    ]
    tracks = build_tracks(first + second)

    candidates = cluster_candidates(tracks)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert len(candidate.tracks) == 2
    assert {rep.observation.shot_id for rep in candidate.gallery} == {"SHOT_1", "SHOT_3"}


def test_two_people_visible_at_same_time_cannot_share_character_id() -> None:
    observations = [
        observation(
            shot_id="SHOT_7", shot_ordinal=7, source_time_us=100_000,
            bbox=(20, 20, 180, 300), face=[1.0, 0.0], reid=[1.0, 0.0], interference=0.0,
        ),
        observation(
            shot_id="SHOT_7", shot_ordinal=7, source_time_us=100_000,
            bbox=(300, 20, 180, 300), face=[1.0, 0.0], reid=[1.0, 0.0], interference=0.0,
        ),
    ]
    tracks = build_tracks(observations)

    candidates = cluster_candidates(tracks)

    assert len(tracks) == 2
    assert len(candidates) == 2
