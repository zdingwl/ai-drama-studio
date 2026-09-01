"""R6 Dialogue Timing Engine + persistent RemakeTimeline V1.

The engine consumes current SourceDramaSnapshot + current TargetDialogue facts. It never
changes source Shot boundaries or source ASR. It plans a new target timeline from actual
TTS duration, preferring conservative automatic edits and sending only extreme timing
choices to Review Center.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.remake_timeline_contract_v1 import (
    RemakeEpisodeTimelineV1,
    RemakeProjectTimelineV1,
)
from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Base, Episode, Project, get_session, new_id, utcnow
from engine.app.target_dialogue_pipeline_v1 import validate_target_dialogue_dependencies_v1
from engine.app.target_dialogue_v1 import TargetDialogue, get_target_dialogue_v1


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
    __table_args__ = (
        UniqueConstraint("project_id", "episode_id", name="uq_v2_remake_timeline_episode"),
    )

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


def _target_dialogues_by_shot(dialogues: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for row in dialogues:
        result.setdefault(str(row.get("shot_key") or ""), []).append(row)
    for values in result.values():
        values.sort(key=lambda item: (int(item.get("source_start_us") or 0), str(item.get("source_dialogue_key") or "")))
    return result


def _reaction_carry_candidate(
    shots: list[dict[str, Any]],
    index: int,
    *,
    source_character_id: str | None,
    overrun_us: int,
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
    available = int(next_shot.get("duration_us") or 0) - TRAILING_HOLD_US
    if available < overrun_us:
        return None
    return next_shot


def _dialogue_plans_for_shot(
    shot: Mapping[str, Any],
    target_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], bool, int, str | None]:
    source_start = int(shot.get("start_us") or 0)
    cursor = 0
    plans: list[dict[str, Any]] = []
    waiting_audio = False
    max_end_offset = 0
    sole_source_character_id: str | None = None
    source_characters: set[str] = set()

    for row in target_rows:
        source_line_start = int(row.get("source_start_us") or source_start)
        source_line_end = int(row.get("source_end_us") or source_line_start)
        start_offset = max(0, source_line_start - source_start, cursor)
        duration = int(row.get("speech_duration_us") or 0)
        audio_ready = row.get("status") == "READY" and row.get("audio_status") == "READY" and duration > 0
        if not audio_ready:
            waiting_audio = True
            duration = max(1, source_line_end - source_line_start)
        end_offset = start_offset + duration
        cursor = end_offset + INTER_DIALOGUE_GAP_US
        max_end_offset = max(max_end_offset, end_offset)
        source_character_id = str(row.get("source_character_id") or "") or None
        if source_character_id:
            source_characters.add(source_character_id)
        plans.append({
            "target_dialogue_id": str(row.get("id") or ""),
            "source_dialogue_key": str(row.get("source_dialogue_key") or ""),
            "source_character_id": source_character_id,
            "target_character_id": str(row.get("target_character_id") or "") or None,
            "source_start_us": source_line_start,
            "source_end_us": source_line_end,
            "source_window_us": max(0, source_line_end - source_line_start),
            "speech_duration_us": duration,
            "planned_start_offset_us": start_offset,
            "planned_end_offset_us": end_offset,
            "planned_start_us": 0,
            "planned_end_us": 1,
            "strategy": "KEEP",
            "carry_over_shot_key": None,
            "overrun_us": 0,
            "reason": "目标对白按源对白相对起点进入新时间轴",
        })
    if len(source_characters) == 1:
        sole_source_character_id = next(iter(source_characters))
    return plans, waiting_audio, max_end_offset, sole_source_character_id


def _auto_shot_plan(
    shots: list[dict[str, Any]],
    index: int,
    *,
    target_dialogues_by_shot: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    shot = shots[index]
    shot_key = str(shot.get("shot_key") or "")
    source_duration = max(1, int(shot.get("duration_us") or 0))
    target_rows = list(target_dialogues_by_shot.get(shot_key) or [])
    dialogue_plans, waiting_audio, max_dialogue_end, source_character_id = _dialogue_plans_for_shot(shot, target_rows)

    if not target_rows:
        strategy, status, planned_duration = "KEEP", "READY", source_duration
        reason = "无目标对白，保持原镜头时长"
    elif waiting_audio:
        strategy, status, planned_duration = "KEEP", "WAITING_AUDIO", source_duration
        reason = "目标对白尚缺可用真实音频，暂时保持原时长等待 TTS"
    else:
        required_duration = max(source_duration, max_dialogue_end + TRAILING_HOLD_US)
        overrun = max(0, required_duration - source_duration)
        if overrun > 0:
            carry = _reaction_carry_candidate(
                shots,
                index,
                source_character_id=source_character_id,
                overrun_us=overrun,
                target_dialogues_by_shot=target_dialogues_by_shot,
            )
            if carry is not None:
                strategy, status, planned_duration = "CARRY_OVER_REACTION", "READY", source_duration
                reason = "目标对白略长，自动延续到下一无对白反应镜，当前镜头不做慢放"
                carry_key = str(carry.get("shot_key") or "")
                for plan in dialogue_plans:
                    if plan["planned_end_offset_us"] > source_duration:
                        plan["strategy"] = "CARRY_OVER_REACTION"
                        plan["carry_over_shot_key"] = carry_key
                        plan["overrun_us"] = plan["planned_end_offset_us"] - source_duration
                        plan["reason"] = "对白尾部跨到下一反应镜继续播放"
            elif required_duration / source_duration > EXTREME_DURATION_RATIO and overrun > EXTREME_OVERRUN_US:
                strategy, status, planned_duration = "HUMAN_REVIEW", "REVIEW", required_duration
                reason = "目标对白比原镜头显著更长，直接延长可能破坏动作/节奏，需要确认是否接受延长或改写对白"
                for plan in dialogue_plans:
                    if plan["planned_end_offset_us"] > source_duration:
                        plan["strategy"] = "HUMAN_REVIEW"
                        plan["overrun_us"] = plan["planned_end_offset_us"] - source_duration
                        plan["reason"] = reason
            else:
                strategy, status, planned_duration = "EXTEND", "READY", required_duration
                reason = "目标对白长于原镜头，延长镜头到真实语音结束并保留尾部停顿"
                for plan in dialogue_plans:
                    if plan["planned_end_offset_us"] > source_duration:
                        plan["strategy"] = "EXTEND"
                        plan["overrun_us"] = plan["planned_end_offset_us"] - source_duration
                        plan["reason"] = "目标语音超出原镜头，随镜头一起延长"
        else:
            # Conservative trim: only one line, source dialogue originally ended near Shot tail,
            # and the target speech creates a meaningful but not destructive shortening.
            candidate_duration = max_dialogue_end + TRAILING_HOLD_US
            source_line_tail = source_duration
            if len(target_rows) == 1:
                source_line_tail = max(0, source_duration - max(0, int(target_rows[0].get("source_end_us") or 0) - int(shot.get("start_us") or 0)))
            saving = source_duration - candidate_duration
            min_allowed = max(TRIM_MIN_DURATION_US, int(round(source_duration * TRIM_MIN_SOURCE_RATIO)))
            if (
                len(target_rows) == 1
                and source_line_tail <= TRIM_MAX_SOURCE_TAIL_US
                and saving >= TRIM_MIN_SAVING_US
                and candidate_duration >= min_allowed
            ):
                strategy, status, planned_duration = "TRIM", "READY", candidate_duration
                reason = "目标对白明显更短且原对白接近镜头尾部，安全裁短镜头尾部空白"
                for plan in dialogue_plans:
                    plan["strategy"] = "TRIM"
                    plan["reason"] = reason
            else:
                strategy, status, planned_duration = "KEEP", "READY", source_duration
                reason = "目标对白可在原镜头内自然完成，保持原镜头节奏"

    return {
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
    }


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
    by_shot = _target_dialogues_by_shot(dialogue_rows)
    shot_plans = [
        _auto_shot_plan(shots, index, target_dialogues_by_shot=by_shot)
        for index in range(len(shots))
    ]
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
                session.commit(); session.refresh(row)
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
        episode_order = {
            item.id: item.sort_order
            for item in session.scalars(select(Episode).where(Episode.project_id == project_id)).all()
        }
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
    required_end_offset = max((int(item["planned_end_offset_us"]) for item in shot.get("dialogue_plans") or []), default=0)
    if strategy == "CARRY_OVER_REACTION":
        if not carry_over_shot_key:
            raise ValueError("CARRY_OVER_REACTION 必须指定下一反应镜")
        _validate_manual_carry(shot_plans, index, carry_over_shot_key, required_end_offset)
    elif planned_duration_us < required_end_offset + TRAILING_HOLD_US:
        raise ValueError("目标镜头时长不足以容纳当前真实目标语音")

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
