from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from engine.app.character_detection import (
    CLUSTER_MIN_COSINE,
    FACE_SCORE_THRESHOLD,
    PROFILE_VERSION,
    FaceObservation,
    TrackDraft,
    _blob_to_embedding,
    _build_sample_plan,
    _build_shot_tracks,
    _cluster_tracks,
    _embedding_to_blob,
    _normalize_embedding,
    _tracks_conflict,
)
from engine.app.shot_workbench import FinalShotRecord

NOW = datetime.now(timezone.utc)


def _shot(ordinal: int, start: int, end: int) -> FinalShotRecord:
    return FinalShotRecord(
        id=f"SHOT_{ordinal}",
        edit_set_id="SHOT_EDIT_test",
        project_id="PROJECT_test",
        ordinal=ordinal,
        final_start_us=start,
        final_end_us=end,
        duration_us=end - start,
        origin_kind="auto",
        origin_candidate_ids=(f"CANDIDATE_{ordinal}",),
        created_at=NOW,
        updated_at=NOW,
    )


def _embedding(axis: int = 0, blend_axis: int | None = None, blend: float = 0.0) -> np.ndarray:
    vector = np.zeros(128, dtype=np.float32)
    vector[axis] = 1.0
    if blend_axis is not None:
        vector[blend_axis] = blend
    return _normalize_embedding(vector)


def _observation(
    *,
    shot_id: str,
    shot_ordinal: int,
    time_us: int,
    bbox: tuple[int, int, int, int],
    embedding: np.ndarray,
    quality: float = 0.9,
) -> FaceObservation:
    return FaceObservation(
        final_shot_id=shot_id,
        final_shot_ordinal=shot_ordinal,
        source_time_us=time_us,
        bbox=bbox,
        detection_score=0.95,
        face_quality=quality,
        embedding=embedding,
    )


def test_f06_v2_profile_restores_confirmed_detection_and_cluster_thresholds() -> None:
    assert PROFILE_VERSION == "f06-v2"
    assert FACE_SCORE_THRESHOLD == 0.90
    assert CLUSTER_MIN_COSINE == 0.45


def test_sample_plan_uses_real_pts_and_stays_inside_final_shots() -> None:
    shots = (_shot(1, 100_000, 900_000), _shot(2, 900_000, 2_000_000))
    # 故意使用不规则 PTS，确保结果来自这组真实时间，而不是 frame_index / fps。
    pts = (100_000, 137_000, 221_000, 355_000, 508_000, 701_000, 899_000, 941_000, 1_111_000, 1_509_000, 1_997_000)
    plan = _build_sample_plan(shots=shots, frame_source_pts=pts)

    assert plan
    assert all(item.source_time_us in pts for item in plan)
    assert all(
        next(shot for shot in shots if shot.id == item.final_shot_id).final_start_us
        <= item.source_time_us
        < next(shot for shot in shots if shot.id == item.final_shot_id).final_end_us
        for item in plan
    )
    assert len({item.frame_index for item in plan}) == len(plan)


def test_shot_local_tracking_merges_same_face_but_keeps_cooccurring_other_face_separate() -> None:
    person_a = _embedding(0)
    person_b = _embedding(1)
    observations = (
        _observation(shot_id="SHOT_1", shot_ordinal=1, time_us=100_000, bbox=(100, 100, 80, 80), embedding=person_a),
        _observation(shot_id="SHOT_1", shot_ordinal=1, time_us=100_000, bbox=(400, 100, 80, 80), embedding=person_b),
        _observation(shot_id="SHOT_1", shot_ordinal=1, time_us=350_000, bbox=(108, 102, 82, 82), embedding=person_a),
        _observation(shot_id="SHOT_1", shot_ordinal=1, time_us=350_000, bbox=(392, 102, 82, 82), embedding=person_b),
    )

    tracks = _build_shot_tracks(observations)
    assert len(tracks) == 2
    assert sorted(track.sample_count for track in tracks) == [2, 2]
    assert all(track.final_shot_id == "SHOT_1" for track in tracks)


