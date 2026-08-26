"""Character V6.3 Global Identity Resolver。

在 V6.2 Global Identity Graph 上修正两个实际回归：
1. “共享同一个 Shot”不等于“不同人”。同一真人会因为遮挡/检测断裂在同 Shot 产生多条 Track。
2. 同时出现也不能机械 cannot-link：如果两条 Track 在同一时间、同一位置高度重合，且 Face/ReID 强一致，
   它们更可能是同一人的重复检测，应允许去重。

最终原则：cannot-link 使用时间 + 空间 + Face 冲突；partial/body-only 仍不能创建新身份。
"""
from __future__ import annotations

from statistics import median
from typing import Any

from engine.app import character_identity_v6 as base
from engine.app import character_visual_v5 as v5

TrackDraft = base.TrackDraft
CandidateDraft = base.CandidateDraft
IdentityEdge = base.IdentityEdge

DUPLICATE_FACE_STRONG = 0.62
DUPLICATE_FACE_VERY_STRONG = 0.72
DUPLICATE_REID_SUPPORT = 0.80
DUPLICATE_BBOX_IOU = 0.55
DUPLICATE_TIME_TOLERANCE_US = 125_000

# Body/partial 挂回已有身份也使用多证据，而不是单个 max ReID 决策。
BODY_ATTACH_MULTI_REID = 0.90
BODY_ATTACH_SINGLE_REID = 0.96


def _near_time_bbox_iou(left: TrackDraft, right: TrackDraft) -> float:
    if left.shot_id != right.shot_id:
        return 0.0
    best = 0.0
    for a in left.observations:
        for b in right.observations:
            if abs(int(a.source_time_us) - int(b.source_time_us)) > DUPLICATE_TIME_TOLERANCE_US:
                continue
            best = max(best, v5.bbox_iou(a.bbox, b.bbox))
    return best


def _simultaneous_duplicate(
    left: TrackDraft,
    right: TrackDraft,
    *,
    face: float | None = None,
    reid: float | None = None,
) -> bool:
    """同时出现的两条 Track 是否其实是同一人的重复检测。"""

    if not base._simultaneous(left, right):
        return False
    face_score = base._face_similarity(left, right) if face is None else face
    reid_score = base._reid_similarity(left, right) if reid is None else reid
    if face_score is None or face_score < DUPLICATE_FACE_STRONG:
        return False
    if _near_time_bbox_iou(left, right) < DUPLICATE_BBOX_IOU:
        return False
    return bool(
        face_score >= DUPLICATE_FACE_VERY_STRONG
        or (reid_score is not None and reid_score >= DUPLICATE_REID_SUPPORT)
    )


def _identity_edge(
    left_index: int,
    right_index: int,
    left: TrackDraft,
    right: TrackDraft,
) -> IdentityEdge | None:
    face = base._face_similarity(left, right)
    reid = base._reid_similarity(left, right)
    gap = base._shot_gap(left, right)
    both_have_face = bool(base._face_vectors(left)) and bool(base._face_vectors(right))

    if base._simultaneous(left, right):
        if _simultaneous_duplicate(left, right, face=face, reid=reid):
            score = min(0.995, max(0.0, face or 0.0) * 0.84 + max(0.0, reid or 0.0) * 0.16)
            return IdentityEdge(left_index, right_index, score, face, reid, "same-shot-duplicate")
        return None

    if both_have_face and face is not None and face < base.FACE_CLUSTER_HARD_CONFLICT:
        return None

    if face is not None and face >= base.FACE_STRONG_EDGE:
        return IdentityEdge(
            left_index,
            right_index,
            min(0.99, face * 0.88 + max(0.0, reid or 0.0) * 0.12),
            face,
            reid,
            "strong-face",
        )

    if face is not None and face >= base.FACE_SUPPORTED_EDGE and reid is not None and reid >= base.REID_SUPPORT_EDGE:
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
        and reid >= base.REID_STRONG_EDGE
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


def _cluster_compatible(left: set[int], right: set[int], tracks: list[TrackDraft]) -> bool:
    """真正的 cannot-link：时空上确实是两个人，或存在明确 Face hard conflict。"""

    for left_index in left:
        for right_index in right:
            a, b = tracks[left_index], tracks[right_index]
            left_faces, right_faces = base._face_vectors(a), base._face_vectors(b)
            face = base._symmetric_similarity(left_faces, right_faces) if left_faces and right_faces else None
            reid = base._reid_similarity(a, b)

            if base._simultaneous(a, b) and not _simultaneous_duplicate(a, b, face=face, reid=reid):
                return False
            if face is not None and face < base.FACE_CLUSTER_HARD_CONFLICT:
                return False
    return True


