from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation
from app.core.errors import AppError
from app.skills.models import ArtifactType
from app.source_snapshot import service
from app.source_snapshot.schemas import P10_REQUIRED_ARTIFACT_TYPES


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P10-guards",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_p10_dependency_graph_contract_covers_every_frozen_source_artifact() -> None:
    assert set(service._DEPENDENCY_RELATIONS) == set(P10_REQUIRED_ARTIFACT_TYPES)
    assert service._DEPENDENCY_RELATIONS[ArtifactType.SOURCE_VIDEO] == ArtifactRelationType.DERIVED_FROM
    assert service._DEPENDENCY_RELATIONS[ArtifactType.SHOT_ANCHORS] == ArtifactRelationType.DERIVED_FROM
    assert service._DEPENDENCY_RELATIONS[ArtifactType.SOURCE_DIALOGUE] == ArtifactRelationType.DERIVED_FROM
    assert service._DEPENDENCY_RELATIONS[ArtifactType.SOURCE_SHOT_FACTS] == ArtifactRelationType.DERIVED_FROM
    assert service._DEPENDENCY_RELATIONS[ArtifactType.SOURCE_BIBLE] == ArtifactRelationType.USES
    assert service._DEPENDENCY_RELATIONS[ArtifactType.STORY_SKELETON] == ArtifactRelationType.USES
    assert service._DEPENDENCY_RELATIONS[ArtifactType.RHYTHM_SKELETON] == ArtifactRelationType.USES
    for artifact_type in (
        ArtifactType.SOURCE_CHARACTERS,
        ArtifactType.SOURCE_SPEAKERS,
        ArtifactType.SOURCE_SCENES,
        ArtifactType.SOURCE_PROPS,
    ):
        assert service._DEPENDENCY_RELATIONS[artifact_type] == ArtifactRelationType.CONTAINS


@pytest.mark.parametrize("artifact_type", P10_REQUIRED_ARTIFACT_TYPES)
def test_p10_requires_each_frozen_artifact_to_be_current(monkeypatch, artifact_type: ArtifactType) -> None:
    monkeypatch.setattr(service, "_current_artifact", lambda _db, _project_id, _artifact_type: None)

    with pytest.raises(AppError) as captured:
        service._require_current(object(), "project-p10", artifact_type)

    assert captured.value.code == "P10_SOURCE_ARTIFACT_REQUIRED"
    assert captured.value.details == {"artifact_type": artifact_type.value}


@pytest.mark.parametrize("artifact_type", P10_REQUIRED_ARTIFACT_TYPES)
def test_every_frozen_upstream_revision_marks_snapshot_stale(
    client: TestClient,
    session_factory: sessionmaker[Session],
    artifact_type: ArtifactType,
) -> None:
    project = _project(client)
    with session_factory() as db:
        upstream_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=artifact_type,
            namespace=ArtifactNamespace.SOURCE,
            label=f"{artifact_type.value} v1",
            input_fingerprint=_SHA_A,
            skill_id="p10-guard-fixture",
            skill_version="1.0.0",
        )
        snapshot = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
            namespace=ArtifactNamespace.SOURCE,
            label="原片分析定稿",
            input_fingerprint=_SHA_B,
            skill_id="source-video-snapshot",
            skill_version="1.0.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=upstream_v1.id,
            target_node_id=snapshot.id,
            relation_type=service._DEPENDENCY_RELATIONS[artifact_type],
        )

        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=artifact_type,
            namespace=ArtifactNamespace.SOURCE,
            label=f"{artifact_type.value} v2",
            input_fingerprint=_SHA_C,
            skill_id="p10-guard-fixture",
            skill_version="1.0.0",
        )

        stale = db.get(ArtifactNode, snapshot.id)
        assert stale is not None
        assert stale.validity == ArtifactValidity.STALE
        assert stale.is_current is False


def test_p10_identical_current_chain_is_idempotent_and_skips_publication(monkeypatch) -> None:
    db = object()
    inputs = object()
    content = object()
    current = SimpleNamespace(metadata_json={"source_chain_fingerprint": _SHA_A})
    expected = SimpleNamespace(status="CURRENT", revision=7)

    monkeypatch.setattr(service, "_assert_storage_ready", lambda _db: None)
    monkeypatch.setattr(service, "_load_inputs", lambda _db, _project_id: inputs)
    monkeypatch.setattr(service, "_build_content", lambda _inputs: content)
    monkeypatch.setattr(service, "_source_chain_fingerprint", lambda _inputs, _content: _SHA_A)
    monkeypatch.setattr(service, "_current_artifact", lambda _db, _project_id, _artifact_type: current)
    monkeypatch.setattr(service, "get_source_video_snapshot", lambda _db, _project_id: expected)

    def unexpected_publish(*_args, **_kwargs):
        pytest.fail("identical CURRENT Source chain must not publish another snapshot revision")

    monkeypatch.setattr(service, "_publish_snapshot", unexpected_publish)

    assert service.finalize_source_video_snapshot(db, "project-p10") is expected


def test_target_artifact_cannot_write_back_into_source_snapshot(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        snapshot = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
            namespace=ArtifactNamespace.SOURCE,
            label="原片分析定稿",
            input_fingerprint=_SHA_A,
            skill_id="source-video-snapshot",
            skill_version="1.0.0",
        )
        target = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Target fixture",
            input_fingerprint=_SHA_B,
            skill_id="target-fixture",
            skill_version="1.0.0",
        )

        with pytest.raises(AppError) as captured:
            create_artifact_relation(
                db,
                project_id=project["id"],
                source_node_id=target.id,
                target_node_id=snapshot.id,
                relation_type=ArtifactRelationType.USES,
            )

        assert captured.value.code == "SOURCE_NAMESPACE_BACKFLOW"
