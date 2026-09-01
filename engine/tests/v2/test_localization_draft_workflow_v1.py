from __future__ import annotations

import pytest

from engine.app import localization_draft_workflow_v1 as workflow
from engine.app.localization_draft_v1 import LocalizationDraftConflictError


def _view(*, status: str = "DRAFT", stale: bool = False, decision: str = "LOCALIZE", final_text: str | None = None) -> dict[str, object]:
    return {
        "revision_id": "LOCALREV_1",
        "status": status,
        "stale": stale,
        "scenes": [
            {
                "shots": [
                    {
                        "entries": [
                            {
                                "source_key": "S1:H1:D1",
                                "decision": decision,
                                "final_text": final_text,
                            }
                        ]
                    }
                ]
            }
        ],
    }


def test_partial_localize_is_editable_draft_but_not_review_ready(monkeypatch) -> None:
    current = _view(decision="LOCALIZE", final_text=None)
    monkeypatch.setattr(workflow, "get_current_localization_draft", lambda _episode_id: current)
    monkeypatch.setattr(workflow, "edit_localization_draft", lambda *args, **kwargs: {"saved": True})

    result = workflow.edit_localization_draft_safe(
        "EPISODE_1",
        base_revision_id="LOCALREV_1",
        entries=[{
            "source_key": "S1:H1:D1",
            "decision": "LOCALIZE",
            "translated_text": "You finally came.",
            "localized_text": "You made it.",
            "final_text": None,
        }],
    )
    assert result == {"saved": True}

    with pytest.raises(LocalizationDraftConflictError, match="缺少最终文案"):
        workflow.set_localization_draft_status_safe(
            "EPISODE_1",
            base_revision_id="LOCALREV_1",
            status="IN_REVIEW",
        )


def test_review_ready_localize_can_enter_review(monkeypatch) -> None:
    current = _view(decision="LOCALIZE", final_text="You made it.")
    monkeypatch.setattr(workflow, "get_current_localization_draft", lambda _episode_id: current)
    monkeypatch.setattr(workflow, "set_localization_draft_status", lambda *args, **kwargs: {"status": "IN_REVIEW"})

    result = workflow.set_localization_draft_status_safe(
        "EPISODE_1",
        base_revision_id="LOCALREV_1",
        status="IN_REVIEW",
    )
    assert result == {"status": "IN_REVIEW"}


def test_review_draft_cannot_be_patched_without_explicit_return(monkeypatch) -> None:
    current = _view(status="IN_REVIEW", decision="KEEP_SOURCE")
    monkeypatch.setattr(workflow, "get_current_localization_draft", lambda _episode_id: current)

    with pytest.raises(LocalizationDraftConflictError, match="退回修改"):
        workflow.edit_localization_draft_safe(
            "EPISODE_1",
            base_revision_id="LOCALREV_1",
            entries=[{"source_key": "S1:H1:D1", "decision": "KEEP_SOURCE"}],
        )


def test_stale_draft_cannot_write(monkeypatch) -> None:
    current = _view(stale=True, decision="KEEP_SOURCE")
    monkeypatch.setattr(workflow, "get_current_localization_draft", lambda _episode_id: current)

    with pytest.raises(LocalizationDraftConflictError, match="重建草稿"):
        workflow.edit_localization_draft_safe(
            "EPISODE_1",
            base_revision_id="LOCALREV_1",
            entries=[{"source_key": "S1:H1:D1", "decision": "KEEP_SOURCE"}],
        )