def _fragment_merge_score(
    left: set[int],
    right: set[int],
    tracks: list[TrackDraft],
) -> float | None:
    """同人碎片二次合并。

    注意：不再因为共享 Shot 就拒绝。共享 Shot 由 _cluster_compatible 的真实时空关系判断。
    """

    if not _cluster_compatible(left, right, tracks):
        return None

    left_faces = base._cluster_face_vectors(left, tracks)
    right_faces = base._cluster_face_vectors(right, tracks)
    if not left_faces or not right_faces:
        return None

    face_centroid = v5.cosine(v5.mean_vector(left_faces), v5.mean_vector(right_faces))
    left_reids = base._cluster_reid_vectors(left, tracks)
    right_reids = base._cluster_reid_vectors(right, tracks)
    reid_centroid = (
        v5.cosine(v5.mean_vector(left_reids), v5.mean_vector(right_reids))
        if left_reids and right_reids
        else None
    )

    qualifies = bool(
        face_centroid is not None
        and (
            face_centroid >= base.FRAGMENT_FACE_STRONG
            or (
                face_centroid >= base.FRAGMENT_FACE_SUPPORTED
                and reid_centroid is not None
                and reid_centroid >= base.FRAGMENT_REID_SUPPORT
            )
        )
    )
    if not qualifies:
        return None
    return max(0.0, float(face_centroid or 0.0)) * 0.78 + max(0.0, float(reid_centroid or 0.0)) * 0.22


def _merge_resolved_fragments(
    uf: Any,
    tracks: list[TrackDraft],
    accepted_scores: dict[int, list[float]],
) -> None:
    while True:
        current = base._clusters(uf, len(tracks))
        face_clusters = [
            set(indices)
            for indices in current.values()
            if any(base._face_vectors(tracks[index]) for index in indices)
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
        accepted_scores[new_root] = (
            accepted_scores.pop(left_root, [])
            + accepted_scores.pop(right_root, [])
            + [score]
        )


def _body_attach_score(body_track: TrackDraft, cluster: set[int], tracks: list[TrackDraft]) -> float | None:
    """Body/partial 必须得到多条 identity evidence 支持，避免一个偶然高 ReID 把 Shot 挂错人。"""

    if any(base._simultaneous(body_track, tracks[index]) for index in cluster):
        return None

    gaps = [
        base._shot_gap(body_track, tracks[index])
        for index in cluster
        if base._shot_gap(body_track, tracks[index]) is not None
    ]
    gap = min(gaps) if gaps else None
    if gap is None or gap > base.BODY_ATTACH_MAX_SHOT_GAP:
        return None

    scores = [base._reid_similarity(body_track, tracks[index]) for index in cluster]
    clean = sorted((float(score) for score in scores if score is not None), reverse=True)
    if not clean:
        return None
    if len(clean) >= 2:
        top = clean[: min(3, len(clean))]
        support = float(median(top))
        return support if min(top[:2]) >= BODY_ATTACH_MULTI_REID and support >= base.BODY_ATTACH_REID else None
    return clean[0] if clean[0] >= BODY_ATTACH_SINGLE_REID else None


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

    face_indices = [index for index, track in enumerate(ordered) if base._face_vectors(track)]
    uf = base._UnionFind(len(ordered))
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
        current = base._clusters(uf, len(ordered))
        left_cluster = current.get(left_root, {edge.left})
        right_cluster = current.get(right_root, {edge.right})
        if not _cluster_compatible(left_cluster, right_cluster, ordered):
            continue
        new_root = uf.union(left_root, right_root)
        accepted_scores[new_root] = (
            accepted_scores.pop(left_root, [])
            + accepted_scores.pop(right_root, [])
            + [edge.score]
        )

    _merge_resolved_fragments(uf, ordered, accepted_scores)

    all_clusters = base._clusters(uf, len(ordered))
    face_clusters: list[set[int]] = []
    body_only_indices: list[int] = []
    for indices in all_clusters.values():
        if any(base._face_vectors(ordered[index]) for index in indices):
            face_clusters.append(set(indices))
        else:
            body_only_indices.extend(indices)

    for body_index in body_only_indices:
        body_track = ordered[body_index]
        best_cluster: set[int] | None = None
        best_score = -1.0
        for cluster in face_clusters:
            score = _body_attach_score(body_track, cluster, ordered)
            if score is not None and score > best_score:
                best_cluster = cluster
                best_score = score
        if best_cluster is not None:
            best_cluster.add(body_index)
        else:
            face_clusters.append({body_index})

    candidates: list[CandidateDraft] = []
    for indices in face_clusters:
        resolved = base._resolved_cluster(indices, ordered)
        roots = {uf.find(index) for index in indices}
        scores: list[float] = []
        for root in roots:
            scores.extend(accepted_scores.get(root, []))
        candidate = base._candidate_from_indices(
            indices,
            ordered,
            resolved=resolved,
            edge_scores=scores or None,
        )
        metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
        metadata.update({
            "resolver": "global-identity-graph-v6.3-spatiotemporal",
            "spatiotemporal_cannot_link": True,
            "safe_face_ownership": True,
        })
        candidate.v6_metadata = metadata  # type: ignore[attr-defined]
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            0 if item.identity_status == "RESOLVED" else 1,
            min((track.episode_order for track in item.tracks), default=999999),
            min((track.shot_ordinal for track in item.tracks), default=999999),
        )
    )
    return candidates
