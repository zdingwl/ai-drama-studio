"""Character V8 Anchor-first / Confirm-then-Absorb identity resolver.

核心原则：
1. Person Track 永远只是 Evidence，不决定人物数量；
2. 先从剩余 Face Evidence 中选择质量最高的 seed；
3. seed 必须得到跨 Shot Face 支持，才允许确认一个 Character Identity；
4. Identity 一旦确认，后续所有 Face 都必须先和全部已确认 Identity Gallery 比较；
5. 能匹配就吸收，有相似但不够确定就留 UNRESOLVED；只有明确与全部已知 Identity 不同，才允许创建下一个人物；
6. Body / Partial Track 只能挂到已确认人物，永远不能创建新人物。

这与传统“先把所有 Track 聚类、再合并碎片”不同。V8 是顺序式身份建立：
确认 A -> 用 A 扫剩余 Evidence -> 确认 B -> 用 A+B 扫剩余 Evidence -> ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

from engine.app import character_visual_v5 as v5
from engine.app.studio_v2 import new_id

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft
Observation = v5.Observation

# Face Evidence 基础门槛。
FACE_ANCHOR_MIN_SCORE = 0.70
SEED_MIN_FACE_SCORE = 0.80
SEED_MIN_QUALITY = 0.68
GALLERY_LIMIT = 16

# 已确认人物吸收新 Face Evidence。
ABSORB_FACE_STRONG = 0.50
ABSORB_FACE_BEST = 0.57
ABSORB_FACE_SUPPORTED = 0.36
ABSORB_REID_SUPPORTED = 0.82
ABSORB_AMBIGUITY_MARGIN = 0.055

# 新人物确认：两 Shot 只有非常强的 Face 才能确认；正常情况要求至少 3 个独立 Shot。
CONFIRM_MIN_SHOTS = 3
CONFIRM_FACE_SUPPORTED = 0.42
CONFIRM_FACE_STRONG = 0.58
CONFIRM_TWO_SHOT_FACE = 0.70

# “新人物”在创建前必须先证明不是已有 Identity 的困难视角。
# 若与已有身份仍有中等 Face 相似，则宁可 UNRESOLVED，也不创建重复人物。
NOVELTY_BLOCK_FACE = 0.34

# 同一采样时刻两个空间不同的脸是永久 cannot-link；重复检测同一脸允许归一。
SAME_SAMPLE_TOLERANCE_US = 45_000
SAME_FACE_IOU = 0.34

# Body / Partial 只在身份已经存在以后回挂。
BODY_ATTACH_MIN = 0.92
BODY_ATTACH_SINGLE = 0.97
BODY_ATTACH_MARGIN = 0.05
BODY_ATTACH_MAX_SHOT_GAP = 2


@dataclass(frozen=True)
class FaceEvidence:
    index: int
    track_index: int
    observation_index: int
    observation: Observation
    quality: float

    @property
    def shot_id(self) -> str:
        return self.observation.shot_id

    @property
    def source_time_us(self) -> int:
        return int(self.observation.source_time_us)


@dataclass
class ConfirmedIdentity:
    ordinal: int
    evidence_indices: set[int] = field(default_factory=set)
    scores: list[float] = field(default_factory=list)
    seed_index: int | None = None


def _is_partial(observation: Observation) -> bool:
    return "partial" in str(getattr(observation, "detection_source", "") or "").lower()


def _valid_face(observation: Observation) -> bool:
    return bool(
        observation.face_embedding is not None
        and observation.face_bbox is not None
        and not _is_partial(observation)
        and float(getattr(observation, "face_score", observation.detection_score)) >= FACE_ANCHOR_MIN_SCORE
    )


def _face_quality(observation: Observation) -> float:
    face_score = max(0.0, min(1.0, float(getattr(observation, "face_score", observation.detection_score))))
    clarity = max(0.0, min(1.0, float(getattr(observation, "clarity_score", 0.0))))
    frame_area = max(1, int(getattr(observation, "frame_width", 0)) * int(getattr(observation, "frame_height", 0)))
    face_area = 0
    if observation.face_bbox is not None:
        face_area = max(0, int(observation.face_bbox[2]) * int(observation.face_bbox[3]))
    size_score = min(1.0, (face_area / float(frame_area)) / 0.035) if frame_area and face_area else 0.0
    detection = max(0.0, min(1.0, float(observation.detection_score)))
    return face_score * 0.55 + clarity * 0.22 + size_score * 0.15 + detection * 0.08


def _face_evidence(tracks: list[TrackDraft]) -> list[FaceEvidence]:
    result: list[FaceEvidence] = []
    for track_index, track in enumerate(tracks):
        for observation_index, observation in enumerate(track.observations):
            if not _valid_face(observation):
                continue
            result.append(FaceEvidence(
                index=len(result),
                track_index=track_index,
                observation_index=observation_index,
                observation=observation,
                quality=_face_quality(observation),
            ))
    return result


def _face_similarity(left: FaceEvidence, right: FaceEvidence) -> float | None:
    return v5.cosine(left.observation.face_embedding, right.observation.face_embedding)


def _reid_similarity(left: FaceEvidence, right: FaceEvidence) -> float | None:
    return v5.cosine(left.observation.reid_embedding, right.observation.reid_embedding)


def _same_sample(left: FaceEvidence, right: FaceEvidence) -> bool:
    return bool(
        left.shot_id == right.shot_id
        and abs(left.source_time_us - right.source_time_us) <= SAME_SAMPLE_TOLERANCE_US
    )


def _face_iou(left: FaceEvidence, right: FaceEvidence) -> float:
    if left.observation.face_bbox is None or right.observation.face_bbox is None:
        return 0.0
    return v5.bbox_iou(left.observation.face_bbox, right.observation.face_bbox)


def _same_sample_distinct(left: FaceEvidence, right: FaceEvidence) -> bool:
    return _same_sample(left, right) and _face_iou(left, right) < SAME_FACE_IOU


def _gallery(identity: ConfirmedIdentity, evidence: list[FaceEvidence]) -> list[FaceEvidence]:
    values = [evidence[index] for index in identity.evidence_indices]
    # 同一 Shot 只留质量最高的几张，避免长 Shot 大量近重复样本支配 Gallery。
    best_by_shot: dict[str, list[FaceEvidence]] = {}
    for item in sorted(values, key=lambda value: value.quality, reverse=True):
        bucket = best_by_shot.setdefault(item.shot_id, [])
        if len(bucket) < 2:
            bucket.append(item)
    gallery = [item for bucket in best_by_shot.values() for item in bucket]
    gallery.sort(key=lambda value: value.quality, reverse=True)
    return gallery[:GALLERY_LIMIT]


def _top_average(values: list[float], limit: int = 3) -> float | None:
    if not values:
        return None
    selected = sorted(values, reverse=True)[:limit]
    return sum(selected) / len(selected)


def _identity_similarity(
    item: FaceEvidence,
    identity: ConfirmedIdentity,
    evidence: list[FaceEvidence],
) -> tuple[float | None, float | None, float | None]:
    gallery = _gallery(identity, evidence)
    face_values: list[float] = []
    reid_values: list[float] = []
    for member in gallery:
        if _same_sample_distinct(item, member):
            continue
        face = _face_similarity(item, member)
        if face is not None:
            face_values.append(float(face))
        reid = _reid_similarity(item, member)
        if reid is not None:
            reid_values.append(float(reid))
    if not face_values:
        return None, None, None
    face_best = max(face_values)
    face_support = _top_average(face_values)
    reid_support = _top_average(reid_values)
    return face_best, face_support, reid_support


def _match_score(
    item: FaceEvidence,
    identity: ConfirmedIdentity,
    evidence: list[FaceEvidence],
) -> float | None:
    face_best, face_support, reid_support = _identity_similarity(item, identity, evidence)
    if face_best is None or face_support is None:
        return None
    qualifies = bool(
        face_support >= ABSORB_FACE_STRONG
        or face_best >= ABSORB_FACE_BEST
        or (
            face_support >= ABSORB_FACE_SUPPORTED
            and reid_support is not None
            and reid_support >= ABSORB_REID_SUPPORTED
        )
    )
    if not qualifies:
        return None
    return face_support * 0.76 + max(0.0, reid_support or 0.0) * 0.24


def _best_identity_match(
    item: FaceEvidence,
    identities: list[ConfirmedIdentity],
    evidence: list[FaceEvidence],
) -> tuple[int | None, float | None, bool]:
    matches: list[tuple[float, int]] = []
    for identity_index, identity in enumerate(identities):
        score = _match_score(item, identity, evidence)
        if score is not None:
            matches.append((score, identity_index))
    if not matches:
        return None, None, False
    matches.sort(reverse=True)
    best_score, best_index = matches[0]
    if len(matches) >= 2 and best_score - matches[1][0] < ABSORB_AMBIGUITY_MARGIN:
        return None, best_score, True
    return best_index, best_score, False


def _seed_pair_support(seed: FaceEvidence, other: FaceEvidence) -> float | None:
    if seed.shot_id == other.shot_id:
        return None
    face = _face_similarity(seed, other)
    reid = _reid_similarity(seed, other)
    if face is None:
        return None
    if face >= CONFIRM_FACE_STRONG:
        return face * 0.88 + max(0.0, reid or 0.0) * 0.12
    if face >= CONFIRM_FACE_SUPPORTED and reid is not None and reid >= ABSORB_REID_SUPPORTED:
        return face * 0.72 + reid * 0.28
    return None


def _seed_group(seed_index: int, remaining: set[int], evidence: list[FaceEvidence]) -> tuple[set[int], list[float]]:
    seed = evidence[seed_index]
    by_shot: dict[str, tuple[float, int]] = {}
    for index in remaining:
        if index == seed_index:
            continue
        other = evidence[index]
        score = _seed_pair_support(seed, other)
        if score is None:
            continue
        current = by_shot.get(other.shot_id)
        if current is None or score > current[0]:
            by_shot[other.shot_id] = (score, index)
    group = {seed_index, *(index for _score, index in by_shot.values())}
    scores = [score for score, _index in by_shot.values()]
    return group, scores


def _group_confirmed(indices: set[int], scores: list[float], evidence: list[FaceEvidence]) -> bool:
    shots = {evidence[index].shot_id for index in indices}
    if len(shots) >= CONFIRM_MIN_SHOTS:
        return len(scores) >= 2 and median(scores[: min(4, len(scores))]) >= CONFIRM_FACE_SUPPORTED
    if len(shots) == 2 and scores:
        # 两 Shot 角色只在 seed/support Face 极强时自动确认。
        seed = evidence[min(indices, key=lambda index: -evidence[index].quality)]
        best_other = max((evidence[index] for index in indices if index != seed.index), key=lambda item: item.quality)
        face = _face_similarity(seed, best_other)
        return bool(face is not None and face >= CONFIRM_TWO_SHOT_FACE)
    return False


def _group_is_novel(
    indices: set[int],
    identities: list[ConfirmedIdentity],
    evidence: list[FaceEvidence],
) -> bool:
    if not identities:
        return True
    for identity in identities:
        gallery = _gallery(identity, evidence)
        # 若新 seed 与已知人物在同一时刻空间明确不同，这是“不同人”的正证据。
        cooccurs_distinct = any(
            _same_sample_distinct(evidence[index], member)
            for index in indices
            for member in gallery
        )
        if cooccurs_distinct:
            continue

        similarities = [
            float(score)
            for index in indices
            for member in gallery
            if (score := _face_similarity(evidence[index], member)) is not None
        ]
        if similarities and max(similarities) >= NOVELTY_BLOCK_FACE:
            # 仍然有中等相似度：更可能是已知人物的困难角度。宁可 unresolved，不创建重复人物。
            return False
    return True


def _absorb_until_stable(
    identities: list[ConfirmedIdentity],
    remaining: set[int],
    evidence: list[FaceEvidence],
) -> None:
    changed = True
    while changed and identities:
        changed = False
        for index in sorted(remaining, key=lambda value: evidence[value].quality, reverse=True):
            identity_index, score, ambiguous = _best_identity_match(evidence[index], identities, evidence)
            if ambiguous or identity_index is None or score is None:
                continue
            identities[identity_index].evidence_indices.add(index)
            identities[identity_index].scores.append(score)
            remaining.remove(index)
            changed = True


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


def _candidate_from_identity(
    identity: ConfirmedIdentity,
    ordered_tracks: list[TrackDraft],
    evidence: list[FaceEvidence],
    assignment: dict[int, int],
) -> CandidateDraft:
    candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="RESOLVED")

    evidence_by_track: dict[int, list[FaceEvidence]] = {}
    for evidence_index in identity.evidence_indices:
        item = evidence[evidence_index]
        evidence_by_track.setdefault(item.track_index, []).append(item)

    for track_index, assigned in sorted(evidence_by_track.items()):
        source = ordered_tracks[track_index]
        valid_in_track = [
            item for item in evidence if item.track_index == track_index
        ]
        assigned_identity_ids = {
            assignment[item.index]
            for item in valid_in_track
            if item.index in assignment
        }
        unresolved_face_exists = any(item.index not in assignment for item in valid_in_track)

        if assigned_identity_ids == {identity.ordinal} and not unresolved_face_exists:
            member = source
        else:
            observations = [item.observation for item in assigned]
            member = _build_track(source, observations)
        v5._append_track(candidate, member)

    candidate.identity_status = "RESOLVED"
    candidate.scores = list(identity.scores)
    seed = evidence[identity.seed_index] if identity.seed_index is not None else None
    candidate.v6_metadata = {  # type: ignore[attr-defined]
        "resolver": "anchor-first-v8-confirm-then-absorb",
        "identity_ordinal": identity.ordinal + 1,
        "seed_face_score": float(getattr(seed.observation, "face_score", 0.0)) if seed else None,
        "seed_quality": round(seed.quality, 6) if seed else None,
        "face_anchor_count": len(identity.evidence_indices),
        "face_shot_count": len({evidence[index].shot_id for index in identity.evidence_indices}),
        "policy": "confirmed identity first; all later evidence must compare against confirmed identities before new identity creation",
    }
    return candidate


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
    gaps = [
        abs(int(track.shot_ordinal) - int(member.shot_ordinal))
        for member in candidate.tracks
        if track.episode_id == member.episode_id
    ]
    if not gaps or min(gaps) > BODY_ATTACH_MAX_SHOT_GAP:
        return None

    body = _clean_reid_vectors(track)
    gallery = [vector for member in candidate.tracks for vector in _clean_reid_vectors(member)]
    if not body or not gallery:
        return None
    scores = sorted(
        (
            float(score)
            for left in body
            for right in gallery
            if (score := v5.cosine(left, right)) is not None
        ),
        reverse=True,
    )
    if not scores:
        return None
    if len(scores) >= 2:
        support = median(scores[: min(4, len(scores))])
        return float(support) if scores[1] >= BODY_ATTACH_MIN and support >= BODY_ATTACH_MIN else None
    return scores[0] if scores[0] >= BODY_ATTACH_SINGLE else None


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    ordered_tracks = sorted(
        tracks,
        key=lambda item: (
            item.episode_order,
            item.shot_ordinal,
            item.start_us if item.start_us is not None else -1,
        ),
    )
    evidence = _face_evidence(ordered_tracks)
    remaining = set(range(len(evidence)))
    identities: list[ConfirmedIdentity] = []

    # 1) 顺序式确认身份：吸收已有 -> 再从剩余里选最高质量 seed -> 确认下一个。
    while remaining:
        _absorb_until_stable(identities, remaining, evidence)
        if not remaining:
            break

        created = False
        for seed_index in sorted(remaining, key=lambda index: evidence[index].quality, reverse=True):
            seed = evidence[seed_index]
            if float(getattr(seed.observation, "face_score", seed.observation.detection_score)) < SEED_MIN_FACE_SCORE:
                continue
            if seed.quality < SEED_MIN_QUALITY:
                continue

            group, scores = _seed_group(seed_index, remaining, evidence)
            if not _group_confirmed(group, scores, evidence):
                continue
            if not _group_is_novel(group, identities, evidence):
                continue

            identity = ConfirmedIdentity(
                ordinal=len(identities),
                evidence_indices=set(group),
                scores=list(scores),
                seed_index=seed_index,
            )
            identities.append(identity)
            remaining.difference_update(group)
            created = True
            break

        if not created:
            break

    _absorb_until_stable(identities, remaining, evidence)

    # evidence_index -> confirmed identity ordinal。
    assignment: dict[int, int] = {}
    for identity in identities:
        for evidence_index in identity.evidence_indices:
            assignment[evidence_index] = identity.ordinal

    candidates = [
        _candidate_from_identity(identity, ordered_tracks, evidence, assignment)
        for identity in identities
    ]

    # 2) 只有完全没有可确认 Face 的 Track 才允许走 Body/Partial 回挂；
    #    有未解析 Face 的 Track 保持 UNRESOLVED，避免脏 Face 被 ReID 强行塞入已知人物。
    face_indices_by_track: dict[int, list[int]] = {}
    for item in evidence:
        face_indices_by_track.setdefault(item.track_index, []).append(item.index)

    attached_track_indices = {
        item.track_index
        for identity in identities
        for evidence_index in identity.evidence_indices
        for item in [evidence[evidence_index]]
    }
    unresolved_tracks: list[TrackDraft] = []

    for track_index, track in enumerate(ordered_tracks):
        if track_index in attached_track_indices:
            continue
        has_unresolved_face = bool(face_indices_by_track.get(track_index))
        if has_unresolved_face or not candidates:
            unresolved_tracks.append(track)
            continue

        matches: list[tuple[float, int]] = []
        for candidate_index, candidate in enumerate(candidates):
            score = _body_attach_score(track, candidate)
            if score is not None:
                matches.append((score, candidate_index))
        matches.sort(reverse=True)
        if not matches:
            unresolved_tracks.append(track)
            continue
        if len(matches) >= 2 and matches[0][0] - matches[1][0] < BODY_ATTACH_MARGIN:
            unresolved_tracks.append(track)
            continue
        v5._append_track(candidates[matches[0][1]], track, matches[0][0])

    # 3) 未确认 Face / Body / Partial 完整保留 Evidence，但永远不是 Final Character。
    for track in unresolved_tracks:
        candidate = CandidateDraft(id=new_id("CHAR_CANDIDATE"), identity_status="UNRESOLVED")
        v5._append_track(candidate, track)
        candidate.identity_status = "UNRESOLVED"
        candidate.v6_metadata = {  # type: ignore[attr-defined]
            "resolver": "anchor-first-v8-confirm-then-absorb",
            "reason": "not-confirmed-as-new-identity",
            "policy": "Evidence only; cannot increase Final Character count",
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
