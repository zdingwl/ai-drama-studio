from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill, get_professional_skill_detail


def test_episode_understanding_professional_skill_is_machine_loadable() -> None:
    skill = get_professional_skill("source-video-understanding")

    assert skill.version == "1.0.0"
    assert skill.required_inputs == (ArtifactType.SOURCE_VIDEO, ArtifactType.SOURCE_DIALOGUE)
    assert skill.optional_inputs == (ArtifactType.SHOT_ANCHORS,)
    assert Capability.EPISODE_UNDERSTANDING in skill.required_capabilities
    assert Capability.STORY_RHYTHM in skill.required_capabilities
    assert ArtifactType.SOURCE_BIBLE in skill.output_contracts
    assert ArtifactType.STORY_SKELETON in skill.output_contracts
    assert ArtifactType.RHYTHM_SKELETON in skill.output_contracts


def test_episode_understanding_skill_manual_and_provider_rules_preserve_source_truth() -> None:
    detail = get_professional_skill_detail("source-video-understanding")
    rules = "\n".join(detail.provider_rules)

    assert "宁可 UNKNOWN" in rules
    assert "社会学泛化" in rules
    assert "canonical" in rules
    assert "P8" in rules
    assert "FACT" in detail.manual
    assert "INFERENCE" in detail.manual
    assert "UNKNOWN" in detail.manual
    assert "完整 Episode" in detail.manual
    assert "逐 Shot" in detail.manual
