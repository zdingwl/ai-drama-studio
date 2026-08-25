from __future__ import annotations

from engine.app import task_routes_v2


def _install_task_spies(monkeypatch):
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(task_routes_v2, "start_task", lambda *args, **kwargs: events.append(("start", kwargs)))
    monkeypatch.setattr(task_routes_v2, "update_task", lambda *args, **kwargs: events.append(("update", kwargs)))
    monkeypatch.setattr(task_routes_v2, "finish_task", lambda *args, **kwargs: events.append(("finish", kwargs)))
    monkeypatch.setattr(task_routes_v2, "fail_task", lambda *args, **kwargs: events.append(("fail", kwargs)))
    return events


def test_shot_workflow_auto_preprocesses_when_media_assets_are_missing(monkeypatch) -> None:
    """未准备媒体资产时，用户只执行“拉片”就必须自动先完成预处理。"""

    events = _install_task_spies(monkeypatch)
    calls: list[str] = []
    episode = {
        "id": "EPISODE_01",
        "project_id": "PROJECT_01",
        "title": "第01集",
        "sort_order": 1,
        "preprocess_status": None,
    }

    monkeypatch.setattr(task_routes_v2, "get_episode", lambda episode_id: episode)

    def fake_preprocess(episode_id: str, progress=None):
        calls.append("preprocess")
        assert episode_id == "EPISODE_01"
        if progress:
            progress(100, "ready", "视频初始化完成", 1, 1)
        return {"proxy_path": "proxy.mp4"}

    def fake_shots(episode_id: str, progress=None):
        calls.append("shots")
        assert episode_id == "EPISODE_01"
        if progress:
            progress(100, "ready", "拉片完成", 1, 1)
        return [{"id": "SHOT_01"}]

    monkeypatch.setattr(task_routes_v2, "preprocess_episode", fake_preprocess)
    monkeypatch.setattr(task_routes_v2, "detect_episode_shots", fake_shots)

    task_routes_v2.run_episode_shots_task("TASK_01", "EPISODE_01")

    assert calls == ["preprocess", "shots"]
    assert not [event for event in events if event[0] == "fail"]
    assert [event for event in events if event[0] == "finish"]


def test_shot_workflow_reuses_ready_media_assets(monkeypatch) -> None:
    """已有 READY Proxy / Audio 时重新拉片不得重复执行 FFmpeg 预处理。"""

    events = _install_task_spies(monkeypatch)
    calls: list[str] = []
    episode = {
        "id": "EPISODE_01",
        "project_id": "PROJECT_01",
        "title": "第01集",
        "sort_order": 1,
        "preprocess_status": "READY",
    }

    monkeypatch.setattr(task_routes_v2, "get_episode", lambda episode_id: episode)

    def forbidden_preprocess(*args, **kwargs):
        raise AssertionError("READY 的媒体资产不应该重新预处理")

    def fake_shots(episode_id: str, progress=None):
        calls.append("shots")
        if progress:
            progress(100, "ready", "拉片完成", 1, 1)
        return [{"id": "SHOT_01"}, {"id": "SHOT_02"}]

    monkeypatch.setattr(task_routes_v2, "preprocess_episode", forbidden_preprocess)
    monkeypatch.setattr(task_routes_v2, "detect_episode_shots", fake_shots)

    task_routes_v2.run_episode_shots_task("TASK_02", "EPISODE_01")

    assert calls == ["shots"]
    assert not [event for event in events if event[0] == "fail"]
    reuse_updates = [
        payload for kind, payload in events
        if kind == "update" and payload.get("stage_key") == "reuse_preprocess"
    ]
    assert reuse_updates
