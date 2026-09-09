from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill, get_professional_skill_detail


def test_episode_understanding_professional_skill_is_machine_loadable() -> None:
    skill = get_professional_skill("source-video-understanding")

    assert skill.version == "1.1.0"
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

    assert "UNKNOWN 不是" in rules
    assert "社会学泛化" in rules
    assert "canonical" in rules
    assert "P8" in rules
    assert "grounded-source-truth-v2" in detail.manual
    assert "FACT" in detail.manual
    assert "INFERENCE" in detail.manual
    assert "UNKNOWN" in detail.manual
    assert "完整 Episode" in detail.manual
    assert "逐 Shot" in detail.manual


def test_shot_breakdown_professional_skill_is_machine_loadable() -> None:
    skill = get_professional_skill("shot-breakdown")

    assert skill.version == "1.0.0"
    assert skill.required_inputs == (
        ArtifactType.SOURCE_VIDEO,
        ArtifactType.SOURCE_BIBLE,
        ArtifactType.SHOT_ANCHORS,
        ArtifactType.SOURCE_DIALOGUE,
    )
    assert skill.optional_inputs == ()
    assert skill.required_capabilities == (Capability.SHOT_BREAKDOWN,)
    assert skill.output_contracts == (ArtifactType.SOURCE_SHOT_FACTS,)


def test_shot_breakdown_skill_preserves_p5_p6_p7_authority_and_p9_boundary() -> None:
    detail = get_professional_skill_detail("shot-breakdown")
    rules = "\n".join(detail.provider_rules)

    assert "完整 Episode" in rules
    assert "CURRENT P5" in rules
    assert "CURRENT P6" in rules
    assert "CURRENT SOURCE_BIBLE" in rules
    assert "不得输出 speaker attribution" in rules
    assert "Reference Clip" in rules
    assert "source-bible-shot-facts-v1" in detail.manual
    assert "P9" in detail.manual
