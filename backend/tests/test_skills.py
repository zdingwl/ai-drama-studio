from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.skills.registry import SkillRegistry


def test_skill_registry_exposes_six_versioned_root_skills(client: TestClient) -> None:
    response = client.get("/api/v3/skills")
    assert response.status_code == 200
    skills = response.json()
    assert len(skills) == 6
    by_type = {skill["project_type"]: skill for skill in skills}
    assert set(by_type) == {
        "REPLICA",
        "REDRAW",
        "TRANSLATION",
        "NOVEL_TO_DRAMA",
        "SCRIPT_TO_DRAMA",
        "SCRIPT_LOCALIZATION",
    }
    assert by_type["REPLICA"]["version"] == "1.1.0"
    assert {skill["version"] for project_type, skill in by_type.items() if project_type != "REPLICA"} == {"1.0.0"}
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
    assert detail["version"] == "1.1.0"
    steps = {step["id"]: step for step in detail["steps"]}
    assert steps["target_bible"]["requires"] == ["SOURCE_VIDEO_SNAPSHOT"]
    assert steps["target_bible"]["produces"] == ["ADAPTATION_PLAN", "TARGET_BIBLE"]
    assert steps["target_script"]["requires"] == ["TARGET_BIBLE", "SOURCE_VIDEO_SNAPSHOT"]


def test_professional_skill_api_exposes_episode_understanding_and_p11_manuals(client: TestClient) -> None:
    listed = client.get("/api/v3/skills/professional")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert "source-video-understanding" in ids
    assert "replica-target-bible" in ids

    response = client.get("/api/v3/skills/professional/source-video-understanding")
    assert response.status_code == 200
    detail = response.json()
    assert detail["version"] == "1.1.0"
    assert detail["required_inputs"] == ["SOURCE_VIDEO", "SOURCE_DIALOGUE"]
    assert "EPISODE_UNDERSTANDING" in detail["required_capabilities"]
    rules = "\n".join(detail["provider_rules"])
    assert "UNKNOWN 不是" in rules
    assert "grounded-source-truth-v2" in detail["manual"]
    assert "完整 Episode" in detail["manual"]
    assert "P8" in detail["manual"]

    p11 = client.get("/api/v3/skills/professional/replica-target-bible")
    assert p11.status_code == 200
    p11_detail = p11.json()
    assert p11_detail["version"] == "1.0.0"
    assert p11_detail["required_inputs"] == ["SOURCE_VIDEO_SNAPSHOT"]
    assert p11_detail["output_contracts"] == ["ADAPTATION_PLAN", "TARGET_BIBLE"]
    assert "TARGET_SCRIPT" not in p11_detail["output_contracts"]


def test_missing_professional_skill_returns_404(client: TestClient) -> None:
    response = client.get("/api/v3/skills/professional/not-found")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROFESSIONAL_SKILL_NOT_FOUND"


def test_capability_registry_reflects_p10_acceptance_and_p11_admission(client: TestClient) -> None:
    response = client.get("/api/v3/skills/capabilities")
    assert response.status_code == 200
    capabilities = {item["id"]: item for item in response.json()}
    assert "EPISODE_UNDERSTANDING" in capabilities
    assert "STORY_RHYTHM" in capabilities
    assert "SHOT_BREAKDOWN" in capabilities
    assert "SOURCE_SNAPSHOT" in capabilities
    assert "LOCALIZATION" in capabilities
    assert "TARGET_BIBLE" in capabilities
    assert "VIDEO_GENERATION" in capabilities
    assert capabilities["EPISODE_UNDERSTANDING"]["availability"] == "AVAILABLE"
    assert capabilities["STORY_RHYTHM"]["availability"] == "AVAILABLE"
    assert capabilities["STORY_RHYTHM"]["title"] == "故事与节奏"
    assert capabilities["SHOT_BREAKDOWN"]["availability"] == "AVAILABLE"
    assert capabilities["SOURCE_SNAPSHOT"]["availability"] == "AVAILABLE"
    assert capabilities["LOCALIZATION"]["availability"] == "PLANNED"
    assert capabilities["TARGET_BIBLE"]["availability"] == "PLANNED"
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
