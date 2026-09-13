from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import expected_namespace
from app.replica_product.service import create_adaptation_task
from app.skills.models import ArtifactType
from app.workflow.models import ProviderJob, Task, TaskStatus


_SHA = "a" * 64


def _project(client: TestClient, project_type: str = "REPLICA") -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": f"Product-{project_type}",
            "project_type": project_type,
            "source_language": "zh-CN" if project_type in {"REPLICA", "REDRAW", "TRANSLATION"} else None,
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode:
    node = ArtifactNode(
        project_id=project_id,
        artifact_type=artifact_type.value,
        namespace=expected_namespace(artifact_type),
        label=f"test-{artifact_type.value}",
        revision=1,
        input_fingerprint=_SHA,
        skill_id="test-product-workflow",
        skill_version="1.0.0",
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={"test": True},
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _counts(factory: sessionmaker[Session]) -> tuple[int, int, int]:
    with factory() as db:
        return (
            int(db.scalar(select(func.count()).select_from(ArtifactNode)) or 0),
            int(db.scalar(select(func.count()).select_from(Task)) or 0),
            int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0),
        )


def _action(client: TestClient, project_id: str) -> str:
    response = client.get(f"/api/v3/projects/{project_id}/replica-workflow")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["steps"]) == 3
    assert [item["title"] for item in body["steps"]] == ["原片", "改编设定", "生成成片"]
    return body["next_action"]


def test_replica_product_workflow_get_is_read_only_and_non_replica_fails_closed(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    replica = _project(client)
    before = _counts(session_factory)

    response = client.get(f"/api/v3/projects/{replica['id']}/replica-workflow")
    assert response.status_code == 200, response.text
    assert response.json()["next_action"] == "UPLOAD_SOURCE"
    assert _counts(session_factory) == before

    redraw = _project(client, "REDRAW")
    rejected = client.get(f"/api/v3/projects/{redraw['id']}/replica-workflow")
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "REPLICA_PRODUCT_ONLY"


def test_replica_product_workflow_collapses_formal_artifacts_to_one_next_action(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    project_id = project["id"]
    assert _action(client, project_id) == "UPLOAD_SOURCE"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.SOURCE_VIDEO)
    assert _action(client, project_id) == "ANALYZE_SOURCE"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    assert _action(client, project_id) == "GENERATE_ADAPTATION"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.TARGET_BIBLE)
        _seed_current(db, project_id, ArtifactType.TARGET_SCRIPT)
        _seed_current(db, project_id, ArtifactType.TARGET_ASSETS)
    assert _action(client, project_id) == "CAST_VOICES"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.TARGET_AUDIO)
    assert _action(client, project_id) == "REVIEW_AUDIO"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.TIMING_PLAN)
    assert _action(client, project_id) == "GENERATE_VIDEO"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.GENERATION_SELECTION)
    assert _action(client, project_id) == "BUILD_FINAL"

    with session_factory() as db:
        _seed_current(db, project_id, ArtifactType.FINAL_OUTPUT)
    assert _action(client, project_id) == "COMPLETE"


def test_product_commands_fail_closed_before_hard_inputs_and_adaptation_parent_is_durable(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    project_id = project["id"]

    before = _counts(session_factory)
    generation = client.post(
        f"/api/v3/projects/{project_id}/commands/replica-generation",
        headers={"Idempotency-Key": "product-generation-too-early"},
    )
    assert generation.status_code == 409, generation.text
    assert generation.json()["error"]["code"] == "REPLICA_PRODUCT_PRODUCTION_INPUT_REQUIRED"
    assert _counts(session_factory) == before

    with session_factory() as db:
        snapshot = _seed_current(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
        first = create_adaptation_task(db, project_id=project_id, idempotency_key="product-adaptation-durable")
        duplicate = create_adaptation_task(db, project_id=project_id, idempotency_key="product-adaptation-durable")
        assert first.id == duplicate.id
        assert first.status == TaskStatus.QUEUED
        assert first.input_artifact_ids_json == [snapshot.id]
        assert first.task_name == "生成改编方案"
        assert db.scalar(select(func.count()).select_from(ProviderJob)) == 0
