from __future__ import annotations

import pytest

from engine.app.main import create_app
from engine.app.shot_detection import ShotDetectionError
import engine.app.shot_detection_rerun as rerun_module


def test_f04_rerun_route_is_explicit_post_endpoint() -> None:
    """首次 POST 与重跑 POST 必须是两个不同入口，避免重复请求静默覆盖 READY。"""

    app = create_app()
    rerun_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/projects/{project_id}/shot-detection/rerun"
    ]

    assert len(rerun_routes) == 1
    assert "POST" in (rerun_routes[0].methods or set())


def test_rerun_requires_existing_ready_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有旧 READY 时不能把 rerun 当成首次运行，防止 API 语义混淆。"""

    monkeypatch.setattr(rerun_module, "get_shot_detection", lambda **_: None)

    with pytest.raises(ShotDetectionError) as error:
        rerun_module.rerun_shot_detection(project_id="PROJECT_" + "a" * 32)

    assert error.value.code == "SHOT_DETECTION_RERUN_NOT_READY"
