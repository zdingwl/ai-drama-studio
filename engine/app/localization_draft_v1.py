"""P7.2 immutable Localization Draft persistence and review workflow.

Authority rules:
- P7.1 source snapshot is immutable and version anchored.
- API edits contain target-side values only; source_text is never writable.
- every edit/status/rebase creates a new immutable revision.
- optimistic base_revision_id prevents lost updates.
- stale source anchors/fingerprint block edit/review/finalize until an explicit rebase.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Iterable, Mapping

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.localization_draft_contract_v1 import (
    LocalizationDraftEditV1,
    LocalizationDraftStatus,
    LocalizationDraftViewV1,
    LocalizationRevisionSummaryV1,
)
from engine.app.localization_source_contract_v1 import LocalizationSourcePackageV1
from engine.app.localization_source_v1 import load_episode_localization_source_v1
from engine.app.studio_v2 import Base, Episode, get_session, new_id, utcnow


class LocalizationDraftError(RuntimeError):
    """Base P7.2 business error."""


class LocalizationDraftConflictError(LocalizationDraftError):
    """Optimistic concurrency or state-machine conflict."""


class LocalizationDraftStaleError(LocalizationDraftError):
    """Draft no longer matches the current P7.1 source."""


class LocalizationRevision(Base):
    __tablename__ = "v2_localization_revisions"
    __table_args__ = (UniqueConstraint("episode_id", "revision", name="uq_v2_localization_revision_episode_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_breakdown_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_shot_revision_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_asset_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    edits_json: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _canonical_source_payload(source: LocalizationSourcePackageV1) -> dict[str, Any]:
    payload = source.model_dump(mode="json")
    # Operational warnings/status must not invalidate otherwise identical localization anchors.
    payload.pop("status", None)
    payload.pop("warnings", None)
    return payload


def localization_source_fingerprint_v1(source: Mapping[str, Any] | LocalizationSourcePackageV1) -> str:
    parsed = source if isinstance(source, LocalizationSourcePackageV1) else LocalizationSourcePackageV1.model_validate(source)
    encoded = json.dumps(
        _canonical_source_payload(parsed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_source(episode_id: str) -> LocalizationSourcePackageV1:
    raw = load_episode_localization_source_v1(episode_id)
    if raw is None:
        raise LocalizationDraftError("当前剧集还没有可用的本土化源资料")
    source = LocalizationSourcePackageV1.model_validate(raw)
    if source.episode_id != episode_id:
        raise LocalizationDraftError("本土化源资料与剧集不一致")
    return source


def _current_revision(session: Any, episode_id: str) -> LocalizationRevision | None:
    return session.scalar(select(LocalizationRevision).where(
        LocalizationRevision.episode_id == episode_id,
        LocalizationRevision.is_current.is_(True),
    ))


def _next_revision(session: Any, episode_id: str) -> int:
    latest = session.scalar(select(func.max(LocalizationRevision.revision)).where(
        LocalizationRevision.episode_id == episode_id,
    ))
    return int(latest or 0) + 1


def _stored_source(revision: LocalizationRevision) -> LocalizationSourcePackageV1:
    try:
        return LocalizationSourcePackageV1.model_validate(json.loads(revision.source_snapshot_json))
    except (json.JSONDecodeError, ValueError) as exc:
        raise LocalizationDraftError("Localization Revision source snapshot 已损坏") from exc


def _stored_edits(revision: LocalizationRevision) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(revision.edits_json)
    except json.JSONDecodeError as exc:
        raise LocalizationDraftError("Localization Revision edits snapshot 已损坏") from exc
    if not isinstance(raw, dict):
        raise LocalizationDraftError("Localization Revision edits snapshot 格式非法")
    result: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise LocalizationDraftError("Localization Revision edit item 格式非法")
        edit = LocalizationDraftEditV1.model_validate({"source_key": key, **value})
        result[key] = edit.model_dump(mode="json", exclude={"source_key"})
    return result


def _source_entry_rows(source: LocalizationSourcePackageV1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scene in source.scenes:
        for shot in scene.shots:
            for item in shot.source_dialogue:
                rows.append({
                    "source_key": item.source_key,
                    "kind": "dialogue",
                    "scene_ordinal": scene.ordinal,
                    "shot_ordinal": shot.ordinal,
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "source_text": item.source_text,
                    "speakers": [person.model_dump(mode="json") for person in item.speakers],
                })
            for item in shot.source_on_screen_text:
                rows.append({
                    "source_key": item.source_key,
                    "kind": "on_screen_text",
                    "scene_ordinal": scene.ordinal,
                    "shot_ordinal": shot.ordinal,
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "source_text": item.source_text,
                    "speakers": [],
                })
    keys = [item["source_key"] for item in rows]
    if len(set(keys)) != len(keys):
        raise LocalizationDraftError("P7.1 source_key 跨剧集包重复")
    return rows


def _blank_edits(source: LocalizationSourcePackageV1) -> dict[str, dict[str, Any]]:
    return {
        row["source_key"]: {
            "decision": "PENDING",
            "translated_text": None,
            "localized_text": None,
            "final_text": None,
            "note": None,
        }
        for row in _source_entry_rows(source)
    }


def _effective_text(source_text: str, edit: Mapping[str, Any]) -> str | None:
    decision = edit.get("decision")
    if decision == "LOCALIZE":
        return str(edit.get("final_text") or "") or None
    if decision == "KEEP_SOURCE":
        return source_text
    return None


def _is_stale(revision: LocalizationRevision, source: LocalizationSourcePackageV1 | None) -> bool:
    if source is None:
        return True
    return revision.source_fingerprint != localization_source_fingerprint_v1(source)


def _serialize_summary(revision: LocalizationRevision) -> dict[str, Any]:
    return LocalizationRevisionSummaryV1(
        id=revision.id,
        episode_id=revision.episode_id,
        revision=revision.revision,
        kind=revision.kind,
        status=revision.status,
        is_current=revision.is_current,
        source_breakdown_run_id=revision.source_breakdown_run_id,
        source_shot_revision_id=revision.source_shot_revision_id,
        source_asset_revision_id=revision.source_asset_revision_id,
        source_fingerprint=revision.source_fingerprint,
        note=revision.note,
        created_at=revision.created_at.isoformat(),
    ).model_dump(mode="json")


def _serialize_view(
    revision: LocalizationRevision,
    *,
    current_source: LocalizationSourcePackageV1 | None,
) -> dict[str, Any]:
    source = _stored_source(revision)
    edits = _stored_edits(revision)
    rows_by_key = {row["source_key"]: row for row in _source_entry_rows(source)}
    warnings = list(source.warnings)
    stale = _is_stale(revision, current_source)
    if stale:
        warnings.append("当前拉片/资产源已变化；此稿件只读，请先重建到最新源版本。")

    missing_edits = sorted(set(rows_by_key) - set(edits))
    unknown_edits = sorted(set(edits) - set(rows_by_key))
    if missing_edits or unknown_edits:
        warnings.append("当前 Localization Revision 的 source_key 快照不完整，请勿继续编辑。")
        stale = True

    scenes: list[dict[str, Any]] = []
    decisions: list[str] = []
    for scene in source.scenes:
        shot_rows: list[dict[str, Any]] = []
        for shot in scene.shots:
            entries: list[dict[str, Any]] = []
            source_items: list[dict[str, Any]] = []
            for item in shot.source_dialogue:
                source_items.append({
                    "source_key": item.source_key,
                    "kind": "dialogue",
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "source_text": item.source_text,
                    "speakers": [person.model_dump(mode="json") for person in item.speakers],
                })
            for item in shot.source_on_screen_text:
                source_items.append({
                    "source_key": item.source_key,
                    "kind": "on_screen_text",
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "source_text": item.source_text,
                    "speakers": [],
                })
            source_items.sort(key=lambda item: (item["start_us"], item["end_us"], item["kind"], item["source_key"]))
            for item in source_items:
                edit = edits.get(item["source_key"]) or {
                    "decision": "PENDING",
                    "translated_text": None,
                    "localized_text": None,
                    "final_text": None,
                    "note": None,
                }
                decisions.append(str(edit["decision"]))
                entries.append({
                    **item,
                    "scene_ordinal": scene.ordinal,
                    "shot_ordinal": shot.ordinal,
                    **edit,
                    "effective_final_text": _effective_text(item["source_text"], edit),
                })
            shot_rows.append({
                "ordinal": shot.ordinal,
                "start_us": shot.start_us,
                "end_us": shot.end_us,
                "reference_url": shot.reference_url,
                "thumbnail_url": shot.thumbnail_url,
                "visual_description": shot.visual_description,
                "people": [person.model_dump(mode="json") for person in shot.people],
                "entries": entries,
            })
        scenes.append({
            "ordinal": scene.ordinal,
            "title": scene.title,
            "story_summary": scene.story_summary,
            "shots": shot_rows,
        })

    progress = {
        "total": len(decisions),
        "pending": sum(item == "PENDING" for item in decisions),
        "localized": sum(item == "LOCALIZE" for item in decisions),
        "keep_source": sum(item == "KEEP_SOURCE" for item in decisions),
        "omitted": sum(item == "OMIT" for item in decisions),
    }
    return LocalizationDraftViewV1(
        revision_id=revision.id,
        revision=revision.revision,
        kind=revision.kind,
        status=revision.status,
        is_current=revision.is_current,
        stale=stale,
        project_id=revision.project_id,
        episode_id=revision.episode_id,
        source_schema_version=revision.source_schema_version,
        source_breakdown_run_id=revision.source_breakdown_run_id,
        source_shot_revision_id=revision.source_shot_revision_id,
        source_asset_revision_id=revision.source_asset_revision_id,
        source_fingerprint=revision.source_fingerprint,
        source_language=source.source_language,
        target_language=source.target_language,
        target_region=source.target_region,
        progress=progress,
        scenes=scenes,
        warnings=list(dict.fromkeys(warnings)),
        note=revision.note,
        created_at=revision.created_at.isoformat(),
    ).model_dump(mode="json")


def _create_revision(
    session: Any,
    *,
    episode: Episode,
    source: LocalizationSourcePackageV1,
    edits: Mapping[str, Mapping[str, Any]],
    kind: str,
    status: LocalizationDraftStatus,
    note: str | None,
) -> LocalizationRevision:
    for previous in session.scalars(select(LocalizationRevision).where(
        LocalizationRevision.episode_id == episode.id,
        LocalizationRevision.is_current.is_(True),
    )).all():
        previous.is_current = False
    revision = LocalizationRevision(
        id=new_id("LOCALREV"),
        project_id=episode.project_id,
        episode_id=episode.id,
        revision=_next_revision(session, episode.id),
        kind=kind,
        status=status,
        is_current=True,
        source_schema_version=source.schema_version,
        source_breakdown_run_id=source.source_breakdown_run_id,
        source_shot_revision_id=source.source_shot_revision_id,
        source_asset_revision_id=source.source_asset_revision_id,
        source_fingerprint=localization_source_fingerprint_v1(source),
        source_snapshot_json=json.dumps(source.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
        edits_json=json.dumps(dict(edits), ensure_ascii=False, sort_keys=True),
        note=note,
    )
    session.add(revision)
    session.flush()
    return revision


def _require_current_source(revision: LocalizationRevision) -> LocalizationSourcePackageV1:
    source = _load_source(revision.episode_id)
    if _is_stale(revision, source):
        raise LocalizationDraftStaleError("本土化源版本已经变化，请先重建草稿")
    return source


def create_localization_draft(episode_id: str, *, note: str | None = None) -> dict[str, Any]:
    source = _load_source(episode_id)
    fingerprint = localization_source_fingerprint_v1(source)
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        current = _current_revision(session, episode_id)
        if current is not None:
            if current.source_fingerprint == fingerprint:
                return _serialize_view(current, current_source=source)
            raise LocalizationDraftStaleError("已有稿件基于旧的拉片/资产版本，请使用重建草稿")
        revision = _create_revision(
            session,
            episode=episode,
            source=source,
            edits=_blank_edits(source),
            kind="CREATE",
            status="DRAFT",
            note=note or "从当前 P7.1 源包创建本土化草稿",
        )
        session.commit()
        return _serialize_view(revision, current_source=source)


def edit_localization_draft(
    episode_id: str,
    *,
    base_revision_id: str,
    entries: Iterable[Mapping[str, Any] | LocalizationDraftEditV1],
    note: str | None = None,
) -> dict[str, Any]:
    parsed = [item if isinstance(item, LocalizationDraftEditV1) else LocalizationDraftEditV1.model_validate(item) for item in entries]
    if not parsed:
        raise LocalizationDraftError("至少提交一条本土化修改")
    keys = [item.source_key for item in parsed]
    if len(set(keys)) != len(keys):
        raise LocalizationDraftError("同一次编辑不允许重复 source_key")

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        current = _current_revision(session, episode_id)
        if current is None:
            raise LocalizationDraftConflictError("当前剧集还没有本土化草稿")
        if current.id != base_revision_id:
            raise LocalizationDraftConflictError("稿件已被更新，请刷新后再编辑")
        if current.status == "FINAL":
            raise LocalizationDraftConflictError("已定稿版本不可直接编辑")
        source = _require_current_source(current)
        source_keys = {row["source_key"] for row in _source_entry_rows(source)}
        if not set(keys).issubset(source_keys):
            raise LocalizationDraftError("提交内容包含不属于当前源版本的 source_key")
        edits = _stored_edits(current)
        for item in parsed:
            edits[item.source_key] = item.model_dump(mode="json", exclude={"source_key"})
        revision = _create_revision(
            session,
            episode=episode,
            source=source,
            edits=edits,
            kind="EDIT",
            status="DRAFT",
            note=note or "人工编辑本土化文本",
        )
        session.commit()
        return _serialize_view(revision, current_source=source)


def set_localization_draft_status(
    episode_id: str,
    *,
    base_revision_id: str,
    status: LocalizationDraftStatus,
    note: str | None = None,
) -> dict[str, Any]:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        current = _current_revision(session, episode_id)
        if current is None:
            raise LocalizationDraftConflictError("当前剧集还没有本土化草稿")
        if current.id != base_revision_id:
            raise LocalizationDraftConflictError("稿件已被更新，请刷新后再操作")
        source = _require_current_source(current)
        if status == current.status:
            return _serialize_view(current, current_source=source)

        transitions = {
            "DRAFT": {"IN_REVIEW"},
            "IN_REVIEW": {"DRAFT", "FINAL"},
            "FINAL": set(),
        }
        if status not in transitions.get(current.status, set()):
            raise LocalizationDraftConflictError(f"不允许从 {current.status} 直接变更为 {status}")
        edits = _stored_edits(current)
        if status in {"IN_REVIEW", "FINAL"}:
            source_keys = {row["source_key"] for row in _source_entry_rows(source)}
            pending = [key for key in source_keys if (edits.get(key) or {}).get("decision") == "PENDING"]
            if pending:
                raise LocalizationDraftConflictError(f"仍有 {len(pending)} 条内容未处理，不能送审/定稿")

        revision = _create_revision(
            session,
            episode=episode,
            source=source,
            edits=edits,
            kind="STATUS",
            status=status,
            note=note or ("送审本土化稿" if status == "IN_REVIEW" else "本土化稿定稿" if status == "FINAL" else "退回继续编辑"),
        )
        session.commit()
        return _serialize_view(revision, current_source=source)


def rebase_localization_draft(episode_id: str, *, note: str | None = None) -> dict[str, Any]:
    source = _load_source(episode_id)
    new_fingerprint = localization_source_fingerprint_v1(source)
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        current = _current_revision(session, episode_id)
        if current is None:
            revision = _create_revision(
                session,
                episode=episode,
                source=source,
                edits=_blank_edits(source),
                kind="CREATE",
                status="DRAFT",
                note=note or "从当前 P7.1 源包创建本土化草稿",
            )
            session.commit()
            return _serialize_view(revision, current_source=source)
        if current.source_fingerprint == new_fingerprint:
            return _serialize_view(current, current_source=source)

        old_source = _stored_source(current)
        old_rows = {row["source_key"]: row for row in _source_entry_rows(old_source)}
        new_rows = {row["source_key"]: row for row in _source_entry_rows(source)}
        old_edits = _stored_edits(current)
        next_edits = _blank_edits(source)
        carried = 0
        for key, new_row in new_rows.items():
            old_row = old_rows.get(key)
            if old_row is None:
                continue
            safe_match = all(old_row.get(field) == new_row.get(field) for field in (
                "kind", "scene_ordinal", "shot_ordinal", "start_us", "end_us", "source_text"
            ))
            if safe_match and key in old_edits:
                next_edits[key] = old_edits[key]
                carried += 1
        revision = _create_revision(
            session,
            episode=episode,
            source=source,
            edits=next_edits,
            kind="REBASE",
            status="DRAFT",
            note=note or f"源版本变化：安全继承 {carried}/{len(new_rows)} 条编辑",
        )
        session.commit()
        return _serialize_view(revision, current_source=source)


def get_current_localization_draft(episode_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        current = _current_revision(session, episode_id)
        if current is None:
            return None
        try:
            source = _load_source(episode_id)
        except Exception:
            source = None
        return _serialize_view(current, current_source=source)


def get_localization_revision(revision_id: str) -> dict[str, Any]:
    with get_session() as session:
        revision = session.get(LocalizationRevision, revision_id)
        if revision is None:
            raise LookupError("Localization Revision 不存在")
        try:
            source = _load_source(revision.episode_id)
        except Exception:
            source = None
        return _serialize_view(revision, current_source=source)


def list_localization_revisions(episode_id: str) -> list[dict[str, Any]]:
    with get_session() as session:
        if session.get(Episode, episode_id) is None:
            raise LookupError("Episode 不存在")
        revisions = list(session.scalars(select(LocalizationRevision).where(
            LocalizationRevision.episode_id == episode_id,
        ).order_by(LocalizationRevision.revision.desc())).all())
        return [_serialize_summary(item) for item in revisions]


__all__ = [
    "LocalizationDraftConflictError",
    "LocalizationDraftError",
    "LocalizationDraftStaleError",
    "LocalizationRevision",
    "create_localization_draft",
    "edit_localization_draft",
    "get_current_localization_draft",
    "get_localization_revision",
    "list_localization_revisions",
    "localization_source_fingerprint_v1",
    "rebase_localization_draft",
    "set_localization_draft_status",
]