def test_conservative_clustering_merges_cross_shot_same_identity() -> None:
    person = _embedding(0, 2, 0.1)
    first = TrackDraft(
        id="TRACK_1",
        final_shot_id="SHOT_1",
        final_shot_ordinal=1,
        observations=[_observation(shot_id="SHOT_1", shot_ordinal=1, time_us=100_000, bbox=(10, 10, 80, 80), embedding=person)],
        embedding=person,
        track_ordinal_in_shot=1,
    )
    second = TrackDraft(
        id="TRACK_2",
        final_shot_id="SHOT_2",
        final_shot_ordinal=2,
        observations=[_observation(shot_id="SHOT_2", shot_ordinal=2, time_us=1_100_000, bbox=(20, 20, 82, 82), embedding=person)],
        embedding=person,
        track_ordinal_in_shot=1,
    )

    candidates = _cluster_tracks([first, second])
    assert len(candidates) == 1
    assert len(candidates[0].tracks) == 2
    assert candidates[0].cluster_score is not None
    assert candidates[0].cluster_score >= CLUSTER_MIN_COSINE


def test_v2_merges_cross_pose_tracks_between_old_050_and_new_045_threshold() -> None:
    """真实素材回归：同一人物侧脸/角度变化不能因为旧 0.50 门槛被拆成多个 Candidate。"""

    frontal = _embedding(0)
    # cosine(frontal, angled) ≈ 0.475：旧 f06-v1(0.50) 会拆，f06-v2(0.45) 应合并。
    angled = _embedding(0, 1, 1.85)
    assert 0.45 <= float(np.dot(frontal, angled)) < 0.50

    first = TrackDraft(
        id="TRACK_FRONTAL",
        final_shot_id="SHOT_1",
        final_shot_ordinal=1,
        observations=[_observation(shot_id="SHOT_1", shot_ordinal=1, time_us=100_000, bbox=(10, 10, 100, 100), embedding=frontal)],
        embedding=frontal,
        track_ordinal_in_shot=1,
    )
    second = TrackDraft(
        id="TRACK_ANGLED",
        final_shot_id="SHOT_2",
        final_shot_ordinal=2,
        observations=[_observation(shot_id="SHOT_2", shot_ordinal=2, time_us=1_100_000, bbox=(20, 20, 96, 96), embedding=angled)],
        embedding=angled,
        track_ordinal_in_shot=1,
    )

    candidates = _cluster_tracks([first, second])
    assert len(candidates) == 1
    assert {track.id for track in candidates[0].tracks} == {"TRACK_FRONTAL", "TRACK_ANGLED"}


def test_cooccurring_tracks_are_hard_conflict_even_with_identical_embedding() -> None:
    person = _embedding(0)
    first = TrackDraft(
        id="TRACK_1",
        final_shot_id="SHOT_1",
        final_shot_ordinal=1,
        observations=[_observation(shot_id="SHOT_1", shot_ordinal=1, time_us=100_000, bbox=(10, 10, 80, 80), embedding=person)],
        embedding=person,
        track_ordinal_in_shot=1,
    )
    second = TrackDraft(
        id="TRACK_2",
        final_shot_id="SHOT_1",
        final_shot_ordinal=1,
        observations=[_observation(shot_id="SHOT_1", shot_ordinal=1, time_us=100_000, bbox=(300, 10, 80, 80), embedding=person)],
        embedding=person,
        track_ordinal_in_shot=2,
    )

    assert _tracks_conflict(first, second) is True
    candidates = _cluster_tracks([first, second])
    assert len(candidates) == 2


def test_embedding_blob_is_little_endian_float32_and_round_trips() -> None:
    vector = _embedding(3, 4, 0.25)
    blob = _embedding_to_blob(vector)
    assert len(blob) == 128 * 4
    restored = _blob_to_embedding(blob)
    assert restored.dtype == np.float32
    assert restored.shape == (128,)
    assert np.allclose(restored, vector, atol=1e-6)
