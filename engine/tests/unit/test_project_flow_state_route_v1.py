from __future__ import annotations

from engine.app.main import app


def test_project_flow_state_route_is_mounted() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/projects/{project_id}/flow-state" in paths
