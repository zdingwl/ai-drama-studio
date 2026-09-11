from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.projects.models import Project
from app.skills.plan_models import ProjectExecutionPlanRecord


PROJECT_TYPES = (
    "REPLICA",
    "REDRAW",
    "TRANSLATION",
    "NOVEL_TO_DRAMA",
    "SCRIPT_TO_DRAMA",
    "SCRIPT_LOCALIZATION",
)
VIDEO_TYPES = {"REPLICA", "REDRAW", "TRANSLATION"}
EXPECTED_SKILLS = {
    "REPLICA": "project.replica",
    "REDRAW": "project.redraw",
    "TRANSLATION": "project.translation",
    "NOVEL_TO_DRAMA": "project.novel_to_drama",
    "SCRIPT_TO_DRAMA": "project.script_to_drama",
    "SCRIPT_LOCALIZATION": "project.script_localization",
}
EXPECTED_SKILL_VERSIONS = {
    "REPLICA": "1.1.0",
    "REDRAW": "1.0.0",
    "TRANSLATION": "1.0.0",
    "NOVEL_TO_DRAMA": "1.0.0",
    "SCRIPT_TO_DRAMA": "1.0.0",
    "SCRIPT_LOCALIZATION": "1.0.0",
}


def _payload(project_type: str, name: str | None = None) -> dict:
    payload = {
        "name": name or f"测试-{project_type}",
        "project_type": project_type,
        "target_language": "en-US",
        "target_region": "US",
        "visual_style": "SOURCE_LIKE",
    }
    if project_type in VIDEO_TYPES:
        payload["source_language"] = "zh-CN"
    return payload


def _compile(client: TestClient, project_id: str) -> dict:
    response = client.post(f"/api/v3/projects/{project_id}/commands/compile-plan")
    assert response.status_code == 200, response.text
    return response.json()


def test_all_six_project_types_are_persisted_and_bound_to_root_skills(client: TestClient) -> None:
    for project_type in PROJECT_TYPES:
        response = client.post("/api/v3/projects", json=_payload(project_type))
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["project_type"] == project_type
        assert body["root_skill_id"] == EXPECTED_SKILLS[project_type]
        assert body["root_skill_version"] == EXPECTED_SKILL_VERSIONS[project_type]
        assert body["current_plan_id"] is None

    response = client.get("/api/v3/projects")
    assert response.status_code == 200
    assert {item["project_type"] for item in response.json()} == set(PROJECT_TYPES)


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


def test_plan_must_be_explicitly_compiled_then_get_is_read_only(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("REPLICA")).json()

    missing = client.get(f"/api/v3/projects/{project['id']}/plan")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PLAN_NOT_COMPILED"

    plan = _compile(client, project["id"])
    assert plan["skill_id"] == "project.replica"
    assert plan["skill_version"] == "1.1.0"
    assert plan["revision"] == 1
    assert len(plan["input_fingerprint"]) == 64
    assert plan["steps"][0]["id"] == "source_input"
    assert plan["steps"][0]["status"] == "READY"
    assert plan["steps"][1]["status"] == "BLOCKED_DEPENDENCY"

    persisted = client.get(f"/api/v3/projects/{project['id']}/plan")
    assert persisted.status_code == 200
    assert persisted.json() == plan

    same = _compile(client, project["id"])
    assert same["id"] == plan["id"]
    assert same["revision"] == 1
    assert same["input_fingerprint"] == plan["input_fingerprint"]


def test_translation_and_script_localization_have_different_persisted_plans(client: TestClient) -> None:
    translation = client.post("/api/v3/projects", json=_payload("TRANSLATION")).json()
    localization = client.post("/api/v3/projects", json=_payload("SCRIPT_LOCALIZATION")).json()

    translation_plan = _compile(client, translation["id"])
    localization_plan = _compile(client, localization["id"])

    assert {step["id"] for step in translation_plan["steps"]} == {
        "source_input",
        "shot_boundary",
        "dialogue",
        "target_dialogue",
        "voice_timing",
        "post",
    }
    translation_steps = {step["id"]: step for step in translation_plan["steps"]}
    assert translation_steps["shot_boundary"]["capabilities"] == ["MEDIA_PREFLIGHT", "SHOT_BOUNDARY"]
    assert translation_steps["shot_boundary"]["produces"] == ["SHOT_ANCHORS"]
    assert translation_steps["dialogue"]["capabilities"] == ["SOURCE_DIALOGUE_EVIDENCE"]

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


def test_project_patch_invalidates_plan_and_recompile_creates_new_revision(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("SCRIPT_TO_DRAMA")).json()
    first_plan = _compile(client, project["id"])

    response = client.patch(
        f"/api/v3/projects/{project['id']}",
        json={"target_region": "CA", "target_language": "en-CA"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["target_region"] == "CA"
    assert updated["workflow_revision"] == project["workflow_revision"] + 1
    assert updated["current_plan_id"] is None
    assert client.get(f"/api/v3/projects/{project['id']}/plan").status_code == 404

    second_plan = _compile(client, project["id"])
    assert second_plan["revision"] == 2
    assert second_plan["id"] != first_plan["id"]
    assert second_plan["input_fingerprint"] != first_plan["input_fingerprint"]


def test_noop_patch_does_not_increment_workflow_revision(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("SCRIPT_TO_DRAMA")).json()
    response = client.patch(
        f"/api/v3/projects/{project['id']}",
        json={"target_region": project["target_region"]},
    )
    assert response.status_code == 200
    assert response.json()["workflow_revision"] == project["workflow_revision"]


def test_get_endpoints_do_not_write_database(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = client.post("/api/v3/projects", json=_payload("REPLICA")).json()
    _compile(client, project["id"])

    with session_factory() as db:
        before_projects = db.scalar(select(func.count(Project.id)))
        before_plans = db.scalar(select(func.count(ProjectExecutionPlanRecord.id)))

    for path in (
        "/api/v3/projects",
        f"/api/v3/projects/{project['id']}",
        f"/api/v3/projects/{project['id']}/plan",
        f"/api/v3/projects/{project['id']}/artifacts",
        f"/api/v3/projects/{project['id']}/artifact-graph",
        "/api/v3/skills",
        "/api/v3/skills/capabilities",
    ):
        assert client.get(path).status_code == 200

    with session_factory() as db:
        after_projects = db.scalar(select(func.count(Project.id)))
        after_plans = db.scalar(select(func.count(ProjectExecutionPlanRecord.id)))

    assert before_projects == after_projects == 1
    assert before_plans == after_plans == 1


def test_artifact_graph_starts_empty(client: TestClient) -> None:
    project = client.post("/api/v3/projects", json=_payload("NOVEL_TO_DRAMA")).json()
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["available_artifact_types"] == []
