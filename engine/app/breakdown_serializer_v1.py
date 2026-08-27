"""Breakdown-first Phase P1.4 的只读 Draft Serializer。

职责：
- 读取 BreakdownRun 历史和当前 READY 类 Run；
- 把 P1 匿名 Draft 组织成稳定的 SceneSegment → Shot → Subject/Event/Prop 结构；
- 所有历史媒体链接都锚定 ShotRevisionItem，而不是 Current Shot；
- 对 PROCESSING/FAILED/STALE 历史 Run 也保持只读可查看；
- 安全解析 P1 JSON 文本字段，避免历史坏 JSON 让查询 API 整体崩溃。

边界：
- 纯读取，不创建/更新/删除任何数据库记录；
- 不调用 ensure_current_revision，不因读取而补写 BASELINE Revision；
- 不运行 ASR/OCR/VLM；
- 不写 Final Character/Scene/Prop、Shot Binding 或 AssetRevision；
- 不负责 ShotRevision 改变后的主动 STALE 联动（P1.6）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from engine.app import studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownEvidenceLink,
    BreakdownRun,
    DraftPropHint,
    DraftPropOccurrence,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
    TimelineEvent,
    TimelineEventSubject,
)
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem

READY_STATUSES = {"READY", "READY_WITH_WARNINGS"}


def _json_value(raw: str | None, *, default: Any) -> Any:
    """把数据库 JSON 文本转换为 API 值；坏历史数据保留 raw，不让只读接口崩溃。"""

    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"_invalid_json": True, "_raw": str(raw)}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_revision(revision: ShotRevision | None, *, item_count: int) -> dict[str, Any] | None:
    if revision is None:
        return None
    return {
        "id": revision.id,
        "episode_id": revision.episode_id,
        "revision": revision.revision,
        "kind": revision.kind,
        "is_current": revision.is_current,
        "source_revision_id": revision.source_revision_id,
        "note": revision.note,
        "created_at": _iso(revision.created_at),
        "item_count": item_count,
    }


def _serialize_run_summary(
    run: BreakdownRun,
    *,
    revision: ShotRevision | None,
    revision_item_count: int,
) -> dict[str, Any]:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "episode_id": run.episode_id,
        "source_shot_revision_id": run.source_shot_revision_id,
        "source_shot_revision": _serialize_revision(revision, item_count=revision_item_count),
        "status": run.status,
        "is_current": run.is_current,
        "schema_version": run.schema_version,
        "pipeline_profile": run.pipeline_profile,
        "component_status": _json_value(run.component_status_json, default={}),
        "provider_metadata": _json_value(run.provider_metadata_json, default={}),
        "counts": _json_value(run.counts_json, default={}),
        "warnings": _json_value(run.warning_json, default={}),
        "error_message": run.error_message,
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
    }


def _serialize_revision_item(item: ShotRevisionItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.id,
        "revision_id": item.revision_id,
        "original_shot_id": item.original_shot_id,
        "ordinal": item.ordinal,
        "start_us": item.start_us,
        "end_us": item.end_us,
        "duration_us": item.duration_us,
        "shot_status": item.shot_status,
        "short_description": item.short_description,
        "shot_type": item.shot_type,
        "camera_motion": item.camera_motion,
        "keyframes": _json_value(item.keyframes_json, default=[]),
        "reference_url": f"/api/shot-revision-items/{item.id}/reference" if item.reference_clip_path else None,
        "thumbnail_url": f"/api/shot-revision-items/{item.id}/thumbnail" if item.thumbnail_path else None,
    }


def _serialize_subject(subject: LocalSubject) -> dict[str, Any]:
    return {
        "id": subject.id,
        "run_id": subject.run_id,
        "scene_segment_id": subject.scene_segment_id,
        "ordinal": subject.ordinal,
        "display_label": subject.display_label,
        "role_hint": subject.role_hint,
        "appearance_summary": subject.appearance_summary,
        "appearance": _json_value(subject.appearance_json, default={}),
        "first_seen_us": subject.first_seen_us,
        "last_seen_us": subject.last_seen_us,
        "speaking_state_summary": subject.speaking_state_summary,
        "confidence": subject.confidence,
    }


def _subject_ref(subject: LocalSubject | None, *, local_subject_id: str) -> dict[str, Any]:
    if subject is None:
        return {"id": local_subject_id, "display_label": None, "ordinal": None}
    return {"id": subject.id, "display_label": subject.display_label, "ordinal": subject.ordinal}


def _serialize_subject_presence(
    presence: ShotLocalSubject,
    *,
    subject: LocalSubject | None,
) -> dict[str, Any]:
    return {
        "id": presence.id,
        "run_id": presence.run_id,
        "shot_draft_id": presence.shot_draft_id,
        "local_subject_id": presence.local_subject_id,
        "subject": _subject_ref(subject, local_subject_id=presence.local_subject_id),
        "first_seen_us": presence.first_seen_us,
        "last_seen_us": presence.last_seen_us,
        "screen_position": presence.screen_position,
        "visibility": presence.visibility,
        "speaking_state": presence.speaking_state,
        "activity_summary": presence.activity_summary,
        "confidence": presence.confidence,
        "search_hint": _json_value(presence.search_hint_json, default={}),
    }


def _serialize_event_participant(
    participant: TimelineEventSubject,
    *,
    subject: LocalSubject | None,
) -> dict[str, Any]:
    return {
        "id": participant.id,
        "event_id": participant.event_id,
        "local_subject_id": participant.local_subject_id,
        "subject": _subject_ref(subject, local_subject_id=participant.local_subject_id),
        "role": participant.role,
        "confidence": participant.confidence,
    }


def _serialize_event(
    event: TimelineEvent,
    *,
    participants: list[TimelineEventSubject],
    subject_by_id: dict[str, LocalSubject],
) -> dict[str, Any]:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "shot_draft_id": event.shot_draft_id,
        "ordinal": event.ordinal,
        "event_type": event.event_type,
        "source_start_us": event.source_start_us,
        "source_end_us": event.source_end_us,
        "shot_relative_start_us": event.shot_relative_start_us,
        "shot_relative_end_us": event.shot_relative_end_us,
        "content_text": event.content_text,
        "language": event.language,
        "emotion_hint": event.emotion_hint,
        "speaking_style_hint": event.speaking_style_hint,
        "confidence": event.confidence,
        "origin": event.origin,
        "metadata": _json_value(event.metadata_json, default={}),
        "participants": [
            _serialize_event_participant(item, subject=subject_by_id.get(item.local_subject_id))
            for item in participants
        ],
    }


def _serialize_prop_hint(prop: DraftPropHint) -> dict[str, Any]:
    return {
        "id": prop.id,
        "run_id": prop.run_id,
        "scene_segment_id": prop.scene_segment_id,
        "ordinal": prop.ordinal,
        "label_hint": prop.label_hint,
        "normalized_hint": prop.normalized_hint,
        "importance": prop.importance,
        "narrative_reason": prop.narrative_reason,
        "first_seen_us": prop.first_seen_us,
        "last_seen_us": prop.last_seen_us,
        "confidence": prop.confidence,
        "metadata": _json_value(prop.metadata_json, default={}),
    }


def _prop_ref(prop: DraftPropHint | None, *, prop_hint_id: str) -> dict[str, Any]:
    if prop is None:
        return {"id": prop_hint_id, "label_hint": None, "normalized_hint": None, "importance": None}
    return {
        "id": prop.id,
        "label_hint": prop.label_hint,
        "normalized_hint": prop.normalized_hint,
        "importance": prop.importance,
    }


def _serialize_prop_occurrence(
    occurrence: DraftPropOccurrence,
    *,
    prop: DraftPropHint | None,
) -> dict[str, Any]:
    return {
        "id": occurrence.id,
        "prop_hint_id": occurrence.prop_hint_id,
        "prop_hint": _prop_ref(prop, prop_hint_id=occurrence.prop_hint_id),
        "shot_draft_id": occurrence.shot_draft_id,
        "source_start_us": occurrence.source_start_us,
        "source_end_us": occurrence.source_end_us,
        "screen_position_hint": occurrence.screen_position_hint,
        "interaction_summary": occurrence.interaction_summary,
        "confidence": occurrence.confidence,
        "search_region_hint": _json_value(occurrence.search_region_hint_json, default={}),
    }


def _serialize_shot(
    shot: ShotSemanticDraft,
    *,
    revision_item: ShotRevisionItem | None,
    presences: list[ShotLocalSubject],
    events: list[TimelineEvent],
    occurrences: list[DraftPropOccurrence],
    participants_by_event: dict[str, list[TimelineEventSubject]],
    subject_by_id: dict[str, LocalSubject],
    prop_by_id: dict[str, DraftPropHint],
) -> dict[str, Any]:
    return {
        "id": shot.id,
        "run_id": shot.run_id,
        "scene_segment_id": shot.scene_segment_id,
        "source_shot_revision_item_id": shot.source_shot_revision_item_id,
        "source_shot_id_snapshot": shot.source_shot_id_snapshot,
        "shot_ordinal_snapshot": shot.shot_ordinal_snapshot,
        "source_start_us": shot.source_start_us,
        "source_end_us": shot.source_end_us,
        "summary": shot.summary,
        "visual_description": shot.visual_description,
        "shot_language": shot.shot_language,
        "shot_type_hint": shot.shot_type_hint,
        "camera_motion_hint": shot.camera_motion_hint,
        "narrative_function_hint": shot.narrative_function_hint,
        "confidence": shot.confidence,
        "model_metadata": _json_value(shot.model_metadata_json, default={}),
        "source_shot_revision_item": _serialize_revision_item(revision_item),
        "subjects": [
            _serialize_subject_presence(item, subject=subject_by_id.get(item.local_subject_id))
            for item in presences
        ],
        "events": [
            _serialize_event(
                item,
                participants=participants_by_event.get(item.id, []),
                subject_by_id=subject_by_id,
            )
            for item in events
        ],
        "prop_occurrences": [
            _serialize_prop_occurrence(item, prop=prop_by_id.get(item.prop_hint_id))
            for item in occurrences
        ],
    }


def _serialize_segment(
    segment: SceneSegmentDraft,
    *,
    subjects: list[LocalSubject],
    props: list[DraftPropHint],
    shots: list[ShotSemanticDraft],
    revision_item_by_id: dict[str, ShotRevisionItem],
    presences_by_shot: dict[str, list[ShotLocalSubject]],
    events_by_shot: dict[str, list[TimelineEvent]],
    occurrences_by_shot: dict[str, list[DraftPropOccurrence]],
    participants_by_event: dict[str, list[TimelineEventSubject]],
    subject_by_id: dict[str, LocalSubject],
    prop_by_id: dict[str, DraftPropHint],
) -> dict[str, Any]:
    return {
        "id": segment.id,
        "run_id": segment.run_id,
        "episode_id": segment.episode_id,
        "ordinal": segment.ordinal,
        "source_start_us": segment.source_start_us,
        "source_end_us": segment.source_end_us,
        "location_hint": segment.location_hint,
        "interior_exterior": segment.interior_exterior,
        "time_of_day": segment.time_of_day,
        "scene_function_hint": segment.scene_function_hint,
        "summary": segment.summary,
        "environment_description": segment.environment_description,
        "confidence": segment.confidence,
        "metadata": _json_value(segment.metadata_json, default={}),
        "subjects": [_serialize_subject(item) for item in subjects],
        "prop_hints": [_serialize_prop_hint(item) for item in props],
        "shots": [
            _serialize_shot(
                item,
                revision_item=revision_item_by_id.get(item.source_shot_revision_item_id),
                presences=presences_by_shot.get(item.id, []),
                events=events_by_shot.get(item.id, []),
                occurrences=occurrences_by_shot.get(item.id, []),
                participants_by_event=participants_by_event,
                subject_by_id=subject_by_id,
                prop_by_id=prop_by_id,
            )
            for item in shots
        ],
    }


def _serialize_evidence_link(link: BreakdownEvidenceLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "run_id": link.run_id,
        "owner_type": link.owner_type,
        "owner_id": link.owner_id,
        "source_type": link.source_type,
        "source_id": link.source_id,
        "source_uri": link.source_uri,
        "role": link.role,
        "confidence": link.confidence,
        "metadata": _json_value(link.metadata_json, default={}),
    }


def _revision_map(session: Any, revision_ids: list[str]) -> dict[str, ShotRevision]:
    if not revision_ids:
        return {}
    rows = session.scalars(select(ShotRevision).where(ShotRevision.id.in_(revision_ids))).all()
    return {item.id: item for item in rows}


def _revision_item_counts(session: Any, revision_ids: list[str]) -> dict[str, int]:
    result = {revision_id: 0 for revision_id in revision_ids}
    if not revision_ids:
        return result
    items = session.scalars(
        select(ShotRevisionItem).where(ShotRevisionItem.revision_id.in_(revision_ids))
    ).all()
    for item in items:
        result[item.revision_id] = result.get(item.revision_id, 0) + 1
    return result


def list_breakdown_runs(episode_id: str) -> list[dict[str, Any]]:
    """列出 Episode 的全部 Breakdown Run 历史；纯读取，不自动创建任何 Revision。"""

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")

        runs = list(session.scalars(
            select(BreakdownRun)
            .where(BreakdownRun.episode_id == episode_id)
            .order_by(BreakdownRun.started_at.desc(), BreakdownRun.id.desc())
        ).all())
        revision_ids = list(dict.fromkeys(item.source_shot_revision_id for item in runs))
        revision_by_id = _revision_map(session, revision_ids)
        item_counts = _revision_item_counts(session, revision_ids)
        return [
            _serialize_run_summary(
                item,
                revision=revision_by_id.get(item.source_shot_revision_id),
                revision_item_count=item_counts.get(item.source_shot_revision_id, 0),
            )
            for item in runs
        ]


def get_current_breakdown(episode_id: str) -> dict[str, Any] | None:
    """返回 Episode 当前 READY 类 Breakdown Draft；没有 Current 时返回 None。"""

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")

        run = session.scalar(
            select(BreakdownRun)
            .where(
                BreakdownRun.episode_id == episode_id,
                BreakdownRun.is_current.is_(True),
                BreakdownRun.status.in_(READY_STATUSES),
            )
            .order_by(BreakdownRun.started_at.desc(), BreakdownRun.id.desc())
        )
        if run is None:
            return None
        return _serialize_full_run(session, run)


def get_breakdown_run(run_id: str) -> dict[str, Any] | None:
    """按 Run ID 返回完整结构化 Draft；FAILED/STALE 历史 Run 也允许读取。"""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            return None
        return _serialize_full_run(session, run)


def _serialize_full_run(session: Any, run: BreakdownRun) -> dict[str, Any]:
    revision = session.get(ShotRevision, run.source_shot_revision_id)
    revision_items = list(session.scalars(
        select(ShotRevisionItem)
        .where(ShotRevisionItem.revision_id == run.source_shot_revision_id)
        .order_by(ShotRevisionItem.ordinal, ShotRevisionItem.id)
    ).all())
    revision_item_by_id = {item.id: item for item in revision_items}

    segments = list(session.scalars(
        select(SceneSegmentDraft)
        .where(SceneSegmentDraft.run_id == run.id)
        .order_by(SceneSegmentDraft.ordinal, SceneSegmentDraft.id)
    ).all())
    shots = list(session.scalars(
        select(ShotSemanticDraft)
        .where(ShotSemanticDraft.run_id == run.id)
        .order_by(ShotSemanticDraft.shot_ordinal_snapshot, ShotSemanticDraft.id)
    ).all())
    subjects = list(session.scalars(
        select(LocalSubject)
        .where(LocalSubject.run_id == run.id)
        .order_by(LocalSubject.scene_segment_id, LocalSubject.ordinal, LocalSubject.id)
    ).all())
    presences = list(session.scalars(
        select(ShotLocalSubject)
        .where(ShotLocalSubject.run_id == run.id)
        .order_by(ShotLocalSubject.shot_draft_id, ShotLocalSubject.first_seen_us, ShotLocalSubject.id)
    ).all())
    events = list(session.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.run_id == run.id)
        .order_by(TimelineEvent.shot_draft_id, TimelineEvent.ordinal, TimelineEvent.id)
    ).all())
    props = list(session.scalars(
        select(DraftPropHint)
        .where(DraftPropHint.run_id == run.id)
        .order_by(DraftPropHint.scene_segment_id, DraftPropHint.ordinal, DraftPropHint.id)
    ).all())
    evidence_links = list(session.scalars(
        select(BreakdownEvidenceLink)
        .where(BreakdownEvidenceLink.run_id == run.id)
        .order_by(
            BreakdownEvidenceLink.owner_type,
            BreakdownEvidenceLink.owner_id,
            BreakdownEvidenceLink.id,
        )
    ).all())

    event_ids = [item.id for item in events]
    subject_ids = [item.id for item in subjects]
    participant_clauses = []
    if event_ids:
        participant_clauses.append(TimelineEventSubject.event_id.in_(event_ids))
    if subject_ids:
        participant_clauses.append(TimelineEventSubject.local_subject_id.in_(subject_ids))
    if participant_clauses:
        participants = list(session.scalars(
            select(TimelineEventSubject)
            .where(or_(*participant_clauses))
            .order_by(
                TimelineEventSubject.event_id,
                TimelineEventSubject.role,
                TimelineEventSubject.id,
            )
        ).all())
    else:
        participants = []

    shot_ids = [item.id for item in shots]
    prop_ids = [item.id for item in props]
    occurrence_clauses = []
    if shot_ids:
        occurrence_clauses.append(DraftPropOccurrence.shot_draft_id.in_(shot_ids))
    if prop_ids:
        occurrence_clauses.append(DraftPropOccurrence.prop_hint_id.in_(prop_ids))
    if occurrence_clauses:
        occurrences = list(session.scalars(
            select(DraftPropOccurrence)
            .where(or_(*occurrence_clauses))
            .order_by(
                DraftPropOccurrence.shot_draft_id,
                DraftPropOccurrence.source_start_us,
                DraftPropOccurrence.id,
            )
        ).all())
    else:
        occurrences = []

    segment_by_id = {item.id: item for item in segments}
    shot_by_id = {item.id: item for item in shots}
    subject_by_id = {item.id: item for item in subjects}
    event_by_id = {item.id: item for item in events}
    prop_by_id = {item.id: item for item in props}

    subjects_by_segment: dict[str, list[LocalSubject]] = defaultdict(list)
    for item in subjects:
        subjects_by_segment[item.scene_segment_id].append(item)

    props_by_segment: dict[str, list[DraftPropHint]] = defaultdict(list)
    for item in props:
        props_by_segment[item.scene_segment_id].append(item)

    shots_by_segment: dict[str, list[ShotSemanticDraft]] = defaultdict(list)
    for item in shots:
        shots_by_segment[item.scene_segment_id].append(item)

    presences_by_shot: dict[str, list[ShotLocalSubject]] = defaultdict(list)
    for item in presences:
        presences_by_shot[item.shot_draft_id].append(item)

    events_by_shot: dict[str, list[TimelineEvent]] = defaultdict(list)
    for item in events:
        events_by_shot[item.shot_draft_id].append(item)

    participants_by_event: dict[str, list[TimelineEventSubject]] = defaultdict(list)
    for item in participants:
        participants_by_event[item.event_id].append(item)

    occurrences_by_shot: dict[str, list[DraftPropOccurrence]] = defaultdict(list)
    for item in occurrences:
        occurrences_by_shot[item.shot_draft_id].append(item)

    scene_segments = [
        _serialize_segment(
            item,
            subjects=subjects_by_segment.get(item.id, []),
            props=props_by_segment.get(item.id, []),
            shots=shots_by_segment.get(item.id, []),
            revision_item_by_id=revision_item_by_id,
            presences_by_shot=presences_by_shot,
            events_by_shot=events_by_shot,
            occurrences_by_shot=occurrences_by_shot,
            participants_by_event=participants_by_event,
            subject_by_id=subject_by_id,
            prop_by_id=prop_by_id,
        )
        for item in segments
    ]

    # READY Run 正常情况下以下集合都应为空；PROCESSING/FAILED 或损坏历史数据仍不应被只读 API 静默丢弃。
    unassigned_shots = [item for item in shots if item.scene_segment_id not in segment_by_id]
    unassigned_subjects = [item for item in subjects if item.scene_segment_id not in segment_by_id]
    unassigned_props = [item for item in props if item.scene_segment_id not in segment_by_id]
    unassigned_presences = [
        item for item in presences
        if item.shot_draft_id not in shot_by_id or item.local_subject_id not in subject_by_id
    ]
    unassigned_events = [item for item in events if item.shot_draft_id not in shot_by_id]
    unassigned_participants = [
        item for item in participants
        if item.event_id not in event_by_id or item.local_subject_id not in subject_by_id
    ]
    unassigned_occurrences = [
        item for item in occurrences
        if item.shot_draft_id not in shot_by_id or item.prop_hint_id not in prop_by_id
    ]

    return {
        "run": _serialize_run_summary(
            run,
            revision=revision,
            revision_item_count=len(revision_items),
        ),
        "scene_segments": scene_segments,
        "evidence_links": [_serialize_evidence_link(item) for item in evidence_links],
        "unassigned": {
            "shots": [
                _serialize_shot(
                    item,
                    revision_item=revision_item_by_id.get(item.source_shot_revision_item_id),
                    presences=presences_by_shot.get(item.id, []),
                    events=events_by_shot.get(item.id, []),
                    occurrences=occurrences_by_shot.get(item.id, []),
                    participants_by_event=participants_by_event,
                    subject_by_id=subject_by_id,
                    prop_by_id=prop_by_id,
                )
                for item in unassigned_shots
            ],
            "subjects": [_serialize_subject(item) for item in unassigned_subjects],
            "subject_presences": [
                _serialize_subject_presence(item, subject=subject_by_id.get(item.local_subject_id))
                for item in unassigned_presences
            ],
            "events": [
                _serialize_event(
                    item,
                    participants=participants_by_event.get(item.id, []),
                    subject_by_id=subject_by_id,
                )
                for item in unassigned_events
            ],
            "event_participants": [
                _serialize_event_participant(item, subject=subject_by_id.get(item.local_subject_id))
                for item in unassigned_participants
            ],
            "prop_hints": [_serialize_prop_hint(item) for item in unassigned_props],
            "prop_occurrences": [
                _serialize_prop_occurrence(item, prop=prop_by_id.get(item.prop_hint_id))
                for item in unassigned_occurrences
            ],
        },
    }
