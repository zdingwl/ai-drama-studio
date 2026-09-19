from types import SimpleNamespace
import pytest
from app.core.errors import AppError

from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.projects.enums import AudioPolicy, ProjectType, SceneStrategy
from app.projects.models import Project
from app.replica_pipeline import h3_prompting as h3_prompting_module
from app.skills.models import ArtifactType
from app.workflow.models import TaskStatus
from app.sources.models import Episode, SourceAsset
from app.sources.enums import SourceAssetKind


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
        source = SourceAsset(project_id=project.id, asset_kind=SourceAssetKind.VIDEO, original_filename='test.mp4', mime_type='video/mp4', size_bytes=1, sha256='f'*64, relative_path='test.mp4')
        db.add(source)
        db.flush()
        episode = Episode(project_id=project.id, source_asset_id=source.id, episode_order=1, duration_us=1_000_000, width=100, height=100, codec_name='h264', avg_frame_rate='25/1')
        db.add(episode)
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
            lambda *_: (storyboard_artifact, SimpleNamespace(shots=[SimpleNamespace(episode_id=episode.id)]), assets_artifact, SimpleNamespace()),
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
            episode_id=episode.id,
        )
        second = h3_prompting_module.create_h3_prompt_task(
            db,
            project_id=project.id,
            idempotency_key="h3-prompt-generation-2",
            episode_id=episode.id,
        )
        repeated_second = h3_prompting_module.create_h3_prompt_task(
            db,
            project_id=project.id,
            idempotency_key="h3-prompt-generation-2",
            episode_id=episode.id,
        )

        assert first.status == TaskStatus.QUEUED
        assert first.episode_id == episode.id
        assert second.status == TaskStatus.QUEUED
        assert first.id != second.id
        assert first.input_fingerprint != second.input_fingerprint
        assert first.checkpoint_json["h3_prompt_generation_sequence"] == 1
        assert second.checkpoint_json["h3_prompt_generation_sequence"] == 2
        assert repeated_second.id == second.id
        assert repeated_second.checkpoint_json["h3_prompt_generation_sequence"] == 2


def test_episode_regeneration_preserves_other_episode_exactly():
    old1 = SimpleNamespace(episode_id='e1', episode_order=1, segment_number=1, prompt='old')
    old2 = SimpleNamespace(episode_id='e2', episode_order=2, segment_number=1, prompt='keep')
    new1 = SimpleNamespace(episode_id='e1', episode_order=1, segment_number=1, prompt='new')
    result = h3_prompting_module._merge_episode_segments([old1, old2], [new1], 'e1')
    assert result == [new1, old2]
    assert result[1] is old2
    with pytest.raises(AppError):
        h3_prompting_module._merge_episode_segments([old1], [old2], 'e1')
    with pytest.raises(AppError):
        h3_prompting_module._merge_episode_segments([old1], [], 'e1')


def _legacy_h3_provenance() -> dict:
    return {
        "target_storyboard_artifact_id": "storyboard-artifact",
        "target_storyboard_revision": 1,
        "target_storyboard_fingerprint": "a" * 64,
        "target_assets_artifact_id": "assets-artifact",
        "target_assets_revision": 1,
        "target_assets_fingerprint": "b" * 64,
        "professional_skill_id": "minimax-h3-prompting",
        "professional_skill_version": "1.0.0",
        "model_id": "MiniMaxAI/MiniMax-H3",
        "prompt_contract": "minimax-h3-ref2va-v1",
        "prompt_provider": "legacy-provider",
        "prompt_model": "legacy-model",
        "provider_jobs": [
            {
                "provider_job_id": "provider-job-1",
                "provider": "legacy-provider",
                "model": "legacy-model",
                "payload_fingerprint": "c" * 64,
            }
        ],
        "generated_by_task_id": "legacy-task",
    }


def test_read_legacy_h3_prompt_provenance_falls_back_to_artifact_revision() -> None:
    raw = _legacy_h3_provenance()
    artifact = SimpleNamespace(metadata_json={}, revision=3)

    provenance = h3_prompting_module._read_h3_prompt_provenance(raw, artifact)

    assert provenance.generation_sequence == 3
    assert "generation_sequence" not in raw


def test_read_legacy_h3_prompt_provenance_prefers_metadata_generation_sequence() -> None:
    raw = _legacy_h3_provenance()
    artifact = SimpleNamespace(metadata_json={"generation_sequence": 7}, revision=3)

    provenance = h3_prompting_module._read_h3_prompt_provenance(raw, artifact)

    assert provenance.generation_sequence == 7
