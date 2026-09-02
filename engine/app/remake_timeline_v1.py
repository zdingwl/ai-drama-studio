"""R6 Dialogue Timing Engine + persistent RemakeTimeline V1.

The engine consumes current SourceDramaSnapshot + current canonical TargetDialogue facts.
It never changes source Shot boundaries or source ASR. It plans a new target timeline from
actual TTS duration, preferring conservative automatic edits and sending only extreme timing
choices to Review Center.

A canonical TargetDialogue is emitted once per complete source utterance. When that source
utterance projects across multiple Shots, the dialogue plan is anchored once on the first
projection Shot and may remain active across later Shot windows. It is never duplicated per
projection. If target speech exceeds the complete source projection span, timing changes are
applied to the last projection Shot (or a safe following reaction Shot), not incorrectly to
the first Shot.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.remake_timeline_contract_v1 import RemakeEpisodeTimelineV1, RemakeProjectTimelineV1
from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Base, Episode, Project, get_session, new_id, utcnow
from engine.app.target_dialogue_pipeline_v1 import validate_target_dialogue_dependencies_v1
from engine.app.target_dialogue_v1 import get_target_dialogue_v1


TIMING_REVIEW_PREFIX = "auto:dialogue-timing:"
TRAILING_HOLD_US = 180_000
INTER_DIALOGUE_GAP_US = 80_000
TRIM_MIN_SAVING_US = 300_000
TRIM_MAX_SOURCE_TAIL_US = 350_000
TRIM_MIN_DURATION_US = 800_000
TRIM_MIN_SOURCE_RATIO = 0.65
EXTREME_OVERRUN_US = 2_000_000
EXTREME_DURATION_RATIO = 2.20


class RemakeTimelineError(RuntimeError):
    pass


class RemakeTimeline(Base):
    __tablename__ = "v2_remake_timelines"
    __table_args__ = (UniqueConstraint("project_id", "episode_id", name="uq_v2_remake_timeline_episode"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_dialogue_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def target_dialogue_fingerprint_v1(dialogues: list[Mapping[str, Any]]) -> str:
    rows = [
        {
            "source_dialogue_key": item.get("source_dialogue_key"),
            "source_dialogue_signature": item.get("source_dialogue_signature"),
            "target_character_id": item.get("target_character_id"),
            "final_text": item.get("final_text"),
            "status": item.get("status"),
            "audio_status": item.get("audio_status"),
            "audio_input_signature": item.get("audio_input_signature"),
            "speech_duration_us": item.get("speech_duration_us"),
        }
        for item in dialogues
    ]
    rows.sort(key=lambda item: str(item["source_dialogue_key"] or ""))
    return _digest(rows)


def _timing_issue_key(episode_id: str, shot_key: str) -> str:
    digest = hashlib.sha1(f"{episode_id}:{shot_key}".encode("utf-8")).hexdigest()[:28]
    return f"{TIMING_REVIEW_PREFIX}{digest}"


def _resolve_issue(project_id: str, source_key: str, reason: str) -> None:
    with get_session() as session:
        row = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == source_key,
            ReviewIssue.status == "OPEN",
        ))
        if row is None:
            return
        now = utcnow()
        row.status = "RESOLVED"
        row.resolution_json = json.dumps({"automatic": True, "reason": reason}, ensure_ascii=False)
        row.resolved_at = now
        row.updated_at = now
        session.commit()


def _resolve_stale_timing_issues(project_id: str, active_keys: set[str]) -> None:
    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.source_key.like(f"{TIMING_REVIEW_PREFIX}%"),
        )).all()
        now = utcnow()
        changed = False
        for row in rows:
            if row.source_key in active_keys:
                continue
            row.status = "RESOLVED"
            row.resolution_json = json.dumps({"automatic": True, "reason": "当前时间轴已不再报告此时长问题"}, ensure_ascii=False)
            row.resolved_at = now
            row.updated_at = now
            changed = True
        if changed:
            session.commit()


def _shot_character_ids(scene: Mapping[str, Any], shot: Mapping[str, Any]) -> set[str]:
    person_character: dict[str, str] = {}
    for person in scene.get("people") or []:
        if not isinstance(person, Mapping) or not person.get("person_key"):
            continue
        character = person.get("character")
        if isinstance(character, Mapping) and character.get("id"):
            person_character[str(person["person_key"])] = str(character["id"])
    return {
        person_character[key]
        for key in (str(item) for item in shot.get("people") or [])
        if key in person_character
    }


def _source_shot_rows(episode: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scene in episode.get("scenes") or []:
        if not isinstance(scene, Mapping):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, Mapping):
                continue
            row = dict(shot)
            row["scene_key"] = str(scene.get("scene_key") or "")
            row["source_character_ids"] = sorted(_shot_character_ids(scene, shot))
            rows.append(row)
    rows.sort(key=lambda item: (int(item.get("start_us") or 0), int(item.get("ordinal") or 0)))
    return rows


def _canonical_utterance_index(episode: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    utterances = episode.get("source_dialogue_utterances")
    if not isinstance(utterances, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for item in utterances:
        if not isinstance(item, Mapping):
            continue
        group_id = str(item.get("dialogue_group_id") or "").strip()
        if not group_id:
            continue
        if group_id in result:
            raise RemakeTimelineError("SourceDramaSnapshot contains duplicate dialogue_group_id")
        result[group_id] = item
    return result


def _target_dialogues_by_shot(
    dialogues: list[Mapping[str, Any]],
    *,
    episode: Mapping[str, Any],
    shots: list[dict[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Anchor one canonical TargetDialogue on its first source projection Shot.

    Internal ``_source_span_*`` fields are timing-only metadata and are never serialized into
    the public RemakeTimeline contract.
    """

    result: dict[str, list[Mapping[str, Any]]] = {}
    shot_by_key = {str(item.get("shot_key") or ""): item for item in shots}
    utterance_by_group = _canonical_utterance_index(episode)
    canonical_mode = "source_dialogue_utterances" in episode

    for row in dialogues:
        source_key = str(row.get("source_dialogue_key") or "")
        enriched = dict(row)
        anchor_key = str(row.get("shot_key") or "")
        utterance = utterance_by_group.get(source_key)
        if canonical_mode:
            if utterance is None:
                raise RemakeTimelineError(f"TargetDialogue {source_key} does not exist in current source utterances")
            projections = [
                item for item in utterance.get("projections") or []
                if isinstance(item, Mapping) and item.get("shot_key")
            ]
            projections.sort(key=lambda item: (
                int(item.get("projection_index") or 0),
                int(item.get("start_us") or 0),
                str(item.get("dialogue_key") or ""),
            ))
            if not projections:
                raise RemakeTimelineError(f"Source utterance {source_key} has no Shot projections")
            projection_keys = [str(item["shot_key"]) for item in projections]
            if any(key not in shot_by_key for key in projection_keys):
                raise RemakeTimelineError(f"Source utterance {source_key} references a missing Shot")
            anchor_key = projection_keys[0]
            last_key = projection_keys[-1]
            last_shot = shot_by_key[last_key]
            enriched["shot_key"] = anchor_key
            enriched["source_start_us"] = int(utterance.get("start_us") or row.get("source_start_us") or 0)
            enriched["source_end_us"] = int(utterance.get("end_us") or row.get("source_end_us") or 0)
            enriched["_source_projection_count"] = len(projection_keys)
            enriched["_source_projection_shot_keys"] = projection_keys
            enriched["_source_span_last_shot_key"] = last_key
            # Allow target speech to use the natural visual tail of the last source projection
            # Shot before declaring that video timing must change.
            enriched["_source_span_end_us"] = int(last_shot.get("end_us") or enriched["source_end_us"])
        else:
            anchor_shot = shot_by_key.get(anchor_key)
            enriched["_source_projection_count"] = 1
            enriched["_source_projection_shot_keys"] = [anchor_key]
            enriched["_source_span_last_shot_key"] = anchor_key
            enriched["_source_span_end_us"] = int(
                anchor_shot.get("end_us") if anchor_shot is not None else row.get("source_end_us") or 0
            )

        if anchor_key not in shot_by_key:
            raise RemakeTimelineError(f"TargetDialogue {source_key} references a missing anchor Shot")
        result.setdefault(anchor_key, []).append(enriched)

    for values in result.values():
        values.sort(key=lambda item: (
            int(item.get("source_start_us") or 0),
            str(item.get("source_dialogue_key") or ""),
        ))
    return result


