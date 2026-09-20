import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace
from app.core.config import get_settings
from app.script_to_drama.production import _publish_one
from app.skills.models import ArtifactType


def _project(client: TestClient) -> str:
    response = client.post("/api/v3/projects", json={
        "name": "剧本媒体版本隔离", "project_type": "SCRIPT_TO_DRAMA",
        "target_language": "zh-CN", "target_region": "CN",
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _publish_media(factory: sessionmaker[Session], project_id: str, reference_id: str, content: bytes) -> None:
    root = get_settings().artifact_root.resolve()
    relative = f"script_to_drama/test_media/{project_id}/{reference_id}.png"
    output = root / relative
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    with factory() as db:
        _publish_one(
            db, project_id=project_id, kind=ArtifactType.TARGET_ASSET_IMAGES,
            namespace=ArtifactNamespace.TARGET, label="media-scope-test",
            content={"assets": [{"media": [{
                "reference_id": reference_id, "storage_relpath": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
            }]}]},
            sources=[], skill_id="media-test", skill_version="1.0.0", task_id=None,
        )
        db.commit()


def test_media_endpoint_uses_only_current_project_revision(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    first_project = _project(client)
    second_project = _project(client)
    old = "ref:" + uuid4().hex
    current = "ref:" + uuid4().hex
    _publish_media(session_factory, first_project, old, b"old-media")
    base = f"/api/v3/projects/{first_project}/script-to-drama/media"
    assert client.get(f"{base}/{old}").content == b"old-media"
    assert client.get(f"/api/v3/projects/{second_project}/script-to-drama/media/{old}").status_code == 404

    _publish_media(session_factory, first_project, current, b"current-media")
    assert client.get(f"{base}/{old}").status_code == 404
    assert client.get(f"{base}/{current}").content == b"current-media"
