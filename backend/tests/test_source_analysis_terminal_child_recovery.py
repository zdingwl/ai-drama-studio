from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.shot_breakdown import service as p8_base_service
from app.source_analysis import service as source_analysis_service
from app.source_resolution import service as p9_base_service
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate
from app.workflow.task_service import create_task_from_command
from app.workflow.worker import TaskExecutionContext


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "terminal-child-recovery",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _exhausted_child(db: Session, project_id: str) -> Task:
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key="historical-p8-terminal",
        payload=TaskCommandCreate(
            task_type="P8_SHOT_BREAKDOWN",
            task_name="历史逐镜精细拉片",
            input_fingerprint="a" * 64,
            input_artifact_ids=[],
            max_attempts=3,
        ),
    )
    task.status = TaskStatus.FAILED
    task.attempt = 3
    task.progress_percent = 68
    task.last_error = "历史 P8 已耗尽重试"
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _succeed_runner(seen_ids: list[str]):
    def runner(factory: sessionmaker[Session], task_id: str) -> None:
        with factory() as db:
            task = db.get(Task, task_id)
            assert task is not None
            assert task.status == TaskStatus.QUEUED
            assert task.attempt == 0
            seen_ids.append(task.id)
            task.status = TaskStatus.SUCCEEDED
            task.progress_percent = 100
            db.add(task)
            db.commit()

    return runner


def test_one_click_uses_non_eager_p8_p9_creators() -> None:
    # P8/P9 debug adapters eagerly retry FAILED tasks. The one-click orchestrator
    # must receive the terminal Task itself so it can apply explicit recovery
    # generation semantics instead of raising TASK_RETRY_LIMIT_REACHED first.
    assert source_analysis_service.create_shot_breakdown_task is p8_base_service.create_shot_breakdown_task
    assert source_analysis_service.create_source_resolution_task is p9_base_service.create_source_resolution_task


def test_explicit_source_analysis_restarts_terminal_child_without_mutating_history(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        historical = _exhausted_child(db, project["id"])
        historical_id = historical.id
        historical_business_key = historical.business_key

    first_seen: list[str] = []
    source_analysis_service._ensure_child_succeeded(
        TaskExecutionContext(
            session_factory=session_factory,
            task_id="source-analysis-parent-1",
            worker_id="test-parent-1",
        ),
        child=SimpleNamespace(id=historical_id),
        runner=_succeed_runner(first_seen),
    )

    assert len(first_seen) == 1
    first_recovery_id = first_seen[0]
    assert first_recovery_id != historical_id

    with session_factory() as db:
        historical = db.get(Task, historical_id)
        first_recovery = db.get(Task, first_recovery_id)
        assert historical is not None
        assert first_recovery is not None
        assert historical.status == TaskStatus.FAILED
        assert historical.attempt == 3
        assert historical.last_error == "历史 P8 已耗尽重试"
        assert historical.business_key == historical_business_key
        assert first_recovery.status == TaskStatus.SUCCEEDED
        assert first_recovery.input_fingerprint == historical.input_fingerprint
        assert first_recovery.input_artifact_ids_json == historical.input_artifact_ids_json
        assert first_recovery.business_key != historical.business_key
        assert first_recovery.max_attempts == historical.max_attempts

        # Simulate this explicit recovery generation eventually exhausting too.
        first_recovery.status = TaskStatus.FAILED
        first_recovery.attempt = first_recovery.max_attempts
        first_recovery.progress_percent = 68
        first_recovery.last_error = "第一代恢复任务也已耗尽"
        db.add(first_recovery)
        db.commit()

    second_seen: list[str] = []
    source_analysis_service._ensure_child_succeeded(
        TaskExecutionContext(
            session_factory=session_factory,
            task_id="source-analysis-parent-2",
            worker_id="test-parent-2",
        ),
        # A stage creator can still return the original business-key row. The
        # recovery helper must locate the latest equivalent execution generation.
        child=SimpleNamespace(id=historical_id),
        runner=_succeed_runner(second_seen),
    )

    assert len(second_seen) == 1
    second_recovery_id = second_seen[0]
    assert second_recovery_id not in {historical_id, first_recovery_id}

    with session_factory() as db:
        historical = db.get(Task, historical_id)
        first_recovery = db.get(Task, first_recovery_id)
        second_recovery = db.get(Task, second_recovery_id)
        assert historical is not None
        assert first_recovery is not None
        assert second_recovery is not None
        assert historical.status == TaskStatus.FAILED
        assert historical.attempt == 3
        assert first_recovery.status == TaskStatus.FAILED
        assert first_recovery.attempt == 3
        assert second_recovery.status == TaskStatus.SUCCEEDED
        assert second_recovery.input_fingerprint == historical.input_fingerprint
        assert len({historical.business_key, first_recovery.business_key, second_recovery.business_key}) == 3

        equivalent = list(
            db.scalars(
                select(Task).where(
                    Task.project_id == project["id"],
                    Task.task_type == "P8_SHOT_BREAKDOWN",
                    Task.input_fingerprint == "a" * 64,
                )
            ).all()
        )
        assert len(equivalent) == 3
