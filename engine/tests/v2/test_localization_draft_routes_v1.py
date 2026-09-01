from __future__ import annotations

import pytest
from fastapi import HTTPException

from engine.app import breakdown_read_model_routes_v1 as routes
from engine.app.localization_draft_v1 import LocalizationDraftConflictError, LocalizationDraftStaleError


def _view() -> dict[str, object]:
    return {
        "schema_version": "localization-draft-v1",
        "revision_id": "LOCALREV_1",
        "revision": 1,
        "kind": "CREATE",
        "status": "DRAFT",
        "is_current": True,
        "stale": False,
        "project_id": "PROJECT_1",
        "episode_id": "EPISODE_1",
        "source_schema_version": "localization-source-v1",
        "source_breakdown_run_id": "RUN_1",
        "source_shot_revision_id": "SHOTREV_1",
        "source_asset_revision_id": None,
        "source_fingerprint": "a" * 64,
        "source_language": "zh-CN",
        "target_language": "en-US",
        "target_region": "US",
        "progress": {"total": 0, "pending": 0, "localized": 0, "keep_source": 0, "omitted": 0},
        "scenes": [],
        "warnings": [],
        "note": None,
        "created_at": "2026-09-01T00:00:00+00:00",
    }


def test_create_route_forwards_only_target_side_request(monkeypatch) -> None:
    expected = _view()
    monkeypatch.setattr(routes, "create_localization_draft", lambda episode_id, note=None: expected)

    result = routes.api_create_localization_draft(
        "EPISODE_1",
        routes.LocalizationDraftCreateRequest(note="开始本土化"),
    )
    assert result == expected


def test_edit_route_maps_revision_conflict_to_409(monkeypatch) -> None:
    def conflict(*args, **kwargs):
        raise LocalizationDraftConflictError("稿件已被更新，请刷新后再编辑")

    monkeypatch.setattr(routes, "edit_localization_draft", conflict)
    payload = routes.LocalizationDraftEditRequest(
        base_revision_id="LOCALREV_OLD",
        entries=[{"source_key": "S1:H1:D1", "decision": "KEEP_SOURCE"}],
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.api_edit_localization_draft("EPISODE_1", payload)

    assert exc_info.value.status_code == 409
    assert "刷新" in str(exc_info.value.detail)


def test_rebase_route_maps_stale_business_error_without_internal_details(monkeypatch) -> None:
    def stale(*args, **kwargs):
        raise LocalizationDraftStaleError("本土化源版本已经变化，请先重建草稿")

    monkeypatch.setattr(routes, "rebase_localization_draft", stale)
    with pytest.raises(HTTPException) as exc_info:
        routes.api_rebase_localization_draft("EPISODE_1", routes.LocalizationDraftRebaseRequest())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "本土化源版本已经变化，请先重建草稿"


def test_router_exposes_revisioned_localization_surface() -> None:
    methods_by_path: dict[str, set[str]] = {}
    for route in routes.router.routes:
        methods_by_path.setdefault(route.path, set()).update(route.methods or set())

    assert methods_by_path["/api/episodes/{episode_id}/localization-draft"] == {"GET", "POST", "PATCH"}
    assert methods_by_path["/api/episodes/{episode_id}/localization-draft/status"] == {"POST"}
    assert methods_by_path["/api/episodes/{episode_id}/localization-draft/rebase"] == {"POST"}
    assert methods_by_path["/api/episodes/{episode_id}/localization-revisions"] == {"GET"}
    assert methods_by_path["/api/localization-revisions/{revision_id}"] == {"GET"}
