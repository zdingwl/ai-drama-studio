from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from engine.app import breakdown_routes_v1 as routes


def _selection(run_id: str = "RUN_1", episode_id: str = "EP_1") -> SimpleNamespace:
    payload = {
        "run_id": run_id,
        "selection_mode": "episode_id",
        "project_id": "PROJECT_1",
        "episode_id": episode_id,
        "status": "READY",
        "is_current": True,
        "started_at": "2026-08-30T10:00:00+00:00",
        "completed_at": "2026-08-30T10:18:30+00:00",
        "vlm_profile": {
            "production_vlm_profile": "breakdown-p2-vlm-fast-grounded-v1",
            "is_fast_grounded": True,
        },
    }
    return SimpleNamespace(run_id=run_id, as_dict=lambda: dict(payload))


def test_g1_diagnostics_payload_reuses_read_only_selector_snapshot_and_summary(monkeypatch) -> None:
    selection = _selection()
    calls = {}

    def resolve(**kwargs):
        calls["selector"] = kwargs
        return selection

    def build_snapshot(run_id: str):
        calls["snapshot_run_id"] = run_id
        return {"run": {"run_id": run_id}, "scene_count": 4}

    monkeypatch.setattr(routes, "resolve_g1_run_selection", resolve)
    monkeypatch.setattr(routes, "build_g1_acceptance_snapshot", build_snapshot)
    monkeypatch.setattr(
        routes,
        "build_g1_console_summary",
        lambda snapshot: f"summary:{snapshot['selection']['run_id']}",
    )

    payload = routes._g1_diagnostics_payload(episode_id="EP_1")

    assert calls["selector"] == {"run_id": None, "episode_id": "EP_1", "latest": False}
    assert calls["snapshot_run_id"] == "RUN_1"
    assert payload["selection"]["run_id"] == "RUN_1"
    assert payload["diagnostics"]["selection"]["run_id"] == "RUN_1"
    assert payload["summary"] == "summary:RUN_1"


def test_episode_g1_diagnostics_returns_404_for_missing_episode(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_episode", lambda _episode_id: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_episode_g1_diagnostics("EP_MISSING")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "剧集不存在"


def test_run_g1_diagnostics_refuses_non_fast_grounded_run(monkeypatch) -> None:
    def fail_selection(**_kwargs):
        raise ValueError("该 Run 不是 Fast Grounded V2 生产结果，拒绝用于 G1 真实验收")

    monkeypatch.setattr(routes, "resolve_g1_run_selection", fail_selection)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_get_run_g1_diagnostics("RUN_OLD")

    assert exc_info.value.status_code == 400
    assert "不是 Fast Grounded" in str(exc_info.value.detail)


def test_router_exposes_read_only_g1_diagnostic_paths() -> None:
    paths = {route.path for route in routes.router.routes}

    assert "/api/episodes/{episode_id}/breakdown-g1-diagnostics" in paths
    assert "/api/breakdown-runs/{run_id}/g1-diagnostics" in paths
