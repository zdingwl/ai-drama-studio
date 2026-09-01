"""R9 current selected H3 output per GenerationSegment.

GenerationAttempt remains immutable execution history. GenerationSelection is the small current
pointer consumed by downstream continuity/assembly. It is invalidated whenever the authoritative
GenerationSegment input fingerprint changes.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.generation_attempt_v1 import GenerationAttempt
from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.h3_qc_contract_v1 import GenerationSelectionV1
from engine.app.review_issue_v1 import ReviewIssue
from engine.app.studio_v2 import Base, get_session, new_id, utcnow


class GenerationSelectionError(RuntimeError):
    pass


class GenerationSelection(Base):
    __tablename__ = "v2_generation_selections"
    __table_args__ = (
        UniqueConstraint("generation_segment_id", name="uq_v2_generation_selection_segment"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    generation_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_segments.id", ondelete="CASCADE"), index=True)
    segment_input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selected_attempt_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_attempts.id", ondelete="CASCADE"), index=True)
    quality_check_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    selection_source: Mapped[str] = mapped_column(String(24), nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _serialize(row: GenerationSelection) -> dict[str, Any]:
    return GenerationSelectionV1.model_validate({
        "id": row.id,
        "project_id": row.project_id,
        "episode_id": row.episode_id,
        "generation_segment_id": row.generation_segment_id,
        "segment_input_fingerprint": row.segment_input_fingerprint,
        "selected_attempt_id": row.selected_attempt_id,
        "quality_check_id": row.quality_check_id,
        "selection_source": row.selection_source,
        "quality_score": row.quality_score,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }).model_dump(mode="json")


def _current_segments(project_id: str) -> dict[str, dict[str, Any]]:
    plan = get_generation_segments_v1(project_id)
    return {
        str(segment["id"]): dict(segment)
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("id")
    }


def invalidate_stale_generation_selections_v1(project_id: str) -> int:
    current = _current_segments(project_id)
    removed = 0
    with get_session() as session:
        rows = session.scalars(select(GenerationSelection).where(GenerationSelection.project_id == project_id)).all()
        for row in rows:
            segment = current.get(row.generation_segment_id)
            attempt = session.get(GenerationAttempt, row.selected_attempt_id)
            valid = (
                segment is not None
                and str(segment.get("input_fingerprint") or "") == row.segment_input_fingerprint
                and attempt is not None
                and attempt.status == "SUCCEEDED"
                and attempt.segment_input_fingerprint == row.segment_input_fingerprint
                and bool(attempt.output_path)
                and Path(str(attempt.output_path)).is_file()
            )
            if valid:
                continue
            session.delete(row)
            removed += 1
        if removed:
            session.commit()
    return removed


def set_generation_selection_v1(
    attempt_id: str,
    *,
    selection_source: str,
    quality_check_id: str | None = None,
    quality_score: float | None = None,
) -> dict[str, Any]:
    source = selection_source.strip().upper()
    if source not in {"AUTO", "MANUAL"}:
        raise ValueError("selection_source 只支持 AUTO / MANUAL")

    with get_session() as session:
        attempt = session.get(GenerationAttempt, attempt_id)
        if attempt is None:
            raise LookupError("GenerationAttempt 不存在")
        if attempt.status != "SUCCEEDED" or not attempt.output_path:
            raise GenerationSelectionError("只有当前成功的 GenerationAttempt 才能被选中")
        output = Path(attempt.output_path)
        if not output.is_file() or output.stat().st_size <= 0:
            raise GenerationSelectionError("GenerationAttempt 输出文件不存在")
        project_id = attempt.project_id
        segment_id = attempt.generation_segment_id
        fingerprint = attempt.segment_input_fingerprint

    current = _current_segments(project_id).get(segment_id)
    if current is None or str(current.get("input_fingerprint") or "") != fingerprint:
        raise GenerationSelectionError("GenerationAttempt 已因上游变化失效，不能成为当前输出")

    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(GenerationSelection).where(
            GenerationSelection.generation_segment_id == segment_id
        ))
        if row is None:
            row = GenerationSelection(
                id=new_id("GENSELECTION"),
                project_id=project_id,
                episode_id=str(current["episode_id"]),
                generation_segment_id=segment_id,
                segment_input_fingerprint=fingerprint,
                selected_attempt_id=attempt_id,
                quality_check_id=quality_check_id,
                selection_source=source,
                quality_score=quality_score,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.project_id = project_id
            row.episode_id = str(current["episode_id"])
            row.segment_input_fingerprint = fingerprint
            row.selected_attempt_id = attempt_id
            row.quality_check_id = quality_check_id
            row.selection_source = source
            row.quality_score = quality_score
            row.updated_at = now

        issue = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == f"auto:h3-qc:{segment_id}",
            ReviewIssue.status == "OPEN",
        ))
        if issue is not None:
            issue.status = "RESOLVED"
            issue.resolution_json = (
                '{"automatic":true,"reason":"H3 current output selected"}'
                if source == "AUTO"
                else '{"manual":true,"reason":"User selected H3 output"}'
            )
            issue.resolved_at = now
            issue.updated_at = now

        session.commit()
        session.refresh(row)
        return _serialize(row)


def get_generation_selection_v1(project_id: str, segment_id: str) -> dict[str, Any] | None:
    invalidate_stale_generation_selections_v1(project_id)
    with get_session() as session:
        row = session.scalar(select(GenerationSelection).where(
            GenerationSelection.project_id == project_id,
            GenerationSelection.generation_segment_id == segment_id,
        ))
        return _serialize(row) if row else None


def list_generation_selections_v1(project_id: str) -> list[dict[str, Any]]:
    invalidate_stale_generation_selections_v1(project_id)
    with get_session() as session:
        rows = session.scalars(
            select(GenerationSelection)
            .where(GenerationSelection.project_id == project_id)
            .order_by(GenerationSelection.episode_id, GenerationSelection.created_at)
        ).all()
        return [_serialize(row) for row in rows]


def selected_generation_output_v1(project_id: str, segment_id: str) -> Path | None:
    selection = get_generation_selection_v1(project_id, segment_id)
    if selection is None:
        return None
    with get_session() as session:
        attempt = session.get(GenerationAttempt, selection["selected_attempt_id"])
        path = Path(attempt.output_path) if attempt is not None and attempt.output_path else None
    return path if path is not None and path.is_file() and path.stat().st_size > 0 else None


__all__ = [
    "GenerationSelection",
    "GenerationSelectionError",
    "get_generation_selection_v1",
    "invalidate_stale_generation_selections_v1",
    "list_generation_selections_v1",
    "selected_generation_output_v1",
    "set_generation_selection_v1",
]
