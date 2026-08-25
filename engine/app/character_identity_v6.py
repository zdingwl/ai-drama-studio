"""Character V6 Global Identity Resolver。

职责：
- 等整集/整项目所有 Person Track 完成以后，再统一解决“到底有几个人”；
- 不再按视频顺序遇到一个不匹配 Track 就立即创建 Final Character；
- Face 是跨 Shot 身份主证据，CLEAN Body ReID / Shot 连续性只做支持；
- 同 Shot 同时存在是永久 cannot-link；明显 Face 冲突禁止任何传递合并；
- 先构建全局 Track Identity Graph，再生成 RESOLVED / UNRESOLVED Candidate；
- UNRESOLVED Candidate 只保留 Evidence，不允许自动物化成 Final Character。

当前 Face provider：YuNet + SFace（接口与 Global Resolver 解耦）。
后续替换为有明确授权的 ArcFace 权重时，本模块不需要改业务结构。
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from engine.app import character_visual_v5 as v5

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft

# SFace cosine 官方常见同人阈值在 0.36 左右。V6 不再用单一高阈值；
# 强 Face 可独立连边，中等 Face 必须由 CLEAN ReID / 时间连续支持。
FACE_STRONG_EDGE = 0.48
FACE_SUPPORTED_EDGE = 0.35
FACE_CLUSTER_HARD_CONFLICT = 0.20
REID_SUPPORT_EDGE = 0.80
REID_STRONG_EDGE = 0.89
BODY_ATTACH_REID = 0.91
BODY_ATTACH_MAX_SHOT_GAP = 1
FACE_ANCHOR_MIN_SCORE = 0.70
SINGLE_TRACK_RESOLVE_FACE_SAMPLES = 3
SINGLE_TRACK_RESOLVE_FACE_SCORE = 0.86


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
    values = [
        item.face_embedding
        for item in track.observations
        if item.face_embedding is not None
        and float(getattr(item, "face_score", item.detection_score)) >= FACE_ANCHOR_MIN_SCORE
    ]
    if not values and track.face_embedding is not None:
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
    return float(median(values)) if values else None


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
            left_index, right_index,
            min(0.99, face * 0.88 + max(0.0, reid or 0.0) * 0.12),
            face, reid, "strong-face",
        )

    if face is not None and face >= FACE_SUPPORTED_EDGE and reid is not None and reid >= REID_SUPPORT_EDGE:
        temporal = 0.03 if gap is not None and gap <= 2 else 0.0
        return IdentityEdge(
            left_index, right_index,
            min(0.97, face * 0.70 + reid * 0.27 + temporal),
            face, reid, "face+clean-reid",
        )

    # SFace 在极端侧脸/小脸时可能只落在 0.33~0.36；只有相邻镜头且 CLEAN ReID 极强才允许连边。
    if (
        face is not None and face >= 0.32
        and reid is not None and reid >= REID_STRONG_EDGE
        and gap is not None and gap <= 1
    ):
        return IdentityEdge(
            left_index, right_index,
            min(0.94, face * 0.62 + reid * 0.35 + 0.03),
            face, reid, "adjacent-face+strong-reid",
        )
    return None


def _clusters(uf: _UnionFind, size: int) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for index in range(size):
        result.setdefault(uf.find(index), set()).add(index)
    return result


def _cluster_compatible(left: set[int], right: set[int], tracks: list[TrackDraft]) -> bool:
    """阻断图传递错误：任何同框或明确 Face 冲突都禁止两个 cluster 合并。"""

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


def _face_track_count(indices: set[int], tracks: list[TrackDraft]) -> int:
    return sum(1 for index in indices if _face_vectors(tracks[index]))


def _face_sample_count(indices: set[int], tracks: list[TrackDraft]) -> int:
    return sum(len(_face_vectors(tracks[index])) for index in indices)


def _best_face_score(indices: set[int], tracks: list[TrackDraft]) -> float:
    values = [
        float(getattr(item, "face_score", item.detection_score))
        for index in indices
        for item in tracks[index].observations
        if item.face_embedding is not None
    ]
    return max(values) if values else 0.0


def _resolved_cluster(indices: set[int], tracks: list[TrackDraft]) -> bool:
    face_tracks = _face_track_count(indices, tracks)
    if face_tracks <= 0:
        return False
    shot_count = len({tracks[index].shot_id for index in indices})
    if face_tracks >= 2 and shot_count >= 2:
        return True
    # 单镜角色必须有连续多个可靠人脸样本，避免一次误检直接成为 Final Character。
    if (
        len(indices) == 1
        and _face_sample_count(indices, tracks) >= SINGLE_TRACK_RESOLVE_FACE_SAMPLES
        and _best_face_score(indices, tracks) >= SINGLE_TRACK_RESOLVE_FACE_SCORE
    ):
        return True
    return False


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
    for index in sorted(indices, key=lambda value: (
        tracks[value].episode_order,
        tracks[value].shot_ordinal,
        tracks[value].start_us if tracks[value].start_us is not None else -1,
    )):
        v5._append_track(candidate, tracks[index])
    candidate.identity_status = "RESOLVED" if resolved else "UNRESOLVED"
    if edge_scores:
        candidate.scores = list(edge_scores)
    candidate.v6_metadata = {  # type: ignore[attr-defined]
        "resolver": "global-identity-graph",
        "resolved": resolved,
        "face_track_count": _face_track_count(indices, tracks),
        "face_sample_count": _face_sample_count(indices, tracks),
        "shot_count": len({tracks[index].shot_id for index in indices}),
    }
    return candidate


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    """整项目 Track -> Global Identity Graph -> Character Candidates。"""

    ordered = sorted(tracks, key=lambda item: (
        item.episode_order,
        item.shot_ordinal,
        item.start_us if item.start_us is not None else -1,
    ))
    if not ordered:
        return []

    # 只有 Face anchored Track 参与身份 cluster 建图；body-only 不允许自行创造 Character。
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

    all_clusters = _clusters(uf, len(ordered))
    # union-find 还包含所有 body-only singleton；先只取拥有 Face 的 cluster。
    face_clusters: list[set[int]] = []
    body_only_indices: list[int] = []
    for indices in all_clusters.values():
        if any(_face_vectors(ordered[index]) for index in indices):
            face_clusters.append(set(indices))
        else:
            body_only_indices.extend(indices)

    # Body-only 只能挂到已经由 Face 建立的 cluster；相邻 Shot + 极强 CLEAN ReID。
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
        root = uf.find(next(iter(indices)))
        candidates.append(_candidate_from_indices(
            indices,
            ordered,
            resolved=resolved,
            edge_scores=accepted_scores.get(root),
        ))

    # Final ordering：RESOLVED 在前，之后才是 Unresolved Evidence；两者绝不能在 Final Asset 层混为一谈。
    candidates.sort(key=lambda item: (
        0 if item.identity_status == "RESOLVED" else 1,
        min((track.episode_order for track in item.tracks), default=999999),
        min((track.shot_ordinal for track in item.tracks), default=999999),
    ))
    return candidates
