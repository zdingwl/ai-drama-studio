from types import SimpleNamespace

from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.projects.enums import AudioPolicy, ProjectType, SceneStrategy
from app.projects.models import Project
from app.replica_pipeline import h3_prompting as h3_prompting_module
from app.skills.models import ArtifactType
from app.workflow.models import TaskStatus


def test_explicit_h3_prompt_regeneration_creates_new_task_generation(
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    with session_factory() as db:
        project = Project(
            name="H3 prompt regenerate",
            project_type=ProjectType.REPLICA,
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
            scene_strategy=SceneStrategy.LOCALIZE,
            audio_policy=AudioPolicy.REGENERATE_AUDIO,
            visual_style="写实电影感",
            root_skill_id="replica",
            root_skill_version="1.0.0",
        )
        db.add(project)
        db.flush()
        storyboard_artifact = ArtifactNode(
            project_id=project.id,
            artifact_type=ArtifactType.TARGET_STORYBOARD.value,
            namespace=ArtifactNamespace.TARGET,
            label="本土化分镜表",
            revision=1,
            input_fingerprint="a" * 64,
            skill_id="storyboard-localization",
            skill_version="1.0.0",
            validity=ArtifactValidity.CURRENT,
            is_current=True,
            metadata_json={},
        )
        assets_artifact = ArtifactNode(
            project_id=project.id,
            artifact_type=ArtifactType.TARGET_ASSETS.value,
            namespace=ArtifactNamespace.TARGET,
            label="目标资产图",
            revision=1,
            input_fingerprint="b" * 64,
            skill_id="asset-image-generation",
            skill_version="1.6.0",
            validity=ArtifactValidity.CURRENT,
            is_current=True,
            metadata_json={},
        )
        db.add_all([storyboard_artifact, assets_artifact])
        db.commit()
        db.refresh(project)
        db.refresh(storyboard_artifact)
        db.refresh(assets_artifact)
        binding = SimpleNamespace(model_id="MiniMaxAI/MiniMax-H3", prompt_contract="minimax-h3-ref2va-v1")
        skill = SimpleNamespace(id="minimax-h3-prompting", version="1.1.0")
        provider = SimpleNamespace(
            provider_name="test-provider",
            model_name="test-model",
            profile=lambda: {"provider": "test-provider", "model": "test-model"},
        )

        monkeypatch.setattr(
            h3_prompting_module,
            "_load_inputs",
            lambda *_: (storyboard_artifact, SimpleNamespace(), assets_artifact, SimpleNamespace()),
        )
        monkeypatch.setattr(
            h3_prompting_module,
            "selected_video_model_prompt_skill",
            lambda *_: (binding, skill),
        )
        monkeypatch.setattr(h3_prompting_module, "_prompt_author_provider", lambda *_: provider)

        first = h3_prompting_module.create_h3_prompt_task(
            db,
            project_id=project.id,
            idempotency_key="h3-prompt-generation-1",
        )
        second = h3_prompting_module.create_h3_prompt_task(
            db,
            project_id=project.id,
            idempotency_key="h3-prompt-generation-2",
        )
        repeated_second = h3_prompting_module.create_h3_prompt_task(
            db,
            project_id=project.id,
            idempotency_key="h3-prompt-generation-2",
        )

        assert first.status == TaskStatus.QUEUED
        assert second.status == TaskStatus.QUEUED
        assert first.id != second.id
        assert first.input_fingerprint != second.input_fingerprint
        assert first.checkpoint_json["h3_prompt_generation_sequence"] == 1
        assert second.checkpoint_json["h3_prompt_generation_sequence"] == 2
        assert repeated_second.id == second.id
        assert repeated_second.checkpoint_json["h3_prompt_generation_sequence"] == 2
