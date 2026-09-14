from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, expected_namespace
from app.core.errors import AppError
from app.projects.enums import ProjectType, SceneStrategy
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.skills.registry import get_root_skill
from app.source_script.schemas import SourceScriptContent
from app.target_bible import service
from app.target_bible.schemas import (
    LocalizationCategory,
    PreservationCategory,
    ProviderTargetCharacter,
    ProviderTargetProp,
    ProviderTargetScene,
    ProviderTargetWorld,
    ReplicaTargetBibleSemantic,
)
from app.workflow.models import ProviderJob, Task


_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _project(client: TestClient, project_type: str = "REPLICA") -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": f"P11-{project_type}",
            "project_type": project_type,
            "source_language": "zh-CN" if project_type in {"REPLICA", "REDRAW", "TRANSLATION"} else None,
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _semantic(*, include_prop: bool = True) -> ReplicaTargetBibleSemantic:
    return ReplicaTargetBibleSemantic(
        target_world=ProviderTargetWorld(
            setting_summary="美国城市公寓社区中的邻里冲突",
            cultural_context="保留邻里边界与货到付款冲突，用美国本地生活语境表达。",
            social_context="普通城市租住社区。",
            localization_principles=["不改变故事因果", "不改变反转顺序"],
        ),
        characters=[
            ProviderTargetCharacter(
                source_character_id="chr-src-1",
                display_name="Ryan",
                localized_identity="年轻上班族邻居",
                appearance_direction="日常都市休闲装",
                personality_constraints=["保持克制反击的故事功能"],
                continuity_rules=["发型与服装主色保持一致"],
                reason="本土化姓名与职业语境，不改变人物功能。",
            )
        ],
        scenes=[
            ProviderTargetScene(
                source_scene_id="scn-src-1",
                display_name="Ryan's Living Room",
                localized_setting="美国城市公寓客厅",
                visual_direction="现实主义住宅内景",
                continuity_rules=["门、沙发和入户动线保持连续"],
                reason="替换文化环境但保持场次功能。",
            )
        ],
        props=(
            [
                ProviderTargetProp(
                    source_prop_id="prop-src-1",
                    display_name="COD Parcel",
                    localized_form="本地快递货到付款包裹",
                    continuity_rules=["包裹外观在连续镜头保持一致"],
                    reason="保留剧情功能并换成本地包装。",
                )
            ]
            if include_prop
            else []
        ),
        visual_style="现实主义竖屏短剧，保留原片快节奏反应镜头。",
        continuity_rules=["人物年龄与核心造型跨场保持一致"],
        dialogue_style_rules=["使用自然美式口语", "称谓按邻里关系本土化"],
        adaptation_summary="故事与节奏完全保留，只替换人物身份、生活环境和文化表达。",
        localization_decisions=[],
    )


def _source_script_content() -> SourceScriptContent:
    return SourceScriptContent.model_validate(
        {
            "episodes": [
                {
                    "episode_id": "ep-1",
                    "episode_order": 1,
                    "source_filename": "episode.mp4",
                    "duration_us": 5_000_000,
                    "story_summary": "邻里冲突升级。",
                    "story_background": "现代住宅社区。",
                    "narrative_structure": "快速建立冲突并推进反击。",
                    "dialogue": [],
                    "story_segments": [],
                    "characters": [
                        {
                            "source_character_id": "chr-src-1",
                            "name": "徐然",
                            "story_function": "冲突主角",
                            "appearance_baseline": "年轻都市男性",
                        }
                    ],
                    "scenes": [
                        {
                            "source_scene_id": "scn-src-1",
                            "name": "徐然家客厅",
                            "time_ranges": [{"start_us": 0, "end_us": 5_000_000}],
                            "spatial_relationship": "住宅客厅",
                            "environment_details": "门、沙发与入户动线清晰",
                        }
                    ],
                    "props": [
                        {
                            "source_prop_id": "prop-src-1",
                            "name": "货到付款包裹",
                            "time_ranges": [{"start_us": 0, "end_us": 5_000_000}],
                            "appearance_state": "未拆封快递包裹",
                            "story_function": "冲突触发物",
                        }
                    ],
                    "story_skeleton": {
                        "premise": "邻里冲突升级",
                        "central_conflict": "拒绝代付",
                        "beats": [
                            {
                                "beat_type": "HOOK",
                                "time_range": {"start_us": 0, "end_us": 2_000_000},
                                "summary": "邻居再次把货到付款包裹推给主角",
                                "importance": 5,
                            }
                        ],
                    },
                    "rhythm_skeleton": {
                        "overall_pace": "快节奏冲突",
                        "phases": [
                            {
                                "time_range": {"start_us": 0, "end_us": 5_000_000},
                                "pace": "快",
                                "scene_rhythm": "快速进入冲突",
                                "dialogue_reaction_rhythm": "一句一反应",
                                "allowable_deviation_ms": 300,
                            }
                        ],
                    },
                }
            ]
        }
    )


