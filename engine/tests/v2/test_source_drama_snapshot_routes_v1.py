from __future__ import annotations

import pytest
from fastapi import HTTPException

from engine.app import source_drama_snapshot_routes_v1 as routes
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError


EPISODE_PAYLOAD = {
    "schema_version": "source-drama-snapshot-v1",
    "status": "READY",
    "project_id": "PROJECT_1",
    "episode_id": "EP_1",
    "episode_title": "第一集",
    "episode_order": 1,
    "source_language": "zh-CN",
    "source_breakdown_run_id": "BREAKDOWN_1",
    "source_shot_revision_id": "SHOTREV_1",
    "source_asset_revision_id": None,
    "source_fingerprint": "a" * 64,
    "scene_count": 0,
    "shot_count": 0,
    "resolved_character_count": 0,
    "unresolved_person_count": 0,
    "source_dialogue_count": 0,
    "source_on_screen_text_count": 0,
    "warnings": [],
    "scenes": [],
}

PROJECT_PAYLOAD = {
    "schema_version": "source-drama-project-snapshot-v1",
    "status": "READY",
    "project_id": "PROJECT_1",
    "project_name": "测试短剧",
    "source_language": "zh-CN",
    "source_fingerprint": "b" * 64,
    "episode_count": 1,
    "scene_count": 0,
    "shot_count": 0,
    "resolved_character_count": 0,
    "source_dialogue_count": 0,
    "warnings": [],
    "characters": [],
    "episodes": [EPISODE_PAYLOAD],
}


def test_episode_snapshot_route_returns_current_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(routes, "load_episode_source_drama_snapshot_v1", lambda _episode_id: EPISODE_PAYLOAD)
    assert routes.api_get_episode_source_drama_snapshot("EP_1") == EPISODE_PAYLOAD


def test_episode_snapshot_route_fails_closed_when_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(routes, "load_episode_source_drama_snapshot_v1", lambda _episode_id: None)
    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_source_drama_snapshot("EP_1")
    assert exc_info.value.status_code == 409
    assert "SourceDramaSnapshot" in str(exc_info.value.detail)


def test_project_snapshot_route_returns_current_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(routes, "load_project_source_drama_snapshot_v1", lambda _project_id: PROJECT_PAYLOAD)
    assert routes.api_get_project_source_drama_snapshot("PROJECT_1") == PROJECT_PAYLOAD


def test_snapshot_route_hides_internal_composition_detail(monkeypatch) -> None:
    def unsafe(_project_id: str):
        raise SourceDramaSnapshotError("SECRET P5/P6 internal mismatch")

    monkeypatch.setattr(routes, "load_project_source_drama_snapshot_v1", unsafe)
    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_project_source_drama_snapshot("PROJECT_1")

    assert exc_info.value.status_code == 409
    assert "SECRET" not in str(exc_info.value.detail)


def test_snapshot_routes_are_get_only() -> None:
    methods_by_path = {route.path: set(route.methods or set()) for route in routes.router.routes}
    assert methods_by_path["/api/episodes/{episode_id}/source-drama-snapshot"] == {"GET"}
    assert methods_by_path["/api/projects/{project_id}/source-drama-snapshot"] == {"GET"}
