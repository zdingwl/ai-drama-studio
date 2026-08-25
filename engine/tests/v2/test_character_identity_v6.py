from __future__ import annotations

import numpy as np

from engine.app import character_identity_v6 as v6
from engine.app import character_visual_v5 as v5


def vec(*values: float) -> np.ndarray:
    value = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(value))
    return value / norm if norm else value


def observation(
    *,
    shot_id: str,
    shot_ordinal: int,
    at_us: int,
    face: np.ndarray | None,
    reid: np.ndarray | None,
    face_score: float = 0.95,
) -> v5.Observation:
    return v5.Observation(
        shot_id=shot_id,
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=at_us,
        local_time_us=max(0, at_us - shot_ordinal * 1_000_000),
        bbox=(20, 20, 120, 300),
        face_bbox=(45, 30, 60, 60) if face is not None else None,
        reference_path="unused.mp4",
        detection_score=0.96,
        face_embedding=face,
        reid_embedding=reid,
        body_hist=None,
        face_visible=face is not None,
        detection_source="test",
        frame_width=720,
        frame_height=1280,
        face_score=face_score if face is not None else 0.0,
        clarity_score=0.9,
        body_completeness=0.9,
        interference_ratio=0.0,
        other_person_boxes=[],
    )


def track(
    *,
    shot_id: str,
    shot_ordinal: int,
    face: np.ndarray | None,
    reid: np.ndarray | None,
    samples: int = 3,
    face_score: float = 0.95,
    start_offset_us: int = 0,
) -> v5.TrackDraft:
    observations = [
        observation(
            shot_id=shot_id,
            shot_ordinal=shot_ordinal,
            at_us=shot_ordinal * 1_000_000 + start_offset_us + index * 80_000,
            face=face,
            reid=reid,
            face_score=face_score,
        )
        for index in range(samples)
    ]
    value = v5.TrackDraft(
        shot_id=shot_id,
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        observations=observations,
    )
    v5._refresh_track(value)
    value.representatives = [
        v5.TrackRepresentative(observation=item, quality_score=0.92, clean=True)
        for item in observations[: min(samples, 3)]
    ]
    return value


def test_many_track_fragments_of_three_people_resolve_to_three_characters() -> None:
    """底层 Track 数可以很多，但 Final identity 数不能跟 Track 碎片数一起膨胀。"""

    faces = [vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)]
    reids = [vec(1, 0.05, 0), vec(0.05, 1, 0), vec(0, 0.05, 1)]
    tracks: list[v5.TrackDraft] = []
    shot = 1
    for person_index in range(3):
        for _fragment in range(5):
            tracks.append(track(
                shot_id=f"SHOT_{shot}",
                shot_ordinal=shot,
                face=faces[person_index],
                reid=reids[person_index],
            ))
            shot += 1

    candidates = v6.resolve_global_identities(tracks)
    resolved = [item for item in candidates if item.identity_status == "RESOLVED"]

    assert len(tracks) == 15
    assert len(resolved) == 3
    assert sorted(len(item.tracks) for item in resolved) == [5, 5, 5]


def test_simultaneous_people_cannot_merge_through_transitive_graph_path() -> None:
    """A 与 B 同框是永久 cannot-link，即使它们都与第三条模糊 Track 相似也不能被图传递合并。"""

    a = track(
        shot_id="SHOT_1", shot_ordinal=1,
        face=vec(1.0, 0.0, 0.0), reid=vec(1.0, 0.0, 0.0),
        start_offset_us=0,
    )
    b = track(
        shot_id="SHOT_1", shot_ordinal=1,
        face=vec(0.72, 0.69, 0.0), reid=vec(0.72, 0.69, 0.0),
        start_offset_us=0,
    )
    bridge = track(
        shot_id="SHOT_2", shot_ordinal=2,
        face=vec(0.92, 0.39, 0.0), reid=vec(0.92, 0.39, 0.0),
    )

    candidates = v6.resolve_global_identities([a, b, bridge])
    groups = [{track.shot_id + ":" + str(track.start_us) for track in item.tracks} for item in candidates]

    assert len(candidates) >= 2
    assert not any(len(item.tracks) == 3 for item in candidates)
    assert groups


def test_isolated_face_fragment_stays_unresolved() -> None:
    fragment = track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face=vec(1, 0, 0),
        reid=vec(1, 0, 0),
        samples=1,
        face_score=0.91,
    )

    candidates = v6.resolve_global_identities([fragment])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "UNRESOLVED"


def test_single_track_with_multiple_high_quality_face_samples_can_resolve() -> None:
    value = track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face=vec(1, 0, 0),
        reid=vec(1, 0, 0),
        samples=4,
        face_score=0.94,
    )

    candidates = v6.resolve_global_identities([value])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "RESOLVED"


def test_body_only_track_cannot_create_character_identity() -> None:
    body = track(
        shot_id="SHOT_7",
        shot_ordinal=7,
        face=None,
        reid=vec(1, 0, 0),
        samples=4,
    )

    candidates = v6.resolve_global_identities([body])

    assert len(candidates) == 1
    assert candidates[0].identity_status == "UNRESOLVED"


def test_adjacent_body_only_track_can_attach_to_existing_face_identity() -> None:
    face_track = track(
        shot_id="SHOT_1",
        shot_ordinal=1,
        face=vec(1, 0, 0),
        reid=vec(1, 0, 0),
        samples=4,
    )
    body = track(
        shot_id="SHOT_2",
        shot_ordinal=2,
        face=None,
        reid=vec(1, 0, 0),
        samples=4,
    )

    candidates = v6.resolve_global_identities([face_track, body])
    resolved = [item for item in candidates if item.identity_status == "RESOLVED"]

    assert len(resolved) == 1
    assert len(resolved[0].tracks) == 2
