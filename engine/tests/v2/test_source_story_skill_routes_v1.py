from __future__ import annotations

import pytest
from fastapi import HTTPException

from engine.app import source_drama_snapshot_routes_v1 as routes
from engine.app.source_story_skills_v1 import SourceStorySkillError


def test_source_screenplay_compile_route_is_post_only() -> None:
    methods_by_path = {route.path: set(route.methods or set()) for route in routes.router.routes}

    assert methods_by_path["/api/episodes/{episode_id}/source-screenplay/compile"] == {"POST"}


def test_source_screenplay_compile_requires_current_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(routes, "load_episode_source_drama_snapshot_v1", lambda _episode_id: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_compile_episode_source_screenplay("EP_1")

    assert exc_info.value.status_code == 409
    assert "原片事实" in str(exc_info.value.detail)


def test_source_screenplay_compile_calls_sidecar_compiler_only_after_snapshot(monkeypatch) -> None:
    snapshot = {"episode_id": "EP_1", "source_fingerprint": "a" * 64}
    compiled = {"episode_id": "EP_1", "status": "READY"}
    calls: list[object] = []
    monkeypatch.setattr(routes, "load_episode_source_drama_snapshot_v1", lambda _episode_id: snapshot)

    def compile_stub(payload):
        calls.append(payload)
        return compiled

    monkeypatch.setattr(routes, "compile_source_screenplay_v1", compile_stub)

    assert routes.api_compile_episode_source_screenplay("EP_1") == compiled
    assert calls == [snapshot]


def test_source_story_validation_failure_is_runtime_error_not_source_write(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "load_episode_source_drama_snapshot_v1",
        lambda _episode_id: {"episode_id": "EP_1"},
    )

    def unsafe(_payload):
        raise SourceStorySkillError("unknown source ref")

    monkeypatch.setattr(routes, "compile_source_screenplay_v1", unsafe)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_compile_episode_source_screenplay("EP_1")

    assert exc_info.value.status_code == 503
    assert "没有修改任何原片事实" in str(exc_info.value.detail)
