from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P4 人工验收项目",
            "project_type": "SCRIPT_TO_DRAMA",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start(client: TestClient, project_id: str, scenario: str, key: str) -> dict:
    response = client.post(
        f"/api/v3/projects/{project_id}/commands/p4-acceptance/{scenario}",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _get_task(client: TestClient, project_id: str, task_id: str) -> dict:
    response = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_acceptance_success_uses_real_task_and_provider_job_guardrails(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    created = _start(client, project["id"], "success", "manual-success-1")
    task = _get_task(client, project["id"], created["id"])

    assert task["status"] == TaskStatus.SUCCEEDED
    assert task["progress_percent"] == 100
    assert task["attempt"] == 1
    assert task["last_error"] is None

    with session_factory() as db:
        persisted = db.get(Task, task["id"])
        assert persisted is not None
        assert persisted.checkpoint_json["stage"] == "finalizing"
        jobs = list(db.scalars(select(ProviderJob).where(ProviderJob.task_id == task["id"])).all())
        assert len(jobs) == 1
        assert jobs[0].status == ProviderJobStatus.SUCCEEDED
        assert jobs[0].provider == "p4-local-mock"
        assert jobs[0].model == "local-no-billing"
        assert jobs[0].payload_fingerprint


def test_manual_acceptance_same_idempotency_key_creates_only_one_dedupe_task(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    first = _start(client, project["id"], "dedupe", "manual-dedupe-1")
    second = _start(client, project["id"], "dedupe", "manual-dedupe-1")

    assert first["id"] == second["id"]
    assert first["task_name"] == second["task_name"] == "P4 验收：防重复提交"
    with session_factory() as db:
        assert db.scalar(select(func.count(Task.id)).where(Task.project_id == project["id"])) == 1
        assert db.scalar(select(func.count(ProviderJob.id)).where(ProviderJob.task_id == first["id"])) == 1


def test_manual_acceptance_failure_can_retry_to_success(
    client: TestClient,
) -> None:
    project = _project(client)
    created = _start(client, project["id"], "retry", "manual-retry-1")
    failed = _get_task(client, project["id"], created["id"])

    assert failed["status"] == TaskStatus.FAILED
    assert failed["progress_percent"] == 40
    assert failed["can_retry"] is True
    assert "请点击重试" in failed["last_error"]

    retried = client.post(
        f"/api/v3/projects/{project['id']}/tasks/{created['id']}/commands/retry"
    )
    assert retried.status_code == 200, retried.text

    succeeded = _get_task(client, project["id"], created["id"])
    assert succeeded["status"] == TaskStatus.SUCCEEDED
    assert succeeded["progress_percent"] == 100
    assert succeeded["attempt"] == 2


def test_manual_acceptance_interrupted_task_resumes_from_checkpoint(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    created = _start(client, project["id"], "resume", "manual-resume-1")
    interrupted = _get_task(client, project["id"], created["id"])

    assert interrupted["status"] == TaskStatus.INTERRUPTED
    assert interrupted["progress_percent"] == 55
    assert interrupted["can_resume"] is True

    with session_factory() as db:
        persisted = db.get(Task, created["id"])
        assert persisted is not None
        assert persisted.checkpoint_json == {"stage": "resume-checkpoint", "progress_percent": 55}

    resumed = client.post(
        f"/api/v3/projects/{project['id']}/tasks/{created['id']}/commands/resume"
    )
    assert resumed.status_code == 200, resumed.text

    succeeded = _get_task(client, project["id"], created["id"])
    assert succeeded["status"] == TaskStatus.SUCCEEDED
    assert succeeded["progress_percent"] == 100
    assert succeeded["attempt"] == 2
