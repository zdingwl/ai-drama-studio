from fastapi.testclient import TestClient


def test_skill_registry_exposes_six_root_skills(client: TestClient) -> None:
    response = client.get("/api/v3/skills")
    assert response.status_code == 200
    skills = response.json()
    assert len(skills) == 6
    assert {skill["project_type"] for skill in skills} == {
        "REPLICA",
        "REDRAW",
        "TRANSLATION",
        "NOVEL_TO_DRAMA",
        "SCRIPT_TO_DRAMA",
        "SCRIPT_LOCALIZATION",
    }


def test_skill_detail_contains_real_manual(client: TestClient) -> None:
    response = client.get("/api/v3/skills/project.replica")
    assert response.status_code == 200
    detail = response.json()
    assert detail["title"] == "复刻短剧"
    assert "故事骨架" in detail["manual"]
    assert "节奏骨架" in detail["manual"]
    assert detail["manual_path"].endswith("replica/SKILL.md")


def test_capability_registry_is_business_oriented(client: TestClient) -> None:
    response = client.get("/api/v3/skills/capabilities")
    assert response.status_code == 200
    capabilities = {item["id"]: item for item in response.json()}
    assert "EPISODE_UNDERSTANDING" in capabilities
    assert "STORY_RHYTHM" in capabilities
    assert "VIDEO_GENERATION" in capabilities
    assert capabilities["STORY_RHYTHM"]["title"] == "故事与节奏"


def test_missing_skill_returns_404(client: TestClient) -> None:
    response = client.get("/api/v3/skills/project.unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"
