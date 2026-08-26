from __future__ import annotations

import numpy as np

from engine.app import character_identity_v7 as v7
from engine.app import character_resolution_gate_v7 as gate
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
    bbox: tuple[int, int, int, int],
    face: np.ndarray | None,
    reid: np.ndarray | None,
    face_bbox: tuple[int, int, int, int] | None = None,
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
        face_bbox=face_bbox if face is not None else None,
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
    face: np.ndarray | None,
    reid: np.ndarray | None,
    bbox: tuple[int, int, int, int],
    face_bbox: tuple[int, int, int, int] | None = None,
    samples: int = 3,
    offset_us: int = 0,
    source: str = "v6.3-yolox+face",
) -> v5.TrackDraft:
    observations = [
        observation(
            shot_id=shot_id,
            shot_ordinal=shot_ordinal,
            at_us=shot_ordinal * 1_000_000 + offset_us + index * 80_000,
            bbox=bbox,
            face=face,
            reid=reid,
            face_bbox=face_bbox or (bbox[0] + 35, bbox[1] + 25, 60, 60),
            source=source,
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
        for item in observations
    ]
    return value


def resolved(candidates: list[v5.CandidateDraft]) -> list[v5.CandidateDraft]:
    return [item for item in candidates if item.identity_status == "RESOLVED"]


def test_three_real_people_with_many_track_fragments_still_publish_three() -> None:
    faces = [vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)]
    reids = [vec(1, 0.02, 0), vec(0.02, 1, 0), vec(0, 0.02, 1)]
    tracks: list[v5.TrackDraft] = []

    shot = 1
    for person_index in range(3):
        for _ in range(4):
            tracks.append(track(
                shot_id=f"SHOT_{shot}",
                shot_ordinal=shot,
                face=faces[person_index],
                reid=reids[person_index],
                bbox=(80 + person_index * 190, 100, 170, 650),
            ))
            shot += 1

    tracks.extend([
        track(
            shot_id="SHOT_9", shot_ordinal=9,
            face=faces[2], reid=reids[2],
            bbox=(460, 105, 170, 645), face_bbox=(500, 135, 60, 60),
        ),
        track(
            shot_id="SHOT_10", shot_ordinal=10,
            face=faces[2], reid=reids[2],
            bbox=(462, 102, 168, 648), face_bbox=(502, 132, 60, 60),
        ),
    ])

    candidates = v7.resolve_global_identities(tracks)
    gate.enforce_resolution_gate(candidates)

    assert len(resolved(candidates)) == 3


def test_body_and_partial_tracks_never_increase_final_character_count() -> None:
    face = vec(1, 0, 0)
    reid = vec(1, 0.02, 0)
    tracks = [
        track(shot_id=f"SHOT_{index}", shot_ordinal=index, face=face, reid=reid, bbox=(100, 100, 180, 650))
        for index in range(1, 5)
    ]
    for index in range(5, 15):
        tracks.append(track(
            shot_id=f"SHOT_{index}",
            shot_ordinal=index,
            face=None,
            reid=vec(0.2, 0.8, 0),
            bbox=(0, 80, 130, 820),
            source="v6.3-yolox-edge-partial",
        ))

    candidates = v7.resolve_global_identities(tracks)
    gate.enforce_resolution_gate(candidates)

    assert len(resolved(candidates)) == 1


def test_two_shot_face_fragment_with_only_two_samples_per_shot_stays_unresolved() -> None:
    face = vec(1, 0, 0)
    reid = vec(1, 0.01, 0)
    tracks = [
        track(shot_id="SHOT_20", shot_ordinal=20, face=face, reid=reid, bbox=(100, 100, 180, 650), samples=2),
        track(shot_id="SHOT_21", shot_ordinal=21, face=face, reid=reid, bbox=(100, 100, 180, 650), samples=2),
    ]

    candidates = v7.resolve_global_identities(tracks)
    gate.enforce_resolution_gate(candidates)

    assert len(resolved(candidates)) == 0
    assert any(item.identity_status == "UNRESOLVED" for item in candidates)


def test_even_extremely_strong_two_shot_face_identity_is_not_auto_final() -> None:
    face = vec(1, 0, 0)
    reid = vec(1, 0.001, 0)
    tracks = [
        track(shot_id="SHOT_22", shot_ordinal=22, face=face, reid=reid, bbox=(100, 100, 180, 650), samples=6),
        track(shot_id="SHOT_23", shot_ordinal=23, face=face, reid=reid, bbox=(100, 100, 180, 650), samples=6),
    ]

    candidates = v7.resolve_global_identities(tracks)
    assert len(resolved(candidates)) == 1  # identity resolver may recognize it strongly

    gate.enforce_resolution_gate(candidates)

    assert len(resolved(candidates)) == 0
    assert candidates[0].v6_metadata["v7_resolution_reason"] == "fewer-than-3-distinct-face-shots"


def test_same_sample_spatially_distinct_faces_cannot_merge_even_if_embedding_is_similar() -> None:
    face = vec(1, 0, 0)
    left = track(
        shot_id="SHOT_30", shot_ordinal=30,
        face=face, reid=vec(1, 0, 0),
        bbox=(20, 100, 180, 650), face_bbox=(60, 130, 60, 60), samples=1,
    )
    right = track(
        shot_id="SHOT_30", shot_ordinal=30,
        face=face, reid=vec(1, 0, 0),
        bbox=(480, 100, 180, 650), face_bbox=(520, 130, 60, 60), samples=1,
    )

    anchors = v7._anchors([left, right])

    assert len(anchors) == 2
    assert v7._same_sample_distinct(anchors[0], anchors[1]) is True
    assert v7._pair_edge(anchors[0], anchors[1]) is None


def test_duplicate_tracks_of_same_face_in_same_sample_share_one_face_identity() -> None:
    face = vec(1, 0, 0)
    reid = vec(1, 0.01, 0)
    left = track(
        shot_id="SHOT_40", shot_ordinal=40,
        face=face, reid=reid,
        bbox=(200, 100, 220, 700), face_bbox=(250, 135, 70, 70), samples=1,
    )
    right = track(
        shot_id="SHOT_40", shot_ordinal=40,
        face=face, reid=reid,
        bbox=(205, 105, 215, 695), face_bbox=(252, 137, 70, 70), samples=1,
    )

    anchors = v7._anchors([left, right])

    assert v7._pair_edge(anchors[0], anchors[1]) is not None
