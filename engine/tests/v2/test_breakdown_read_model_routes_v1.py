from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from engine.app import breakdown_read_model_routes_v1 as routes
from engine.app.breakdown_read_model_v1 import BreakdownReadModelError


def _payload() -> dict[str, Any]:
    return {
        "schema_version": "breakdown-read-model-v1",
        "timeline": {
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
        },
        "identity": {
            "asset_revision_id": None,
            "resolved_count": 0,
            "unresolved_count": 0,
            "warnings": [],
            "scenes": [],
        },
    }


def test_episode_read_model_returns_current_composed_payload(monkeypatch) -> None:
    expected = _payload()
    monkeypatch.setattr(
        routes,
        "load_episode_breakdown_read_model_v1",
        lambda episode_id: expected if episode_id == "EP_1" else None,
    )

    assert routes.api_get_episode_breakdown_read_model("EP_1") == expected


def test_episode_read_model_returns_null_when_no_current_breakdown(monkeypatch) -> None:
    monkeypatch.setattr(routes, "load_episode_breakdown_read_model_v1", lambda _episode_id: None)

    assert routes.api_get_episode_breakdown_read_model("EP_1") is None


def test_episode_read_model_returns_404_for_missing_episode(monkeypatch) -> None:
    def missing(_episode_id: str):
        raise LookupError("内部数据库信息不应直接暴露")

    monkeypatch.setattr(routes, "load_episode_breakdown_read_model_v1", missing)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_breakdown_read_model("EP_MISSING")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "剧集不存在"
    assert "数据库" not in str(exc_info.value.detail)


def test_unsafe_composition_is_hidden_behind_user_safe_409(monkeypatch) -> None:
    def unsafe(_episode_id: str):
        raise BreakdownReadModelError("P5 local_subject_id=SECRET_INTERNAL mismatch")

    monkeypatch.setattr(routes, "load_episode_breakdown_read_model_v1", unsafe)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_breakdown_read_model("EP_1")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "拉片阅读结果当前不可用，请先确认本集拉片结果。"
    assert "SECRET_INTERNAL" not in str(exc_info.value.detail)


def test_router_exposes_read_model_as_get_only() -> None:
    methods_by_path = {
        route.path: set(route.methods or set())
        for route in routes.router.routes
    }

    assert methods_by_path["/api/episodes/{episode_id}/breakdown-read-model"] == {"GET"}


def test_main_registers_p6_read_model_router() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "engine" / "app" / "main.py").read_text(encoding="utf-8")

    assert "breakdown_read_model_routes_v1" in source
    assert "app.include_router(breakdown_read_model_router)" in source
