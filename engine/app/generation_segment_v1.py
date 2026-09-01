"""R7.1 GenerationSegment compiler and persistence.

The compiler consumes only current product-facing truth:
SourceDramaSnapshot + TargetLocalization + TargetDialogue + RemakeTimeline.
It does not call an AI model and never mutates upstream source/target facts.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from typing import Any, Mapping

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.generation_segment_contract_v1 import GenerationSegmentPlanV1, GenerationSegmentV1
from engine.app.remake_timeline_v1 import get_remake_timeline_v1
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Base, Project, get_session, utcnow
from engine.app.target_dialogue_v1 import get_target_dialogue_v1
from engine.app.target_localization_v1 import get_target_localization_v1


H3_MIN_OUTPUT_US = 4_000_000
H3_MAX_OUTPUT_US = 15_000_000
H3_MIN_REF_VIDEO_US = 2_000_000
H3_MAX_REF_VIDEO_US = 15_000_000


class GenerationSegmentError(RuntimeError):
    pass


class GenerationSegment(Base):
    __tablename__ = "v2_generation_segments"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "episode_id",
            "shot_plan_id",
            "segment_index",
            name="uq_v2_generation_segment_shot_index",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    remake_timeline_id: Mapped[str] = mapped_column(ForeignKey("v2_remake_timelines.id", ondelete="CASCADE"), index=True)
    shot_plan_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    shot_key: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    upstream_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    target_end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    target_duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    h3_duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _without_timestamps(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_timestamps(item)
            for key, item in value.items()
            if key not in {"created_at", "updated_at"}
        }
    if isinstance(value, list):
        return [_without_timestamps(item) for item in value]
    return value


def target_localization_fingerprint_v1(bundle: Mapping[str, Any]) -> str:
    return _digest(_without_timestamps({
        "target_language": bundle.get("target_language"),
        "target_region": bundle.get("target_region"),
        "scene_policy": bundle.get("scene_policy"),
        "target_characters": bundle.get("target_characters") or [],
        "scene_mappings": bundle.get("scene_mappings") or [],
    }))


def remake_timeline_fingerprint_v1(bundle: Mapping[str, Any]) -> str:
    return _digest(_without_timestamps({
        "source_fingerprint": bundle.get("source_fingerprint"),
        "target_dialogue_fingerprint": bundle.get("target_dialogue_fingerprint"),
        "episodes": bundle.get("episodes") or [],
    }))


def _upstream_fingerprints(
    source: Mapping[str, Any],
    target_localization: Mapping[str, Any],
    timeline: Mapping[str, Any],
) -> tuple[str, str, str, str, str]:
    source_fp = str(source.get("source_fingerprint") or "")
    dialogue_fp = str(timeline.get("target_dialogue_fingerprint") or "")
    localization_fp = target_localization_fingerprint_v1(target_localization)
    timeline_fp = remake_timeline_fingerprint_v1(timeline)
    upstream_fp = _digest({
        "source_fingerprint": source_fp,
        "target_dialogue_fingerprint": dialogue_fp,
        "target_localization_fingerprint": localization_fp,
        "remake_timeline_fingerprint": timeline_fp,
    })
    return source_fp, dialogue_fp, localization_fp, timeline_fp, upstream_fp


def _h3_duration_us(target_duration_us: int) -> int:
    if target_duration_us <= 0 or target_duration_us > H3_MAX_OUTPUT_US:
        raise ValueError("单个 GenerationSegment 目标时长必须在 0-15 秒内")
    whole_seconds = math.ceil(target_duration_us / 1_000_000)
    whole_seconds = min(15, max(4, whole_seconds))
    return whole_seconds * 1_000_000


def _split_target_windows(start_us: int, duration_us: int) -> list[tuple[int, int]]:
    if duration_us <= 0:
        raise ValueError("目标镜头时长必须大于 0")
    count = max(1, math.ceil(duration_us / H3_MAX_OUTPUT_US))
    windows: list[tuple[int, int]] = []
    for index in range(count):
        offset_start = duration_us * index // count
        offset_end = duration_us * (index + 1) // count
        windows.append((start_us + offset_start, start_us + offset_end))
    return windows


def _segment_id(timeline_id: str, shot_plan_id: str, segment_index: int) -> str:
    digest = hashlib.sha1(f"{timeline_id}:{shot_plan_id}:{segment_index}".encode("utf-8")).hexdigest()
    return f"GENSEG_{digest}"


def _source_shot_index(source: Mapping[str, Any]) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]]:
    result: dict[str, tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = {}
    for episode in source.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, Mapping):
                continue
            for shot in scene.get("shots") or []:
                if not isinstance(shot, Mapping) or not shot.get("shot_key"):
                    continue
                result[str(shot["shot_key"])] = (episode, scene, shot)
    return result


def _scene_mapping_key(scene: Mapping[str, Any]) -> str:
    final_scene = scene.get("final_scene")
    if isinstance(final_scene, Mapping) and final_scene.get("id"):
        return f"ASSET:{final_scene['id']}"
    return str(scene.get("scene_key") or "")


def _visible_source_characters(scene: Mapping[str, Any], shot: Mapping[str, Any]) -> tuple[list[str], int]:
    by_person_key: dict[str, str | None] = {}
    for person in scene.get("people") or []:
        if not isinstance(person, Mapping) or not person.get("person_key"):
            continue
        character = person.get("character")
        source_character_id = str(character.get("id") or "") if isinstance(character, Mapping) else ""
        by_person_key[str(person["person_key"])] = source_character_id or None
    ids: list[str] = []
    unresolved = 0
    for person_key in shot.get("people") or []:
        character_id = by_person_key.get(str(person_key))
        if character_id:
            if character_id not in ids:
                ids.append(character_id)
        else:
            unresolved += 1
    return ids, unresolved


def _reference_plan(
    *,
    reference_url: str | None,
    source_duration_us: int,
    shot_planned_duration_us: int,
    segment_target_start_us: int,
    shot_target_start_us: int,
) -> tuple[str, int | None, int | None]:
    if not reference_url or source_duration_us < H3_MIN_REF_VIDEO_US:
        return "FL2VA", None, None

    target_relative_start = max(0, segment_target_start_us - shot_target_start_us)
    # If target time extends beyond all source action, continue from a generated keyframe
    # instead of replaying the same reference video.
    if target_relative_start >= source_duration_us:
        return "FL2VA", None, None

    if source_duration_us <= H3_MAX_REF_VIDEO_US:
        return "REF2VA", 0, source_duration_us

    ratio = target_relative_start / max(1, shot_planned_duration_us)
    ref_start = int(source_duration_us * ratio)
    ref_start = min(ref_start, max(0, source_duration_us - H3_MIN_REF_VIDEO_US))
    ref_duration = min(H3_MAX_REF_VIDEO_US, source_duration_us - ref_start)
    if ref_duration < H3_MIN_REF_VIDEO_US:
        ref_start = max(0, source_duration_us - H3_MIN_REF_VIDEO_US)
        ref_duration = source_duration_us - ref_start
    return "REF2VA", ref_start, ref_duration


def _dialogue_events(timeline_episode: Mapping[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for shot_plan in timeline_episode.get("shot_plans") or []:
        if not isinstance(shot_plan, Mapping):
            continue
        origin_shot_key = str(shot_plan.get("shot_key") or "")
        for dialogue in shot_plan.get("dialogue_plans") or []:
            if not isinstance(dialogue, Mapping):
                continue
            events.append({**dict(dialogue), "origin_shot_key": origin_shot_key})
    return events


def _segment_dialogues(
    *,
    segment_start_us: int,
    segment_end_us: int,
    current_shot_key: str,
    events: list[dict[str, Any]],
    target_dialogue_by_id: Mapping[str, Mapping[str, Any]],
    target_character_by_id: Mapping[str, Mapping[str, Any]],
    visible_target_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str], bool]:
    rows: list[dict[str, Any]] = []
    review_reasons: list[str] = []
    waiting_audio = False
    for event in events:
        event_start = int(event.get("planned_start_us") or 0)
        event_end = int(event.get("planned_end_us") or 0)
        if event_end <= segment_start_us or event_start >= segment_end_us:
            continue
        dialogue_id = str(event.get("target_dialogue_id") or "")
        target = target_dialogue_by_id.get(dialogue_id)
        if target is None:
            review_reasons.append(f"目标对白 {dialogue_id or 'unknown'} 不存在")
            continue
        target_character_id = str(target.get("target_character_id") or "") or None
        target_character = target_character_by_id.get(target_character_id or "")
        if target.get("status") != "READY" or not target.get("final_text"):
            review_reasons.append(f"对白 {target.get('source_dialogue_key') or dialogue_id} 尚未定稿")
        if target.get("audio_status") != "READY" or not target.get("audio_path"):
            waiting_audio = True
        local_start = max(0, event_start - segment_start_us)
        local_end = min(segment_end_us - segment_start_us, event_end - segment_start_us)
        if local_end <= local_start:
            continue
        origin_shot_key = str(event.get("origin_shot_key") or current_shot_key)
        rows.append({
            "target_dialogue_id": dialogue_id,
            "source_dialogue_key": str(target.get("source_dialogue_key") or ""),
            "origin_shot_key": origin_shot_key,
            "target_character_id": target_character_id,
            "target_character_name": target_character.get("target_name") if target_character else None,
            "final_text": target.get("final_text"),
            "audio_status": str(target.get("audio_status") or "PENDING"),
            "audio_path": target.get("audio_path"),
            "global_start_us": event_start,
            "global_end_us": event_end,
            "segment_start_offset_us": local_start,
            "segment_end_offset_us": local_end,
            "speaker_visible": bool(target_character_id and target_character_id in visible_target_ids),
            "carried_from_previous_shot": origin_shot_key != current_shot_key,
        })
    return rows, review_reasons, waiting_audio


def _load_inputs(project_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = load_project_source_drama_snapshot_v1(project_id)
    target_localization = get_target_localization_v1(project_id)
    target_dialogue = get_target_dialogue_v1(project_id)
    timeline = get_remake_timeline_v1(project_id)
    if str(source.get("source_fingerprint")) != str(target_localization.get("source_fingerprint")):
        raise GenerationSegmentError("TargetLocalization source fingerprint 与当前原片不一致")
    if str(source.get("source_fingerprint")) != str(target_dialogue.get("source_fingerprint")):
        raise GenerationSegmentError("TargetDialogue source fingerprint 与当前原片不一致")
    if str(source.get("source_fingerprint")) != str(timeline.get("source_fingerprint")):
        raise GenerationSegmentError("RemakeTimeline source fingerprint 与当前原片不一致")
    return source, target_localization, target_dialogue, timeline


def _build_plan(
    project_id: str,
    *,
    created_at_by_id: Mapping[str, datetime] | None = None,
) -> dict[str, Any]:
    source, target_localization, target_dialogue, timeline = _load_inputs(project_id)
    source_fp, dialogue_fp, localization_fp, timeline_fp, upstream_fp = _upstream_fingerprints(
        source, target_localization, timeline
    )
    source_shots = _source_shot_index(source)
    target_character_by_source = {
        str(item.get("source_character_id") or ""): item
        for item in target_localization.get("target_characters") or []
        if isinstance(item, Mapping)
    }
    target_character_by_id = {
        str(item.get("id") or ""): item
        for item in target_localization.get("target_characters") or []
        if isinstance(item, Mapping)
    }
    scene_mapping_by_key: dict[str, Mapping[str, Any]] = {}
    for item in target_localization.get("scene_mappings") or []:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("scene_key") or "")
        if key:
            scene_mapping_by_key[key] = item
        source_scene_id = str(item.get("source_scene_id") or "")
        if source_scene_id:
            scene_mapping_by_key[f"ASSET:{source_scene_id}"] = item
    target_dialogue_by_id = {
        str(item.get("id") or ""): item
        for item in target_dialogue.get("dialogues") or []
        if isinstance(item, Mapping)
    }
    created_map = dict(created_at_by_id or {})
    now = utcnow()
    episode_plans: list[dict[str, Any]] = []

    for timeline_episode in timeline.get("episodes") or []:
        if not isinstance(timeline_episode, Mapping):
            continue
        episode_id = str(timeline_episode.get("episode_id") or "")
        timeline_id = str(timeline_episode.get("id") or "")
        events = _dialogue_events(timeline_episode)
        segments: list[dict[str, Any]] = []
        for shot_plan in timeline_episode.get("shot_plans") or []:
            if not isinstance(shot_plan, Mapping):
                continue
            shot_key = str(shot_plan.get("shot_key") or "")
            source_tuple = source_shots.get(shot_key)
            if source_tuple is None:
                raise GenerationSegmentError(f"RemakeTimeline Shot 不存在于 SourceDramaSnapshot：{shot_key}")
            source_episode, source_scene, source_shot = source_tuple
            if str(source_episode.get("episode_id") or "") != episode_id:
                raise GenerationSegmentError(f"GenerationSegment Shot Episode 不一致：{shot_key}")

            source_character_ids, unresolved_people = _visible_source_characters(source_scene, source_shot)
            target_characters: list[dict[str, Any]] = []
            review_reasons: list[str] = []
            if unresolved_people:
                review_reasons.append(f"镜头仍有 {unresolved_people} 个未解析源人物")
            for source_character_id in source_character_ids:
                target_character = target_character_by_source.get(source_character_id)
                if target_character is None:
                    review_reasons.append(f"源人物 {source_character_id} 缺少 TargetCharacter")
                    continue
                if target_character.get("status") != "READY":
                    review_reasons.append(f"目标人物 {target_character.get('target_name') or source_character_id} 尚未确认")
                target_characters.append({
                    "source_character_id": source_character_id,
                    "target_character_id": str(target_character.get("id") or ""),
                    "target_name": str(target_character.get("target_name") or ""),
                    "appearance_profile": str(target_character.get("appearance_profile") or ""),
                    "generation_prompt": str(target_character.get("generation_prompt") or ""),
                    "reference_assets": list(target_character.get("reference_assets") or []),
                })

            mapping = scene_mapping_by_key.get(_scene_mapping_key(source_scene))
            target_scene: dict[str, Any] | None = None
            if mapping is None:
                review_reasons.append("当前源场景缺少 SceneLocalizationMapping")
            elif mapping.get("status") != "READY" or mapping.get("decision") not in {"KEEP", "LOCALIZE"}:
                review_reasons.append("当前目标场景策略尚未确认")
            else:
                target_scene = {
                    "mapping_id": str(mapping.get("id") or ""),
                    "source_scene_id": mapping.get("source_scene_id"),
                    "source_scene_name": mapping.get("source_scene_name"),
                    "decision": str(mapping.get("decision")),
                    "target_label": mapping.get("target_label"),
                    "target_description": mapping.get("target_description"),
                }

            shot_status = str(shot_plan.get("status") or "REVIEW")
            if shot_status == "REVIEW":
                review_reasons.append(str(shot_plan.get("reason") or "目标镜头时间仍需确认"))
            waiting_from_timeline = shot_status == "WAITING_AUDIO"
            reference_url = str(source_shot.get("reference_url") or "") or None
            if reference_url is None:
                review_reasons.append("Source Shot 缺少 Reference Video")

            shot_target_start = int(shot_plan.get("planned_start_us") or 0)
            shot_target_duration = int(shot_plan.get("planned_duration_us") or 0)
            source_duration = int(source_shot.get("duration_us") or shot_plan.get("source_duration_us") or 0)
            windows = _split_target_windows(shot_target_start, shot_target_duration)
            previous_segment_id: str | None = None
            for zero_index, (segment_start, segment_end) in enumerate(windows):
                segment_number = zero_index + 1
                segment_id = _segment_id(timeline_id, str(shot_plan.get("shot_plan_id") or ""), segment_number)
                target_duration = segment_end - segment_start
                h3_duration = _h3_duration_us(target_duration)
                mode, ref_start, ref_duration = _reference_plan(
                    reference_url=reference_url,
                    source_duration_us=source_duration,
                    shot_planned_duration_us=shot_target_duration,
                    segment_target_start_us=segment_start,
                    shot_target_start_us=shot_target_start,
                )
                visible_target_ids = {str(item["target_character_id"]) for item in target_characters}
                dialogue_rows, dialogue_review_reasons, waiting_dialogue_audio = _segment_dialogues(
                    segment_start_us=segment_start,
                    segment_end_us=segment_end,
                    current_shot_key=shot_key,
                    events=events,
                    target_dialogue_by_id=target_dialogue_by_id,
                    target_character_by_id=target_character_by_id,
                    visible_target_ids=visible_target_ids,
                )
                segment_review_reasons = list(dict.fromkeys(review_reasons + dialogue_review_reasons))
                waiting_audio = waiting_from_timeline or waiting_dialogue_audio
                if segment_review_reasons:
                    status = "REVIEW"
                    reason = "；".join(segment_review_reasons)
                elif waiting_audio:
                    status = "WAITING_AUDIO"
                    reason = "目标对白音频尚未全部 READY，GenerationSegment 先保留但禁止提交 H3"
                else:
                    status = "READY"
                    reason = "Source / Target / Dialogue / Timing 事实完整，可进入 H3 Context Compiler"

                input_fingerprint = _digest({
                    "upstream_fingerprint": upstream_fp,
                    "timeline_id": timeline_id,
                    "shot_plan_id": shot_plan.get("shot_plan_id"),
                    "shot_key": shot_key,
                    "segment_index": segment_number,
                    "target_start_us": segment_start,
                    "target_end_us": segment_end,
                    "generation_mode": mode,
                    "reference_clip_start_offset_us": ref_start,
                    "reference_clip_duration_us": ref_duration,
                })
                created_at = created_map.get(segment_id, now)
                payload = GenerationSegmentV1.model_validate({
                    "id": segment_id,
                    "project_id": project_id,
                    "episode_id": episode_id,
                    "remake_timeline_id": timeline_id,
                    "shot_plan_id": str(shot_plan.get("shot_plan_id") or ""),
                    "scene_key": str(shot_plan.get("scene_key") or source_scene.get("scene_key") or ""),
                    "shot_key": shot_key,
                    "source_shot_id": source_shot.get("source_shot_id") or shot_plan.get("source_shot_id"),
                    "shot_ordinal": int(shot_plan.get("ordinal") or source_shot.get("ordinal") or 1),
                    "shot_segment_index": segment_number,
                    "shot_segment_count": len(windows),
                    "source_fingerprint": source_fp,
                    "target_dialogue_fingerprint": dialogue_fp,
                    "target_localization_fingerprint": localization_fp,
                    "remake_timeline_fingerprint": timeline_fp,
                    "upstream_fingerprint": upstream_fp,
                    "input_fingerprint": input_fingerprint,
                    "target_start_us": segment_start,
                    "target_end_us": segment_end,
                    "target_duration_us": target_duration,
                    "h3_duration_us": h3_duration,
                    "post_trim_duration_us": target_duration if h3_duration != target_duration else None,
                    "timing_strategy": str(shot_plan.get("strategy") or "KEEP"),
                    "generation_mode": mode,
                    "reference_url": reference_url,
                    "reference_clip_start_offset_us": ref_start,
                    "reference_clip_duration_us": ref_duration,
                    "continuity_from_segment_id": previous_segment_id if mode == "FL2VA" else None,
                    "status": status,
                    "reason": reason,
                    "visual_description": source_shot.get("visual_description"),
                    "performance": list(source_shot.get("performance") or []),
                    "cinematography": dict(source_shot.get("cinematography") or {}),
                    "observed_props": list(source_shot.get("observed_props") or []),
                    "final_props": [item for item in (source_shot.get("final_props") or []) if isinstance(item, Mapping)],
                    "target_scene": target_scene,
                    "target_characters": target_characters,
                    "dialogues": dialogue_rows,
                    "created_at": created_at.isoformat(),
                    "updated_at": now.isoformat(),
                }).model_dump(mode="json")
                segments.append(payload)
                previous_segment_id = segment_id

        review_count = sum(item["status"] == "REVIEW" for item in segments)
        waiting_count = sum(item["status"] == "WAITING_AUDIO" for item in segments)
        episode_status = "REVIEW" if review_count else "WAITING_AUDIO" if waiting_count else "READY"
        episode_plans.append({
            "episode_id": episode_id,
            "remake_timeline_id": timeline_id,
            "status": episode_status,
            "segment_count": len(segments),
            "review_count": review_count,
            "waiting_audio_count": waiting_count,
            "segments": segments,
        })

    review_count = sum(int(item["review_count"]) for item in episode_plans)
    waiting_count = sum(int(item["waiting_audio_count"]) for item in episode_plans)
    status = "REVIEW" if review_count else "WAITING_AUDIO" if waiting_count else "READY"
    return GenerationSegmentPlanV1.model_validate({
        "schema_version": "generation-segment-plan-v1",
        "project_id": project_id,
        "source_fingerprint": source_fp,
        "target_dialogue_fingerprint": dialogue_fp,
        "target_localization_fingerprint": localization_fp,
        "remake_timeline_fingerprint": timeline_fp,
        "upstream_fingerprint": upstream_fp,
        "status": status,
        "episode_count": len(episode_plans),
        "segment_count": sum(int(item["segment_count"]) for item in episode_plans),
        "review_count": review_count,
        "waiting_audio_count": waiting_count,
        "episodes": episode_plans,
    }).model_dump(mode="json")


def compile_generation_segments_v1(project_id: str) -> dict[str, Any]:
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        current_rows = list(session.scalars(select(GenerationSegment).where(GenerationSegment.project_id == project_id)).all())
        created_map = {row.id: row.created_at for row in current_rows}

    plan = _build_plan(project_id, created_at_by_id=created_map)
    active_ids = {segment["id"] for episode in plan["episodes"] for segment in episode["segments"]}
    now = utcnow()
    with get_session() as session:
        existing = {
            row.id: row
            for row in session.scalars(select(GenerationSegment).where(GenerationSegment.project_id == project_id)).all()
        }
        for row_id, row in existing.items():
            if row_id not in active_ids:
                session.delete(row)
        for episode in plan["episodes"]:
            for segment in episode["segments"]:
                row = existing.get(segment["id"])
                if row is None:
                    row = GenerationSegment(
                        id=segment["id"],
                        project_id=project_id,
                        episode_id=segment["episode_id"],
                        remake_timeline_id=segment["remake_timeline_id"],
                        shot_plan_id=segment["shot_plan_id"],
                        shot_key=segment["shot_key"],
                        segment_index=segment["shot_segment_index"],
                        status=segment["status"],
                        generation_mode=segment["generation_mode"],
                        upstream_fingerprint=segment["upstream_fingerprint"],
                        input_fingerprint=segment["input_fingerprint"],
                        target_start_us=segment["target_start_us"],
                        target_end_us=segment["target_end_us"],
                        target_duration_us=segment["target_duration_us"],
                        h3_duration_us=segment["h3_duration_us"],
                        payload_json="{}",
                        created_at=datetime.fromisoformat(segment["created_at"]),
                        updated_at=now,
                    )
                    session.add(row)
                row.episode_id = segment["episode_id"]
                row.remake_timeline_id = segment["remake_timeline_id"]
                row.shot_plan_id = segment["shot_plan_id"]
                row.shot_key = segment["shot_key"]
                row.segment_index = int(segment["shot_segment_index"])
                row.status = segment["status"]
                row.generation_mode = segment["generation_mode"]
                row.upstream_fingerprint = segment["upstream_fingerprint"]
                row.input_fingerprint = segment["input_fingerprint"]
                row.target_start_us = int(segment["target_start_us"])
                row.target_end_us = int(segment["target_end_us"])
                row.target_duration_us = int(segment["target_duration_us"])
                row.h3_duration_us = int(segment["h3_duration_us"])
                row.payload_json = json.dumps(segment, ensure_ascii=False)
                row.updated_at = now
        session.commit()
    return plan


def _load_segment_payload(row: GenerationSegment) -> dict[str, Any]:
    try:
        raw = json.loads(row.payload_json)
    except json.JSONDecodeError as exc:
        raise GenerationSegmentError(f"GenerationSegment payload 已损坏：{row.id}") from exc
    return GenerationSegmentV1.model_validate(raw).model_dump(mode="json")


def get_generation_segments_v1(project_id: str) -> dict[str, Any]:
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        rows = list(session.scalars(select(GenerationSegment).where(GenerationSegment.project_id == project_id)).all())
        created_map = {row.id: row.created_at for row in rows}
    if not rows:
        raise GenerationSegmentError("当前项目尚未编译 GenerationSegment")

    expected = _build_plan(project_id, created_at_by_id=created_map)
    expected_by_id = {
        segment["id"]: segment
        for episode in expected["episodes"]
        for segment in episode["segments"]
    }
    if {row.id for row in rows} != set(expected_by_id):
        raise GenerationSegmentError("GenerationSegment 数量或拆分方式已过期，请重新编译")
    if any(row.upstream_fingerprint != expected["upstream_fingerprint"] for row in rows):
        raise GenerationSegmentError("GenerationSegment 上游事实已变化，请重新编译")

    persisted_by_episode: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        payload = _load_segment_payload(row)
        expected_segment = expected_by_id[row.id]
        if payload["input_fingerprint"] != expected_segment["input_fingerprint"]:
            raise GenerationSegmentError(f"GenerationSegment 输入已变化：{row.id}")
        persisted_by_episode.setdefault(row.episode_id, []).append(payload)

    episodes: list[dict[str, Any]] = []
    for expected_episode in expected["episodes"]:
        episode_id = expected_episode["episode_id"]
        segments = persisted_by_episode.get(episode_id, [])
        segments.sort(key=lambda item: (int(item["target_start_us"]), int(item["shot_ordinal"]), int(item["shot_segment_index"])))
        review_count = sum(item["status"] == "REVIEW" for item in segments)
        waiting_count = sum(item["status"] == "WAITING_AUDIO" for item in segments)
        episodes.append({
            "episode_id": episode_id,
            "remake_timeline_id": expected_episode["remake_timeline_id"],
            "status": "REVIEW" if review_count else "WAITING_AUDIO" if waiting_count else "READY",
            "segment_count": len(segments),
            "review_count": review_count,
            "waiting_audio_count": waiting_count,
            "segments": segments,
        })
    review_count = sum(int(item["review_count"]) for item in episodes)
    waiting_count = sum(int(item["waiting_audio_count"]) for item in episodes)
    return GenerationSegmentPlanV1.model_validate({
        **{key: expected[key] for key in (
            "schema_version",
            "project_id",
            "source_fingerprint",
            "target_dialogue_fingerprint",
            "target_localization_fingerprint",
            "remake_timeline_fingerprint",
            "upstream_fingerprint",
        )},
        "status": "REVIEW" if review_count else "WAITING_AUDIO" if waiting_count else "READY",
        "episode_count": len(episodes),
        "segment_count": sum(len(item["segments"]) for item in episodes),
        "review_count": review_count,
        "waiting_audio_count": waiting_count,
        "episodes": episodes,
    }).model_dump(mode="json")


__all__ = [
    "GenerationSegment",
    "GenerationSegmentError",
    "compile_generation_segments_v1",
    "get_generation_segments_v1",
    "remake_timeline_fingerprint_v1",
    "target_localization_fingerprint_v1",
]
