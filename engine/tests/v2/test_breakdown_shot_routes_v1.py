from __future__ import annotations

from fastapi import BackgroundTasks

from engine.app import breakdown_routes_v1 as routes
from unittest.mock import create_autospec
from engine.app import task_progress_v2


def test_shot_runner_uses_real_task_signatures_and_reaches_scoped_worker(monkeypatch):
    start = create_autospec(task_progress_v2.start_task)
    update = create_autospec(task_progress_v2.update_task)
    finish = create_autospec(task_progress_v2.finish_task)
    fail = create_autospec(task_progress_v2.fail_task)
    monkeypatch.setattr(routes, 'get_episode', lambda _: {'title': '第1集'})
    for name, mock in [('start_task', start), ('update_task', update), ('finish_task', finish), ('fail_task', fail)]:
        monkeypatch.setattr(routes, name, mock)
    called = []
    def worker(episode_id, ordinal, *, progress):
        called.append((episode_id, ordinal))
        progress(10, 'breakdown_shot_prepare', '准备完成')
        return {'warnings': []}
    monkeypatch.setattr(routes, 'run_shot_breakdown_rerun_v1', worker)
    routes.run_shot_breakdown_task('TASK_TEST', 'EPISODE_TEST', 2)
    assert called == [('EPISODE_TEST', 2)]
    start.assert_called_once()
    update.assert_any_call('TASK_TEST', current_item='Shot 02', current_index=1, total_items=1)
    finish.assert_called_once()
    fail.assert_not_called()


def _task(*, title: str, status: str = "PROCESSING") -> dict[str, object]:
    return {
        "id": f"TASK_{title[-2:]}",
        "project_id": "PROJECT_1",
        "episode_id": "EPISODE_1",
        "task_type": routes.BREAKDOWN_SHOT_TASK_TYPE,
        "title": title,
        "status": status,
    }


def test_active_single_shot_task_dedup_is_scoped_by_shot_title(monkeypatch) -> None:
    shot3 = _task(title="AI 拉片 · 第1集 · Shot 03")
    monkeypatch.setattr(routes, "list_project_tasks", lambda _project_id, limit=100: [shot3])

    assert routes._active_task(
        "PROJECT_1",
        routes.BREAKDOWN_SHOT_TASK_TYPE,
        "EPISODE_1",
        title="AI 拉片 · 第1集 · Shot 03",
    ) == shot3
    assert routes._active_task(
        "PROJECT_1",
        routes.BREAKDOWN_SHOT_TASK_TYPE,
        "EPISODE_1",
        title="AI 拉片 · 第1集 · Shot 04",
    ) is None


def test_shot_endpoint_enqueues_real_shot_runner(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_episode",
        lambda episode_id: {
            "id": episode_id,
            "project_id": "PROJECT_1",
            "title": "第1集",
        },
    )
    monkeypatch.setattr(
        routes,
        "get_current_breakdown",
        lambda _episode_id: {"run": {"id": "RUN_1"}},
    )
    captured: dict[str, object] = {}

    def fake_enqueue(background, **kwargs):
        captured.update(kwargs)
        return {"id": "TASK_1", "status": "QUEUED"}

    monkeypatch.setattr(routes, "_enqueue", fake_enqueue)
    result = routes.api_start_shot_breakdown("EPISODE_1", 7, BackgroundTasks())

    assert result == {"id": "TASK_1", "status": "QUEUED"}
    assert captured["project_id"] == "PROJECT_1"
    assert captured["episode_id"] == "EPISODE_1"
    assert captured["task_type"] == routes.BREAKDOWN_SHOT_TASK_TYPE
    assert captured["title"] == "AI 拉片 · 第1集 · Shot 07"
    assert captured["runner"] is routes.run_shot_breakdown_task
    assert captured["runner_args"] == ("EPISODE_1", 7)
    assert captured["total_items"] == 1


def test_shot_endpoint_requires_complete_episode_breakdown_baseline(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_episode",
        lambda episode_id: {
            "id": episode_id,
            "project_id": "PROJECT_1",
            "title": "第1集",
        },
    )
    monkeypatch.setattr(routes, "get_current_breakdown", lambda _episode_id: None)

    try:
        routes.api_start_shot_breakdown("EPISODE_1", 1, BackgroundTasks())
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
        assert "整集拉片" in str(getattr(exc, "detail", ""))
    else:
        raise AssertionError("没有整集拉片基线时必须拒绝单镜重拉")
