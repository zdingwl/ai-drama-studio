from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.service import expected_namespace
from app.core.errors import AppError
from app.projects.enums import ProjectType
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill, get_professional_skill_detail
from app.skills.registry import get_root_skill
from app.source_resolution.schemas import CharacterResolutionSemantic
from app.source_resolution import service, service_v2
from app.workflow.models import TaskStatus


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P9-contract",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_p9_professional_skills_are_machine_loadable_and_preserve_boundaries() -> None:
    expected = {
        "character-resolution": (Capability.IDENTITY_RESOLUTION, ArtifactType.SOURCE_CHARACTERS),
        "speaker-attribution": (Capability.IDENTITY_RESOLUTION, ArtifactType.SOURCE_SPEAKERS),
        "scene-resolution": (Capability.SCENE_RESOLUTION, ArtifactType.SOURCE_SCENES),
        "prop-resolution": (Capability.PROP_RESOLUTION, ArtifactType.SOURCE_PROPS),
    }
    for skill_id, (capability, output) in expected.items():
        skill = get_professional_skill(skill_id)
        detail = get_professional_skill_detail(skill_id)
        rules = "\n".join(detail.provider_rules)
        assert skill.version == "1.0.0"
        assert skill.required_capabilities == (capability,)
        assert skill.output_contracts == (output,)
        assert ArtifactType.SOURCE_VIDEO in skill.required_inputs
        assert ArtifactType.SOURCE_BIBLE in skill.required_inputs
        assert ArtifactType.SOURCE_SHOT_FACTS in skill.required_inputs
        assert ArtifactType.SHOT_ANCHORS in skill.required_inputs
        assert "完整 Episode" in rules or "全集" in rules
        assert "UNKNOWN" in rules or "UNRESOLVED" in rules
        assert "P5" in detail.manual
        assert "P10" in detail.manual

    speaker = get_professional_skill("speaker-attribution")
    assert ArtifactType.SOURCE_DIALOGUE in speaker.required_inputs
    assert ArtifactType.SOURCE_CHARACTERS in speaker.required_inputs
    speaker_rules = "\n".join(get_professional_skill_detail("speaker-attribution").provider_rules)
    assert "一一对应" in speaker_rules


def test_replica_root_skill_exposes_p9_speaker_artifact_without_entering_p10() -> None:
    skill = get_root_skill(ProjectType.REPLICA)
    assert "speaker-attribution" in skill.subskills
    assert ArtifactType.SOURCE_SPEAKERS in skill.readable_artifacts
    source_breakdown = next(step for step in skill.steps if step.id == "source_breakdown")
    assert ArtifactType.SOURCE_SPEAKERS in source_breakdown.produces
    source_finalize = next(step for step in skill.steps if step.id == "source_finalize")
    assert source_finalize.produces == (ArtifactType.SOURCE_VIDEO_SNAPSHOT,)


def test_p9_artifacts_are_source_namespace_and_accepted_capabilities_are_available() -> None:
    for artifact_type in (
        ArtifactType.SOURCE_CHARACTERS,
        ArtifactType.SOURCE_SPEAKERS,
        ArtifactType.SOURCE_SCENES,
        ArtifactType.SOURCE_PROPS,
    ):
        assert expected_namespace(artifact_type) == ArtifactNamespace.SOURCE

    assert CAPABILITY_BY_ID[Capability.IDENTITY_RESOLUTION].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.SCENE_RESOLUTION].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.PROP_RESOLUTION].availability == CapabilityAvailability.AVAILABLE
    # P10 has passed real product acceptance; P9's historical regression must follow the
    # current accepted capability baseline rather than freezing the old pre-P10 state.
    assert CAPABILITY_BY_ID[Capability.SOURCE_SNAPSHOT].availability == CapabilityAvailability.AVAILABLE


def test_p9_provider_schema_rejects_manual_truth_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CharacterResolutionSemantic.model_validate(
            {
                "groups": [
                    {
                        "group_key": "g1",
                        "display_name": "角色A",
                        "confidence": 1.0,
                        "resolution_status": "MANUAL_CONFIRMED",
                        "evidence_refs": [],
                    }
                ],
                "observations": [],
            }
        )

    with pytest.raises(ValidationError):
        CharacterResolutionSemantic.model_validate(
            {
                "groups": [],
                "observations": [
                    {
                        "shot_anchor_id": "shot-1",
                        "source_candidate_id": "char-a",
                        "group_key": None,
                        "resolution_status": "UNKNOWN",
                        "invented_final_character_name": "不得出现",
                    }
                ],
            }
        )


def test_p9_get_is_read_only_and_post_requires_hard_inputs(client: TestClient) -> None:
    project = _project(client)
    before = client.get(f"/api/v3/projects/{project['id']}/tasks")
    assert before.status_code == 200

    result = client.get(f"/api/v3/projects/{project['id']}/source-resolution")
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["characters"]["status"] == "NOT_BUILT"
    assert payload["speakers"]["status"] == "NOT_BUILT"
    assert payload["scenes"]["status"] == "NOT_BUILT"
    assert payload["props"]["status"] == "NOT_BUILT"

    after = client.get(f"/api/v3/projects/{project['id']}/tasks")
    assert after.status_code == 200
    assert after.json() == before.json()

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/source-resolution",
        headers={"Idempotency-Key": "p9-missing-inputs"},
    )
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "SOURCE_VIDEO_REQUIRED"


def test_p9_new_explicit_command_retries_identical_failed_business_task(monkeypatch) -> None:
    failed = SimpleNamespace(
        status=TaskStatus.FAILED,
        id="task-1",
        idempotency_key="first-key",
    )
    retried = SimpleNamespace(status=TaskStatus.QUEUED, id="task-1", idempotency_key="first-key")
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(service_v2._base, "create_source_resolution_task", lambda db, project_id, idempotency_key: failed)
    monkeypatch.setattr(
        service_v2,
        "retry_task",
        lambda db, project_id, task_id: calls.append((project_id, task_id)) or retried,
    )

    result = service_v2.create_source_resolution_task(object(), project_id="project-1", idempotency_key="second-key")
    assert result is retried
    assert calls == [("project-1", "task-1")]

    calls.clear()
    replay = service_v2.create_source_resolution_task(object(), project_id="project-1", idempotency_key="first-key")
    assert replay is failed
    assert calls == []


def test_p9_command_fails_before_provider_when_migration_is_missing(monkeypatch) -> None:
    db = SimpleNamespace(get_bind=lambda: object())
    monkeypatch.setattr(service, "inspect", lambda _bind: SimpleNamespace(has_table=lambda _name: False))

    with pytest.raises(AppError) as captured:
        service._assert_p9_storage_ready(db)

    assert captured.value.code == "P9_DATABASE_MIGRATION_REQUIRED"
