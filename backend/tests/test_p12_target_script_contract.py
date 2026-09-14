from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, expected_namespace
from app.core.errors import AppError
from app.projects.enums import ProjectType
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.skills.registry import get_root_skill
from app.target_script import service
from app.target_script.schemas import ProviderLocalizedDialogue, TargetScriptSemantic
from app.workflow.models import ProviderJob, Task


_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _project(client: TestClient, project_type: str = "REPLICA") -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": f"P12-{project_type}",
            "project_type": project_type,
            "source_language": "zh-CN" if project_type in {"REPLICA", "REDRAW", "TRANSLATION"} else None,
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _compose_inputs() -> service.P12Inputs:
    source_utterance = SimpleNamespace(
        utterance_id="utt-1",
        utterance_number=1,
        start_us=1_000_000,
        end_us=2_000_000,
        text="你别替我做决定。",
        language="zh-CN",
        source_character_id="chr-src-1",
        speaker_name="徐然",
    )
    source_script_content = SimpleNamespace(
        episodes=[
            SimpleNamespace(
                episode_id="ep-1",
                episode_order=1,
                dialogue=[source_utterance],
            )
        ]
    )
    target_bible = SimpleNamespace(
        characters=[SimpleNamespace(source_character_id="chr-src-1", target_character_id="tchr-1")]
    )
    return service.P12Inputs(
        project=SimpleNamespace(target_language="en-US", target_region="US"),
        source_script_artifact=SimpleNamespace(id="source-script-1", revision=3, input_fingerprint=_SHA_A),
        source_script_revision=SimpleNamespace(),
        source_script_content=source_script_content,
        adaptation_plan_artifact=SimpleNamespace(id="plan-1", revision=2, input_fingerprint=_SHA_B),
        adaptation_plan_revision=SimpleNamespace(),
        adaptation_plan=SimpleNamespace(),
        target_bible_artifact=SimpleNamespace(id="bible-1", revision=2, input_fingerprint="c" * 64),
        target_bible_revision=SimpleNamespace(),
        target_bible=target_bible,
    )


def _semantic(utterance_id: str = "utt-1") -> TargetScriptSemantic:
    return TargetScriptSemantic(
        dialogue=[
            ProviderLocalizedDialogue(
                utterance_id=utterance_id,
                translation_text="Don't make decisions for me.",
                localization_text="Don't decide that for me.",
                final_target_dialogue="Don't decide for me.",
                localization_notes=["natural spoken US English"],
            )
        ]
    )


def test_p12_professional_skill_is_script_first_but_not_replica_main_chain() -> None:
    skill = get_professional_skill("target-script-localization")
    assert skill.version == "1.2.0"
    assert skill.required_inputs == (
        ArtifactType.SOURCE_SCRIPT,
        ArtifactType.ADAPTATION_PLAN,
        ArtifactType.TARGET_BIBLE,
    )
    assert skill.required_capabilities == (Capability.TARGET_SCRIPT,)
    assert skill.output_contracts == (ArtifactType.TARGET_SCRIPT,)

    root = get_root_skill(ProjectType.REPLICA)
    assert root.version == "1.7.0"
    assert "target-script-localization" not in root.subskills
    assert all(ArtifactType.TARGET_SCRIPT not in step.requires for step in root.steps)
    assert all(ArtifactType.TARGET_SCRIPT not in step.produces for step in root.steps)
    localized = next(step for step in root.steps if step.id == "localized_storyboard")
    assert localized.requires == (ArtifactType.SOURCE_VIDEO_SNAPSHOT,)
    assert localized.produces == (ArtifactType.TARGET_STORYBOARD,)

    assert service.P12_FORMALLY_ADMITTED is True
    service._assert_p12_admitted()
    assert CAPABILITY_BY_ID[Capability.LOCALIZATION].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.TARGET_BIBLE].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.TARGET_SCRIPT].availability == CapabilityAvailability.AVAILABLE
    assert expected_namespace(ArtifactType.TARGET_SCRIPT) == ArtifactNamespace.TARGET


