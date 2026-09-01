"""P7.2 supported write workflow for Localization Draft.

This facade is the only write boundary used by HTTP routes. It keeps the lower-level
append-only revision service small while enforcing product state rules before a new
revision is created.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from engine.app.localization_draft_contract_v1 import LocalizationDraftEditV1, LocalizationDraftStatus
from engine.app.localization_draft_v1 import (
    LocalizationDraftConflictError,
    LocalizationDraftError,
    create_localization_draft,
    edit_localization_draft,
    get_current_localization_draft,
    rebase_localization_draft,
    set_localization_draft_status,
)


def _current_or_conflict(episode_id: str) -> dict[str, Any]:
    current = get_current_localization_draft(episode_id)
    if current is None:
        raise LocalizationDraftConflictError("当前剧集还没有本土化草稿")
    return current


def _entry_rows(view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for scene in view.get("scenes") or []:
        for shot in scene.get("shots") or []:
            rows.extend(shot.get("entries") or [])
    return rows


def _assert_base(view: Mapping[str, Any], base_revision_id: str) -> None:
    if str(view.get("revision_id") or "") != base_revision_id:
        raise LocalizationDraftConflictError("稿件已被更新，请刷新后再操作")
    if bool(view.get("stale")):
        raise LocalizationDraftConflictError("本土化源版本已经变化，请先重建草稿")


def _assert_review_ready(view: Mapping[str, Any]) -> None:
    entries = _entry_rows(view)
    pending = [item for item in entries if item.get("decision") == "PENDING"]
    if pending:
        raise LocalizationDraftConflictError(f"仍有 {len(pending)} 条内容未处理，不能送审/定稿")
    unfinished = [
        item for item in entries
        if item.get("decision") == "LOCALIZE" and not str(item.get("final_text") or "").strip()
    ]
    if unfinished:
        raise LocalizationDraftConflictError(f"仍有 {len(unfinished)} 条本土化内容缺少最终文案，不能送审/定稿")


def create_localization_draft_safe(episode_id: str, *, note: str | None = None) -> dict[str, Any]:
    return create_localization_draft(episode_id, note=note)


def edit_localization_draft_safe(
    episode_id: str,
    *,
    base_revision_id: str,
    entries: Iterable[Mapping[str, Any] | LocalizationDraftEditV1],
    note: str | None = None,
) -> dict[str, Any]:
    current = _current_or_conflict(episode_id)
    _assert_base(current, base_revision_id)
    if current.get("status") != "DRAFT":
        raise LocalizationDraftConflictError("只有 DRAFT 状态可以编辑；待复核稿请先退回修改")
    return edit_localization_draft(
        episode_id,
        base_revision_id=base_revision_id,
        entries=entries,
        note=note,
    )


def set_localization_draft_status_safe(
    episode_id: str,
    *,
    base_revision_id: str,
    status: LocalizationDraftStatus,
    note: str | None = None,
) -> dict[str, Any]:
    current = _current_or_conflict(episode_id)
    _assert_base(current, base_revision_id)
    if status in {"IN_REVIEW", "FINAL"}:
        _assert_review_ready(current)
    return set_localization_draft_status(
        episode_id,
        base_revision_id=base_revision_id,
        status=status,
        note=note,
    )


def rebase_localization_draft_safe(episode_id: str, *, note: str | None = None) -> dict[str, Any]:
    return rebase_localization_draft(episode_id, note=note)


__all__ = [
    "create_localization_draft_safe",
    "edit_localization_draft_safe",
    "rebase_localization_draft_safe",
    "set_localization_draft_status_safe",
]
