from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.skills.registry import SkillRegistry


def test_skill_registry_exposes_six_versioned_root_skills(client: TestClient) -> None:
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
    assert {skill["version"] for skill in skills} == {"1.0.0"}
    assert all(skill["required_capabilities"] for skill in skills)
    assert all(skill["completion_criteria"] for skill in skills)


def test_skill_detail_contains_real_manual_and_replica_constraints(client: TestClient) -> None:
    response = client.get("/api/v3/skills/project.replica")
    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == "复刻短剧"
    assert "故事骨架" in detail["manual"]
    assert "节奏骨架" in detail["manual"]
    assert detail["manual_path"] == "replica/SKILL.md"
    assert detail["version"] == "1.0.0"


def test_professional_skill_api_exposes_episode_understanding_manual(client: TestClient) -> None:
    listed = client.get("/api/v3/skills/professional")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert "source-video-understanding" in ids

    response = client.get("/api/v3/skills/professional/source-video-understanding")
    assert response.status_code == 200
    detail = response.json()
    assert detail["version"] == "1.0.0"
    assert detail["required_inputs"] == ["SOURCE_VIDEO", "SOURCE_DIALOGUE"]
    assert "EPISODE_UNDERSTANDING" in detail["required_capabilities"]
    assert "宁可 UNKNOWN" in "\n".join(detail["provider_rules"])
    assert "完整 Episode" in detail["manual"]
    assert "P8" in detail["manual"]


def test_missing_professional_skill_returns_404(client: TestClient) -> None:
    response = client.get("/api/v3/skills/professional/not-found")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROFESSIONAL_SKILL_NOT_FOUND"


def test_capability_registry_is_business_oriented_and_does_not_fake_availability(client: TestClient) -> None:
    response = client.get("/api/v3/skills/capabilities")
    assert response.status_code == 200
    capabilities = {item["id"]: item for item in response.json()}
    assert "EPISODE_UNDERSTANDING" in capabilities
    assert "STORY_RHYTHM" in capabilities
    assert "VIDEO_GENERATION" in capabilities
    assert capabilities["STORY_RHYTHM"]["title"] == "故事与节奏"
    assert capabilities["VIDEO_GENERATION"]["availability"] == "PLANNED"


def test_invalid_skill_manifest_fails_fast(tmp_path: Path) -> None:
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "manifest.json").write_text('{"id":"broken"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="Skill manifest 无效"):
        SkillRegistry.load_from(tmp_path)


def test_missing_skill_returns_404(client: TestClient) -> None:
    response = client.get("/api/v3/skills/project.unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"
