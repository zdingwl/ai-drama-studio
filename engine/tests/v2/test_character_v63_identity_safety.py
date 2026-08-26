from __future__ import annotations

import numpy as np

from engine.app import character_identity_v63 as identity
from engine.app import character_observation_v63 as observation
from engine.app import character_visual_v5 as v5


def vec(*values: float) -> np.ndarray:
    value = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(value))
    return value / norm if norm else value


def obs(
    *,
    shot_id: str,
    shot_ordinal: int,
    at_us: int,
    bbox: tuple[int, int, int, int],
    face: np.ndarray | None,
    reid: np.ndarray | None,
    source: str = "v6.3-yolox+face",
) -> v5.Observation:
    return v5.Observation(
        shot_id=shot_id,
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        source_time_us=at_us,
        local_time_us=max(0, at_us - shot_ordinal * 1_000_000),
        bbox=bbox,
        face_bbox=(bbox[0] + 20, bbox[1] + 15, 50, 50) if face is not None else None,
        reference_path="unused.mp4",
        detection_score=0.96,
        face_embedding=face,
        reid_embedding=reid,
        body_hist=None,
        face_visible=face is not None,
        detection_source=source,
        frame_width=720,
        frame_height=1280,
        face_score=0.95 if face is not None else 0.0,
        clarity_score=0.9,
        body_completeness=0.8,
        interference_ratio=0.0,
        other_person_boxes=[],
    )


def track(
    *,
    shot_id: str,
    shot_ordinal: int,
    bbox: tuple[int, int, int, int],
    face: np.ndarray | None,
    reid: np.ndarray | None,
    start_offset_us: int = 0,
    samples: int = 3,
) -> v5.TrackDraft:
    values = [
        obs(
            shot_id=shot_id,
            shot_ordinal=shot_ordinal,
            at_us=shot_ordinal * 1_000_000 + start_offset_us + index * 80_000,
            bbox=bbox,
            face=face,
            reid=reid,
        )
        for index in range(samples)
    ]
    result = v5.TrackDraft(
        shot_id=shot_id,
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=shot_ordinal,
        observations=values,
    )
    v5._refresh_track(result)
    result.representatives = [
        v5.TrackRepresentative(observation=item, quality_score=0.92, clean=True)
        for item in values
    ]
    return result


def test_partial_person_cannot_own_a_face() -> None:
    score = observation._face_owner_score(
        (0, 100, 300, 900),
        (80, 140, 80, 80),
        0.96,
        "v6.3-yolox-edge-partial",
    )
    assert score is None


def test_face_assignment_prefers_normal_person_over_overlapping_partial_box() -> None:
    people = [
        ((0, 50, 500, 1100), 0.20, "v6.3-yolox-partial"),
        ((100, 100, 220, 650), 0.88, "v6.3-yolox"),
    ]
    faces = [(object(), (145, 135, 70, 70), 0.97)]

    assigned, used = observation._assign_faces_to_persons(people, faces)

    assert assigned == {1: 0}
    assert used == {0}


def test_same_shot_non_overlapping_fragments_are_not_automatic_cannot_link() -> None:
    face = vec(1.0, 0.0, 0.0)
    reid = vec(1.0, 0.02, 0.0)
    left = track(
        shot_id="SHOT_10", shot_ordinal=10, bbox=(100, 100, 180, 600),
        face=face, reid=reid, start_offset_us=0,
    )
    right = track(
        shot_id="SHOT_10", shot_ordinal=10, bbox=(105, 105, 180, 600),
        face=face, reid=reid, start_offset_us=500_000,
    )

    assert identity._cluster_compatible({0}, {1}, [left, right]) is True
    assert identity._fragment_merge_score({0}, {1}, [left, right]) is not None


def test_simultaneous_spatially_distinct_people_remain_cannot_link() -> None:
    shared_face_like = vec(1.0, 0.0, 0.0)
    left = track(
        shot_id="SHOT_11", shot_ordinal=11, bbox=(20, 100, 180, 600),
        face=shared_face_like, reid=vec(1.0, 0.0, 0.0),
    )
    right = track(
        shot_id="SHOT_11", shot_ordinal=11, bbox=(500, 100, 180, 600),
        face=shared_face_like, reid=vec(1.0, 0.0, 0.0),
    )

    assert identity._simultaneous_duplicate(left, right) is False
    assert identity._identity_edge(0, 1, left, right) is None
    assert identity._cluster_compatible({0}, {1}, [left, right]) is False


def test_simultaneous_duplicate_detection_of_same_person_can_merge() -> None:
    face = vec(1.0, 0.0, 0.0)
    reid = vec(1.0, 0.01, 0.0)
    left = track(
        shot_id="SHOT_12", shot_ordinal=12, bbox=(200, 100, 220, 700),
        face=face, reid=reid,
    )
    right = track(
        shot_id="SHOT_12", shot_ordinal=12, bbox=(205, 105, 215, 695),
        face=face, reid=reid,
    )

    assert identity._simultaneous_duplicate(left, right) is True
    edge = identity._identity_edge(0, 1, left, right)
    assert edge is not None
    assert edge.reason == "same-shot-duplicate"


def test_three_people_with_extra_same_shot_fragments_still_resolve_to_three() -> None:
    faces = [vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)]
    reids = [vec(1, 0.02, 0), vec(0.02, 1, 0), vec(0, 0.02, 1)]
    tracks: list[v5.TrackDraft] = []

    # 每个人至少两个不同 Shot 的正常 Face anchor。
    for person_index in range(3):
        first_shot = person_index * 3 + 1
        tracks.append(track(
            shot_id=f"SHOT_{first_shot}", shot_ordinal=first_shot,
            bbox=(80 + person_index * 180, 100, 160, 620),
            face=faces[person_index], reid=reids[person_index],
        ))
        tracks.append(track(
            shot_id=f"SHOT_{first_shot + 1}", shot_ordinal=first_shot + 1,
            bbox=(80 + person_index * 180, 100, 160, 620),
            face=faces[person_index], reid=reids[person_index],
        ))

    # 第一个人额外在同一个 Shot 被切成一个非重叠 fragment；不能因此生成第 4 个 Final Character。
    tracks.append(track(
        shot_id="SHOT_1", shot_ordinal=1, bbox=(82, 102, 160, 620),
        face=faces[0], reid=reids[0], start_offset_us=500_000,
    ))

    candidates = identity.resolve_global_identities(tracks)
    resolved = [item for item in candidates if item.identity_status == "RESOLVED"]

    assert len(resolved) == 3
