"""Read-only GenerationAttempt query service.

This module is the product-facing read boundary for GenerationAttempt.  It computes
STALE as an effective status from the current GenerationSegment fingerprint without
modifying immutable attempt history.  Persisted lifecycle changes remain owned by the
explicit H3 execution/recovery paths in generation_attempt_v1.
"""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import select

from engine.app.generation_attempt_v1 import GenerationAttempt, _serialize
from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.h3_context_contract_v1 import GenerationAttemptProjectSummaryV1
from engine.app.studio_v2 import Project, get_session


def list_generation_attempts_read_only_v1(project_id: str) -> dict[str, Any]:
    """Return effective Attempt state without persisting STALE markers."""

    plan = get_generation_segments_v1(project_id)
    current_segments = {
        str(segment.get("id") or ""): str(segment.get("input_fingerprint") or "")
        for episode in plan.get("episodes") or []
        if isinstance(episode, Mapping)
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("id")
    }

    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        rows = list(
            session.scalars(
                select(GenerationAttempt)
                .where(GenerationAttempt.project_id == project_id)
                .order_by(GenerationAttempt.created_at.asc(), GenerationAttempt.attempt_number.asc())
            ).all()
        )

    attempts: list[dict[str, Any]] = []
    for row in rows:
        payload = _serialize(row)
        current_fingerprint = current_segments.get(row.generation_segment_id)
        if row.status in {"SUCCEEDED", "FAILED"} and (
            not current_fingerprint or current_fingerprint != row.segment_input_fingerprint
        ):
            payload["status"] = "STALE"
        attempts.append(payload)

    return GenerationAttemptProjectSummaryV1.model_validate(
        {
            "schema_version": "generation-attempt-summary-v1",
            "project_id": project_id,
            "attempt_count": len(attempts),
            "succeeded_count": sum(item["status"] == "SUCCEEDED" for item in attempts),
            "running_count": sum(
                item["status"] in {"PLANNED", "SUBMITTED", "RUNNING"} for item in attempts
            ),
            "failed_count": sum(item["status"] == "FAILED" for item in attempts),
            "stale_count": sum(item["status"] == "STALE" for item in attempts),
            "attempts": attempts,
        }
    ).model_dump(mode="json")


__all__ = ["list_generation_attempts_read_only_v1"]
