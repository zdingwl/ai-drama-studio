from app.projects.enums import ProjectType
from app.skills.models import ArtifactType, Capability
from app.skills.registry import get_root_skill


def _step_with_capability(project_type: ProjectType, capability: Capability):
    skill = get_root_skill(project_type)
    return next(step for step in skill.steps if capability in step.capabilities)


def test_replica_source_bible_is_internal_to_source_storyboard_stage() -> None:
    root = get_root_skill(ProjectType.REPLICA)
    step = _step_with_capability(ProjectType.REPLICA, Capability.EPISODE_UNDERSTANDING)

    assert root.version == "1.7.0"
    assert "source-video-understanding" in root.subskills
    assert ArtifactType.SOURCE_BIBLE in root.readable_artifacts
    assert step.id == "source_storyboard"
    assert step.title == "分析视频获取分镜表"
    assert step.requires == (ArtifactType.SOURCE_VIDEO,)
    assert Capability.SHOT_BREAKDOWN in step.capabilities
    assert Capability.SOURCE_SNAPSHOT in step.capabilities
    assert step.produces == (ArtifactType.SOURCE_SHOT_FACTS, ArtifactType.SOURCE_VIDEO_SNAPSHOT)


def test_redraw_source_bible_is_formal_source_overview_document() -> None:
    step = _step_with_capability(ProjectType.REDRAW, Capability.EPISODE_UNDERSTANDING)

    assert step.title == "源作概览分析"
    assert step.requires == (ArtifactType.SOURCE_VIDEO, ArtifactType.SOURCE_DIALOGUE)
    assert step.produces == (ArtifactType.SOURCE_BIBLE,)

    breakdown = _step_with_capability(ProjectType.REDRAW, Capability.SHOT_BREAKDOWN)
    assert ArtifactType.SOURCE_BIBLE in breakdown.requires
    assert ArtifactType.SHOT_ANCHORS in breakdown.requires


def test_source_truth_revision_policy_matches_each_current_root_contract() -> None:
    replica = get_root_skill(ProjectType.REPLICA)
    replica_policies = "\n".join((*replica.user_decision_policy, *replica.auto_decision_policy))
    assert ArtifactType.SOURCE_BIBLE in replica.readable_artifacts
    assert "Source Shot 顺序" in replica_policies
    assert "authoritative timing" in replica_policies

    redraw = get_root_skill(ProjectType.REDRAW)
    redraw_policies = "\n".join((*redraw.user_decision_policy, *redraw.auto_decision_policy))
    assert "SOURCE_BIBLE" in redraw_policies
    assert "STALE" in redraw_policies
    assert "canonical Source Evidence" in redraw_policies
