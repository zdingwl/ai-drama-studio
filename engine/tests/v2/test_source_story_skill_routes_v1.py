from __future__ import annotations

import pytest
from fastapi import HTTPException

from engine.app import source_drama_snapshot_routes_v1 as routes
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError
from engine.app.source_story_skills_v1 import SourceStorySkillError


def test_source_screenplay_compile_route_is_post_only_and_read_route_is_get_only() -> None:
    methods_by_path = {route.path: set(route.methods or set()) for route in routes.router.routes}

    assert methods_by_path["/api/episodes/{episode_id}/source-screenplay/compile"] == {"POST"}
    assert methods_by_path["/api/episodes/{episode_id}/source-screenplay"] == {"GET"}


def test_source_screenplay_compile_requires_current_snapshot(monkeypatch) -> None:
    def missing(_episode_id: str):
        raise SourceDramaSnapshotError("当前 Episode 尚未形成可消费的 SourceDramaSnapshot")

    monkeypatch.setattr(routes, "_load_current_snapshot", missing)

    with pytest.raises(HTTPException) as exc_info:
        routes.api_compile_episode_source_screenplay("EP_1")

    assert exc_info.value.status_code == 409
    assert "原片事实" in str(exc_info.value.detail)


def test_source_screenplay_compile_persists_only_after_successful_compile(monkeypatch) -> None:
    snapshot = {"episode_id": "EP_1", "source_fingerprint": "a" * 64}
    compiled = {"episode_id": "EP_1", "status": "READY"}
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(routes, "_load_current_snapshot", lambda _episode_id: snapshot)

    def compile_stub(payload):
        calls.append(("compile", payload))
        return compiled

    def persist_stub(payload, result):
        calls.append(("persist", (payload, result)))

    monkeypatch.setattr(routes, "compile_source_screenplay_v2", compile_stub)
    monkeypatch.setattr(routes, "persist_source_screenplay_v1", persist_stub)

    assert routes.api_compile_episode_source_screenplay("EP_1") == compiled
    assert calls == [
        ("compile", snapshot),
        ("persist", (snapshot, compiled)),
    ]


def test_source_screenplay_get_never_compiles(monkeypatch) -> None:
    snapshot = {"episode_id": "EP_1", "source_fingerprint": "a" * 64}
    read_payload = {"state": "MISSING", "episode_id": "EP_1"}
    monkeypatch.setattr(routes, "_load_current_snapshot", lambda _episode_id: snapshot)
    monkeypatch.setattr(routes, "read_source_screenplay_v1", lambda payload: read_payload)

    def forbidden_compile(_payload):
        raise AssertionError("GET must never execute screenplay inference")

    monkeypatch.setattr(routes, "compile_source_screenplay_v2", forbidden_compile)

    assert routes.api_get_episode_source_screenplay("EP_1") == read_payload


def test_source_story_validation_failure_is_runtime_error_not_source_write(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "_load_current_snapshot",
        lambda _episode_id: {"episode_id": "EP_1"},
    )

    def unsafe(_payload):
        raise SourceStorySkillError("unknown source ref")

    persisted: list[object] = []
    monkeypatch.setattr(routes, "compile_source_screenplay_v2", unsafe)
    monkeypatch.setattr(routes, "persist_source_screenplay_v1", lambda *_args: persisted.append(object()))

    with pytest.raises(HTTPException) as exc_info:
        routes.api_compile_episode_source_screenplay("EP_1")

    assert exc_info.value.status_code == 503
    assert "没有修改任何原片事实" in str(exc_info.value.detail)
    assert persisted == []
