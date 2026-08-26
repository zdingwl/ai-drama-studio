"""Character V6.2 Global Identity Resolver。

职责：
- 等整集/整项目所有 Person Track 完成以后，再统一解决“到底有几个人”；
- Face 是跨 Shot 身份主证据，CLEAN Body ReID / Shot 连续性只做支持；
- partial-person 只能补“有人”和挂回已有身份，不能作为新身份 Face anchor；
- 同 Shot 同时存在是永久 cannot-link；明显 Face 冲突禁止任何传递合并；
- 初始 Global Identity Graph 后再做一次保守的 Face fragment consolidation，解决同一演员被拆成多个 RESOLVED；
- UNRESOLVED Candidate 只保留 Evidence，不允许自动物化成 Final Character。
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from engine.app import character_visual_v5 as v5

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft

FACE_STRONG_EDGE = 0.48
FACE_SUPPORTED_EDGE = 0.35
FACE_CLUSTER_HARD_CONFLICT = 0.20
REID_SUPPORT_EDGE = 0.80
REID_STRONG_EDGE = 0.89
BODY_ATTACH_REID = 0.91
BODY_ATTACH_MAX_SHOT_GAP = 1
FACE_ANCHOR_MIN_SCORE = 0.70

# V6.2 二次去碎片：只针对已经各自形成 Face cluster 的候选。
# 不直接降低首轮阈值；只有 cluster centroid Face + CLEAN ReID 同时支持，或 centroid Face 很强时才合并。
FRAGMENT_FACE_STRONG = 0.52
FRAGMENT_FACE_SUPPORTED = 0.40
FRAGMENT_REID_SUPPORT = 0.64


@dataclass(frozen=True)
class IdentityEdge:
    left: int
    right: int
    score: float
    face_score: float | None
    reid_score: float | None
    reason: str


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
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return left_root
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1
        return left_root


def _observation_is_partial(observation: Any) -> bool:
    return "partial" in str(getattr(observation, "detection_source", "") or "").lower()


def _interval(track: TrackDraft) -> tuple[int | None, int | None]:
    if not track.observations:
        return None, None
    return (
        min(item.source_time_us for item in track.observations),
        max(item.source_time_us for item in track.observations),
    )


def _simultaneous(left: TrackDraft, right: TrackDraft) -> bool:
    if left.shot_id != right.shot_id:
        return False
    left_start, left_end = _interval(left)
    right_start, right_end = _interval(right)
    if left_start is None or right_start is None:
        return True
    return max(left_start, right_start) <= min(left_end or left_start, right_end or right_start)


def _face_vectors(track: TrackDraft) -> list[Any]:
    """只返回可创建身份的 Face anchors；partial Face 不能成为新 Character 的根。"""

    values = [
        item.face_embedding
        for item in track.observations
        if item.face_embedding is not None
        and not _observation_is_partial(item)
        and float(getattr(item, "face_score", item.detection_score)) >= FACE_ANCHOR_MIN_SCORE
    ]
    # 只给没有 Observation 明细的历史/测试 Track 使用聚合 fallback；
    # 有 Observation 但全部来自 partial 时，绝不能通过 track.face_embedding 绕回 Face anchor。
    if not values and not track.observations and track.face_embedding is not None:
        values.append(track.face_embedding)
    return values


def _clean_reid_vectors(track: TrackDraft) -> list[Any]:
    values = [
        rep.observation.reid_embedding
        for rep in track.representatives
        if rep.clean and rep.observation.reid_embedding is not None
    ]
    if not values and not track.representatives and track.reid_embedding is not None:
        values.append(track.reid_embedding)
    return values


def _directed_best_median(left: list[Any], right: list[Any]) -> float | None:
    if not left or not right:
        return None
    values: list[float] = []
    for vector in left:
        similarities = [v5.cosine(vector, other) for other in right]
        clean = [float(item) for item in similarities if item is not None]
        if clean:
            values.append(max(clean))
    if not values:
        return None
    return float(median(values))


def _symmetric_similarity(left: list[Any], right: list[Any]) -> float | None:
    lr = _directed_best_median(left, right)
    rl = _directed_best_median(right, left)
    values = [item for item in (lr, rl) if item is not None]
    return sum(values) / len(values) if values else None


def _face_similarity(left: TrackDraft, right: TrackDraft) -> float | None:
    return _symmetric_similarity(_face_vectors(left), _face_vectors(right))


def _reid_similarity(left: TrackDraft, right: TrackDraft) -> float | None:
    return _symmetric_similarity(_clean_reid_vectors(left), _clean_reid_vectors(right))


def _shot_gap(left: TrackDraft, right: TrackDraft) -> int | None:
    if left.episode_id != right.episode_id:
        return None
    return abs(int(left.shot_ordinal) - int(right.shot_ordinal))


def _identity_edge(left_index: int, right_index: int, left: TrackDraft, right: TrackDraft) -> IdentityEdge | None:
    if _simultaneous(left, right):
        return None

    face = _face_similarity(left, right)
    reid = _reid_similarity(left, right)
    gap = _shot_gap(left, right)
    both_have_face = bool(_face_vectors(left)) and bool(_face_vectors(right))

    if both_have_face and face is not None and face < FACE_CLUSTER_HARD_CONFLICT:
        return None

    if face is not None and face >= FACE_STRONG_EDGE:
        return IdentityEdge(
            left_index,
            right_index,
            min(0.99, face * 0.88 + max(0.0, reid or 0.0) * 0.12),
            face,
            reid,
            "strong-face",
        )

    if face is not None and face >= FACE_SUPPORTED_EDGE and reid is not None and reid >= REID_SUPPORT_EDGE:
        temporal = 0.03 if gap is not None and gap <= 2 else 0.0
        return IdentityEdge(
            left_index,
            right_index,
            min(0.97, face * 0.70 + reid * 0.27 + temporal),
            face,
            reid,
            "face+clean-reid",
        )

    if (
        face is not None
        and face >= 0.32
        and reid is not None
        and reid >= REID_STRONG_EDGE
        and gap is not None
        and gap <= 1
    ):
        return IdentityEdge(
            left_index,
            right_index,
            min(0.94, face * 0.62 + reid * 0.35 + 0.03),
            face,
            reid,
            "adjacent-face+strong-reid",
        )
    return None


def _clusters(uf: _UnionFind, size: int) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for index in range(size):
        result.setdefault(uf.find(index), set()).add(index)
    return result


def _cluster_compatible(left: set[int], right: set[int], tracks: list[TrackDraft]) -> bool:
    for left_index in left:
        for right_index in right:
            a, b = tracks[left_index], tracks[right_index]
            if _simultaneous(a, b):
                return False
            left_faces, right_faces = _face_vectors(a), _face_vectors(b)
            if not left_faces or not right_faces:
                continue
            face = _symmetric_similarity(left_faces, right_faces)
            if face is not None and face < FACE_CLUSTER_HARD_CONFLICT:
                return False
    return True


def _cluster_face_vectors(indices: set[int], tracks: list[TrackDraft]) -> list[Any]:
    values: list[Any] = []
    for index in indices:
        values.extend(_face_vectors(tracks[index]))
    return values


def _cluster_reid_vectors(indices: set[int], tracks: list[TrackDraft]) -> list[Any]:
    values: list[Any] = []
    for index in indices:
        values.extend(_clean_reid_vectors(tracks[index]))
    return values


def _fragment_merge_score(
    left: set[int],
    right: set[int],
    tracks: list[TrackDraft],
) -> float | None:
    """V6.2 保守二次去碎片。

    约束：
    - 两个 cluster 不能共享 Shot；共享 Shot 默认视为不同人，避免多人场景误合并；
    - 继续尊重 simultaneous / hard Face conflict；
    - 使用 cluster centroid，只有强 Face，或 Face + CLEAN ReID 同时支持才允许合并。
    """

    left_shots = {tracks[index].shot_id for index in left}
    right_shots = {tracks[index].shot_id for index in right}
    if left_shots & right_shots:
        return None
    if not _cluster_compatible(left, right, tracks):
        return None

    left_faces = _cluster_face_vectors(left, tracks)
    right_faces = _cluster_face_vectors(right, tracks)
    if not left_faces or not right_faces:
        return None

    face_centroid = v5.cosine(v5.mean_vector(left_faces), v5.mean_vector(right_faces))
    left_reids = _cluster_reid_vectors(left, tracks)
    right_reids = _cluster_reid_vectors(right, tracks)
    reid_centroid = (
        v5.cosine(v5.mean_vector(left_reids), v5.mean_vector(right_reids))
        if left_reids and right_reids
        else None
    )

    qualifies = bool(
        face_centroid is not None
        and (
            face_centroid >= FRAGMENT_FACE_STRONG
            or (
                face_centroid >= FRAGMENT_FACE_SUPPORTED
                and reid_centroid is not None
                and reid_centroid >= FRAGMENT_REID_SUPPORT
            )
        )
    )
    if not qualifies:
        return None
    return max(0.0, float(face_centroid or 0.0)) * 0.78 + max(0.0, float(reid_centroid or 0.0)) * 0.22


def _merge_resolved_fragments(
    uf: _UnionFind,
    tracks: list[TrackDraft],
    accepted_scores: dict[int, list[float]],
) -> None:
    """反复选择最可信的 cluster pair 合并，直到没有满足严格条件的同人碎片。"""

    while True:
        current = _clusters(uf, len(tracks))
        face_clusters = [
            set(indices)
            for indices in current.values()
            if any(_face_vectors(tracks[index]) for index in indices)
        ]
        best: tuple[float, set[int], set[int]] | None = None
        for left_pos, left in enumerate(face_clusters):
            for right in face_clusters[left_pos + 1:]:
                score = _fragment_merge_score(left, right, tracks)
                if score is None:
                    continue
                if best is None or score > best[0]:
                    best = (score, left, right)
        if best is None:
            return

        score, left, right = best
        left_root = uf.find(next(iter(left)))
        right_root = uf.find(next(iter(right)))
        if left_root == right_root:
            continue
        new_root = uf.union(left_root, right_root)
        merged_scores = (
            accepted_scores.pop(left_root, [])
            + accepted_scores.pop(right_root, [])
            + [score]
        )
        accepted_scores[new_root] = merged_scores


def _face_track_count(indices: set[int], tracks: list[TrackDraft]) -> int:
    return sum(1 for index in indices if _face_vectors(tracks[index]))


def _face_sample_count(indices: set[int], tracks: list[TrackDraft]) -> int:
    return sum(len(_face_vectors(tracks[index])) for index in indices)


def _resolved_cluster(indices: set[int], tracks: list[TrackDraft]) -> bool:
    face_tracks = _face_track_count(indices, tracks)
    if face_tracks < 2:
        return False
    face_shots = {
        tracks[index].shot_id
        for index in indices
        if _face_vectors(tracks[index])
    }
    return len(face_shots) >= 2


def _candidate_from_indices(
    indices: set[int],
    tracks: list[TrackDraft],
    *,
    resolved: bool,
    edge_scores: list[float] | None = None,
) -> CandidateDraft:
    candidate = CandidateDraft(
        id=v5.new_id("CHAR_CANDIDATE"),
        identity_status="RESOLVED" if resolved else "UNRESOLVED",
    )
    for index in sorted(
        indices,
        key=lambda value: (
            tracks[value].episode_order,
            tracks[value].shot_ordinal,
            tracks[value].start_us if tracks[value].start_us is not None else -1,
        ),
    ):
        v5._append_track(candidate, tracks[index])
    candidate.identity_status = "RESOLVED" if resolved else "UNRESOLVED"
    if edge_scores:
        candidate.scores = list(edge_scores)
    candidate.v6_metadata = {  # type: ignore[attr-defined]
        "resolver": "global-identity-graph-v6.2",
        "resolved": resolved,
        "face_track_count": _face_track_count(indices, tracks),
        "face_sample_count": _face_sample_count(indices, tracks),
        "face_shot_count": len({
            tracks[index].shot_id
            for index in indices
            if _face_vectors(tracks[index])
        }),
        "shot_count": len({tracks[index].shot_id for index in indices}),
    }
    return candidate


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    ordered = sorted(
        tracks,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
    if not ordered:
        return []

    # 只有非 partial Face anchored Track 参与身份建图。
    face_indices = [index for index, track in enumerate(ordered) if _face_vectors(track)]
    uf = _UnionFind(len(ordered))
    edges: list[IdentityEdge] = []
    for position, left_index in enumerate(face_indices):
        for right_index in face_indices[position + 1:]:
            edge = _identity_edge(left_index, right_index, ordered[left_index], ordered[right_index])
            if edge is not None:
                edges.append(edge)

    accepted_scores: dict[int, list[float]] = {}
    for edge in sorted(edges, key=lambda item: item.score, reverse=True):
        left_root, right_root = uf.find(edge.left), uf.find(edge.right)
        if left_root == right_root:
            accepted_scores.setdefault(left_root, []).append(edge.score)
            continue
        current = _clusters(uf, len(ordered))
        left_cluster = current.get(left_root, {edge.left})
        right_cluster = current.get(right_root, {edge.right})
        if not _cluster_compatible(left_cluster, right_cluster, ordered):
            continue
        new_root = uf.union(left_root, right_root)
        merged_scores = accepted_scores.pop(left_root, []) + accepted_scores.pop(right_root, []) + [edge.score]
        accepted_scores[new_root] = merged_scores

    # 首轮图聚类后做一次保守的二次去碎片，目标是减少“同一演员被拆成两个人物”。
    _merge_resolved_fragments(uf, ordered, accepted_scores)

    all_clusters = _clusters(uf, len(ordered))
    face_clusters: list[set[int]] = []
    body_only_indices: list[int] = []
    for indices in all_clusters.values():
        if any(_face_vectors(ordered[index]) for index in indices):
            face_clusters.append(set(indices))
        else:
            body_only_indices.extend(indices)

    # Body/partial-only 只能挂到已经由正常 Face 建立的 cluster；不能自行创造 Final Character。
    for body_index in body_only_indices:
        body_track = ordered[body_index]
        best_cluster: set[int] | None = None
        best_score = -1.0
        for cluster in face_clusters:
            if any(_simultaneous(body_track, ordered[index]) for index in cluster):
                continue
            gaps = [
                _shot_gap(body_track, ordered[index])
                for index in cluster
                if _shot_gap(body_track, ordered[index]) is not None
            ]
            gap = min(gaps) if gaps else None
            if gap is None or gap > BODY_ATTACH_MAX_SHOT_GAP:
                continue
            scores = [_reid_similarity(body_track, ordered[index]) for index in cluster]
            clean_scores = [score for score in scores if score is not None]
            score = max(clean_scores) if clean_scores else None
            if score is not None and score >= BODY_ATTACH_REID and score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is not None:
            best_cluster.add(body_index)
        else:
            face_clusters.append({body_index})

    candidates: list[CandidateDraft] = []
    for indices in face_clusters:
        resolved = _resolved_cluster(indices, ordered)
        roots = {uf.find(index) for index in indices}
        scores: list[float] = []
        for root in roots:
            scores.extend(accepted_scores.get(root, []))
        candidates.append(
            _candidate_from_indices(
                indices,
                ordered,
                resolved=resolved,
                edge_scores=scores or None,
            )
        )

    candidates.sort(
        key=lambda item: (
            0 if item.identity_status == "RESOLVED" else 1,
            min((track.episode_order for track in item.tracks), default=999999),
            min((track.shot_ordinal for track in item.tracks), default=999999),
        )
    )
    return candidates
