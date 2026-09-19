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
    assert by_type["REPLICA"]["version"] == "1.7.0"
    assert {skill["version"] for project_type, skill in by_type.items() if project_type != "REPLICA"} == {"1.0.0"}
    assert all(skill["required_capabilities"] for skill in skills)
    assert all(skill["completion_criteria"] for skill in skills)


def test_skill_detail_contains_replica_five_step_contract(client: TestClient) -> None:
    response = client.get("/api/v3/skills/project.replica")
    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == "复刻短剧"
    assert detail["manual_path"] == "replica/SKILL.md"
    assert detail["version"] == "1.7.0"
    assert "唯一普通主流程" in detail["manual"]
    assert "minimax-h3-prompting@1.1.0" in detail["manual"]
    assert "z-image-turbo-asset-prompting@1.5.0" in detail["manual"]
    assert "qwen-image-edit-character-asset-prompting@1.0.0" in detail["manual"]
    assert "z-image-turbo-asset-prompting" in detail["subskills"]
    assert "qwen-image-edit-character-asset-prompting" in detail["subskills"]

    assert [step["id"] for step in detail["steps"]] == [
        "source_storyboard",
        "localized_storyboard",
        "asset_images",
        "model_prompting",
        "generate",
    ]
    steps = {step["id"]: step for step in detail["steps"]}
    assert steps["source_storyboard"]["requires"] == ["SOURCE_VIDEO"]
    assert steps["source_storyboard"]["produces"] == ["SOURCE_SHOT_FACTS", "SOURCE_VIDEO_SNAPSHOT"]
    assert steps["localized_storyboard"]["requires"] == ["SOURCE_VIDEO_SNAPSHOT"]
    assert steps["localized_storyboard"]["produces"] == ["TARGET_STORYBOARD"]
    assert steps["asset_images"]["requires"] == ["TARGET_STORYBOARD"]
    assert steps["asset_images"]["produces"] == ["TARGET_ASSETS"]
    assert "Skill" in steps["asset_images"]["title"]
    assert "面部特写" in steps["asset_images"]["description"]
    assert steps["model_prompting"]["requires"] == ["TARGET_STORYBOARD", "TARGET_ASSETS"]
    assert steps["model_prompting"]["produces"] == ["GENERATION_SEGMENTS"]
    assert steps["generate"]["requires"] == ["TARGET_STORYBOARD", "TARGET_ASSETS", "GENERATION_SEGMENTS"]
    assert steps["generate"]["produces"] == ["GENERATED_VIDEO", "GENERATION_SELECTION"]

    # Historical P11/P12/P14/P15/P17 artifacts may remain readable, but are not ordinary Replica steps.
    assert "target_bible" not in steps
    assert "target_script" not in steps
    assert "target_audio" not in steps
    assert "dialogue_timing" not in steps