def _reaction_carry_candidate(
    shots: list[dict[str, Any]],
    index: int,
    *,
    source_character_id: str | None,
    speech_overrun_us: int,
    target_dialogues_by_shot: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any] | None:
    if source_character_id is None or index + 1 >= len(shots):
        return None
    current, next_shot = shots[index], shots[index + 1]
    if current.get("scene_key") != next_shot.get("scene_key"):
        return None
    next_key = str(next_shot.get("shot_key") or "")
    if target_dialogues_by_shot.get(next_key):
        return None
    if source_character_id in set(next_shot.get("source_character_ids") or []):
        return None
    # Reserve the tail hold inside the reaction shot. Only real speech overrun is measured;
    # lack of optional tail padding alone never causes a carry/extend decision.
    available_speech = int(next_shot.get("duration_us") or 0) - TRAILING_HOLD_US
    if available_speech < speech_overrun_us:
        return None
    return next_shot


def _dialogue_plans_for_shot(
    shot: Mapping[str, Any],
    target_rows: list[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    bool,
    int,
    str | None,
    dict[str, dict[str, Any]],
]:
    source_start = int(shot.get("start_us") or 0)
    cursor = 0
    plans: list[dict[str, Any]] = []
    waiting_audio = False
    max_end_offset = 0
    sole_source_character_id: str | None = None
    source_characters: set[str] = set()
    span_meta: dict[str, dict[str, Any]] = {}

    for row in target_rows:
        source_line_start = int(row.get("source_start_us") or source_start)
        source_line_end = int(row.get("source_end_us") or source_line_start)
        source_window = max(1, source_line_end - source_line_start)
        start_offset = max(0, source_line_start - source_start, cursor)
        actual_duration = int(row.get("speech_duration_us") or 0)
        audio_ready = row.get("status") == "READY" and row.get("audio_status") == "READY" and actual_duration > 0
        if not audio_ready:
            waiting_audio = True
        planning_duration = actual_duration if audio_ready else source_window
        end_offset = start_offset + planning_duration
        cursor = end_offset + INTER_DIALOGUE_GAP_US
        max_end_offset = max(max_end_offset, end_offset)
        source_character_id = str(row.get("source_character_id") or "") or None
        if source_character_id:
            source_characters.add(source_character_id)
        target_dialogue_id = str(row.get("id") or "")
        plan = {
            "target_dialogue_id": target_dialogue_id,
            "source_dialogue_key": str(row.get("source_dialogue_key") or ""),
            "source_character_id": source_character_id,
            "target_character_id": str(row.get("target_character_id") or "") or None,
            "source_start_us": source_line_start,
            "source_end_us": source_line_end,
            "source_window_us": source_window,
            "speech_duration_us": actual_duration if audio_ready else None,
            "planned_start_offset_us": start_offset,
            "planned_end_offset_us": end_offset,
            "planned_start_us": 0,
            "planned_end_us": 1,
            "strategy": "KEEP",
            "carry_over_shot_key": None,
            "overrun_us": 0,
            "reason": "目标对白按源对白相对起点进入新时间轴" if audio_ready else "等待真实目标语音，当前仅保留源对白位置作为占位",
        }
        plans.append(plan)
        span_end_us = int(row.get("_source_span_end_us") or shot.get("end_us") or source_line_end)
        span_meta[target_dialogue_id] = {
            "span_end_offset_us": max(source_duration := int(shot.get("duration_us") or 0), span_end_us - source_start),
            "last_shot_key": str(row.get("_source_span_last_shot_key") or shot.get("shot_key") or ""),
            "projection_count": max(1, int(row.get("_source_projection_count") or 1)),
        }
    if len(source_characters) == 1:
        sole_source_character_id = next(iter(source_characters))
    return plans, waiting_audio, max_end_offset, sole_source_character_id, span_meta


def _cross_projection_adjustments(
    shots: list[dict[str, Any]],
    *,
    origin_index: int,
    dialogue_plans: list[dict[str, Any]],
    span_meta: Mapping[str, Mapping[str, Any]],
    target_dialogues_by_shot: Mapping[str, list[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], bool]:
    """Plan timing changes that belong to a later (last-projection) Shot.

    Returns deferred Shot adjustments plus whether any cross-shot dialogue carries into a
    following reaction Shot. The origin Shot duration is never changed for these cases.
    """

    shot_index_by_key = {str(item.get("shot_key") or ""): index for index, item in enumerate(shots)}
    adjustments: list[dict[str, Any]] = []
    has_carry = False

    for plan in dialogue_plans:
        meta = span_meta.get(str(plan["target_dialogue_id"])) or {}
        if int(meta.get("projection_count") or 1) <= 1:
            continue
        span_end_offset = int(meta.get("span_end_offset_us") or 0)
        planned_end = int(plan["planned_end_offset_us"])
        if planned_end <= span_end_offset:
            plan["reason"] = "完整对白跨多个源镜头，目标语音可在原投影视觉范围内自然播放"
            continue

        last_key = str(meta.get("last_shot_key") or "")
        last_index = shot_index_by_key.get(last_key)
        if last_index is None or last_index < origin_index:
            raise RemakeTimelineError("完整对白的最后投影 Shot 无法定位")
        overrun = planned_end - span_end_offset
        source_character_id = str(plan.get("source_character_id") or "") or None
        carry = _reaction_carry_candidate(
            shots,
            last_index,
            source_character_id=source_character_id,
            speech_overrun_us=overrun,
            target_dialogues_by_shot=target_dialogues_by_shot,
        )
        if carry is not None:
            carry_key = str(carry.get("shot_key") or "")
            plan["strategy"] = "CARRY_OVER_REACTION"
            plan["carry_over_shot_key"] = carry_key
            plan["overrun_us"] = overrun
            plan["reason"] = "完整对白已跨原投影镜头，额外语音尾部自动延续到后一无对白反应镜"
            has_carry = True
            continue

        last_shot = shots[last_index]
        last_source_duration = max(1, int(last_shot.get("duration_us") or 0))
        required_duration = last_source_duration + overrun + TRAILING_HOLD_US
        extension_delta = required_duration - last_source_duration
        extreme = (
            required_duration / last_source_duration > EXTREME_DURATION_RATIO
            and extension_delta > EXTREME_OVERRUN_US
        )
        if extreme:
            plan["strategy"] = "HUMAN_REVIEW"
            plan["overrun_us"] = overrun
            plan["reason"] = "完整对白目标语音明显超过全部源投影视觉范围，需要确认最后投影镜延长方案或回到目标对白改写"
            adjustments.append({
                "shot_key": last_key,
                "strategy": "HUMAN_REVIEW",
                "status": "REVIEW",
                "required_duration_us": required_duration,
                "reason": plan["reason"],
            })
        else:
            plan["strategy"] = "EXTEND"
            plan["overrun_us"] = overrun
            plan["reason"] = "完整对白目标语音超过全部源投影视觉范围，延长最后一个投影镜承接尾部语音"
            adjustments.append({
                "shot_key": last_key,
                "strategy": "EXTEND",
                "status": "READY",
                "required_duration_us": required_duration,
                "reason": plan["reason"],
            })

    return adjustments, has_carry


def _auto_shot_plan(
    shots: list[dict[str, Any]],
    index: int,
    *,
    target_dialogues_by_shot: Mapping[str, list[Mapping[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    shot = shots[index]
    shot_key = str(shot.get("shot_key") or "")
    source_duration = max(1, int(shot.get("duration_us") or 0))
    target_rows = list(target_dialogues_by_shot.get(shot_key) or [])
    dialogue_plans, waiting_audio, max_dialogue_end, source_character_id, span_meta = _dialogue_plans_for_shot(shot, target_rows)
    deferred_adjustments: list[dict[str, Any]] = []

    cross_adjustments, cross_carry = _cross_projection_adjustments(
        shots,
        origin_index=index,
        dialogue_plans=dialogue_plans,
        span_meta=span_meta,
        target_dialogues_by_shot=target_dialogues_by_shot,
    )
    deferred_adjustments.extend(cross_adjustments)

    # Local overrun is calculated only for one-Projection utterances. Cross-shot utterances
    # are handled against their complete visual span above and must not extend the first Shot.
    local_plans = [
        plan for plan in dialogue_plans
        if int((span_meta.get(str(plan["target_dialogue_id"])) or {}).get("projection_count") or 1) == 1
    ]
    max_local_end = max((int(plan["planned_end_offset_us"]) for plan in local_plans), default=0)

    if not target_rows:
        strategy, status, planned_duration = "KEEP", "READY", source_duration
        reason = "无目标对白，保持原镜头时长"
    elif waiting_audio:
        strategy, status, planned_duration = "KEEP", "WAITING_AUDIO", source_duration
        reason = "目标对白尚缺真实 TTS 时长，保持原时长等待音频；不使用估算时长替代事实"
    else:
        local_overrun = max(0, max_local_end - source_duration)
        if local_overrun > 0:
            planned_extension_duration = max_local_end + TRAILING_HOLD_US
            extension_delta = planned_extension_duration - source_duration
            carry = _reaction_carry_candidate(
                shots,
                index,
                source_character_id=source_character_id,
                speech_overrun_us=local_overrun,
                target_dialogues_by_shot=target_dialogues_by_shot,
            )
            if carry is not None:
                strategy, status, planned_duration = "CARRY_OVER_REACTION", "READY", source_duration
                reason = "目标对白越过当前切点，自动延续到下一无对白反应镜；当前镜头不做慢放"
                carry_key = str(carry.get("shot_key") or "")
                for plan in local_plans:
                    if int(plan["planned_end_offset_us"]) > source_duration:
                        plan["strategy"] = "CARRY_OVER_REACTION"
                        plan["carry_over_shot_key"] = carry_key
                        plan["overrun_us"] = int(plan["planned_end_offset_us"]) - source_duration
                        plan["reason"] = "目标语音尾部跨到下一反应镜继续播放"
            elif planned_extension_duration / source_duration > EXTREME_DURATION_RATIO and extension_delta > EXTREME_OVERRUN_US:
                strategy, status, planned_duration = "HUMAN_REVIEW", "REVIEW", planned_extension_duration
                reason = "目标对白比原镜头显著更长，直接延长可能破坏动作/节奏，需要确认延长方案或回到目标对白改写"
                for plan in local_plans:
                    if int(plan["planned_end_offset_us"]) > source_duration:
                        plan["strategy"] = "HUMAN_REVIEW"
                        plan["overrun_us"] = int(plan["planned_end_offset_us"]) - source_duration
                        plan["reason"] = reason
            else:
                strategy, status, planned_duration = "EXTEND", "READY", planned_extension_duration
                reason = "真实目标语音越过原切点，延长镜头到语音结束并保留自然尾部停顿"
                for plan in local_plans:
                    if int(plan["planned_end_offset_us"]) > source_duration:
                        plan["strategy"] = "EXTEND"
                        plan["overrun_us"] = int(plan["planned_end_offset_us"]) - source_duration
                        plan["reason"] = "目标语音超出原镜头，随镜头一起延长"
        else:
            has_cross_projection = any(
                int((span_meta.get(str(plan["target_dialogue_id"])) or {}).get("projection_count") or 1) > 1
                for plan in dialogue_plans
            )
            # Conservative trim is only safe when the utterance itself belongs to this Shot.
            # Cross-shot source utterances keep the source Shot rhythm and are never compressed
            # by treating the first projection as if it owned the whole line.
            candidate_duration = max_dialogue_end + TRAILING_HOLD_US
            source_line_tail = source_duration
            if len(target_rows) == 1:
                source_line_end_offset = max(0, int(target_rows[0].get("source_end_us") or 0) - int(shot.get("start_us") or 0))
                source_line_tail = max(0, source_duration - source_line_end_offset)
            saving = source_duration - candidate_duration
            min_allowed = max(TRIM_MIN_DURATION_US, int(round(source_duration * TRIM_MIN_SOURCE_RATIO)))
            if (
                not has_cross_projection
                and len(target_rows) == 1
                and source_line_tail <= TRIM_MAX_SOURCE_TAIL_US
                and saving >= TRIM_MIN_SAVING_US
                and candidate_duration >= min_allowed
            ):
                strategy, status, planned_duration = "TRIM", "READY", candidate_duration
                reason = "目标对白明显更短且原对白接近镜头尾部，安全裁掉镜头尾部多余空白"
                for plan in dialogue_plans:
                    plan["strategy"] = "TRIM"
                    plan["reason"] = reason
            else:
                strategy, status, planned_duration = (
                    "CARRY_OVER_REACTION" if cross_carry else "KEEP",
                    "READY",
                    source_duration,
                )
                reason = (
                    "完整对白跨多个源镜头，目标音频只生成一次并按原投影范围连续播放"
                    if has_cross_projection
                    else "真实目标语音可在原镜头内完成，保持原镜头节奏"
                )

    return ({
        "shot_plan_id": f"SHOTPLAN_{hashlib.sha1(shot_key.encode('utf-8')).hexdigest()[:24]}",
        "scene_key": str(shot.get("scene_key") or ""),
        "shot_key": shot_key,
        "source_shot_id": shot.get("source_shot_id"),
        "ordinal": int(shot.get("ordinal") or index + 1),
        "reference_url": shot.get("reference_url"),
        "source_start_us": int(shot.get("start_us") or 0),
        "source_end_us": int(shot.get("end_us") or 0),
        "source_duration_us": source_duration,
        "planned_start_us": 0,
        "planned_end_us": max(1, planned_duration),
        "planned_duration_us": max(1, planned_duration),
        "duration_delta_us": max(1, planned_duration) - source_duration,
        "strategy": strategy,
        "status": status,
        "decision_source": "AUTO",
        "reason": reason,
        "dialogue_plans": dialogue_plans,
    }, deferred_adjustments)


def _apply_deferred_adjustments(
    shot_plans: list[dict[str, Any]],
    adjustments: list[dict[str, Any]],
) -> None:
    if not adjustments:
        return
    by_key = {str(item.get("shot_key") or ""): item for item in shot_plans}
    priority = {"KEEP": 0, "TRIM": 1, "CARRY_OVER_REACTION": 2, "EXTEND": 3, "HUMAN_REVIEW": 4}
    for adjustment in adjustments:
        shot = by_key.get(str(adjustment.get("shot_key") or ""))
        if shot is None:
            raise RemakeTimelineError("跨镜对白时间调整引用了不存在的 Shot")
        required = max(int(shot["planned_duration_us"]), int(adjustment.get("required_duration_us") or 0))
        shot["planned_duration_us"] = required
        candidate_strategy = str(adjustment.get("strategy") or "EXTEND")
        if priority.get(candidate_strategy, 0) >= priority.get(str(shot.get("strategy") or "KEEP"), 0):
            shot["strategy"] = candidate_strategy
            shot["reason"] = str(adjustment.get("reason") or shot.get("reason") or "跨镜对白时间调整")
        # Missing audio remains the nearer blocker; after audio becomes READY regeneration
        # will surface the deferred human timing decision if it is still necessary.
        if shot.get("status") != "WAITING_AUDIO" and adjustment.get("status") == "REVIEW":
            shot["status"] = "REVIEW"


def _reflow_shot_plans(shot_plans: list[dict[str, Any]]) -> None:
    cursor = 0
    for shot in shot_plans:
        shot["planned_start_us"] = cursor
        shot["planned_end_us"] = cursor + int(shot["planned_duration_us"])
        shot["duration_delta_us"] = int(shot["planned_duration_us"]) - int(shot["source_duration_us"])
        for dialogue in shot.get("dialogue_plans") or []:
            dialogue["planned_start_us"] = cursor + int(dialogue["planned_start_offset_us"])
            dialogue["planned_end_us"] = cursor + int(dialogue["planned_end_offset_us"])
        cursor = shot["planned_end_us"]


def _episode_payload(
    *,
    row_id: str,
    project_id: str,
    episode: Mapping[str, Any],
    source_fingerprint: str,
    target_dialogue_fingerprint: str,
    dialogue_rows: list[Mapping[str, Any]],
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, Any]:
    shots = _source_shot_rows(episode)
    by_shot = _target_dialogues_by_shot(dialogue_rows, episode=episode, shots=shots)
    shot_plans: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    for index in range(len(shots)):
        plan, deferred = _auto_shot_plan(shots, index, target_dialogues_by_shot=by_shot)
        shot_plans.append(plan)
        adjustments.extend(deferred)
    _apply_deferred_adjustments(shot_plans, adjustments)
    _reflow_shot_plans(shot_plans)
    source_duration = sum(int(item["source_duration_us"]) for item in shot_plans)
    planned_duration = sum(int(item["planned_duration_us"]) for item in shot_plans)
    reviews = sum(item["status"] == "REVIEW" for item in shot_plans)
    waiting = sum(item["status"] == "WAITING_AUDIO" for item in shot_plans)
    status = "REVIEW" if reviews else "WAITING_AUDIO" if waiting else "READY"
    return RemakeEpisodeTimelineV1.model_validate({
        "schema_version": "remake-timeline-v1",
        "id": row_id,
        "project_id": project_id,
        "episode_id": str(episode.get("episode_id") or ""),
        "source_fingerprint": source_fingerprint,
        "target_dialogue_fingerprint": target_dialogue_fingerprint,
        "status": status,
        "source_duration_us": source_duration,
        "planned_duration_us": planned_duration,
        "duration_delta_us": planned_duration - source_duration,
        "shot_count": len(shot_plans),
        "review_count": reviews,
        "waiting_audio_count": waiting,
        "shot_plans": shot_plans,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }).model_dump(mode="json")


def generate_remake_timeline_v1(project_id: str) -> dict[str, Any]:
    source = load_project_source_drama_snapshot_v1(project_id)
    validate_target_dialogue_dependencies_v1(project_id)
    dialogue_bundle = get_target_dialogue_v1(project_id)
    dialogue_rows = list(dialogue_bundle.get("dialogues") or [])
    dialogue_fingerprint = target_dialogue_fingerprint_v1(dialogue_rows)
    source_fingerprint = str(source["source_fingerprint"])
    dialogues_by_episode: dict[str, list[Mapping[str, Any]]] = {}
    for item in dialogue_rows:
        dialogues_by_episode.setdefault(str(item.get("episode_id") or ""), []).append(item)

    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        active_episode_ids = {str(item.get("episode_id") or "") for item in source.get("episodes") or []}
        for stale in session.scalars(select(RemakeTimeline).where(RemakeTimeline.project_id == project_id)).all():
            if stale.episode_id not in active_episode_ids:
                session.delete(stale)
        session.commit()

    episode_payloads: list[dict[str, Any]] = []
    active_issue_keys: set[str] = set()
    for episode in source.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        episode_id = str(episode.get("episode_id") or "")
        now = utcnow()
        with get_session() as session:
            row = session.scalar(select(RemakeTimeline).where(
                RemakeTimeline.project_id == project_id,
                RemakeTimeline.episode_id == episode_id,
            ))
            if row is None:
                row = RemakeTimeline(
                    id=new_id("REMAKETIMELINE"),
                    project_id=project_id,
                    episode_id=episode_id,
                    source_fingerprint=source_fingerprint,
                    target_dialogue_fingerprint=dialogue_fingerprint,
                    status="WAITING_AUDIO",
                    plan_json="{}",
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            row_id, created_at = row.id, row.created_at

        payload = _episode_payload(
            row_id=row_id,
            project_id=project_id,
            episode=episode,
            source_fingerprint=source_fingerprint,
            target_dialogue_fingerprint=dialogue_fingerprint,
            dialogue_rows=dialogues_by_episode.get(episode_id, []),
            created_at=created_at,
            updated_at=now,
        )
        with get_session() as session:
            row = session.get(RemakeTimeline, row_id)
            if row is None:
                raise RemakeTimelineError("时间轴持久化记录消失")
            row.source_fingerprint = source_fingerprint
            row.target_dialogue_fingerprint = dialogue_fingerprint
            row.status = str(payload["status"])
            row.plan_json = json.dumps(payload, ensure_ascii=False)
            row.updated_at = now
            session.commit()

        for shot_plan in payload["shot_plans"]:
            issue_key = _timing_issue_key(episode_id, str(shot_plan["shot_key"]))
            if shot_plan["status"] == "REVIEW":
                active_issue_keys.add(issue_key)
                upsert_review_issue(
                    project_id=project_id,
                    episode_id=episode_id,
                    shot_id=shot_plan.get("source_shot_id"),
                    source_key=issue_key,
                    issue_type="DIALOGUE_TIMING",
                    severity="BLOCKING",
                    reason=str(shot_plan["reason"]),
                    ai_suggestion={
                        "recommended_strategy": "EXTEND",
                        "recommended_duration_us": shot_plan["planned_duration_us"],
                        "source_duration_us": shot_plan["source_duration_us"],
                        "duration_delta_us": shot_plan["duration_delta_us"],
                    },
                    editable_payload=shot_plan,
                )
            else:
                _resolve_issue(project_id, issue_key, "当前目标语音已可自动形成合理镜头时长")
        episode_payloads.append(payload)

    _resolve_stale_timing_issues(project_id, active_issue_keys)
    review_count = sum(int(item["review_count"]) for item in episode_payloads)
    waiting_count = sum(int(item["waiting_audio_count"]) for item in episode_payloads)
    status = "REVIEW" if review_count else "WAITING_AUDIO" if waiting_count else "READY"
    return RemakeProjectTimelineV1.model_validate({
        "schema_version": "remake-project-timeline-v1",
        "project_id": project_id,
        "source_fingerprint": source_fingerprint,
        "target_dialogue_fingerprint": dialogue_fingerprint,
        "status": status,
        "episode_count": len(episode_payloads),
        "review_count": review_count,
        "waiting_audio_count": waiting_count,
        "episodes": episode_payloads,
    }).model_dump(mode="json")


def _load_persisted_episode(row: RemakeTimeline) -> dict[str, Any]:
    try:
        payload = json.loads(row.plan_json)
    except json.JSONDecodeError as exc:
        raise RemakeTimelineError("RemakeTimeline plan_json 已损坏") from exc
    return RemakeEpisodeTimelineV1.model_validate(payload).model_dump(mode="json")


def get_remake_timeline_v1(project_id: str) -> dict[str, Any]:
    source = load_project_source_drama_snapshot_v1(project_id)
    validate_target_dialogue_dependencies_v1(project_id)
    dialogue = get_target_dialogue_v1(project_id)
    dialogue_fingerprint = target_dialogue_fingerprint_v1(list(dialogue.get("dialogues") or []))
    source_fingerprint = str(source["source_fingerprint"])
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        episode_order = {item.id: item.sort_order for item in session.scalars(select(Episode).where(Episode.project_id == project_id)).all()}
        rows = list(session.scalars(select(RemakeTimeline).where(RemakeTimeline.project_id == project_id)).all())
    if len(rows) != len(source.get("episodes") or []):
        raise RemakeTimelineError("当前 SourceDramaSnapshot 尚未生成完整 RemakeTimeline")
    episodes = [_load_persisted_episode(row) for row in rows]
    episodes.sort(key=lambda item: episode_order.get(str(item["episode_id"]), 10**9))
    if any(item["source_fingerprint"] != source_fingerprint for item in episodes):
        raise RemakeTimelineError("RemakeTimeline source fingerprint 已过期")
    if any(item["target_dialogue_fingerprint"] != dialogue_fingerprint for item in episodes):
        raise RemakeTimelineError("RemakeTimeline TargetDialogue 已变化，需要重新规划")
    review_count = sum(int(item["review_count"]) for item in episodes)
    waiting_count = sum(int(item["waiting_audio_count"]) for item in episodes)
    status = "REVIEW" if review_count else "WAITING_AUDIO" if waiting_count else "READY"
    return RemakeProjectTimelineV1.model_validate({
        "schema_version": "remake-project-timeline-v1",
        "project_id": project_id,
        "source_fingerprint": source_fingerprint,
        "target_dialogue_fingerprint": dialogue_fingerprint,
        "status": status,
        "episode_count": len(episodes),
        "review_count": review_count,
        "waiting_audio_count": waiting_count,
        "episodes": episodes,
    }).model_dump(mode="json")


def _validate_manual_carry(shot_plans: list[dict[str, Any]], index: int, carry_key: str, required_end_offset: int) -> None:
    if index + 1 >= len(shot_plans):
        raise ValueError("最后一个镜头不能把对白延续到下一反应镜")
    current, next_shot = shot_plans[index], shot_plans[index + 1]
    if str(next_shot["shot_key"]) != carry_key:
        raise ValueError("当前只支持把对白延续到紧邻的下一镜头")
    if current["scene_key"] != next_shot["scene_key"]:
        raise ValueError("不能把对白跨到另一个 Scene")
    if next_shot.get("dialogue_plans"):
        raise ValueError("下一镜头已经有目标对白，不能作为纯反应镜承接")
    overrun = max(0, required_end_offset - int(current["planned_duration_us"]))
    if overrun > int(next_shot["planned_duration_us"]) - TRAILING_HOLD_US:
        raise ValueError("下一反应镜长度不足以承接当前对白")


def update_remake_shot_timing_v1(
    timeline_id: str,
    shot_plan_id: str,
    *,
    strategy: str,
    planned_duration_us: int,
    carry_over_shot_key: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    strategy = strategy.strip().upper()
    if strategy not in {"KEEP", "TRIM", "EXTEND", "CARRY_OVER_REACTION"}:
        raise ValueError("人工时长策略只支持 KEEP / TRIM / EXTEND / CARRY_OVER_REACTION")
    if planned_duration_us < 400_000:
        raise ValueError("目标镜头时长不能小于 0.4 秒")

    with get_session() as session:
        row = session.get(RemakeTimeline, timeline_id)
        if row is None:
            raise LookupError("RemakeTimeline 不存在")
        payload = _load_persisted_episode(row)
        project_id, episode_id = row.project_id, row.episode_id

    shot_plans = list(payload["shot_plans"])
    index = next((i for i, item in enumerate(shot_plans) if item["shot_plan_id"] == shot_plan_id), -1)
    if index < 0:
        raise LookupError("镜头时间计划不存在")
    shot = shot_plans[index]
    if any(item.get("speech_duration_us") is None for item in shot.get("dialogue_plans") or []):
        raise ValueError("当前镜头仍缺真实目标语音时长，不能人工定稿时间轴")
    required_end_offset = max((int(item["planned_end_offset_us"]) for item in shot.get("dialogue_plans") or []), default=0)
    if strategy == "CARRY_OVER_REACTION":
        if not carry_over_shot_key:
            raise ValueError("CARRY_OVER_REACTION 必须指定下一反应镜")
        _validate_manual_carry(shot_plans, index, carry_over_shot_key, required_end_offset)
    elif shot.get("dialogue_plans") and planned_duration_us < required_end_offset + TRAILING_HOLD_US:
        raise ValueError("目标镜头时长不足以容纳当前真实目标语音和自然尾部停顿")

    shot["strategy"] = strategy
    shot["status"] = "READY"
    shot["decision_source"] = "MANUAL"
    shot["planned_duration_us"] = int(planned_duration_us)
    shot["reason"] = (reason or "用户人工确认镜头时长策略").strip()
    for dialogue in shot.get("dialogue_plans") or []:
        dialogue["strategy"] = strategy
        dialogue["carry_over_shot_key"] = carry_over_shot_key if strategy == "CARRY_OVER_REACTION" and int(dialogue["planned_end_offset_us"]) > planned_duration_us else None
        dialogue["overrun_us"] = max(0, int(dialogue["planned_end_offset_us"]) - planned_duration_us)
        dialogue["reason"] = shot["reason"]
    _reflow_shot_plans(shot_plans)

    # A cross-shot HUMAN_REVIEW lives on the last projection Shot while its dialogue plan is
    # anchored on the first projection Shot. Once the user confirms that last Shot's duration,
    # resolve matching cross-shot dialogue plans whose source utterance ends inside this Shot.
    if strategy in {"KEEP", "EXTEND"}:
        edited_source_start = int(shot["source_start_us"])
        edited_source_end = int(shot["source_end_us"])
        edited_target_end = int(shot["planned_end_us"])
        for origin in shot_plans:
            for dialogue in origin.get("dialogue_plans") or []:
                if dialogue.get("strategy") != "HUMAN_REVIEW":
                    continue
                source_end = int(dialogue.get("source_end_us") or 0)
                if not (edited_source_start < source_end <= edited_source_end):
                    continue
                if int(dialogue.get("planned_end_us") or 0) > edited_target_end:
                    continue
                dialogue["strategy"] = "EXTEND" if strategy == "EXTEND" else "KEEP"
                dialogue["carry_over_shot_key"] = None
                dialogue["reason"] = shot["reason"]

    payload["shot_plans"] = shot_plans
    payload["source_duration_us"] = sum(int(item["source_duration_us"]) for item in shot_plans)
    payload["planned_duration_us"] = sum(int(item["planned_duration_us"]) for item in shot_plans)
    payload["duration_delta_us"] = payload["planned_duration_us"] - payload["source_duration_us"]
    payload["review_count"] = sum(item["status"] == "REVIEW" for item in shot_plans)
    payload["waiting_audio_count"] = sum(item["status"] == "WAITING_AUDIO" for item in shot_plans)
    payload["status"] = "REVIEW" if payload["review_count"] else "WAITING_AUDIO" if payload["waiting_audio_count"] else "READY"
    now = utcnow()
    payload["updated_at"] = now.isoformat()
    validated = RemakeEpisodeTimelineV1.model_validate(payload).model_dump(mode="json")

    with get_session() as session:
        row = session.get(RemakeTimeline, timeline_id)
        if row is None:
            raise LookupError("RemakeTimeline 不存在")
        row.status = str(validated["status"])
        row.plan_json = json.dumps(validated, ensure_ascii=False)
        row.updated_at = now
        session.commit()

    _resolve_issue(project_id, _timing_issue_key(episode_id, str(shot["shot_key"])), "用户已确认镜头时间策略")
    return validated


__all__ = [
    "RemakeTimeline",
    "RemakeTimelineError",
    "generate_remake_timeline_v1",
    "get_remake_timeline_v1",
    "target_dialogue_fingerprint_v1",
    "update_remake_shot_timing_v1",
]
