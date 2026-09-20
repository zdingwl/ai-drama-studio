"""Human asset corrections publish new revisions without altering source or Replica."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace
from app.script_to_drama.service import _publish_one
from app.skills.models import ArtifactType


def _project(client: TestClient, kind: str = "SCRIPT_TO_DRAMA") -> str:
    response = client.post("/api/v3/projects", json={
        "name": "资产审核", "project_type": kind,
        "target_language": "zh-CN", "target_region": "CN",
        **({"source_language": "zh-CN"} if kind == "REPLICA" else {}),
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _fixture(factory: sessionmaker[Session], project_id: str) -> tuple[str, str]:
    def publish(db: Session, kind: ArtifactType, namespace: ArtifactNamespace,
                content: dict, sources: list):
        return _publish_one(db, project_id=project_id, kind=kind, namespace=namespace,
                            label="asset-review-test", content=content, sources=sources,
                            skill_id="test", skill_version="1.0", task_id="test", job_id="test")

    with factory() as db:
        snapshot = publish(db, ArtifactType.SOURCE_TEXT_SNAPSHOT, ArtifactNamespace.SOURCE, {"original": True}, [])
        story = publish(db, ArtifactType.STORY_SKELETON, ArtifactNamespace.SOURCE, {"story_beats": []}, [snapshot])
        rhythm = publish(db, ArtifactType.RHYTHM_SKELETON, ArtifactNamespace.SOURCE, {"rhythm_beats": []}, [snapshot])
        world = publish(db, ArtifactType.TARGET_BIBLE, ArtifactNamespace.TARGET, {
            "source_snapshot_artifact_id": snapshot.id,
            "characters": [{"id": "CHAR_A", "name": "甲", "visual_description": "短发", "source_facts": ["甲出现"]}],
            "locations": [{"id": "SCENE_A", "name": "办公室", "visual_description": "白墙"}],
            "props": [], "unresolved_decisions": ["甲的发型需核实"],
        }, [snapshot, story, rhythm])
        definitions = publish(db, ArtifactType.TARGET_ASSETS, ArtifactNamespace.TARGET,
            {"target_bible_artifact_id": world.id, "characters": [], "locations": [], "props": []}, [world])
        images = publish(db, ArtifactType.TARGET_ASSET_IMAGES, ArtifactNamespace.TARGET,
            {"assets": []}, [definitions])
        db.commit()
        return world.id, images.id


def test_human_review_revisions_and_stales_images(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    project_id = _project(client)
    old_world_id, _ = _fixture(session_factory, project_id)
    endpoint = f"/api/v3/projects/{project_id}/script-to-drama/commands/review-world"
    payload = {
        "expected_world_artifact_id": old_world_id,
        "corrections": [{"category": "characters", "entity_id": "CHAR_A", "visual_description": "齐肩长发"}],
        "acknowledged_decisions": ["甲的发型需核实"],
        "reason": "核对原文后人工确认外观",
    }
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["world"]["artifact_id"] != old_world_id
    assert result["world"]["content"]["characters"][0]["visual_description"] == "齐肩长发"
    assert result["world"]["content"]["characters"][0]["source_facts"] == ["甲出现"]
    assert result["world"]["content"]["unresolved_decisions"] == []
    assert result["assets"]["content"]["target_bible_artifact_id"] == result["world"]["artifact_id"]
    assert result["asset_images"]["status"] == "STALE"
    assert result["analysis"]["status"] == "CURRENT"
    assert client.post(endpoint, json=payload).status_code == 409
    assert client.post(endpoint, json={**payload, "expected_world_artifact_id": result["world"]["artifact_id"],
        "corrections": [{"category": "characters", "entity_id": "MISSING", "visual_description": "短发"}],
        "acknowledged_decisions": []}).status_code == 409


def test_replica_project_cannot_edit_script_to_drama_assets(client: TestClient) -> None:
    replica = _project(client, "REPLICA")
    endpoint = f"/api/v3/projects/{replica}/script-to-drama/commands/review-world"
    result = client.post(endpoint, json={
        "expected_world_artifact_id": str(uuid4()),
        "corrections": [{"category": "characters", "entity_id": "CHAR_A", "visual_description": "修改"}],
        "reason": "测试隔离",
    })
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "SCRIPT_TO_DRAMA_NOT_ALLOWED"