def test_professional_skill_api_exposes_legacy_and_five_step_manuals(client: TestClient) -> None:
    listed = client.get("/api/v3/skills/professional")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert "source-video-understanding" in ids
    assert "replica-target-bible" in ids
    assert "target-script-localization" in ids
    assert "replica-target-assets" in ids
    assert "storyboard-localization" in ids
    assert "asset-image-generation" in ids
    assert "seedream-5-asset-prompting" in ids
    assert "qwen-image-edit-character-asset-prompting" in ids
    assert "minimax-h3-prompting" in ids

    response = client.get("/api/v3/skills/professional/source-video-understanding")
    assert response.status_code == 200
    detail = response.json()
    assert detail["version"] == "1.2.0"
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
    assert p11_detail["version"] == "1.1.0"
    assert p11_detail["required_inputs"] == ["SOURCE_SCRIPT"]
    assert p11_detail["output_contracts"] == ["ADAPTATION_PLAN", "TARGET_BIBLE"]
    assert "TARGET_SCRIPT" not in p11_detail["output_contracts"]

    p12 = client.get("/api/v3/skills/professional/target-script-localization")
    assert p12.status_code == 200
    p12_detail = p12.json()
    assert p12_detail["version"] == "1.2.0"
    assert p12_detail["required_inputs"] == ["SOURCE_SCRIPT", "ADAPTATION_PLAN", "TARGET_BIBLE"]
    assert p12_detail["output_contracts"] == ["TARGET_SCRIPT"]

    p13 = client.get("/api/v3/skills/professional/replica-target-assets")
    assert p13.status_code == 200
    p13_detail = p13.json()
    assert p13_detail["version"] == "1.1.0"
    assert p13_detail["required_inputs"] == ["TARGET_BIBLE"]
    assert p13_detail["readable_artifacts"] == ["TARGET_BIBLE"]
    assert p13_detail["output_contracts"] == ["TARGET_ASSETS"]

    localized = client.get("/api/v3/skills/professional/storyboard-localization")
    assert localized.status_code == 200
    localized_detail = localized.json()
    assert localized_detail["version"] == "1.5.0"
    assert "4 words per second" in "\n".join(localized_detail["provider_rules"])
    assert localized_detail["required_inputs"] == ["SOURCE_VIDEO_SNAPSHOT"]
    assert localized_detail["output_contracts"] == ["TARGET_STORYBOARD"]
    localized_rules = "\n".join(localized_detail["provider_rules"])
    assert "Simplified Chinese" in localized_rules
    assert "review translation" in localized_rules

    assets = client.get("/api/v3/skills/professional/asset-image-generation")
    assert assets.status_code == 200
    assets_detail = assets.json()
    assert assets_detail["version"] == "1.7.0"
    assert assets_detail["required_inputs"] == ["TARGET_STORYBOARD"]
    assert assets_detail["output_contracts"] == ["TARGET_ASSETS"]
    asset_rules = "\n".join(assets_detail["provider_rules"])
    assert "Character visual design must happen before model prompt compilation" in asset_rules
    assert "cannot invent identity facts" in asset_rules
    assert "three full-body views plus a face close-up" in assets_detail["manual"]
    assert "identity master" in assets_detail["manual"]
    assert "Image 1" in assets_detail["manual"]
    assert "Z-Image Turbo" in assets_detail["manual"]

    character_visual = client.get("/api/v3/skills/professional/character-visual-design")
    assert character_visual.status_code == 200
    character_visual_detail = character_visual.json()
    assert character_visual_detail["version"] == "1.1.0"
    assert character_visual_detail["required_inputs"] == ["TARGET_STORYBOARD"]
    assert character_visual_detail["optional_inputs"] == ["TARGET_BIBLE"]
    assert "CharacterVisualDesignPacket" in character_visual_detail["manual"]

    zimage = client.get("/api/v3/skills/professional/z-image-turbo-asset-prompting")
    assert zimage.status_code == 200
    zimage_detail = zimage.json()
    assert zimage_detail["version"] == "1.5.0"
    assert zimage_detail["required_inputs"] == ["TARGET_STORYBOARD"]
    assert zimage_detail["output_contracts"] == []
    zimage_rules = "\n".join(zimage_detail["provider_rules"])
    assert "single-character visual identity" in zimage_rules
    assert "face close-up is cropped from the front master" in zimage_rules
    assert "must not mention Runtime-owned layout vocabulary" in zimage_rules

    qwen = client.get("/api/v3/skills/professional/qwen-image-edit-character-asset-prompting")
    assert qwen.status_code == 200
    qwen_detail = qwen.json()
    assert qwen_detail["version"] == "1.0.0"
    assert qwen_detail["required_inputs"] == ["TARGET_STORYBOARD"]
    assert qwen_detail["output_contracts"] == []
    qwen_rules = "\n".join(qwen_detail["provider_rules"])
    assert "authoritative canonical identity" in qwen_rules
    assert "Only camera/person orientation may change" in qwen_rules
    assert "footwear" in qwen_rules

    h3 = client.get("/api/v3/skills/professional/minimax-h3-prompting")
    assert h3.status_code == 200
    h3_detail = h3.json()
    assert h3_detail["version"] == "1.1.0"
    assert h3_detail["required_inputs"] == ["TARGET_STORYBOARD", "TARGET_ASSETS"]
    assert h3_detail["output_contracts"] == ["GENERATION_SEGMENTS"]
    h3_rules = "\n".join(h3_detail["provider_rules"])
    assert "<Picture" in h3_rules
    assert "Chinese dialogue translations" in h3_rules
    assert "FACE and front FULL_BODY" in h3_rules
    assert "off-screen/voice-over" in h3_rules


def test_missing_professional_skill_returns_404(client: TestClient) -> None:
    response = client.get("/api/v3/skills/professional/not-found")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROFESSIONAL_SKILL_NOT_FOUND"


def test_capability_registry_keeps_new_five_step_capabilities_planned_until_real_acceptance(client: TestClient) -> None:
    response = client.get("/api/v3/skills/capabilities")
    assert response.status_code == 200
    capabilities = {item["id"]: item for item in response.json()}
    assert "EPISODE_UNDERSTANDING" in capabilities
    assert "STORY_RHYTHM" in capabilities
    assert "SHOT_BREAKDOWN" in capabilities
    assert "SOURCE_SNAPSHOT" in capabilities
    assert "STORYBOARD_LOCALIZATION" in capabilities
    assert "ASSET_IMAGE_GENERATION" in capabilities
    assert "MODEL_PROMPTING" in capabilities
    assert "VIDEO_GENERATION" in capabilities
    assert "QC_SELECTION" in capabilities
    assert capabilities["EPISODE_UNDERSTANDING"]["availability"] == "AVAILABLE"
    assert capabilities["STORY_RHYTHM"]["availability"] == "AVAILABLE"
    assert capabilities["STORY_RHYTHM"]["title"] == "故事与节奏"
    assert capabilities["SHOT_BREAKDOWN"]["availability"] == "AVAILABLE"
    assert capabilities["SOURCE_SNAPSHOT"]["availability"] == "AVAILABLE"

    # Historical accepted capabilities remain recorded; the new five-step capabilities must not be
    # promoted merely because code/tests exist. docs/55 requires real same-project human acceptance.
    assert capabilities["LOCALIZATION"]["availability"] == "AVAILABLE"
    assert capabilities["TARGET_BIBLE"]["availability"] == "AVAILABLE"
    assert capabilities["TARGET_SCRIPT"]["availability"] == "AVAILABLE"
    assert capabilities["TARGET_ASSETS"]["availability"] == "AVAILABLE"
    assert capabilities["STORYBOARD_LOCALIZATION"]["availability"] == "PLANNED"
    assert capabilities["ASSET_IMAGE_GENERATION"]["availability"] == "PLANNED"
    assert capabilities["MODEL_PROMPTING"]["availability"] == "PLANNED"
    assert capabilities["VIDEO_GENERATION"]["availability"] == "PLANNED"
    assert capabilities["QC_SELECTION"]["availability"] == "PLANNED"


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
