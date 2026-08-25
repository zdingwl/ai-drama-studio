"""Character V5.1 Conservative Identity。

职责：
- Track 已经稳定后，才决定是否并入已有 Character_ID；
- Face 是身份强证据；Body ReID 只做辅助，不能覆盖明确的人脸冲突；
- Body-only Track 只允许在相邻 Shot + 极高 ReID 相似度时临时挂回已有 Character；
- 二次去碎片只在极强 Face 一致时执行；宁可留下待合并碎片，也不把不同人物串到一个 Character。

核心原则：
1. 有可靠 Face 且 Face 不一致 -> 禁止合并；
2. Track 有 CLEAN representative -> ReID 只使用 CLEAN 图；
3. 无 Face -> ReID 不能跨多个 Shot 宽松合并；
4. 同 Shot 同时存在 -> 永久 cannot-link。
"""
from __future__ import annotations

from statistics import median

from engine.app import character_visual_v5 as v5

CandidateDraft = v5.CandidateDraft
TrackDraft = v5.TrackDraft
TrackRepresentative = v5.TrackRepresentative

# 跨 Shot Character_ID 合并阈值。故意比 V5 保守。
FACE_HARD_CONFLICT = 0.30
FACE_STRONG_MATCH = 0.60
FACE_SUPPORTED_MATCH = 0.50
REID_FACE_SUPPORT = 0.82
BODY_ONLY_REID_MATCH = 0.90
BODY_ONLY_MAX_SHOT_GAP = 1
SECOND_PASS_FACE_MATCH = 0.68
SECOND_PASS_FACE_FLOOR = 0.40


def _face_vectors_from_track(track: TrackDraft) -> list[object]:
    return [
        obs.face_embedding
        for obs in track.observations
        if obs.face_embedding is not None
    ]


def _face_vectors_from_candidate(candidate: CandidateDraft) -> list[object]:
    result: list[object] = []
    for track in candidate.tracks:
        result.extend(_face_vectors_from_track(track))
    return result


def _clean_reid_vectors_from_track(track: TrackDraft) -> list[object]:
    clean = [rep for rep in track.representatives if rep.clean]
    return [rep.observation.reid_embedding for rep in clean if rep.observation.reid_embedding is not None]


def _clean_reid_vectors_from_candidate(candidate: CandidateDraft) -> list[object]:
    return [
        rep.observation.reid_embedding
        for rep in candidate.gallery
        if rep.clean and rep.observation.reid_embedding is not None
    ]


def _directed_profile(left: list[object], right: list[object]) -> tuple[float | None, float | None]:
    """left 中每个向量去 right 找最佳匹配，再取中位数和最低最佳值。

    中位数避免“只有一张碰巧像”就并人；最低最佳值用于发现明显反证。
    """

    if not left or not right:
        return None, None
    best_per_left: list[float] = []
    for vector in left:
        values = [v5.cosine(vector, other) for other in right]
        clean = [float(value) for value in values if value is not None]
        if clean:
            best_per_left.append(max(clean))
    if not best_per_left:
        return None, None
    return float(median(best_per_left)), min(best_per_left)


def _symmetric_face_profile(candidate: CandidateDraft, track: TrackDraft) -> tuple[float | None, float | None]:
    candidate_faces = _face_vectors_from_candidate(candidate)
    track_faces = _face_vectors_from_track(track)
    left_score, left_floor = _directed_profile(track_faces, candidate_faces)
    right_score, right_floor = _directed_profile(candidate_faces, track_faces)
    scores = [value for value in (left_score, right_score) if value is not None]
    floors = [value for value in (left_floor, right_floor) if value is not None]
    return (sum(scores) / len(scores) if scores else None, min(floors) if floors else None)


def _reid_profile(candidate: CandidateDraft, track: TrackDraft) -> float | None:
    # 只允许 CLEAN person crop 参与 Body ReID 身份合并。
    candidate_vectors = _clean_reid_vectors_from_candidate(candidate)
    track_vectors = _clean_reid_vectors_from_track(track)
    left, _ = _directed_profile(track_vectors, candidate_vectors)
    right, _ = _directed_profile(candidate_vectors, track_vectors)
    values = [value for value in (left, right) if value is not None]
    return sum(values) / len(values) if values else None


