from __future__ import annotations

import numpy as np

from engine.app import character_identity_v8 as v8
from engine.app import character_visual_v5 as v5


def vec(*values: float) -> np.ndarray:
    value = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(value))
    return value / norm if norm else value


def make_track(
    *,
    shot: int,
    face: np.ndarray | None,
    reid: np.ndarray | None,
    face_score: float = 0.96,
    clarity: float = 0.92,
    source: str = "v6.3-yolox+face",
    bbox: tuple[int, int, int, int] = (100, 100, 220, 720),
) -> v5.TrackDraft:
    observations: list[v5.Observation] = []
    for index in range(3):
        observations.append(v5.Observation(
            shot_id=f"SHOT_{shot:04d}",
            episode_id="EP1",
            episode_order=1,
            shot_ordinal=shot,
            source_time_us=shot * 1_000_000 + index * 80_000,
            local_time_us=index * 80_000,
            bbox=bbox,
            face_bbox=(bbox[0] + 55, bbox[1] + 30, 70, 70) if face is not None else None,
            reference_path="unused.mp4",
            detection_score=0.96,
            face_embedding=face,
            reid_embedding=reid,
            body_hist=None,
            face_visible=face is not None,
            detection_source=source,
            frame_width=720,
            frame_height=1280,
            face_score=face_score if face is not None else 0.0,
            clarity_score=clarity,
            body_completeness=0.85,
            interference_ratio=0.0,
            other_person_boxes=[],
        ))
    track = v5.TrackDraft(
        shot_id=f"SHOT_{shot:04d}",
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=shot,
        observations=observations,
    )
    v5._refresh_track(track)
    track.representatives = [
        v5.TrackRepresentative(observation=item, quality_score=0.95, clean=True)
        for item in observations
    ]
    return track


def final(candidates: list[v5.CandidateDraft]) -> list[v5.CandidateDraft]:
    return [item for item in candidates if item.identity_status == "RESOLVED"]


def test_confirm_one_person_then_later_fragments_are_absorbed_before_new_identity() -> None:
    person_a = vec(1.0, 0.0, 0.0, 0.0)
    person_a_pose = vec(0.94, 0.18, 0.0, 0.0)
    reid_a = vec(1.0, 0.02, 0.0, 0.0)

    tracks = [
        make_track(shot=1, face=person_a, reid=reid_a),
        make_track(shot=2, face=person_a, reid=reid_a),
        make_track(shot=3, face=person_a, reid=reid_a),
        # 后面同一人再次出现，MOT 即使切成三个独立 Track，也必须吸收到已确认 A。
        make_track(shot=19, face=person_a_pose, reid=reid_a),
        make_track(shot=28, face=person_a_pose, reid=reid_a),
        make_track(shot=30, face=person_a_pose, reid=reid_a),
    ]

    candidates = v8.resolve_global_identities(tracks)

    assert len(final(candidates)) == 1
    assert {track.shot_id for track in final(candidates)[0].tracks} >= {
        "SHOT_0001", "SHOT_0002", "SHOT_0003", "SHOT_0019", "SHOT_0028", "SHOT_0030"
    }


def test_three_confirmed_people_remain_three_even_with_many_track_fragments() -> None:
    faces = [
        vec(1, 0, 0, 0),
        vec(0, 1, 0, 0),
        vec(0, 0, 1, 0),
    ]
    reids = [
        vec(1, 0.02, 0, 0),
        vec(0.02, 1, 0, 0),
        vec(0, 0.02, 1, 0),
    ]
    tracks: list[v5.TrackDraft] = []
    shot = 1
    for person in range(3):
        for _ in range(3):
            tracks.append(make_track(shot=shot, face=faces[person], reid=reids[person]))
            shot += 1

    # 第三个人后续又出现三条碎 Track。
    pose = vec(0.0, 0.08, 0.96, 0.0)
    tracks.extend([
        make_track(shot=19, face=pose, reid=reids[2]),
        make_track(shot=28, face=pose, reid=reids[2]),
        make_track(shot=30, face=pose, reid=reids[2]),
    ])

    candidates = v8.resolve_global_identities(tracks)

    assert len(final(candidates)) == 3


def test_ambiguous_face_is_unresolved_instead_of_creating_duplicate_person() -> None:
    person_a = vec(1.0, 0.0, 0.0, 0.0)
    reid_a = vec(1.0, 0.0, 0.0, 0.0)
    tracks = [
        make_track(shot=1, face=person_a, reid=reid_a),
        make_track(shot=2, face=person_a, reid=reid_a),
        make_track(shot=3, face=person_a, reid=reid_a),
    ]

    # 与 A 有中等相似，但达不到可靠吸收门槛；V8 必须保守为 UNRESOLVED，不能创建 A2。
    ambiguous = vec(0.38, 0.925, 0.0, 0.0)
    ambiguous_reid = vec(0.20, 0.98, 0.0, 0.0)
    tracks.extend([
        make_track(shot=10, face=ambiguous, reid=ambiguous_reid),
        make_track(shot=11, face=ambiguous, reid=ambiguous_reid),
        make_track(shot=12, face=ambiguous, reid=ambiguous_reid),
    ])

    candidates = v8.resolve_global_identities(tracks)

    assert len(final(candidates)) == 1
    assert any(item.identity_status == "UNRESOLVED" for item in candidates)


def test_body_partial_evidence_never_creates_new_character() -> None:
    face = vec(1, 0, 0, 0)
    reid = vec(1, 0, 0, 0)
    tracks = [
        make_track(shot=1, face=face, reid=reid),
        make_track(shot=2, face=face, reid=reid),
        make_track(shot=3, face=face, reid=reid),
    ]
    for shot in range(4, 10):
        tracks.append(make_track(
            shot=shot,
            face=None,
            reid=vec(0, 1, 0, 0),
            source="v6.3-yolox-edge-partial",
        ))

    candidates = v8.resolve_global_identities(tracks)

    assert len(final(candidates)) == 1
