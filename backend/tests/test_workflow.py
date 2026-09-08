import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact
from app.core.errors import AppError
from app.core.time import utc_now
from app.skills.models import ArtifactType, Capability
from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.task_service import (
    TaskCancelled,
    checkpoint_task,
    claim_next_task,
    mark_interrupted_tasks,
    publish_validated_task_artifact,
)
from app.workflow.worker import TaskHandlerRegistry, run_worker_once


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P4 Workflow 测试",
            "project_type": "SCRIPT_TO_DRAMA",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _task_payload(
    value: str,
    *,
    task_type: str = "P4_TEST",
    task_name: str = "基础任务",
    max_attempts: int = 3,
    artifact_ids: list[str] | None = None,
) -> dict:
    return {
        "task_type": task_type,
        "task_name": task_name,
        "input_fingerprint": _sha(value),
        "input_artifact_ids": artifact_ids or [],
        "max_attempts": max_attempts,
    }


def _create_task(client: TestClient, project_id: str, value: str, *, key: str, **kwargs) -> dict:
    response = client.post(
        f"/api/v3/projects/{project_id}/commands/tasks",
        json=_task_payload(value, **kwargs),
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_task_command_is_idempotent_and_business_input_is_deduplicated(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    first = _create_task(client, project["id"], "same-input", key="idem-1")
    same_key = _create_task(client, project["id"], "same-input", key="idem-1")
    same_business = _create_task(client, project["id"], "same-input", key="idem-2")

    assert first["id"] == same_key["id"] == same_business["id"]
    assert first["status"] == "queued"
    assert "idempotency_key" not in first
    assert "business_key" not in first
    assert "checkpoint_json" not in first

    conflict = client.post(
        f"/api/v3/projects/{project['id']}/commands/tasks",
        json=_task_payload("different-input"),
        headers={"Idempotency-Key": "idem-1"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    with session_factory() as db:
        assert db.scalar(select(func.count(Task.id))) == 1


def test_stale_artifact_input_is_fail_closed(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        source_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_TEXT,
            namespace=ArtifactNamespace.SOURCE,
            label="source-v1",
            input_fingerprint=_sha("source-v1"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )
        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_TEXT,
            namespace=ArtifactNamespace.SOURCE,
            label="source-v2",
            input_fingerprint=_sha("source-v2"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )

    response = client.post(
        f"/api/v3/projects/{project['id']}/commands/tasks",
        json=_task_payload("stale", artifact_ids=[source_v1.id]),
        headers={"Idempotency-Key": "stale-input"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_ARTIFACT_INPUT"


def test_worker_persists_checkpoint_and_task_success_does_not_auto_publish_artifact(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    created = _create_task(client, project["id"], "checkpoint", key="checkpoint-1")
    registry = TaskHandlerRegistry()

    def handler(context, task) -> None:
        assert task.checkpoint_json == {}
        context.checkpoint({"stage": "halfway", "cursor": 12}, progress_percent=50)
        context.heartbeat()

    registry.register("P4_TEST", handler)
    finished = run_worker_once(session_factory, registry, worker_id="worker-a")
    assert finished is not None
    assert finished.id == created["id"]
    assert finished.status == TaskStatus.SUCCEEDED
    assert finished.progress_percent == 100

    with session_factory() as db:
        persisted = db.get(Task, created["id"])
        assert persisted is not None
        assert persisted.checkpoint_json == {"stage": "halfway", "cursor": 12}
        assert db.scalar(select(func.count(ArtifactNode.id))) == 0

        with pytest.raises(AppError) as exc_info:
            publish_validated_task_artifact(
                db,
                task_id=created["id"],
                validation_passed=False,
                artifact_type=ArtifactType.TARGET_SCRIPT,
                namespace=ArtifactNamespace.TARGET,
                label="invalid output",
                input_fingerprint=_sha("output"),
                skill_id="project.script_to_drama",
                skill_version="1.0.0",
            )
        assert exc_info.value.code == "TASK_OUTPUT_VALIDATION_FAILED"
        assert db.scalar(select(func.count(ArtifactNode.id))) == 0

        artifact = publish_validated_task_artifact(
            db,
            task_id=created["id"],
            validation_passed=True,
            artifact_type=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET,
            label="validated output",
            input_fingerprint=_sha("validated-output"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )
        assert artifact.artifact_type == ArtifactType.TARGET_SCRIPT.value
        assert db.scalar(select(func.count(ArtifactNode.id))) == 1


def test_stale_heartbeat_becomes_interrupted_and_resume_keeps_checkpoint(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    created = _create_task(client, project["id"], "resume", key="resume-1")

    with session_factory() as db:
        claimed = claim_next_task(db, "worker-crashed")
        assert claimed is not None and claimed.id == created["id"]
        checkpoint_task(
            db,
            claimed.id,
            checkpoint={"page": 7},
            progress_percent=35,
            worker_id="worker-crashed",
        )
        persisted = db.get(Task, claimed.id)
        assert persisted is not None
        persisted.heartbeat_at = utc_now() - timedelta(minutes=10)
        db.add(persisted)
        db.commit()

    with session_factory() as db:
        interrupted = mark_interrupted_tasks(db, stale_before=utc_now() - timedelta(minutes=5))
        assert [task.id for task in interrupted] == [created["id"]]
        assert interrupted[0].status == TaskStatus.INTERRUPTED

    resumed = client.post(f"/api/v3/projects/{project['id']}/tasks/{created['id']}/commands/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"

    registry = TaskHandlerRegistry()

    def handler(context, task) -> None:
        assert task.checkpoint_json == {"page": 7}
        context.checkpoint({"page": 8}, progress_percent=80)

    registry.register("P4_TEST", handler)
    finished = run_worker_once(session_factory, registry, worker_id="worker-resumed")
    assert finished is not None
    assert finished.status == TaskStatus.SUCCEEDED
    assert finished.attempt == 2


def test_retry_is_finite_and_does_not_exceed_max_attempts(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    created = _create_task(
        client,
        project["id"],
        "finite-retry",
        key="retry-1",
        max_attempts=2,
    )
    registry = TaskHandlerRegistry()

    def failing_handler(context, task) -> None:
        raise RuntimeError("this raw error must not be persisted")

    registry.register("P4_TEST", failing_handler)
    first = run_worker_once(session_factory, registry, worker_id="worker-retry-1")
    assert first is not None
    assert first.status == TaskStatus.FAILED
    assert first.attempt == 1
    assert first.last_error == "任务执行失败（RuntimeError）"

    retry = client.post(f"/api/v3/projects/{project['id']}/tasks/{created['id']}/commands/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "queued"

    second = run_worker_once(session_factory, registry, worker_id="worker-retry-2")
    assert second is not None
    assert second.status == TaskStatus.FAILED
    assert second.attempt == 2

    exhausted = client.post(f"/api/v3/projects/{project['id']}/tasks/{created['id']}/commands/retry")
    assert exhausted.status_code == 409
    assert exhausted.json()["error"]["code"] == "TASK_RETRY_LIMIT_REACHED"


def test_cancel_stops_queued_and_running_tasks_at_deterministic_boundary(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    queued = _create_task(client, project["id"], "cancel-queued", key="cancel-q")
    cancelled = client.post(f"/api/v3/projects/{project['id']}/tasks/{queued['id']}/commands/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    registry = TaskHandlerRegistry()
    registry.register("P4_TEST", lambda context, task: None)
    assert run_worker_once(session_factory, registry, worker_id="worker-empty") is None

    running = _create_task(client, project["id"], "cancel-running", key="cancel-r")
    with session_factory() as db:
        claimed = claim_next_task(db, "worker-running")
        assert claimed is not None and claimed.id == running["id"]

    requested = client.post(f"/api/v3/projects/{project['id']}/tasks/{running['id']}/commands/cancel")
    assert requested.status_code == 200
    assert requested.json()["status"] == "running"

    with session_factory() as db:
        with pytest.raises(TaskCancelled):
            checkpoint_task(
                db,
                running["id"],
                checkpoint={"next": "should-not-run"},
                progress_percent=60,
                worker_id="worker-running",
            )
        persisted = db.get(Task, running["id"])
        assert persisted is not None
        assert persisted.status == TaskStatus.CANCELLED


def test_provider_job_is_committed_before_remote_call_and_never_persists_credentials(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog,
) -> None:
    project = _project(client)
    created = _create_task(client, project["id"], "provider", key="provider-1")

    with session_factory() as db:
        claimed = claim_next_task(db, "worker-provider")
        assert claimed is not None and claimed.id == created["id"]

        def remote_call(job: ProviderJob) -> ProviderDispatchResult:
            with session_factory() as committed_db:
                committed = committed_db.get(ProviderJob, job.id)
                assert committed is not None
                assert committed.status == ProviderJobStatus.RUNNING
                assert committed.payload_fingerprint == _sha('{"prompt":"hello"}') or len(committed.payload_fingerprint) == 64
            return ProviderDispatchResult(value={"ok": True}, remote_job_id="remote-123", completed=True)

        job, result = dispatch_provider_call(
            db,
            task_id=created["id"],
            provider="mock-provider",
            model="mock-model",
            capability=Capability.MEDIA_PREFLIGHT,
            payload={"prompt": "hello"},
            remote_call=remote_call,
        )
        assert result.value == {"ok": True}
        assert job.status == ProviderJobStatus.SUCCEEDED
        assert job.remote_job_id == "remote-123"
        assert not hasattr(job, "api_key")
        assert not hasattr(job, "authorization")

        with pytest.raises(AppError) as sensitive:
            dispatch_provider_call(
                db,
                task_id=created["id"],
                provider="mock-provider",
                model="mock-model",
                capability=Capability.MEDIA_PREFLIGHT,
                payload={"api_key": "sk-should-never-persist"},
                remote_call=lambda job: ProviderDispatchResult(),
            )
        assert sensitive.value.code == "SENSITIVE_PROVIDER_PAYLOAD"

        with pytest.raises(AppError) as failed:
            dispatch_provider_call(
                db,
                task_id=created["id"],
                provider="mock-provider",
                model="mock-model",
                capability=Capability.MEDIA_PREFLIGHT,
                payload={"prompt": "failure"},
                remote_call=lambda job: (_ for _ in ()).throw(RuntimeError("sk-live-secret")),
            )
        assert failed.value.code == "PROVIDER_REQUEST_FAILED"

    with session_factory() as db:
        jobs = list(db.scalars(select(ProviderJob).order_by(ProviderJob.created_at.asc())).all())
        assert len(jobs) == 2
        assert jobs[-1].status == ProviderJobStatus.FAILED
        assert jobs[-1].safe_error == "Provider 请求失败（RuntimeError）"
        persisted_text = " ".join(
            str(value)
            for job in jobs
            for value in (
                job.provider,
                job.model,
                job.capability,
                job.payload_fingerprint,
                job.safe_error,
                job.remote_job_id,
            )
            if value is not None
        )
        assert "sk-live-secret" not in persisted_text
        assert "sk-should-never-persist" not in persisted_text
    assert "sk-live-secret" not in caplog.text
    assert "sk-should-never-persist" not in caplog.text


def test_task_get_routes_are_read_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    created = _create_task(client, project["id"], "read-only", key="read-only-1")

    with session_factory() as db:
        before_tasks = db.scalar(select(func.count(Task.id)))
        before_jobs = db.scalar(select(func.count(ProviderJob.id)))

    assert client.get(f"/api/v3/projects/{project['id']}/tasks").status_code == 200
    assert client.get(f"/api/v3/projects/{project['id']}/tasks/{created['id']}").status_code == 200
    assert client.get(f"/api/v3/projects/{project['id']}").status_code == 200

    with session_factory() as db:
        after_tasks = db.scalar(select(func.count(Task.id)))
        after_jobs = db.scalar(select(func.count(ProviderJob.id)))

    assert before_tasks == after_tasks == 1
    assert before_jobs == after_jobs == 0