def _candidate_match_score(candidate: CandidateDraft, track: TrackDraft) -> float | None:
    if v5._simultaneous_conflict(candidate, track):
        return None

    face, face_floor = _symmetric_face_profile(candidate, track)
    reid = _reid_profile(candidate, track)
    gap = v5._track_gap(candidate, track)
    candidate_has_face = bool(_face_vectors_from_candidate(candidate))
    track_has_face = bool(_face_vectors_from_track(track))

    # 两边都有 Face 时，Face 具有否决权：明显不一致时 ReID 再高也不允许并人。
    if candidate_has_face and track_has_face:
        if face is None or face_floor is None:
            return None
        if face < FACE_HARD_CONFLICT or face_floor < FACE_HARD_CONFLICT:
            return None
        if face >= FACE_STRONG_MATCH and face_floor >= 0.36:
            return face * 0.82 + max(0.0, reid or 0.0) * 0.18
        if face >= FACE_SUPPORTED_MATCH and face_floor >= 0.34 and reid is not None and reid >= REID_FACE_SUPPORT:
            return face * 0.76 + reid * 0.24
        return None

    # 只有一边有 Face：只能把 body-only Track 在非常近的时间连续性下临时挂回。
    # 不允许像 V5 那样跨 4 个 Shot 用 0.76 ReID 自动合并。
    if gap is None or gap > BODY_ONLY_MAX_SHOT_GAP:
        return None
    if reid is None or reid < BODY_ONLY_REID_MATCH:
        return None
    return reid * 0.92 + 0.03


def _candidate_pair_score(left: CandidateDraft, right: CandidateDraft) -> float | None:
    # 同框冲突仍是永久 hard cannot-link。
    for track in right.tracks:
        if v5._simultaneous_conflict(left, track):
            return None

    left_faces = _face_vectors_from_candidate(left)
    right_faces = _face_vectors_from_candidate(right)
    if not left_faces or not right_faces:
        return None

    lr, lr_floor = _directed_profile(left_faces, right_faces)
    rl, rl_floor = _directed_profile(right_faces, left_faces)
    if lr is None or rl is None or lr_floor is None or rl_floor is None:
        return None
    face = (lr + rl) / 2.0
    floor = min(lr_floor, rl_floor)

    # 二次去碎片只允许非常强的双向 Face 一致。
    if face < SECOND_PASS_FACE_MATCH or floor < SECOND_PASS_FACE_FLOOR:
        return None
    return face


def _merge_candidate_fragments(candidates: list[CandidateDraft]) -> list[CandidateDraft]:
    changed = True
    while changed:
        changed = False
        best: tuple[float, int, int] | None = None
        for left_index in range(len(candidates)):
            for right_index in range(left_index + 1, len(candidates)):
                score = _candidate_pair_score(candidates[left_index], candidates[right_index])
                if score is not None and (best is None or score > best[0]):
                    best = (score, left_index, right_index)
        if best is None:
            break
        score, left_index, right_index = best
        source = candidates[right_index]
        for track in source.tracks:
            v5._append_track(candidates[left_index], track, score)
        del candidates[right_index]
        changed = True
    return candidates


def cluster_candidates(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    """V5.1 Track Gallery -> Character Gallery。

    处理顺序按剧集/Shot 时间推进。任何证据不足的 Track 都先成为独立 Candidate，
    后面只有非常强的 Face 证据才自动去碎片。
    """

    ordered = sorted(
        tracks,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
    candidates: list[CandidateDraft] = []
    for track in ordered:
        best_candidate: CandidateDraft | None = None
        best_score = -1.0
        for candidate in candidates:
            score = _candidate_match_score(candidate, track)
            if score is not None and score > best_score:
                best_candidate = candidate
                best_score = score

        if best_candidate is None:
            best_candidate = CandidateDraft(
                id=v5.new_id("CHAR_CANDIDATE"),
                identity_status="RESOLVED" if track.face_embedding is not None else "UNRESOLVED",
            )
            candidates.append(best_candidate)
            v5._append_track(best_candidate, track)
        else:
            v5._append_track(best_candidate, track, best_score)

    return _merge_candidate_fragments(candidates)