def _compose_inputs() -> service.P11Inputs:
    project = SimpleNamespace(
        target_language="en-US",
        target_region="US",
        scene_strategy=SceneStrategy.MIXED,
        visual_style=None,
    )
    content = _source_script_content()
    return service.P11Inputs(
        project=project,
        source_script_artifact=SimpleNamespace(id="source-script-1", revision=1, input_fingerprint=_SHA_A),
        source_script_revision=SimpleNamespace(),
        source_script_content=content,
        preservation_locks=service._build_preservation_locks(content),
    )


def test_p11_professional_skill_is_script_first_but_not_replica_main_chain() -> None:
    skill = get_professional_skill("replica-target-bible")
    assert skill.version == "1.1.0"
    assert skill.required_inputs == (ArtifactType.SOURCE_SCRIPT,)
    assert skill.required_capabilities == (Capability.LOCALIZATION, Capability.TARGET_BIBLE)
    assert skill.output_contracts == (ArtifactType.ADAPTATION_PLAN, ArtifactType.TARGET_BIBLE)

    root = get_root_skill(ProjectType.REPLICA)
    assert root.version == "1.7.0"
    assert "replica-target-bible" not in root.subskills
    assert all(ArtifactType.ADAPTATION_PLAN not in step.produces for step in root.steps)
    assert all(ArtifactType.TARGET_BIBLE not in step.produces for step in root.steps)
    localized = next(step for step in root.steps if step.id == "localized_storyboard")
    assert localized.requires == (ArtifactType.SOURCE_VIDEO_SNAPSHOT,)
    assert localized.produces == (ArtifactType.TARGET_STORYBOARD,)

    assert CAPABILITY_BY_ID[Capability.SOURCE_SNAPSHOT].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.LOCALIZATION].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.TARGET_BIBLE].availability == CapabilityAvailability.AVAILABLE
    assert CAPABILITY_BY_ID[Capability.TARGET_SCRIPT].availability == CapabilityAvailability.AVAILABLE
    assert expected_namespace(ArtifactType.ADAPTATION_PLAN) == ArtifactNamespace.TARGET
    assert expected_namespace(ArtifactType.TARGET_BIBLE) == ArtifactNamespace.TARGET


def test_p11_get_is_read_only_and_command_requires_current_source_script(
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
    result = client.get(f"/api/v3/projects/{project['id']}/target-bible")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "NOT_BUILT"
    revisions = client.get(f"/api/v3/projects/{project['id']}/target-bible/revisions")
    assert revisions.status_code == 200, revisions.text
    assert revisions.json() == []
    assert counts() == before

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-bible",
        headers={"Idempotency-Key": "p11-no-source-script"},
    )
    assert start.status_code == 409, start.text
    assert start.json()["error"]["code"] == "SOURCE_SCRIPT_REQUIRED"
    assert counts() == before


