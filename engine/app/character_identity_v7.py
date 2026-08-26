"""Character V7 Face-first Global Identity Resolver.

核心改变：Final Character 数量不再由 Person Track cluster 决定，而只由稳定 Face Identity cluster 决定。
Person/partial/body Track 只负责 Shot presence / body continuity，不能因为 Track 碎片数量增加 Character 数。

流程：
Face observations -> face-anchor graph -> stable Face Identity
-> attach contributing Person Tracks
-> conservatively attach body/partial Tracks
-> unresolved Evidence for everything else.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.studio_v2 import new_id

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft
Observation = v5.Observation

FACE_ANCHOR_MIN_SCORE = 0.70
FACE_EDGE_STRONG = 0.50
FACE_EDGE_SUPPORTED = 0.36
FACE_HARD_CONFLICT = 0.14
REID_EDGE_SUPPORT = 0.82
REID_EDGE_STRONG = 0.90

SAME_SAMPLE_TOLERANCE_US = 45_000
SAME_FACE_IOU = 0.34
SAME_FACE_STRONG = 0.56

FRAGMENT_FACE_STRONG = 0.49
FRAGMENT_FACE_SUPPORTED = 0.37
FRAGMENT_REID_SUPPORT = 0.76

# 宁可保留 UNRESOLVED，也不能用两个弱碎片发布新人物。
RESOLVED_MIN_FACE_SHOTS = 3
TWO_SHOT_FACE_STRONG = 0.68
TWO_SHOT_FACE_SUPPORTED = 0.56
TWO_SHOT_REID_SUPPORT = 0.90
TWO_SHOT_MIN_FACE_SAMPLES = 6

BODY_ATTACH_MAX_SHOT_GAP = 1
BODY_ATTACH_SCORE = 0.92
BODY_ATTACH_SINGLE_SCORE = 0.97
BODY_ATTACH_MARGIN = 0.04


@dataclass(frozen=True)
class FaceAnchor:
    index: int
    track_index: int
    observation: Observation

    @property
    def shot_id(self) -> str:
        return self.observation.shot_id

    @property
    def source_time_us(self) -> int:
        return int(self.observation.source_time_us)

    @property
    def face_bbox(self) -> tuple[int, int, int, int] | None:
        return self.observation.face_bbox

    @property
    def face_embedding(self) -> Any:
        return self.observation.face_embedding

    @property
    def reid_embedding(self) -> Any:
        return self.observation.reid_embedding


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> int:
        a, b = self.find(left), self.find(right)
        if a == b:
            return a
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1
        return a


def _is_partial(observation: Observation) -> bool:
    return "partial" in str(observation.detection_source or "").lower()


def _valid_face_anchor(observation: Observation) -> bool:
    return bool(
        observation.face_embedding is not None
        and observation.face_bbox is not None
        and not _is_partial(observation)
        and float(getattr(observation, "face_score", observation.detection_score)) >= FACE_ANCHOR_MIN_SCORE
    )


def _anchors(tracks: list[TrackDraft]) -> list[FaceAnchor]:
    result: list[FaceAnchor] = []
    for track_index, track in enumerate(tracks):
        for observation in track.observations:
            if not _valid_face_anchor(observation):
                continue
            result.append(FaceAnchor(len(result), track_index, observation))
    return result


def _same_sample(left: FaceAnchor, right: FaceAnchor) -> bool:
    return bool(
        left.shot_id == right.shot_id
        and abs(left.source_time_us - right.source_time_us) <= SAME_SAMPLE_TOLERANCE_US
    )


def _face_iou(left: FaceAnchor, right: FaceAnchor) -> float:
    if left.face_bbox is None or right.face_bbox is None:
        return 0.0
    return v5.bbox_iou(left.face_bbox, right.face_bbox)


def _face_similarity(left: FaceAnchor, right: FaceAnchor) -> float | None:
    return v5.cosine(left.face_embedding, right.face_embedding)


def _reid_similarity(left: FaceAnchor, right: FaceAnchor) -> float | None:
    return v5.cosine(left.reid_embedding, right.reid_embedding)


def _same_sample_distinct(left: FaceAnchor, right: FaceAnchor) -> bool:
    if not _same_sample(left, right):
        return False
    return _face_iou(left, right) < SAME_FACE_IOU


def _pair_edge(left: FaceAnchor, right: FaceAnchor) -> float | None:
    face = _face_similarity(left, right)
    reid = _reid_similarity(left, right)

    if _same_sample(left, right):
        # 同一采样时刻只有同一 Face bbox 的重复 observation 才允许合并。
        if _face_iou(left, right) >= SAME_FACE_IOU and face is not None and face >= SAME_FACE_STRONG:
            return min(0.995, face * 0.88 + max(0.0, reid or 0.0) * 0.12)
        return None

    if face is None:
        return None
    if face >= FACE_EDGE_STRONG:
        return min(0.99, face * 0.90 + max(0.0, reid or 0.0) * 0.10)
    if face >= FACE_EDGE_SUPPORTED and reid is not None and reid >= REID_EDGE_SUPPORT:
        return min(0.97, face * 0.72 + reid * 0.28)

    # 相邻 Shot 的困难侧脸，只在 ReID 极强时补边。
    shot_gap = abs(int(left.observation.shot_ordinal) - int(right.observation.shot_ordinal))
    if face >= 0.32 and reid is not None and reid >= REID_EDGE_STRONG and shot_gap <= 1:
        return min(0.94, face * 0.64 + reid * 0.36)
    return None


def _clusters(uf: _UnionFind, size: int) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for index in range(size):
        result.setdefault(uf.find(index), set()).add(index)
    return result


def _cluster_compatible(left: set[int], right: set[int], anchors: list[FaceAnchor]) -> bool:
    for left_index in left:
        for right_index in right:
            a, b = anchors[left_index], anchors[right_index]
            if _same_sample_distinct(a, b):
                return False
            face = _face_similarity(a, b)
            if face is not None and face < FACE_HARD_CONFLICT:
                return False
    return True


def _cluster_face_vectors(indices: set[int], anchors: list[FaceAnchor]) -> list[Any]:
    return [anchors[index].face_embedding for index in indices]


def _cluster_reid_vectors(indices: set[int], anchors: list[FaceAnchor]) -> list[Any]:
    return [anchors[index].reid_embedding for index in indices if anchors[index].reid_embedding is not None]


def _fragment_merge_score(left: set[int], right: set[int], anchors: list[FaceAnchor]) -> float | None:
    if not _cluster_compatible(left, right, anchors):
        return None
    left_faces = _cluster_face_vectors(left, anchors)
    right_faces = _cluster_face_vectors(right, anchors)
    face = v5.cosine(v5.mean_vector(left_faces), v5.mean_vector(right_faces))
    left_reid = _cluster_reid_vectors(left, anchors)
    right_reid = _cluster_reid_vectors(right, anchors)
    reid = (
        v5.cosine(v5.mean_vector(left_reid), v5.mean_vector(right_reid))
        if left_reid and right_reid
        else None
    )
    if face is None:
        return None
    if face >= FRAGMENT_FACE_STRONG:
        return face * 0.82 + max(0.0, reid or 0.0) * 0.18
    if face >= FRAGMENT_FACE_SUPPORTED and reid is not None and reid >= FRAGMENT_REID_SUPPORT:
        return face * 0.72 + reid * 0.28
    return None


def _merge_fragments(uf: _UnionFind, anchors: list[FaceAnchor]) -> None:
    while True:
        current = [set(value) for value in _clusters(uf, len(anchors)).values()]
        best: tuple[float, set[int], set[int]] | None = None
        for left_pos, left in enumerate(current):
            for right in current[left_pos + 1:]:
                score = _fragment_merge_score(left, right, anchors)
                if score is None:
                    continue
                if best is None or score > best[0]:
                    best = (score, left, right)
        if best is None:
            return
        _score, left, right = best
        uf.union(next(iter(left)), next(iter(right)))


def _cross_shot_scores(indices: set[int], anchors: list[FaceAnchor]) -> list[tuple[float, float | None]]:
    values: list[tuple[float, float | None]] = []
    ordered = sorted(indices)
    for pos, left_index in enumerate(ordered):
        for right_index in ordered[pos + 1:]:
            left, right = anchors[left_index], anchors[right_index]
            if left.shot_id == right.shot_id:
                continue
            face = _face_similarity(left, right)
            if face is None:
                continue
            values.append((float(face), _reid_similarity(left, right)))
    return values


def _resolved(indices: set[int], anchors: list[FaceAnchor]) -> bool:
    shots = {anchors[index].shot_id for index in indices}
    if len(shots) < 2:
        return False

    pairs = _cross_shot_scores(indices, anchors)
    if not pairs:
        return False

    # 正常自动发布：至少三个独立 Face Shot。
    if len(shots) >= RESOLVED_MIN_FACE_SHOTS:
        strong_pairs = [face for face, _reid in pairs if face >= FACE_EDGE_SUPPORTED]
        return len(strong_pairs) >= 2

    # 两 Shot 角色只在证据极强时例外发布，避免两个 Face 碎片制造第 4/5/6 个人物。
    if len(indices) < TWO_SHOT_MIN_FACE_SAMPLES:
        return False
    best_face, best_reid = max(pairs, key=lambda item: item[0])
    return bool(
        best_face >= TWO_SHOT_FACE_STRONG
        or (
            best_face >= TWO_SHOT_FACE_SUPPORTED
            and best_reid is not None
            and best_reid >= TWO_SHOT_REID_SUPPORT
        )
    )


def _build_track(source: TrackDraft, observations: list[Observation]) -> TrackDraft:
    value = TrackDraft(
        shot_id=source.shot_id,
        episode_id=source.episode_id,
        episode_order=source.episode_order,
        shot_ordinal=source.shot_ordinal,
        observations=sorted(observations, key=lambda item: item.source_time_us),
    )
    v5._refresh_track(value)
    value.representatives = v5.select_track_representatives(value)
    return value


def _track_interval(track: TrackDraft) -> tuple[int | None, int | None]:
    if not track.observations:
        return None, None
    return (
        min(item.source_time_us for item in track.observations),
        max(item.source_time_us for item in track.observations),
    )


def _simultaneous_distinct(track: TrackDraft, member: TrackDraft) -> bool:
    if track.shot_id != member.shot_id:
        return False
    left_start, left_end = _track_interval(track)
    right_start, right_end = _track_interval(member)
    if left_start is None or right_start is None:
        return True
    if max(left_start, right_start) > min(left_end or left_start, right_end or right_start):
        return False
    # 高度重合允许视为同人重复 Track；空间明显不同才是冲突。
    best_iou = max(
        (v5.bbox_iou(a.bbox, b.bbox) for a in track.observations for b in member.observations),
        default=0.0,
    )
    return best_iou < 0.45


def _clean_reid_vectors(track: TrackDraft) -> list[Any]:
    values = [
        rep.observation.reid_embedding
        for rep in track.representatives
        if rep.clean and rep.observation.reid_embedding is not None
    ]
    if not values and track.reid_embedding is not None:
        values.append(track.reid_embedding)
    return values


def _body_attach_score(track: TrackDraft, candidate: CandidateDraft) -> float | None:
    if any(_simultaneous_distinct(track, member) for member in candidate.tracks):
        return None
    gaps = [
        abs(int(track.shot_ordinal) - int(member.shot_ordinal))
        for member in candidate.tracks
        if track.episode_id == member.episode_id
    ]
    if not gaps or min(gaps) > BODY_ATTACH_MAX_SHOT_GAP:
        return None

    body_vectors = _clean_reid_vectors(track)
    gallery_vectors = [
        value
        for member in candidate.tracks
        for value in _clean_reid_vectors(member)
    ]
    if not body_vectors or not gallery_vectors:
        return None

    scores = sorted(
        (
            float(score)
            for left in body_vectors
            for right in gallery_vectors
            if (score := v5.cosine(left, right)) is not None
        ),
        reverse=True,
    )
    if not scores:
        return None
    if len(scores) >= 2:
        support = float(median(scores[: min(4, len(scores))]))
        return support if scores[1] >= BODY_ATTACH_SCORE and support >= BODY_ATTACH_SCORE else None
    return scores[0] if scores[0] >= BODY_ATTACH_SINGLE_SCORE else None


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    ordered = sorted(
        tracks,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
    anchors = _anchors(ordered)
    if not anchors:
        # 人体 Evidence 仍保留，但没有 Face Identity 时 Final Character 必须是 0。
        unresolved: list[CandidateDraft] = []
        for track in ordered:
            candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
            v5._append_track(candidate, track)
            candidate.identity_status = "UNRESOLVED"
            candidate.v6_metadata = {"resolver": "face-first-v7", "reason": "no-face-anchor"}  # type: ignore[attr-defined]
            unresolved.append(candidate)
        return unresolved

    uf = _UnionFind(len(anchors))
    edges: list[tuple[float, int, int]] = []
    for left_index, left in enumerate(anchors):
        for right_index in range(left_index + 1, len(anchors)):
            right = anchors[right_index]
            score = _pair_edge(left, right)
            if score is not None:
                edges.append((score, left_index, right_index))

    for _score, left_index, right_index in sorted(edges, reverse=True):
        left_root, right_root = uf.find(left_index), uf.find(right_index)
        if left_root == right_root:
            continue
        current = _clusters(uf, len(anchors))
        left_cluster = current[left_root]
        right_cluster = current[right_root]
        if _cluster_compatible(left_cluster, right_cluster, anchors):
            uf.union(left_root, right_root)

    _merge_fragments(uf, anchors)
    anchor_clusters = [set(value) for value in _clusters(uf, len(anchors)).values()]
    cluster_by_anchor = {anchor_index: cluster_index for cluster_index, cluster in enumerate(anchor_clusters) for anchor_index in cluster}

    # Observation object -> Face Identity cluster；同一 Track 即使被 MOT 切碎，也不会因此创造额外身份。
    cluster_by_observation: dict[int, int] = {}
    for anchor in anchors:
        cluster_by_observation[id(anchor.observation)] = cluster_by_anchor[anchor.index]

    candidates: list[CandidateDraft] = []
    used_track_indices: set[int] = set()
    for cluster_index, anchor_indices in enumerate(anchor_clusters):
        resolved = _resolved(anchor_indices, anchors)
        candidate = CandidateDraft(
            id=new_id("CHAR_CANDIDATE"),
            identity_status="RESOLVED" if resolved else "UNRESOLVED",
        )

        contributing_tracks = sorted({anchors[index].track_index for index in anchor_indices})
        for track_index in contributing_tracks:
            track = ordered[track_index]
            track_cluster_ids = {
                cluster_by_observation[id(observation)]
                for observation in track.observations
                if id(observation) in cluster_by_observation
            }
            if track_cluster_ids == {cluster_index}:
                v5._append_track(candidate, track)
                used_track_indices.add(track_index)
                continue

            # 一个 Track 若真的混入多个 Face identity，不再整条塞进任何角色；只保留属于本 identity 的 Face observations。
            selected = [
                observation
                for observation in track.observations
                if cluster_by_observation.get(id(observation)) == cluster_index
            ]
            if selected:
                v5._append_track(candidate, _build_track(track, selected))
                used_track_indices.add(track_index)

        candidate.identity_status = "RESOLVED" if resolved else "UNRESOLVED"
        candidate.scores = [score for score, left, right in edges if left in anchor_indices and right in anchor_indices]
        candidate.v6_metadata = {  # type: ignore[attr-defined]
            "resolver": "face-first-global-identity-v7",
            "identity_source": "face-cluster-only",
            "face_anchor_count": len(anchor_indices),
            "face_shot_count": len({anchors[index].shot_id for index in anchor_indices}),
            "final_character_count_source": "stable-face-identities",
            "partial_can_create_identity": False,
        }
        candidates.append(candidate)

    # 没有 Face identity 的 Track 只允许非常保守地挂回已有 identity；否则留 UNRESOLVED。
    unresolved_tracks: list[TrackDraft] = []
    for track_index, track in enumerate(ordered):
        if track_index in used_track_indices:
            continue
        scored: list[tuple[float, int]] = []
        for candidate_index, candidate in enumerate(candidates):
            score = _body_attach_score(track, candidate)
            if score is not None:
                scored.append((score, candidate_index))
        scored.sort(reverse=True)
        if scored and (len(scored) == 1 or scored[0][0] - scored[1][0] >= BODY_ATTACH_MARGIN):
            v5._append_track(candidates[scored[0][1]], track, scored[0][0])
            # Body attach 绝不能改变原本的 identity publish status。
            original = _resolved(anchor_clusters[scored[0][1]], anchors)
            candidates[scored[0][1]].identity_status = "RESOLVED" if original else "UNRESOLVED"
        else:
            unresolved_tracks.append(track)

    for track in unresolved_tracks:
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
        v5._append_track(candidate, track)
        candidate.identity_status = "UNRESOLVED"
        candidate.v6_metadata = {  # type: ignore[attr-defined]
            "resolver": "face-first-global-identity-v7",
            "identity_source": "body-or-partial-evidence-only",
            "final_character_eligible": False,
        }
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            0 if item.identity_status == "RESOLVED" else 1,
            min((track.episode_order for track in item.tracks), default=999999),
            min((track.shot_ordinal for track in item.tracks), default=999999),
        )
    )
    return candidates
