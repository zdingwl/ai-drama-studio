from app.projects.enums import ProjectType
from app.skills.models import ArtifactType, Capability
from app.skills.registry import get_root_skill


def _steps(project_type: ProjectType):
    skill = get_root_skill(project_type)
    return {step.id: step for step in skill.steps}


def test_replica_source_evidence_and_breakdown_are_internal_to_source_storyboard_stage() -> None:
    steps = _steps(ProjectType.REPLICA)
    source = steps["source_storyboard"]

    assert source.requires == (ArtifactType.SOURCE_VIDEO,)
    assert Capability.SHOT_BOUNDARY in source.capabilities
    assert Capability.SOURCE_DIALOGUE_EVIDENCE in source.capabilities
    assert Capability.EPISODE_UNDERSTANDING in source.capabilities
    assert Capability.SHOT_BREAKDOWN in source.capabilities
    assert Capability.SOURCE_SNAPSHOT in source.capabilities
    assert source.produces == (ArtifactType.SOURCE_SHOT_FACTS, ArtifactType.SOURCE_VIDEO_SNAPSHOT)


def test_redraw_whole_episode_understanding_precedes_shot_breakdown() -> None:
    steps = _steps(ProjectType.REDRAW)

    assert steps["shot_boundary"].requires == (ArtifactType.SOURCE_VIDEO,)
    assert steps["source_evidence"].requires == (ArtifactType.SOURCE_VIDEO,)
    assert steps["source_understand"].requires == (
        ArtifactType.SOURCE_VIDEO,
        ArtifactType.SOURCE_DIALOGUE,
    )
    assert steps["source_breakdown"].requires == (
        ArtifactType.SOURCE_BIBLE,
        ArtifactType.SHOT_ANCHORS,
    )


def test_translation_dialogue_evidence_is_independent_of_shot_anchors() -> None:
    steps = _steps(ProjectType.TRANSLATION)

    assert steps["shot_boundary"].requires == (ArtifactType.SOURCE_VIDEO,)
    assert steps["dialogue"].requires == (ArtifactType.SOURCE_VIDEO,)
    assert ArtifactType.SHOT_ANCHORS not in steps["dialogue"].requires
    assert ArtifactType.SHOT_ANCHORS in steps["voice_timing"].requires
