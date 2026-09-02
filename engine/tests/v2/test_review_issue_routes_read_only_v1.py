from __future__ import annotations

import pytest

from engine.app import review_issue_routes_v1 as routes


def test_review_issue_get_is_pure_read(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    def forbidden(*_args, **_kwargs):
        raise AssertionError("GET /review-issues must not run migration or repair writes")

    def fake_list(project_id: str, *, status: str | None = None):
        calls.append((project_id, status))
        return [{"id": "ISSUE_1"}]

    monkeypatch.setattr(routes, "resolve_legacy_character_evidence_issues", forbidden)
    monkeypatch.setattr(routes, "cleanup_incomplete_auto_dialogue_reviews_v1", forbidden)
    monkeypatch.setattr(routes, "_refresh_legacy_speaker_context", forbidden)
    monkeypatch.setattr(routes, "list_review_issues", fake_list)

    result = routes.api_list_review_issues("PROJECT_READ_ONLY", status="OPEN")

    assert result == [{"id": "ISSUE_1"}]
    assert calls == [("PROJECT_READ_ONLY", "OPEN")]


def test_legacy_review_repair_is_explicit_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_character(project_id: str) -> int:
        calls.append(f"character:{project_id}")
        return 2

    def fake_dialogue(project_id: str) -> int:
        calls.append(f"dialogue:{project_id}")
        return 3

    def fake_speaker(project_id: str) -> bool:
        calls.append(f"speaker:{project_id}")
        return True

    def fake_list(project_id: str, *, status: str | None = None):
        calls.append(f"list:{project_id}:{status}")
        return []

    monkeypatch.setattr(routes, "resolve_legacy_character_evidence_issues", fake_character)
    monkeypatch.setattr(routes, "cleanup_incomplete_auto_dialogue_reviews_v1", fake_dialogue)
    monkeypatch.setattr(routes, "_refresh_legacy_speaker_context", fake_speaker)
    monkeypatch.setattr(routes, "list_review_issues", fake_list)

    result = routes.api_repair_legacy_review_issues("PROJECT_REPAIR")

    assert result == {
        "project_id": "PROJECT_REPAIR",
        "character_evidence_resolved": 2,
        "incomplete_dialogue_reviews_removed": 3,
        "speaker_context_refreshed": True,
        "open_issues": [],
    }
    assert calls == [
        "character:PROJECT_REPAIR",
        "dialogue:PROJECT_REPAIR",
        "speaker:PROJECT_REPAIR",
        "list:PROJECT_REPAIR:OPEN",
    ]


def test_review_routes_include_explicit_legacy_repair_endpoint() -> None:
    from engine.app.main import app

    methods_by_path = {
        route.path: set(route.methods or set())
        for route in app.routes
        if hasattr(route, "methods")
    }

    assert methods_by_path["/api/projects/{project_id}/review-issues"] == {"GET"}
    assert "POST" in methods_by_path["/api/projects/{project_id}/review-issues/repair-legacy"]