def test_p11_non_replica_fails_closed_without_side_effects(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client, "REDRAW")
    read = client.get(f"/api/v3/projects/{project['id']}/target-bible")
    assert read.status_code == 422, read.text
    assert read.json()["error"]["code"] == "REPLICA_TARGET_BIBLE_NOT_ALLOWED"

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-bible",
        headers={"Idempotency-Key": "redraw-p11-forbidden"},
    )
    assert start.status_code == 422, start.text
    with session_factory() as db:
        assert int(db.scalar(select(func.count()).select_from(Task)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0) == 0


def test_p11_provider_semantic_requires_exact_source_identity_coverage() -> None:
    inputs = _compose_inputs()
    service._validate_semantic(inputs, _semantic())
    with pytest.raises(AppError) as captured:
        service._validate_semantic(inputs, _semantic(include_prop=False))
    assert captured.value.code == "P11_PROP_COVERAGE_INVALID"


def test_p11_compose_creates_distinct_target_ids_and_keeps_source_lineage() -> None:
    inputs = _compose_inputs()
    plan, bible = service._compose(inputs, _semantic())
    assert bible.characters[0].source_character_id == "chr-src-1"
    assert bible.characters[0].target_character_id != "chr-src-1"
    assert bible.scenes[0].source_scene_id == "scn-src-1"
    assert bible.scenes[0].target_scene_id != "scn-src-1"
    assert bible.props[0].source_prop_id == "prop-src-1"
    assert bible.props[0].target_prop_id != "prop-src-1"
    assert plan.source_script_artifact_id == "source-script-1"
    assert plan.source_snapshot_artifact_id is None
    assert {item.category for item in plan.localization_decisions} >= {
        LocalizationCategory.CHARACTER,
        LocalizationCategory.SCENE,
        LocalizationCategory.PROP,
    }
    assert bible.dialogue_style_rules == ["使用自然美式口语", "称谓按邻里关系本土化"]


def test_p11_preservation_locks_are_service_generated_from_source_script() -> None:
    content = _source_script_content()
    locks = service._build_preservation_locks(content)
    categories = {item.category for item in locks}
    assert PreservationCategory.STORY_MAINLINE in categories
    assert PreservationCategory.HOOK in categories
    assert PreservationCategory.STORY_BEAT_TIMING in categories
    assert PreservationCategory.SHOT_RHYTHM in categories
    assert PreservationCategory.ACTION_RHYTHM in categories
    assert PreservationCategory.SCENE_ORDER not in categories
    assert PreservationCategory.SHOT_LOGIC not in categories
    assert locks == service._build_preservation_locks(content)


def test_p11_source_script_revision_recursively_stales_target_graph(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        script_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_SCRIPT,
            namespace=ArtifactNamespace.SOURCE,
            label="Source Script v1",
            input_fingerprint=_SHA_A,
            skill_id="source-video-understanding",
            skill_version="1.2.0",
        )
        plan = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.ADAPTATION_PLAN,
            namespace=ArtifactNamespace.TARGET,
            label="Target plan",
            input_fingerprint=_SHA_A,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        bible = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Target Bible",
            input_fingerprint=_SHA_B,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=script_v1.id,
            target_node_id=plan.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=plan.id,
            target_node_id=bible.id,
            relation_type=ArtifactRelationType.USES,
        )
        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_SCRIPT,
            namespace=ArtifactNamespace.SOURCE,
            label="Source Script v2",
            input_fingerprint="c" * 64,
            skill_id="source-video-understanding",
            skill_version="1.2.0",
        )
        for artifact_id in (script_v1.id, plan.id, bible.id):
            artifact = db.get(ArtifactNode, artifact_id)
            assert artifact is not None
            assert artifact.validity == ArtifactValidity.STALE
            assert artifact.is_current is False


def test_p11_target_config_change_stales_existing_target_world(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        plan = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.ADAPTATION_PLAN,
            namespace=ArtifactNamespace.TARGET,
            label="Target plan",
            input_fingerprint=_SHA_A,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        bible = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Target Bible",
            input_fingerprint=_SHA_B,
            skill_id="replica-target-bible",
            skill_version="1.1.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=plan.id,
            target_node_id=bible.id,
            relation_type=ArtifactRelationType.USES,
        )

    changed = client.patch(
        f"/api/v3/projects/{project['id']}",
        json={"target_region": "CA"},
    )
    assert changed.status_code == 200, changed.text
    with session_factory() as db:
        for artifact_id in (plan.id, bible.id):
            artifact = db.get(ArtifactNode, artifact_id)
            assert artifact is not None
            assert artifact.validity == ArtifactValidity.STALE
            assert artifact.is_current is False
