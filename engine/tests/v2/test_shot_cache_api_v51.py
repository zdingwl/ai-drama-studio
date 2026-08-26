from __future__ import annotations

from engine.app.main import app


def test_shot_cache_management_routes_are_registered() -> None:
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}

    assert ("/api/episodes/{episode_id}/shot-cache", ("GET",)) in routes
    assert ("/api/episodes/{episode_id}/shot-cache", ("DELETE",)) in routes
    assert ("/api/projects/{project_id}/shot-cache", ("DELETE",)) in routes
