from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.api.routes import target_script as route
from app.workflow.models import TaskStatus


def test_p12_route_schedules_worker_for_queued_task(monkeypatch) -> None:
    task = SimpleNamespace(id="task-queued", status=TaskStatus.QUEUED)
    monkeypatch.setattr(
        route,
        "create_target_script_task",
        lambda db, *, project_id, idempotency_key: task,
    )
    monkeypatch.setattr(route, "task_to_read", lambda value: value)

    background_tasks = BackgroundTasks()
    db = SimpleNamespace(get_bind=lambda: object())
    result = route.start_target_script_route(
        "project-1",
        background_tasks,
        "p12-route-test",
        db,
    )

    assert result is task
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is route.run_target_script_task
    assert background_tasks.tasks[0].args[1] == "task-queued"


def test_p12_route_does_not_reschedule_non_queued_task(monkeypatch) -> None:
    task = SimpleNamespace(id="task-running", status=TaskStatus.RUNNING)
    monkeypatch.setattr(
        route,
        "create_target_script_task",
        lambda db, *, project_id, idempotency_key: task,
    )
    monkeypatch.setattr(route, "task_to_read", lambda value: value)

    background_tasks = BackgroundTasks()
    db = SimpleNamespace(get_bind=lambda: object())
    route.start_target_script_route(
        "project-1",
        background_tasks,
        "p12-route-running",
        db,
    )

    assert background_tasks.tasks == []
