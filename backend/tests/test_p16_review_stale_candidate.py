from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.p16 import review as review_module
from app.p16.schemas import P16ReviewCommand, SelectionReviewStatus


class _FakeSession:
    def __init__(self, candidate):
        self.candidate = candidate
        self.added = []
        self.committed = False

    def get(self, _model, candidate_id):
        return self.candidate if candidate_id == self.candidate.id else None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def refresh(self, _value):
        return None


def _candidate():
    return SimpleNamespace(
        id="candidate-old",
        project_id="project-1",
        target_storyboard_artifact_id="storyboard-3",
        generation_segments_artifact_id="segments-4",
        target_assets_artifact_id="assets-4",
        generation_sequence=1,
        review_status=SelectionReviewStatus.NEEDS_REVIEW.value,
        review_reason=None,
        reviewed_at=None,
    )


def _command(**overrides):
    values = {
        "expected_target_storyboard_artifact_id": "storyboard-3",
        "expected_generation_segments_artifact_id": "segments-4",
        "expected_target_assets_artifact_id": "assets-4",
        "expected_generation_sequence": 1,
        "reason": "Reject the old result and regenerate from current inputs",
    }
    values.update(overrides)
    return P16ReviewCommand(**values)


def test_reject_allows_exact_historical_candidate_after_formal_inputs_advance(monkeypatch) -> None:
    candidate = _candidate()
    db = _FakeSession(candidate)
    monkeypatch.setattr(review_module, "get_project", lambda *_: SimpleNamespace(id="project-1"))
    monkeypatch.setattr(
        review_module,
        "load_inputs",
        lambda *_: (_ for _ in ()).throw(AssertionError("reject must not require CURRENT P16 inputs")),
    )
    monkeypatch.setattr(review_module, "_candidate_read", lambda row: row)

    result = review_module.reject_selection_candidate(
        db,
        project_id="project-1",
        candidate_id="candidate-old",
        command=_command(),
    )

    assert result is candidate
    assert candidate.review_status == SelectionReviewStatus.REJECTED.value
    assert candidate.review_reason == "Reject the old result and regenerate from current inputs"
    assert candidate.reviewed_at is not None
    assert db.committed is True


def test_reject_still_requires_command_to_name_exact_candidate_lineage(monkeypatch) -> None:
    candidate = _candidate()
    db = _FakeSession(candidate)
    monkeypatch.setattr(review_module, "get_project", lambda *_: SimpleNamespace(id="project-1"))

    with pytest.raises(AppError) as exc_info:
        review_module.reject_selection_candidate(
            db,
            project_id="project-1",
            candidate_id="candidate-old",
            command=_command(expected_generation_segments_artifact_id="segments-new"),
        )

    assert exc_info.value.code == "P16_REVIEW_INPUT_CHANGED"
    assert candidate.review_status == SelectionReviewStatus.NEEDS_REVIEW.value
    assert db.committed is False


def test_accept_context_remains_fail_closed_when_current_inputs_advance(monkeypatch) -> None:
    candidate = _candidate()
    db = _FakeSession(candidate)
    monkeypatch.setattr(review_module, "get_project", lambda *_: SimpleNamespace(id="project-1"))
    current_inputs = SimpleNamespace(
        storyboard_artifact=SimpleNamespace(id="storyboard-3"),
        segments_artifact=SimpleNamespace(id="segments-5"),
        assets_artifact=SimpleNamespace(id="assets-5"),
    )
    monkeypatch.setattr(review_module, "load_inputs", lambda *_: current_inputs)

    with pytest.raises(AppError) as exc_info:
        review_module._review_context(db, "project-1", "candidate-old", _command())

    assert exc_info.value.code == "P16_REVIEW_INPUT_CHANGED"
    assert "旧候选不能确认发布" in exc_info.value.message
