from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.projects.models import Project


PROJECT_TYPES = (
    "REPLICA",
    "REDRAW",
    "TRANSLATION",
    "NOVEL_TO_DRAMA",
    "SCRIPT_TO_DRAMA",
    "SCRIPT_LOCALIZATION",
)
VIDEO_TYPES = {"REPLICA", "REDRAW", "TRANSLATION"}


def _payload(project_type: str, name: str | None = None) -> dict:
    payload = {
        "name": name or f"测试-{project_type}",
        "project_type": project_type,
        "target_language": "en-US",
        "target_region": "US",
    }
    if project_type in VIDEO_TYPES:
        payload["source_language"] = "zh-CN"
    return payload


def test_all_six_project_types_are_persisted(client: TestClient) -> None:
    created = []
    for project_type in PROJECT_TYPES:
        response = client.post("/api/v3/projects", json=_payload(project_type))
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["project_type"] == project_type
        created.append(body["id"])

    response = client.get("/api/v3/projects")
    assert response.status_code == 200
    assert {item["project_type"] for item in response.json()} == set(PROJECT_TYPES)
    assert len(created) == 6


def test_invalid_project_type_returns_validation_error(client: TestClient) -> None:
    payload = _payload("REPLICA")
    payload["project_type"] = "NOT_A_PROJECT_TYPE"
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_video_project_requires_source_language(client: TestClient) -> None:
    payload = _payload("REPLICA")
    payload.pop("source_language")
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 422


def test_project_type_has_no_backend_default(client: TestClient) -> None:
    payload = _payload("REPLICA")
    payload.pop("project_type")
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 422


def test_plan_is_compiled_from_root_skill(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("REPLICA")).json()
    response = client.get(f"/api/v3/projects/{project['id']}/plan")
    assert response.status_code == 200
    plan = response.json()
    assert plan["skill_id"] == "project.replica"
    assert plan["steps"][0]["id"] == "source_input"
    assert plan["steps"][0]["status"] == "READY"
    assert plan["steps"][1]["status"] == "BLOCKED_DEPENDENCY"


def test_translation_and_script_localization_have_different_plans(client: TestClient) -> None:
    translation = client.post("/api/v3/projects", json=_payload("TRANSLATION")).json()
    localization = client.post("/api/v3/projects", json=_payload("SCRIPT_LOCALIZATION")).json()

    translation_plan = client.get(f"/api/v3/projects/{translation['id']}/plan").json()
    localization_plan = client.get(f"/api/v3/projects/{localization['id']}/plan").json()

    assert {step["id"] for step in translation_plan["steps"]} == {
        "source_input",
        "dialogue",
        "target_dialogue",
        "voice_timing",
        "post",
    }
    assert {step["id"] for step in localization_plan["steps"]} == {
        "source_input",
        "script_analyze",
        "localize",
        "target_script",
        "export",
    }
    localization_capabilities = {
        capability for step in localization_plan["steps"] for capability in step["capabilities"]
    }
    assert "VIDEO_GENERATION" not in localization_capabilities


def test_project_patch_increments_workflow_revision(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("SCRIPT_TO_DRAMA")).json()
    response = client.patch(
        f"/api/v3/projects/{project['id']}",
        json={"target_region": "CA", "target_language": "en-CA"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["target_region"] == "CA"
    assert updated["workflow_revision"] == project["workflow_revision"] + 1


def test_get_endpoints_do_not_write_database(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = client.post("/api/v3/projects", json=_payload("REPLICA")).json()

    with session_factory() as db:
        before = db.scalar(select(func.count(Project.id)))

    for path in (
        "/api/v3/projects",
        f"/api/v3/projects/{project['id']}",
        f"/api/v3/projects/{project['id']}/plan",
        f"/api/v3/projects/{project['id']}/artifact-graph",
        "/api/v3/skills",
        "/api/v3/skills/capabilities",
    ):
        assert client.get(path).status_code == 200

    with session_factory() as db:
        after = db.scalar(select(func.count(Project.id)))

    assert before == after == 1


def test_artifact_graph_starts_empty(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("NOVEL_TO_DRAMA")).json()
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["available_artifact_types"] == []
