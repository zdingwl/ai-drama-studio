from types import SimpleNamespace

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.tasks import _schedule_task_if_needed
from app.p14.audio_contract import P14_AUDIO_TASK_TYPE
from app.p14.audio_runtime import run_target_audio_task
from app.p14.timing_service import P14_TIMING_TASK_TYPE, run_timing_plan_task
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


def test_generic_retry_scheduler_dispatches_p14_audio_runner(session_factory: sessionmaker[Session]) -> None:
    background_tasks = BackgroundTasks()
    task = SimpleNamespace(id="p14-audio-task", task_type=P14_AUDIO_TASK_TYPE)

    with session_factory() as db:
        _schedule_task_if_needed(background_tasks, db, task)

    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.func is run_target_audio_task
    assert scheduled.args[1] == "p14-audio-task"


def test_generic_retry_scheduler_dispatches_p14_timing_runner(session_factory: sessionmaker[Session]) -> None:
    background_tasks = BackgroundTasks()
    task = SimpleNamespace(id="p14-timing-task", task_type=P14_TIMING_TASK_TYPE)

    with session_factory() as db:
        _schedule_task_if_needed(background_tasks, db, task)

    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.func is run_timing_plan_task
    assert scheduled.args[1] == "p14-timing-task"
