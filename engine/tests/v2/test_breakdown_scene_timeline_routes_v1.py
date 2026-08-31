from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from engine.app import breakdown_scene_timeline_routes_v1 as routes
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError


def _payload() -> dict[str, Any]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "RUN_1",
        "source_shot_revision_id": "REV_1",
        "episode_id": "EP_1",
        "status": "READY",
        "is_current": True,
        "scene_count": 0,
        "shot_count": 0,
        "warnings": [],
        "scenes": [],
    }


def test_episode_scene_timeline_returns_null_when_no_current_completed_run(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_current_breakdown", lambda _episode_id: None)

    assert routes.api_get_episode_scene_timeline("EP_1") is None


def test_episode_scene_timeline_returns_404_for_missing_episode(monkeypatch) -> None:
    def missing(_episode_id: str):
        raise LookupError("剧集不存在")

    monkeypatch.setattr(routes, "get_current_breakdown", missing)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_scene_timeline("EP_MISSING")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "剧集不存在"


def test_episode_scene_timeline_uses_g25_result_builder(monkeypatch) -> None:
    draft = {"run": {"id": "RUN_1"}}
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(routes, "get_current_breakdown", lambda _episode_id: draft)
    monkeypatch.setattr(
        routes,
        "build_scene_timeline_result_v1",
        lambda value: calls.append(value) or _payload(),
    )

    payload = routes.api_get_episode_scene_timeline("EP_1")

    assert payload == _payload()
    assert calls == [draft]


def test_run_scene_timeline_returns_404_for_missing_run(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_breakdown_run", lambda _run_id: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_run_scene_timeline("RUN_MISSING")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Breakdown Run 不存在"


def test_incomplete_run_is_hidden_behind_safe_409(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_breakdown_run", lambda _run_id: {"run": {"id": "RUN_1"}})

    def unavailable(_draft):
        raise SceneTimelineResultError("PROCESSING internal detail")

    monkeypatch.setattr(routes, "build_scene_timeline_result_v1", unavailable)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_run_scene_timeline("RUN_1")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Scene Timeline 结果当前不可用，请先完成本集拉片。"
    assert "PROCESSING" not in str(exc_info.value.detail)


def test_router_exposes_only_read_scene_timeline_paths() -> None:
    methods_by_path = {
        route.path: set(route.methods or set())
        for route in routes.router.routes
    }

    assert methods_by_path["/api/episodes/{episode_id}/scene-timeline"] == {"GET"}
    assert methods_by_path["/api/breakdown-runs/{run_id}/scene-timeline"] == {"GET"}
