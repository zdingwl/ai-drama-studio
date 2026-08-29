"""P2-E4 final Episode-context Fusion with anonymous-subject continuity graph.

E1 fixed Scene continuity and cross-Shot dialogue truth, but its inherited LocalSubject writer
still linked people by exact ``appearance_summary`` text. Real short-drama acceptance showed
that expression, pose and action wording changes fragmented one woman/man into many temporary
people. E4 keeps the frozen P1 Draft schema and replaces only the anonymous continuity policy:

- E2 window ``subject_continuity_hints`` are primary soft edges;
- Shot-local subject_A/subject_B labels are never treated as global identities;
- stable appearance cues are conservative fallback edges;
- any two observations from the same Shot are a hard cannot-link, including transitive unions;
- unresolved observations remain separate rather than forcing an identity merge.

This is still anonymous Draft continuity. ``LocalSubject != Character`` and Character V10.1 /
Final Asset gates remain untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from engine.app import breakdown_p2_fusion_episode_v2 as e1
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownRun,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
)

FUSION_PROFILE = "breakdown-p2-fusion-episode-context-e4-v1"
FUSION_VERSION = "1"
BASE_FUSION_PROFILE = e1.FUSION_PROFILE
SUBJECT_CONTINUITY_POLICY = "e2-window-hints-plus-stable-appearance-hard-same-shot-cannot-link-v1"
SUBJECT_HINT_POLICY = "e2-window-subject-continuity-primary-v1"
STABLE_APPEARANCE_POLICY = "exclude-expression-action-pose-screen-position-v1"

_DYNAMIC_MARKERS = (
    "表情", "神情", "情绪", "惊讶", "愤怒", "生气", "微笑", "哭", "皱眉", "紧张",
    "动作", "正在", "站立", "站着", "坐着", "坐下", "起身", "走", "跑", "转身",
    "低头", "抬头", "回头", "看向", "注视", "双臂", "抱臂", "交叉", "举手", "挥手",
    "拿着", "手持", "握着", "看手机", "说话", "对话", "张嘴",
)
_FRAMING_MARKERS = (
    "面部特写", "脸部特写", "人物特写", "特写", "近景", "中景", "全景", "远景",
    "左侧", "右侧", "中央", "中心", "前景", "背景", "画面中", "镜头中",
)
_GENDER_GROUPS = {
    "female": ("女性", "女人", "女子", "女孩", "女生", "女童", "老妇", "老太太", "阿姨"),
    "male": ("男性", "男人", "男子", "男孩", "男生", "男童", "老汉", "大叔", "叔叔"),
}
_AGE_TOKENS = ("年轻", "青年", "中年", "老年", "年长", "少年", "儿童")
_HAIR_STYLE_TOKENS = ("长发", "短发", "卷发", "直发", "马尾", "刘海", "光头", "寸头", "披肩发")
_HAIR_COLOR_TOKENS = ("黑发", "棕发", "金发", "白发", "灰发", "红发", "黑色头发", "棕色头发")
_COLOR_TOKENS = ("白色", "黑色", "红色", "蓝色", "灰色", "粉色", "绿色", "黄色", "紫色", "棕色", "米色")
_CLOTHING_TOKENS = ("上衣", "衬衫", "西装", "外套", "夹克", "连衣裙", "裙子", "长裙", "短裙", "裤子", "毛衣", "T恤", "礼服", "睡衣", "制服")
_ACCESSORY_TOKENS = ("眼镜", "耳环", "项链", "帽子", "领带", "围巾", "发箍", "发夹")


@dataclass(frozen=True)
class SubjectObservation:
    shot_revision_item_id: str
    shot_ordinal: int
    label: str
    appearance_summary: str

    @property
    def node_id(self) -> tuple[str, str]:
        return self.shot_revision_item_id, self.label


@dataclass(frozen=True)
class SubjectContinuityStats:
    observation_count: int
    cluster_count: int
    merged_cluster_count: int
    subject_hint_count: int
    explicit_union_count: int
    fallback_union_count: int
    rejected_cannot_link_count: int


class _UnionFind:
    def __init__(self, observations: Sequence[SubjectObservation]) -> None:
        self.parent = list(range(len(observations)))
        self.members: dict[int, set[int]] = {index: {index} for index in range(len(observations))}
        self.shots: dict[int, set[str]] = {
            index: {item.shot_revision_item_id}
            for index, item in enumerate(observations)
        }
        self.rejected_cannot_link_count = 0

    def find(self, index: int) -> int:
        parent = self.parent[index]
        if parent != index:
            self.parent[index] = self.find(parent)
        return self.parent[index]

    def union(self, left: int, right: int) -> bool:
        a = self.find(left)
        b = self.find(right)
        if a == b:
            return False
        # Hard cannot-link: one anonymous cluster can contain at most one observation per Shot.
        if self.shots[a].intersection(self.shots[b]):
            self.rejected_cannot_link_count += 1
            return False
        if len(self.members[a]) < len(self.members[b]):
            a, b = b, a
        self.parent[b] = a
        self.members[a].update(self.members.pop(b))
        self.shots[a].update(self.shots.pop(b))
        return True


def _clean_text(value: Any, *, max_len: int = 2000) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:max_len]


def _normalized(value: Any) -> str:
    return "".join(char.lower() for char in _clean_text(value) if char.isalnum())


def _stable_phrase(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    clauses = [item.strip() for item in re.split(r"[，,。；;、|/]+", text) if item.strip()]
    kept = [
        clause for clause in clauses
        if not any(marker in clause for marker in _DYNAMIC_MARKERS)
    ]
    stable = "，".join(kept) if kept else text
    for marker in _DYNAMIC_MARKERS + _FRAMING_MARKERS:
        stable = stable.replace(marker, "")
    return _normalized(stable)


def _gender(value: Any) -> str | None:
    text = _clean_text(value)
    hits = [name for name, tokens in _GENDER_GROUPS.items() if any(token in text for token in tokens)]
    return hits[0] if len(hits) == 1 else None


def _stable_features(value: Any) -> set[str]:
    text = _clean_text(value)
    features: set[str] = set()
    gender = _gender(text)
    if gender:
        features.add(f"gender:{gender}")
    for token in _AGE_TOKENS:
        if token in text:
            features.add(f"age:{token}")
    for token in _HAIR_STYLE_TOKENS:
        if token in text:
            features.add(f"hair_style:{token}")
    for token in _HAIR_COLOR_TOKENS:
        if token in text:
            features.add(f"hair_color:{token}")
    for token in _COLOR_TOKENS:
        if token in text:
            features.add(f"color:{token}")
    for token in _CLOTHING_TOKENS:
        if token in text:
            features.add(f"clothing:{token}")
    for token in _ACCESSORY_TOKENS:
        if token in text:
            features.add(f"accessory:{token}")
    return features


def _appearance_similarity(left: Any, right: Any) -> tuple[float, int]:
    left_text = _clean_text(left)
    right_text = _clean_text(right)
    left_gender = _gender(left_text)
    right_gender = _gender(right_text)
    if left_gender and right_gender and left_gender != right_gender:
        return -math.inf, 0

    left_phrase = _stable_phrase(left_text)
    right_phrase = _stable_phrase(right_text)
    score = 0.0
    if left_phrase and right_phrase:
        if left_phrase == right_phrase and len(left_phrase) >= 4:
            score += 3.0
        else:
            shorter, longer = sorted((left_phrase, right_phrase), key=len)
            if len(shorter) >= 4 and shorter in longer:
                score += 2.0

    left_features = _stable_features(left_text)
    right_features = _stable_features(right_text)
    shared = left_features.intersection(right_features)
    strong_count = 0
    for feature in shared:
        prefix = feature.split(":", 1)[0]
        if prefix == "gender":
            score += 0.75
        elif prefix == "age":
            score += 0.5
        elif prefix == "hair_style":
            score += 1.5
            strong_count += 1
        elif prefix == "hair_color":
            score += 1.25
            strong_count += 1
        elif prefix in {"color", "clothing"}:
            score += 1.0
            strong_count += 1
        elif prefix == "accessory":
            score += 1.5
            strong_count += 1
    return score, strong_count


def _window_subject_hints(window_summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for window in window_summaries:
        if not isinstance(window, Mapping):
            continue
        raw_hints = window.get("subject_continuity_hints")
        if not isinstance(raw_hints, list):
            continue
        for raw in raw_hints:
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            item["window_id"] = str(window.get("window_id") or "").strip() or None
            marker = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if marker in seen:
                continue
            seen.add(marker)
            result.append(item)
    return result


def _observations_for_plan(segment_plan: Any) -> list[SubjectObservation]:
    observations: list[SubjectObservation] = []
    for shot, semantic in zip(segment_plan.shots, segment_plan.semantics):
        if not isinstance(semantic, Mapping):
            continue
        raw_subjects = semantic.get("subjects")
        if not isinstance(raw_subjects, list):
            continue
        for raw in raw_subjects:
            if not isinstance(raw, Mapping):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            observations.append(SubjectObservation(
                shot_revision_item_id=shot.revision_item_id,
                shot_ordinal=int(shot.ordinal),
                label=label,
                appearance_summary=_clean_text(raw.get("appearance_summary")),
            ))
    return observations


def _resolve_hint_nodes(
    hint: Mapping[str, Any],
    observations: Sequence[SubjectObservation],
    index_by_node: Mapping[tuple[str, str], int],
) -> list[int]:
    result: list[int] = []
    raw_members = hint.get("members")
    if isinstance(raw_members, list):
        for raw in raw_members:
            if not isinstance(raw, Mapping):
                continue
            key = (
                str(raw.get("revision_item_id") or "").strip(),
                str(raw.get("label") or "").strip(),
            )
            index = index_by_node.get(key)
            if index is not None and index not in result:
                result.append(index)
        if len(result) >= 2:
            return result

    raw_ordinals = hint.get("shot_ordinals")
    if not isinstance(raw_ordinals, list):
        return result
    appearance = _clean_text(hint.get("appearance_summary"))
    try:
        ordinals = {int(value) for value in raw_ordinals}
    except (TypeError, ValueError):
        ordinals = set()
    for ordinal in sorted(ordinals):
        candidates = [
            (index, item)
            for index, item in enumerate(observations)
            if item.shot_ordinal == ordinal
        ]
        if not candidates:
            continue
        if len(candidates) == 1:
            index = candidates[0][0]
            if index not in result:
                result.append(index)
            continue
        scored: list[tuple[float, int]] = []
        for index, item in candidates:
            score, _strong = _appearance_similarity(appearance, item.appearance_summary)
            scored.append((score, index))
        scored.sort(reverse=True)
        if not scored or not math.isfinite(scored[0][0]) or scored[0][0] < 1.0:
            continue
        second = scored[1][0] if len(scored) > 1 else -math.inf
        if math.isfinite(second) and scored[0][0] - second < 0.5:
            continue
        if scored[0][1] not in result:
            result.append(scored[0][1])
    return result


def _fallback_pairs(observations: Sequence[SubjectObservation]) -> list[tuple[int, int]]:
    by_ordinal: dict[int, list[int]] = {}
    for index, item in enumerate(observations):
        by_ordinal.setdefault(item.shot_ordinal, []).append(index)
    ordinals = sorted(by_ordinal)
    pairs: list[tuple[int, int]] = []
    for left_pos, left_ordinal in enumerate(ordinals):
        for right_ordinal in ordinals[left_pos + 1:]:
            distance = right_ordinal - left_ordinal
            if distance > 2:
                break
            left_indexes = by_ordinal[left_ordinal]
            right_indexes = by_ordinal[right_ordinal]
            scores: dict[tuple[int, int], tuple[float, int]] = {}
            for left in left_indexes:
                for right in right_indexes:
                    scores[(left, right)] = _appearance_similarity(
                        observations[left].appearance_summary,
                        observations[right].appearance_summary,
                    )
            for left in left_indexes:
                left_ranked = sorted(
                    ((scores[(left, right)][0], right) for right in right_indexes),
                    reverse=True,
                )
                if not left_ranked:
                    continue
                best_score, best_right = left_ranked[0]
                right_ranked = sorted(
                    ((scores[(candidate, best_right)][0], candidate) for candidate in left_indexes),
                    reverse=True,
                )
                if not right_ranked or right_ranked[0][1] != left:
                    continue
                _score, strong_count = scores[(left, best_right)]
                threshold = 4.0 if distance == 1 else 4.5
                if math.isfinite(best_score) and best_score >= threshold and strong_count >= 2:
                    pairs.append((left, best_right))
    return pairs


def _build_subject_cluster_keys(
    segment_plans: Sequence[Any],
    window_summaries: Sequence[Mapping[str, Any]],
) -> tuple[dict[tuple[str, str], str], dict[str, list[dict[str, Any]]], SubjectContinuityStats]:
    """Build conservative anonymous continuity keys consumed by the legacy P1 writer."""

    hints = _window_subject_hints(window_summaries)
    final_keys: dict[tuple[str, str], str] = {}
    cluster_members: dict[str, list[dict[str, Any]]] = {}
    total_observations = 0
    total_clusters = 0
    merged_clusters = 0
    explicit_unions = 0
    fallback_unions = 0
    rejected = 0

    for segment_plan in segment_plans:
        observations = _observations_for_plan(segment_plan)
        if not observations:
            continue
        total_observations += len(observations)
        index_by_node = {item.node_id: index for index, item in enumerate(observations)}
        uf = _UnionFind(observations)
        segment_ordinals = {item.shot_ordinal for item in observations}

        for hint in hints:
            raw_ordinals = hint.get("shot_ordinals")
            if not isinstance(raw_ordinals, list):
                continue
            try:
                hint_ordinals = {int(value) for value in raw_ordinals}
            except (TypeError, ValueError):
                continue
            if len(hint_ordinals.intersection(segment_ordinals)) < 2:
                continue
            nodes = _resolve_hint_nodes(hint, observations, index_by_node)
            for left, right in zip(nodes, nodes[1:]):
                if uf.union(left, right):
                    explicit_unions += 1

        for left, right in _fallback_pairs(observations):
            if uf.union(left, right):
                fallback_unions += 1

        roots: dict[int, list[int]] = {}
        for index in range(len(observations)):
            roots.setdefault(uf.find(index), []).append(index)
        total_clusters += len(roots)
        merged_clusters += sum(1 for members in roots.values() if len(members) > 1)
        rejected += uf.rejected_cannot_link_count

        for members in roots.values():
            ordered = sorted(
                members,
                key=lambda index: (
                    observations[index].shot_ordinal,
                    observations[index].shot_revision_item_id,
                    observations[index].label,
                ),
            )
            first = observations[ordered[0]]
            if len(ordered) > 1:
                key = f"e4:{first.shot_revision_item_id}:{first.label}"
            else:
                key = f"shot:{first.shot_revision_item_id}:{first.label}"
            rows: list[dict[str, Any]] = []
            for index in ordered:
                item = observations[index]
                final_keys[item.node_id] = key
                rows.append({
                    "shot_revision_item_id": item.shot_revision_item_id,
                    "shot_ordinal": item.shot_ordinal,
                    "source_label": item.label,
                    "appearance_summary": item.appearance_summary,
                })
            cluster_members[key] = rows

    return final_keys, cluster_members, SubjectContinuityStats(
        observation_count=total_observations,
        cluster_count=total_clusters,
        merged_cluster_count=merged_clusters,
        subject_hint_count=len(hints),
        explicit_union_count=explicit_unions,
        fallback_union_count=fallback_unions,
        rejected_cannot_link_count=rejected,
    )


def _window_summaries(bundle: legacy.FusionInputBundle) -> tuple[Mapping[str, Any], ...]:
    metadata = bundle.components["VLM"].result.metadata
    raw = metadata.get("window_summaries") if isinstance(metadata, Mapping) else None
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, Mapping))


def _rewrite_subject_metadata(
    session: Any,
    *,
    run_id: str,
    subject_keys: Mapping[tuple[str, str], str],
    cluster_members: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    drafts = {
        item.id: item
        for item in session.scalars(
            select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run_id)
        ).all()
    }
    presences = list(session.scalars(
        select(ShotLocalSubject).where(ShotLocalSubject.run_id == run_id)
    ).all())
    members_by_local: dict[str, list[tuple[str, str, str]]] = {}
    for presence in presences:
        draft = drafts.get(presence.shot_draft_id)
        if draft is None:
            continue
        search_hint = e1._json_object(presence.search_hint_json)
        label = str(search_hint.get("source_vlm_label") or "").strip()
        key = subject_keys.get((draft.source_shot_revision_item_id, label))
        if key:
            members_by_local.setdefault(presence.local_subject_id, []).append(
                (draft.source_shot_revision_item_id, label, key)
            )

    locals_ = list(session.scalars(
        select(LocalSubject).where(LocalSubject.run_id == run_id)
    ).all())
    for local in locals_:
        rows = members_by_local.get(local.id, [])
        cluster_key = rows[0][2] if rows else None
        metadata = e1._json_object(local.appearance_json)
        metadata.update({
            "fusion_profile": FUSION_PROFILE,
            "link_policy": SUBJECT_CONTINUITY_POLICY,
            "subject_hint_policy": SUBJECT_HINT_POLICY,
            "stable_appearance_policy": STABLE_APPEARANCE_POLICY,
            "same_shot_cannot_link": True,
            "cluster_key": cluster_key,
            "source_members": list(cluster_members.get(cluster_key, ())) if cluster_key else [],
        })
        local.appearance_json = e1._json_text(metadata)


def _rewrite_e4_metadata(
    session: Any,
    *,
    run: BreakdownRun,
    stats: SubjectContinuityStats,
) -> None:
    statuses = e1._json_object(run.component_status_json)
    fusion_status = statuses.get("FUSION")
    if not isinstance(fusion_status, dict):
        fusion_status = {}
    fusion_status.update({
        "profile": FUSION_PROFILE,
        "version": FUSION_VERSION,
        "base_profile": BASE_FUSION_PROFILE,
        "subject_continuity": {
            "policy": SUBJECT_CONTINUITY_POLICY,
            "observation_count": stats.observation_count,
            "cluster_count": stats.cluster_count,
            "merged_cluster_count": stats.merged_cluster_count,
            "subject_hint_count": stats.subject_hint_count,
            "explicit_union_count": stats.explicit_union_count,
            "fallback_union_count": stats.fallback_union_count,
            "rejected_cannot_link_count": stats.rejected_cannot_link_count,
        },
    })
    statuses["FUSION"] = fusion_status

    providers = e1._json_object(run.provider_metadata_json)
    previous = providers.get("p2_fusion")
    p2_fusion = dict(previous) if isinstance(previous, Mapping) else {}
    p2_fusion.update({
        "profile": FUSION_PROFILE,
        "version": FUSION_VERSION,
        "base_profile": BASE_FUSION_PROFILE,
        "subject_continuity_policy": SUBJECT_CONTINUITY_POLICY,
        "subject_hint_policy": SUBJECT_HINT_POLICY,
        "stable_appearance_policy": STABLE_APPEARANCE_POLICY,
        "same_shot_cannot_link": "hard",
        "local_subject_semantics": "anonymous-scene-scoped-not-character",
    })
    providers["p2_fusion"] = p2_fusion

    for segment in session.scalars(
        select(SceneSegmentDraft).where(SceneSegmentDraft.run_id == run.id)
    ).all():
        metadata = e1._json_object(segment.metadata_json)
        metadata["fusion_profile"] = FUSION_PROFILE
        segment.metadata_json = e1._json_text(metadata)
    for draft in session.scalars(
        select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)
    ).all():
        metadata = e1._json_object(draft.model_metadata_json)
        metadata["fusion_profile"] = FUSION_PROFILE
        metadata["subject_continuity_policy"] = SUBJECT_CONTINUITY_POLICY
        draft.model_metadata_json = e1._json_text(metadata)

    run.component_status_json = e1._json_text(statuses)
    run.provider_metadata_json = e1._json_text(providers)


def fuse_breakdown_run(run_id: str) -> BreakdownRun:
    """E4 production entry: E2/E3 evidence -> continuity graph -> P1 anonymous Draft."""

    try:
        source_bundle = legacy.load_fusion_inputs(run_id)
        projection_bundle = e1._episode_projection_bundle(source_bundle)
        shots_by_id = {shot.revision_item_id: shot for shot in source_bundle.context.shots}
        vlm_by_shot = {
            item.shot_revision_item_id: item
            for item in source_bundle.components["VLM"].result.evidence
            if item.source_type.strip().upper() == "VLM_OUTPUT"
            and item.shot_revision_item_id in shots_by_id
        }
        segment_plans = e1._continuity_segment_plans(source_bundle.context.shots, vlm_by_shot)
        subject_keys, cluster_members, stats = _build_subject_cluster_keys(
            segment_plans,
            _window_summaries(source_bundle),
        )

        def e4_appearance_key(
            subject: Mapping[str, Any],
            shot: p2.P2ShotInput,
            label: str,
            ambiguous_appearances: set[str] | None = None,
        ) -> str:
            del subject, ambiguous_appearances
            return subject_keys.get(
                (shot.revision_item_id, label),
                f"shot:{shot.revision_item_id}:{label}",
            )

        with e1._FUSION_PATCH_LOCK:
            original_segment_plans = legacy._segment_plans
            original_appearance_key = legacy._appearance_key
            legacy._segment_plans = e1._continuity_segment_plans
            legacy._appearance_key = e4_appearance_key
            try:
                raw_warnings, _generated_counts = legacy._write_fused_draft(projection_bundle)
            finally:
                legacy._segment_plans = original_segment_plans
                legacy._appearance_key = original_appearance_key

        warnings = [
            dict(item) for item in raw_warnings
            if str(item.get("code") or "") != "ASR_CROSS_SHOT_TEXT_FALLBACK"
        ]
        if stats.observation_count >= 4 and stats.merged_cluster_count == 0:
            warnings.append({
                "code": "E4_SUBJECT_CONTINUITY_UNRESOLVED",
                "message": "E4 未形成任何跨镜匿名人物连续簇；请检查 E2 continuity hints / 稳定外观 Evidence",
            })

        with studio_v2.get_session() as session:
            run = session.get(BreakdownRun, run_id)
            if run is None:
                raise LookupError("Breakdown Run 不存在")
            if run.status != "PROCESSING":
                raise legacy.BreakdownP2FusionError(
                    f"E4 post-Fusion 只允许处理 PROCESSING Run，当前状态为 {run.status}"
                )
            e1._rewrite_dialogue_events(session, run_id=run_id, source_bundle=source_bundle)
            e1._rewrite_scene_rows(session, run_id=run_id, source_bundle=source_bundle)
            _rewrite_subject_metadata(
                session,
                run_id=run_id,
                subject_keys=subject_keys,
                cluster_members=cluster_members,
            )
            e1._rewrite_run_metadata(session, run=run, warnings=warnings)
            _rewrite_e4_metadata(session, run=run, stats=stats)
            session.commit()

        return breakdown_service_v1.publish_breakdown_run(
            run_id,
            warnings=warnings or None,
        )
    except Exception as exc:
        legacy._safe_fail_run(run_id, exc)
        raise


__all__ = [
    "BASE_FUSION_PROFILE",
    "FUSION_PROFILE",
    "FUSION_VERSION",
    "STABLE_APPEARANCE_POLICY",
    "SUBJECT_CONTINUITY_POLICY",
    "SUBJECT_HINT_POLICY",
    "SubjectContinuityStats",
    "SubjectObservation",
    "_appearance_similarity",
    "_build_subject_cluster_keys",
    "fuse_breakdown_run",
]
