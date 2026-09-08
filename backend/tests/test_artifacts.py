import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation
from app.core.errors import AppError
from app.skills.models import ArtifactType


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text_project(client: TestClient) -> dict:
    return client.post(
        "/api/v3/projects",
        json={
            "name": "Artifact 测试",
            "project_type": "SCRIPT_TO_DRAMA",
            "target_language": "en-US",
            "target_region": "US",
        },
    ).json()


def test_artifact_namespace_is_derived_from_business_type(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _text_project(client)
    with session_factory() as db:
        with pytest.raises(AppError) as exc_info:
            create_artifact(
                db,
                project_id=project["id"],
                artifact_type=ArtifactType.SOURCE_TEXT,
                namespace=ArtifactNamespace.TARGET,
                label="错误命名空间",
                input_fingerprint=_sha("source"),
                skill_id="project.script_to_drama",
                skill_version="1.0.0",
            )
        assert exc_info.value.code == "ARTIFACT_NAMESPACE_MISMATCH"


def test_artifact_relation_rejects_missing_nodes(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _text_project(client)
    with session_factory() as db:
        source = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_TEXT,
            namespace=ArtifactNamespace.SOURCE,
            label="原剧本",
            input_fingerprint=_sha("source-v1"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )
        with pytest.raises(AppError) as exc_info:
            create_artifact_relation(
                db,
                project_id=project["id"],
                source_node_id=source.id,
                target_node_id="missing",
                relation_type=ArtifactRelationType.DERIVED_FROM,
            )
        assert exc_info.value.code == "ARTIFACT_NOT_FOUND"


def test_new_source_revision_marks_old_and_downstream_artifacts_stale(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _text_project(client)
    with session_factory() as db:
        source_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_TEXT,
            namespace=ArtifactNamespace.SOURCE,
            label="原剧本 v1",
            input_fingerprint=_sha("source-v1"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )
        target = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET,
            label="目标剧本 v1",
            input_fingerprint=_sha("target-v1"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=source_v1.id,
            target_node_id=target.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )

        source_v2 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_TEXT,
            namespace=ArtifactNamespace.SOURCE,
            label="原剧本 v2",
            input_fingerprint=_sha("source-v2"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )

        old_source = db.get(ArtifactNode, source_v1.id)
        old_target = db.get(ArtifactNode, target.id)
        assert source_v2.revision == 2
        assert source_v2.validity == ArtifactValidity.CURRENT
        assert old_source is not None and old_source.validity == ArtifactValidity.STALE
        assert old_target is not None and old_target.validity == ArtifactValidity.STALE
        assert old_target.is_current is False


def test_artifact_change_invalidates_persisted_plan(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _text_project(client)
    compiled = client.post(f"/api/v3/projects/{project['id']}/commands/compile-plan")
    assert compiled.status_code == 200

    with session_factory() as db:
        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_TEXT,
            namespace=ArtifactNamespace.SOURCE,
            label="原剧本",
            input_fingerprint=_sha("source"),
            skill_id="project.script_to_drama",
            skill_version="1.0.0",
        )

    response = client.get(f"/api/v3/projects/{project['id']}/plan")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLAN_NOT_COMPILED"
