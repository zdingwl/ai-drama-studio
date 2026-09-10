from types import SimpleNamespace

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.tasks import _schedule_task_if_needed
from app.source_resolution.service_v2 import P9_TASK_TYPE, run_p9_source_resolution_task
from app.understanding.evidence_reference_runtime import run_p7_source_bible_task
from app.understanding.service import P7_TASK_TYPE


def test_generic_retry_scheduler_dispatches_p7_runner(session_factory: sessionmaker[Session]) -> None:
    background_tasks = BackgroundTasks()
    task = SimpleNamespace(id="p7-task", task_type=P7_TASK_TYPE)

    with session_factory() as db:
        _schedule_task_if_needed(background_tasks, db, task)

    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.func is run_p7_source_bible_task
    assert scheduled.args[1] == "p7-task"


def test_generic_retry_scheduler_dispatches_p9_runner(session_factory: sessionmaker[Session]) -> None:
    background_tasks = BackgroundTasks()
    task = SimpleNamespace(id="p9-task", task_type=P9_TASK_TYPE)

    with session_factory() as db:
        _schedule_task_if_needed(background_tasks, db, task)

    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.func is run_p9_source_resolution_task
    assert scheduled.args[1] == "p9-task"
