from __future__ import annotations

import pytest
from fastapi import HTTPException

from engine.app import breakdown_read_model_routes_v1 as routes
from engine.app.localization_source_v1 import LocalizationSourceError


def _payload() -> dict[str, object]:
    return {
        "schema_version": "localization-source-v1",
        "status": "READY",
        "project_id": "PROJECT1",
        "episode_id": "EP1",
        "source_language": "zh-CN",
        "target_language": "en-US",
        "target_region": "US",
        "source_breakdown_run_id": "RUN1",
        "source_shot_revision_id": "REV1",
        "source_asset_revision_id": None,
        "scene_count": 0,
        "shot_count": 0,
        "source_dialogue_count": 0,
        "source_on_screen_text_count": 0,
        "warnings": [],
        "scenes": [],
    }


def test_localization_source_returns_current_package(monkeypatch) -> None:
    expected = _payload()
    monkeypatch.setattr(
        routes,
        "load_episode_localization_source_v1",
        lambda episode_id: expected if episode_id == "EP1" else None,
    )

    assert routes.api_get_episode_localization_source("EP1") == expected


def test_localization_source_returns_null_without_current_breakdown(monkeypatch) -> None:
    monkeypatch.setattr(routes, "load_episode_localization_source_v1", lambda _episode_id: None)

    assert routes.api_get_episode_localization_source("EP1") is None


def test_localization_source_hides_internal_error_details(monkeypatch) -> None:
    def unsafe(_episode_id: str):
        raise LocalizationSourceError("P* SECRET_INTERNAL mismatch")

    monkeypatch.setattr(routes, "load_episode_localization_source_v1", unsafe)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_localization_source("EP1")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "本土化源资料当前不可用，请先确认拉片和最终资产结果。"
    assert "SECRET_INTERNAL" not in str(exc_info.value.detail)


def test_localization_source_returns_404_for_missing_episode(monkeypatch) -> None:
    def missing(_episode_id: str):
        raise LookupError("internal")

    monkeypatch.setattr(routes, "load_episode_localization_source_v1", missing)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_localization_source("MISSING")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "剧集不存在"


def test_localization_source_endpoint_is_get_only() -> None:
    methods_by_path = {
        route.path: set(route.methods or set())
        for route in routes.router.routes
    }

    assert methods_by_path["/api/episodes/{episode_id}/localization-source"] == {"GET"}
