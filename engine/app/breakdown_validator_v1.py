"""Breakdown-first Phase P1.3 的匿名 Draft 一致性 Validator。

职责：
- 在 Breakdown Run 发布 READY 前验证 ShotRevision / Draft 的一一对应；
- 验证 Scene Segment 连续性与时间覆盖；
- 验证 LocalSubject / Event / Prop 不能跨 Run、跨 Segment；
- 验证绝对时间、Shot 相对时间与 confidence 范围；
- 验证 Current READY Run 不能继续解释已经过期的 ShotRevision；
- 返回结构化错误和真实 Draft counts，供 P1.2 lifecycle 发布门槛消费。

边界：
- 不修改任何 Draft 行；
- 不运行 ASR/OCR/VLM；
- 不创建或解析 Final Character/Scene/Prop；
- 不负责 ShotRevision 变化时主动标记 STALE（P1.6）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

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
EVENT_TYPES = {"VISUAL", "ACTION", "DIALOGUE", "OCR", "AUDIO_EVENT"}
EVENT_ROLES = {"ACTOR", "TARGET", "SPEAKER", "LISTENER", "WITNESS", "OTHER"}
EVIDENCE_OWNER_TYPES = {
    "SCENE_SEGMENT": SceneSegmentDraft,
    "SHOT_DRAFT": ShotSemanticDraft,
    "LOCAL_SUBJECT": LocalSubject,
    "TIMELINE_EVENT": TimelineEvent,
    "PROP_HINT": DraftPropHint,
}
FINAL_ASSET_COLUMN_NAMES = {"character_id", "scene_id", "prop_id"}
DRAFT_MODEL_TYPES = (
    SceneSegmentDraft,
    ShotSemanticDraft,
    LocalSubject,
    ShotLocalSubject,
    TimelineEvent,
    TimelineEventSubject,
    DraftPropHint,
    DraftPropOccurrence,
    BreakdownEvidenceLink,
)


@dataclass(frozen=True)
class BreakdownValidationIssue:
    """一个可定位的 Draft Contract 违反项。"""

    code: str
    message: str
    entity_type: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True)
class BreakdownValidationResult:
    """一次 Breakdown Run Validator 的不可变结果。"""

    run_id: str
    errors: tuple[BreakdownValidationIssue, ...]
    warnings: tuple[BreakdownValidationIssue, ...]
    counts: dict[str, int]

    @property
    def passed(self) -> bool:
        return not self.errors

    def error_message(self) -> str:
        if self.passed:
            return ""
        return "; ".join(f"[{item.code}] {item.message}" for item in self.errors)


def _issue(
    issues: list[BreakdownValidationIssue],
    code: str,
    message: str,
    entity: Any | None = None,
) -> None:
    issues.append(BreakdownValidationIssue(
        code=code,
        message=message,
        entity_type=type(entity).__name__ if entity is not None else None,
        entity_id=str(getattr(entity, "id", "")) or None if entity is not None else None,
    ))


def _confidence_ok(value: float | None) -> bool:
    return value is None or 0.0 <= float(value) <= 1.0


def _check_confidences(
    errors: list[BreakdownValidationIssue],
    rows: Iterable[Any],
) -> None:
    for row in rows:
        if hasattr(row, "confidence") and not _confidence_ok(getattr(row, "confidence")):
            _issue(errors, "CONFIDENCE_OUT_OF_RANGE", "confidence 必须在 0..1 或 NULL", row)


def _validate_schema_has_no_final_asset_fk(errors: list[BreakdownValidationIssue]) -> None:
    """P1 Draft 模型本身不允许出现 Final Asset FK 字段。"""

    for model_type in DRAFT_MODEL_TYPES:
        columns = set(model_type.__table__.columns.keys())
        forbidden = sorted(columns & FINAL_ASSET_COLUMN_NAMES)
        if forbidden:
            _issue(
                errors,
                "FINAL_ASSET_FIELD_FORBIDDEN",
                f"{model_type.__name__} 含禁止的 Final Asset 字段：{', '.join(forbidden)}",
            )


def validate_breakdown_run(run_id: str) -> BreakdownValidationResult:
    """读取正式 V2 数据库并验证一个 Breakdown Run，不修改任何数据。"""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        return validate_breakdown_run_in_session(session, run)


def validate_breakdown_run_in_session(session: Any, run: BreakdownRun) -> BreakdownValidationResult:
    """在调用方事务中验证 Run，供 publish gate 避免跨事务竞态。"""

    errors: list[BreakdownValidationIssue] = []
    warnings: list[BreakdownValidationIssue] = []

    revision = session.get(ShotRevision, run.source_shot_revision_id)
    if revision is None:
        _issue(errors, "SOURCE_REVISION_MISSING", "Run 引用的 ShotRevision 不存在", run)
        revision_items: list[ShotRevisionItem] = []
    else:
        if revision.episode_id != run.episode_id:
            _issue(errors, "SOURCE_REVISION_EPISODE_MISMATCH", "Run 的 ShotRevision 不属于同一 Episode", run)
        revision_items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == revision.id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())

    if run.is_current:
        current_revision = session.scalar(
            select(ShotRevision).where(
                ShotRevision.episode_id == run.episode_id,
                ShotRevision.is_current.is_(True),
            )
        )
        if current_revision is None or current_revision.id != run.source_shot_revision_id:
            _issue(errors, "CURRENT_RUN_SOURCE_STALE", "Current Breakdown Run 的 ShotRevision 已不是 Episode Current", run)

    segments = list(session.scalars(
        select(SceneSegmentDraft)
        .where(SceneSegmentDraft.run_id == run.id)
        .order_by(SceneSegmentDraft.ordinal)
    ).all())
    shot_drafts = list(session.scalars(
        select(ShotSemanticDraft)
        .where(ShotSemanticDraft.run_id == run.id)
        .order_by(ShotSemanticDraft.shot_ordinal_snapshot)
    ).all())
    local_subjects = list(session.scalars(
        select(LocalSubject).where(LocalSubject.run_id == run.id)
    ).all())
    shot_subjects = list(session.scalars(
        select(ShotLocalSubject).where(ShotLocalSubject.run_id == run.id)
    ).all())
    events = list(session.scalars(
        select(TimelineEvent).where(TimelineEvent.run_id == run.id)
    ).all())
    prop_hints = list(session.scalars(
        select(DraftPropHint).where(DraftPropHint.run_id == run.id)
    ).all())
    evidence_links = list(session.scalars(
        select(BreakdownEvidenceLink).where(BreakdownEvidenceLink.run_id == run.id)
    ).all())

    item_by_id = {item.id: item for item in revision_items}
    item_index = {item.id: index for index, item in enumerate(revision_items)}
    segment_by_id = {item.id: item for item in segments}
    shot_by_id = {item.id: item for item in shot_drafts}
    local_by_id = {item.id: item for item in local_subjects}
    event_by_id = {item.id: item for item in events}
    prop_by_id = {item.id: item for item in prop_hints}

    # 1/2/3：RevisionItem ↔ ShotDraft 一一对应，且 Shot Draft 只属于本 Run Segment。
    drafts_by_item: dict[str, list[ShotSemanticDraft]] = {}
    for draft in shot_drafts:
        drafts_by_item.setdefault(draft.source_shot_revision_item_id, []).append(draft)
        item = item_by_id.get(draft.source_shot_revision_item_id)
        if item is None:
            _issue(errors, "SHOT_DRAFT_FOREIGN_REVISION_ITEM", "Shot Draft 引用了本 Run ShotRevision 之外的 RevisionItem", draft)
        else:
            if (
                draft.source_shot_id_snapshot != item.original_shot_id
                or draft.shot_ordinal_snapshot != item.ordinal
                or draft.source_start_us != item.start_us
                or draft.source_end_us != item.end_us
            ):
                _issue(errors, "SHOT_DRAFT_SNAPSHOT_MISMATCH", "Shot Draft 的 Shot ID/ordinal/time 快照与 RevisionItem 不一致", draft)
            if draft.source_start_us >= draft.source_end_us:
                _issue(errors, "SHOT_DRAFT_INVALID_RANGE", "Shot Draft 必须满足 source_start_us < source_end_us", draft)

        segment = segment_by_id.get(draft.scene_segment_id)
        if segment is None or segment.run_id != run.id:
            _issue(errors, "SHOT_DRAFT_FOREIGN_SEGMENT", "Shot Draft 必须恰好属于本 Run 的一个 SceneSegmentDraft", draft)

    for item in revision_items:
        matches = drafts_by_item.get(item.id, [])
        if len(matches) != 1:
            _issue(
                errors,
                "SHOT_DRAFT_CARDINALITY",
                f"RevisionItem {item.id} 必须恰好对应一个 ShotSemanticDraft，当前为 {len(matches)}",
                item,
            )

    # 4/5：Segment 只能由连续 Shot 组成，Segment ordinal 必须与时间顺序一致，时间覆盖等于首尾 Shot。
    segment_ranges: list[tuple[int, int, SceneSegmentDraft]] = []
    for segment in segments:
        if segment.episode_id != run.episode_id:
            _issue(errors, "SEGMENT_EPISODE_MISMATCH", "Scene Segment 的 episode_id 与 Run 不一致", segment)
        if segment.source_start_us >= segment.source_end_us:
            _issue(errors, "SEGMENT_INVALID_RANGE", "Scene Segment 必须满足 source_start_us < source_end_us", segment)
        members = [draft for draft in shot_drafts if draft.scene_segment_id == segment.id]
        indices = sorted(item_index[draft.source_shot_revision_item_id] for draft in members if draft.source_shot_revision_item_id in item_index)
        if not members or len(indices) != len(members):
            _issue(errors, "SEGMENT_EMPTY_OR_FOREIGN_SHOT", "Scene Segment 必须包含至少一个且全部属于本 Revision 的 Shot Draft", segment)
            continue
        expected = list(range(indices[0], indices[-1] + 1))
        if indices != expected:
            _issue(errors, "SEGMENT_SHOTS_NOT_CONTIGUOUS", "Scene Segment 的 Shot Draft 必须在 Revision 时间轴上连续", segment)
        ordered_members = sorted(members, key=lambda item: item.shot_ordinal_snapshot)
        if (
            segment.source_start_us != ordered_members[0].source_start_us
            or segment.source_end_us != ordered_members[-1].source_end_us
        ):
            _issue(errors, "SEGMENT_TIME_COVERAGE_MISMATCH", "Scene Segment 时间必须恰好由首尾 Shot Draft 决定", segment)
        segment_ranges.append((indices[0], indices[-1], segment))

    segment_ranges.sort(key=lambda item: item[2].ordinal)
    if segment_ranges:
        expected_start = 0
        for start_index, end_index, segment in segment_ranges:
            if start_index != expected_start:
                _issue(errors, "SEGMENT_ORDER_MISMATCH", "Scene Segment ordinal 必须与连续 Shot 时间顺序一致且不能跳过 Shot", segment)
            expected_start = end_index + 1
        if expected_start != len(revision_items):
            _issue(errors, "SEGMENT_COVERAGE_INCOMPLETE", "Scene Segment 未按顺序完整覆盖本 Run 的全部 Shot Draft")

    # 6：LocalSubject 与 Shot presence 不能跨 Run/跨 Segment。
    for subject in local_subjects:
        segment = segment_by_id.get(subject.scene_segment_id)
        if segment is None or segment.run_id != run.id:
            _issue(errors, "LOCAL_SUBJECT_FOREIGN_SEGMENT", "LocalSubject 必须属于本 Run 的 Scene Segment", subject)
        elif not (segment.source_start_us <= subject.first_seen_us <= subject.last_seen_us <= segment.source_end_us):
            _issue(errors, "LOCAL_SUBJECT_RANGE_OUTSIDE_SEGMENT", "LocalSubject 首末出现时间必须落在所属 Scene Segment 内", subject)

    for presence in shot_subjects:
        shot = shot_by_id.get(presence.shot_draft_id)
        subject = local_by_id.get(presence.local_subject_id)
        if shot is None or subject is None:
            _issue(errors, "SHOT_SUBJECT_CROSS_RUN", "ShotLocalSubject 不能引用另一个 Run 的 Shot Draft 或 LocalSubject", presence)
            continue
        if shot.scene_segment_id != subject.scene_segment_id:
            _issue(errors, "SHOT_SUBJECT_CROSS_SEGMENT", "LocalSubject 只能出现在自己所属 Scene Segment 的 Shot 中", presence)
        if not (shot.source_start_us <= presence.first_seen_us <= presence.last_seen_us <= shot.source_end_us):
            _issue(errors, "SHOT_SUBJECT_RANGE_OUTSIDE_SHOT", "ShotLocalSubject 首末出现时间必须落在 Shot 范围内", presence)

    # 7/8：TimelineEvent 必须在所属 Shot 内，relative/source 时间严格一致。
    for event in events:
        shot = shot_by_id.get(event.shot_draft_id)
        if shot is None:
            _issue(errors, "EVENT_CROSS_RUN_SHOT", "TimelineEvent 不能引用另一个 Run 的 Shot Draft", event)
            continue
        if event.event_type not in EVENT_TYPES:
            _issue(errors, "EVENT_TYPE_INVALID", f"不支持的 event_type：{event.event_type}", event)
        if not (shot.source_start_us <= event.source_start_us < event.source_end_us <= shot.source_end_us):
            _issue(errors, "EVENT_RANGE_OUTSIDE_SHOT", "TimelineEvent 时间必须严格落在所属 Shot 范围内", event)
        if (
            event.shot_relative_start_us != event.source_start_us - shot.source_start_us
            or event.shot_relative_end_us != event.source_end_us - shot.source_start_us
        ):
            _issue(errors, "EVENT_RELATIVE_TIME_MISMATCH", "TimelineEvent relative/source 时间与 Shot start 快照不一致", event)

    event_ids = list(event_by_id)
    local_ids = list(local_by_id)
    if event_ids or local_ids:
        clauses = []
        if event_ids:
            clauses.append(TimelineEventSubject.event_id.in_(event_ids))
        if local_ids:
            clauses.append(TimelineEventSubject.local_subject_id.in_(local_ids))
        event_subjects = list(session.scalars(select(TimelineEventSubject).where(or_(*clauses))).all())
    else:
        event_subjects = []

    for participant in event_subjects:
        event = event_by_id.get(participant.event_id)
        subject = local_by_id.get(participant.local_subject_id)
        if event is None or subject is None:
            _issue(errors, "EVENT_SUBJECT_CROSS_RUN", "TimelineEventSubject 不能连接不同 Breakdown Run", participant)
            continue
        shot = shot_by_id.get(event.shot_draft_id)
        if shot is None or shot.scene_segment_id != subject.scene_segment_id:
            _issue(errors, "EVENT_SUBJECT_CROSS_SEGMENT", "Event participant 必须属于事件 Shot 的 Scene Segment", participant)
        if participant.role not in EVENT_ROLES:
            _issue(errors, "EVENT_SUBJECT_ROLE_INVALID", f"不支持的 participant role：{participant.role}", participant)

    # 9/12：PropOccurrence 只能连接同 Run、同 Segment，时间必须落在 Shot 内。
    for prop in prop_hints:
        segment = segment_by_id.get(prop.scene_segment_id)
        if segment is None or segment.run_id != run.id:
            _issue(errors, "PROP_HINT_FOREIGN_SEGMENT", "DraftPropHint 必须属于本 Run 的 Scene Segment", prop)
        elif not (segment.source_start_us <= prop.first_seen_us <= prop.last_seen_us <= segment.source_end_us):
            _issue(errors, "PROP_HINT_RANGE_OUTSIDE_SEGMENT", "DraftPropHint 首末出现时间必须落在所属 Scene Segment 内", prop)

    prop_ids = list(prop_by_id)
    shot_ids = list(shot_by_id)
    if prop_ids or shot_ids:
        clauses = []
        if prop_ids:
            clauses.append(DraftPropOccurrence.prop_hint_id.in_(prop_ids))
        if shot_ids:
            clauses.append(DraftPropOccurrence.shot_draft_id.in_(shot_ids))
        prop_occurrences = list(session.scalars(select(DraftPropOccurrence).where(or_(*clauses))).all())
    else:
        prop_occurrences = []

    for occurrence in prop_occurrences:
        prop = prop_by_id.get(occurrence.prop_hint_id)
        shot = shot_by_id.get(occurrence.shot_draft_id)
        if prop is None or shot is None:
            _issue(errors, "PROP_OCCURRENCE_CROSS_RUN", "DraftPropOccurrence 不能连接不同 Breakdown Run", occurrence)
            continue
        if prop.scene_segment_id != shot.scene_segment_id:
            _issue(errors, "PROP_OCCURRENCE_CROSS_SEGMENT", "DraftPropOccurrence 的 PropHint 与 Shot 必须属于同一 Scene Segment", occurrence)
        if not (shot.source_start_us <= occurrence.source_start_us < occurrence.source_end_us <= shot.source_end_us):
            _issue(errors, "PROP_OCCURRENCE_RANGE_OUTSIDE_SHOT", "DraftPropOccurrence 时间必须严格落在所属 Shot 范围内", occurrence)

    # 12：EvidenceLink 的 polymorphic owner 也必须真实存在于同 Run。
    for link in evidence_links:
        owner_type = EVIDENCE_OWNER_TYPES.get(link.owner_type)
        if owner_type is None:
            _issue(errors, "EVIDENCE_OWNER_TYPE_INVALID", f"不支持的 Evidence owner_type：{link.owner_type}", link)
            continue
        owner = session.get(owner_type, link.owner_id)
        if owner is None or getattr(owner, "run_id", None) != run.id:
            _issue(errors, "EVIDENCE_OWNER_CROSS_RUN", "EvidenceLink owner 必须存在且属于同一 Breakdown Run", link)

    # 10：Draft schema 不允许 Final Asset FK；13：所有 confidence 必须为 0..1 或 NULL。
    _validate_schema_has_no_final_asset_fk(errors)
    _check_confidences(
        errors,
        [
            *segments,
            *shot_drafts,
            *local_subjects,
            *shot_subjects,
            *events,
            *event_subjects,
            *prop_hints,
            *prop_occurrences,
            *evidence_links,
        ],
    )

    counts = {
        "scene_segment": len(segments),
        "shot": len(shot_drafts),
        "local_subject": len(local_subjects),
        "shot_local_subject": len(shot_subjects),
        "timeline_event": len(events),
        "timeline_event_subject": len(event_subjects),
        "prop_hint": len(prop_hints),
        "prop_occurrence": len(prop_occurrences),
        "evidence_link": len(evidence_links),
    }
    return BreakdownValidationResult(
        run_id=run.id,
        errors=tuple(errors),
        warnings=tuple(warnings),
        counts=counts,
    )