def test_p12_get_is_read_only_and_post_requires_current_script_first_inputs(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)

    def counts() -> tuple[int, int, int]:
        with session_factory() as db:
            return (
                int(db.scalar(select(func.count()).select_from(ArtifactNode)) or 0),
                int(db.scalar(select(func.count()).select_from(Task)) or 0),
                int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0),
            )

    before = counts()
    read = client.get(f"/api/v3/projects/{project['id']}/target-script")
    assert read.status_code == 200, read.text
    assert read.json()["status"] == "NOT_BUILT"
    revisions = client.get(f"/api/v3/projects/{project['id']}/target-script/revisions")
    assert revisions.status_code == 200, revisions.text
    assert revisions.json() == []
    assert counts() == before

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-script",
        headers={"Idempotency-Key": "p12-missing-hard-inputs"},
    )
    assert start.status_code == 409, start.text
    assert start.json()["error"]["code"] == "P12_SOURCE_SCRIPT_REQUIRED"
    assert counts() == before


def test_p12_non_replica_fails_closed_without_side_effects(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client, "REDRAW")
    read = client.get(f"/api/v3/projects/{project['id']}/target-script")
    assert read.status_code == 422, read.text
    assert read.json()["error"]["code"] == "REPLICA_TARGET_SCRIPT_NOT_ALLOWED"

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-script",
        headers={"Idempotency-Key": "p12-redraw-forbidden"},
    )
    assert start.status_code == 422, start.text
    assert start.json()["error"]["code"] == "REPLICA_TARGET_SCRIPT_NOT_ALLOWED"
    with session_factory() as db:
        assert int(db.scalar(select(func.count()).select_from(Task)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0) == 0


def test_p12_provider_must_exactly_cover_canonical_utterances_in_order() -> None:
    inputs = _compose_inputs()
    service._validate_semantic(inputs, _semantic())
    with pytest.raises(AppError) as captured:
        service._validate_semantic(inputs, _semantic("made-up-utterance"))
    assert captured.value.code == "P12_DIALOGUE_COVERAGE_INVALID"


def test_p12_compose_copies_canonical_source_truth_and_keeps_three_target_text_layers() -> None:
    result = service._compose(_compose_inputs(), _semantic())
    assert len(result.episodes) == 1
    line = result.episodes[0].dialogue[0]
    assert line.utterance_id == "utt-1"
    assert line.utterance_number == 1
    assert line.source_start_us == 1_000_000
    assert line.source_end_us == 2_000_000
    assert line.source_text == "你别替我做决定。"
    assert line.source_language == "zh-CN"
    assert line.target_character_id == "tchr-1"
    assert line.translation_text == "Don't make decisions for me."
    assert line.localization_text == "Don't decide that for me."
    assert line.final_target_dialogue == "Don't decide for me."
    assert result.source_script_artifact_id == "source-script-1"
    assert result.source_snapshot_artifact_id is None
    assert result.adaptation_plan_artifact_id == "plan-1"
    assert result.target_bible_artifact_id == "bible-1"


def test_p12_unknown_source_character_does_not_let_provider_guess_target_character() -> None:
    inputs = _compose_inputs()
    inputs.source_script_content.episodes[0].dialogue[0].source_character_id = None
    result = service._compose(inputs, _semantic())
    assert result.episodes[0].dialogue[0].target_character_id is None


def test_p12_target_bible_revision_recursively_stales_compatibility_target_script_graph(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        source_script = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_SCRIPT,
            namespace=ArtifactNamespace.SOURCE,
            label="Source Script",
            input_fingerprint=_SHA_A,
            skill_id="source-video-understanding",
            skill_version="1.2.0",
        )
        plan = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.ADAPTATION_PLAN,
            namespace=ArtifactNamespace.TARGET,
            label="Plan",
            input_fingerprint=_SHA_A,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        bible_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Bible v1",
            input_fingerprint=_SHA_B,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        script = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET,
            label="Script",
            input_fingerprint="c" * 64,
            skill_id="target-script-localization",
            skill_version="1.2.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=source_script.id,
            target_node_id=script.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )
        for source in (plan, bible_v1):
            create_artifact_relation(
                db,
                project_id=project["id"],
                source_node_id=source.id,
                target_node_id=script.id,
                relation_type=ArtifactRelationType.USES,
            )

        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Bible v2",
            input_fingerprint="d" * 64,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        db.refresh(bible_v1)
        db.refresh(script)
        assert bible_v1.validity == ArtifactValidity.STALE
        assert bible_v1.is_current is False
        assert script.validity == ArtifactValidity.STALE
        assert script.is_current is False
