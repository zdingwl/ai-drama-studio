from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.models import ArtifactNode
from app.sources.models import SourceAsset, SourceDocument


def create_project(client: TestClient, kind: str = "SCRIPT_LOCALIZATION") -> str:
    payload = {"name": f"script-source-{kind}", "project_type": kind, "target_language": "en-US", "target_region": "US"}
    if kind in {"REPLICA", "REDRAW", "TRANSLATION"}:
        payload["source_language"] = "zh-CN"
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_source_read_and_paste_preserve_original_and_revisions(client: TestClient) -> None:
    project_id = create_project(client)
    path = f"/api/v3/projects/{project_id}/script-localization"
    empty = client.get(f"{path}/source")
    assert empty.status_code == 200
    assert empty.json()["text"] is None

    one = client.post(f"{path}/paste", json={"text": "第一场\r\n甲：你好"})
    assert one.status_code == 201, one.text
    assert one.json()["revision"] == 1
    read = client.get(f"{path}/source")
    assert read.json()["filename"] == "粘贴剧本.txt"
    assert read.json()["text"] == "第一场\n甲：你好"

    duplicate = client.post(f"{path}/paste", json={"text": "第一场\n甲：你好"})
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == one.json()["id"]

    two = client.post(f"{path}/paste", json={"text": "第二场\n乙：你好"})
    assert two.status_code == 201
    assert two.json()["revision"] == 2
    assert client.get(f"{path}/source").json()["text"] == "第二场\n乙：你好"
    graph = client.get(f"/api/v3/projects/{project_id}/artifact-graph").json()
    rows = [node for node in graph["nodes"] if node["artifact_type"] == "SOURCE_TEXT"]
    assert [(row["revision"], row["validity"]) for row in rows] == [(1, "STALE"), (2, "CURRENT")]


def test_script_source_get_is_read_only(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    project_id = create_project(client)
    path = f"/api/v3/projects/{project_id}/script-localization/source"
    with session_factory() as db:
        before = tuple(db.scalar(select(func.count(model.id))) for model in (SourceDocument, SourceAsset, ArtifactNode))
    for _ in range(3):
        assert client.get(path).status_code == 200
    with session_factory() as db:
        after = tuple(db.scalar(select(func.count(model.id))) for model in (SourceDocument, SourceAsset, ArtifactNode))
    assert before == after


def test_script_source_rejects_other_types_without_affecting_replica(client: TestClient) -> None:
    replica_id = create_project(client, "REPLICA")
    path = f"/api/v3/projects/{replica_id}/script-localization"
    read = client.get(f"{path}/source")
    paste = client.post(f"{path}/paste", json={"text": "不能写入"})
    assert read.status_code == paste.status_code == 422
    assert read.json()["error"]["code"] == "SCRIPT_LOCALIZATION_NOT_ALLOWED"
    assert paste.json()["error"]["code"] == "SCRIPT_LOCALIZATION_NOT_ALLOWED"
    assert client.get(f"/api/v3/projects/{replica_id}/sources/episodes").status_code == 200


def test_empty_text_is_rejected(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(f"/api/v3/projects/{project_id}/script-localization/paste", json={"text": "  \n  "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TEXT_CONTENT_EMPTY"
