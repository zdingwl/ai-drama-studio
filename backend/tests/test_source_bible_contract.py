from app.projects.enums import ProjectType
from app.skills.models import ArtifactType, Capability
from app.skills.registry import get_root_skill


def _step_with_capability(project_type: ProjectType, capability: Capability):
    skill = get_root_skill(project_type)
    return next(step for step in skill.steps if capability in step.capabilities)


def test_replica_source_bible_is_formal_source_overview_document() -> None:
    step = _step_with_capability(ProjectType.REPLICA, Capability.EPISODE_UNDERSTANDING)

    assert step.title == "源作概览分析"
    assert step.requires == (ArtifactType.SOURCE_VIDEO, ArtifactType.SOURCE_DIALOGUE)
    assert ArtifactType.SOURCE_BIBLE in step.produces

    breakdown = _step_with_capability(ProjectType.REPLICA, Capability.SHOT_BREAKDOWN)
    assert ArtifactType.SOURCE_BIBLE in breakdown.requires
    assert ArtifactType.SHOT_ANCHORS in breakdown.requires


def test_redraw_source_bible_is_formal_source_overview_document() -> None:
    step = _step_with_capability(ProjectType.REDRAW, Capability.EPISODE_UNDERSTANDING)

    assert step.title == "源作概览分析"
    assert step.requires == (ArtifactType.SOURCE_VIDEO, ArtifactType.SOURCE_DIALOGUE)
    assert step.produces == (ArtifactType.SOURCE_BIBLE,)

    breakdown = _step_with_capability(ProjectType.REDRAW, Capability.SHOT_BREAKDOWN)
    assert ArtifactType.SOURCE_BIBLE in breakdown.requires
    assert ArtifactType.SHOT_ANCHORS in breakdown.requires


def test_source_overview_revision_policy_preserves_canonical_evidence() -> None:
    for project_type in (ProjectType.REPLICA, ProjectType.REDRAW):
        skill = get_root_skill(project_type)
        policies = "\n".join((*skill.user_decision_policy, *skill.auto_decision_policy))

        assert "SOURCE_BIBLE" in policies
        assert "STALE" in policies
        assert "canonical Source Evidence" in policies
