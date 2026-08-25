from __future__ import annotations

import numpy as np

from engine.app.character_visual_v2 import Observation, build_tracks, cluster_candidates


def normalized(values: list[float]):
    vector = np.asarray(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def observation(
    *,
    shot_id: str,
    shot_ordinal: int,
    source_time_us: int,
    face: list[float] | None,
    reid: list[float],
    x: int = 20,
) -> Observation:
    bbox = (x, 20, 180, 300)
    return Observation(
        shot_id=shot_id,
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=source_time_us,
        local_time_us=source_time_us,
        bbox=bbox,
        face_bbox=(x + 20, 35, 48, 48) if face is not None else None,
        reference_path="dummy.mp4",
        detection_score=0.96,
        face_embedding=normalized(face) if face is not None else None,
        reid_embedding=normalized(reid),
        body_hist=normalized(reid),
        face_visible=face is not None,
        detection_source="test",
        frame_width=640,
        frame_height=360,
        face_score=0.96 if face is not None else 0.0,
        clarity_score=0.95,
        body_completeness=0.95,
        interference_ratio=0.0,
        other_person_boxes=[],
    )


def test_different_faces_never_merge_even_when_reid_is_identical() -> None:
    tracks = build_tracks([
        observation(
            shot_id="SHOT_1", shot_ordinal=1, source_time_us=100_000,
            face=[1.0, 0.0, 0.0], reid=[1.0, 0.0, 0.0],
        ),
        observation(
            shot_id="SHOT_2", shot_ordinal=2, source_time_us=1_000_000,
            face=[0.0, 1.0, 0.0], reid=[1.0, 0.0, 0.0],
        ),
    ])

    candidates = cluster_candidates(tracks)

    assert len(tracks) == 2
    assert len(candidates) == 2


def test_body_only_track_can_attach_only_to_adjacent_character_with_extreme_reid() -> None:
    tracks = build_tracks([
        observation(
            shot_id="SHOT_1", shot_ordinal=1, source_time_us=100_000,
            face=[1.0, 0.0, 0.0], reid=[1.0, 0.0, 0.0],
        ),
        observation(
            shot_id="SHOT_2", shot_ordinal=2, source_time_us=1_000_000,
            face=None, reid=[0.999, 0.02, 0.0],
        ),
    ])

    candidates = cluster_candidates(tracks)

    assert len(candidates) == 1
    assert len(candidates[0].tracks) == 2


def test_body_only_track_does_not_jump_across_multiple_shots() -> None:
    tracks = build_tracks([
        observation(
            shot_id="SHOT_1", shot_ordinal=1, source_time_us=100_000,
            face=[1.0, 0.0, 0.0], reid=[1.0, 0.0, 0.0],
        ),
        observation(
            shot_id="SHOT_3", shot_ordinal=3, source_time_us=2_000_000,
            face=None, reid=[1.0, 0.0, 0.0],
        ),
    ])

    candidates = cluster_candidates(tracks)

    assert len(candidates) == 2


def test_track_is_split_when_reid_continues_but_face_switches_to_another_person() -> None:
    tracks = build_tracks([
        observation(
            shot_id="SHOT_7", shot_ordinal=7, source_time_us=100_000,
            face=[1.0, 0.0, 0.0], reid=[1.0, 0.0, 0.0], x=20,
        ),
        observation(
            shot_id="SHOT_7", shot_ordinal=7, source_time_us=300_000,
            face=[0.0, 1.0, 0.0], reid=[1.0, 0.0, 0.0], x=22,
        ),
    ])

    assert len(tracks) == 2
    assert tracks[0].end_us < tracks[1].start_us
