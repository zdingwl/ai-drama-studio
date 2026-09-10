from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact
from app.core.errors import AppError
from app.skills.models import ArtifactType
from app.source_analysis.models import SourceStoryboardDraftRevision
from app.source_analysis.schemas import SourceAnalysisState, StoryboardShotEditCommand
from app.source_analysis import draft_service, script_service, service as source_analysis_service
from app.source_analysis.service import SOURCE_ANALYSIS_TASK_TYPE, create_source_analysis_task
from app.sources.enums import SourceAssetKind
from app.sources.models import Episode, SourceAsset
from app.workflow.models import ProviderJob, Task, TaskStatus


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "one-click-source-analysis",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_source(session_factory: sessionmaker[Session], project: dict) -> ArtifactNode:
    with session_factory() as db:
        asset = SourceAsset(
            project_id=project["id"],
            asset_kind=SourceAssetKind.VIDEO,
            original_filename="episode.mp4",
            mime_type="video/mp4",
            size_bytes=1024,
            sha256="a" * 64,
            relative_path=f'{project["id"]}/source/episode.mp4',
            immutable=True,
        )
        db.add(asset)
        db.flush()
        db.add(
            Episode(
                project_id=project["id"],
                source_asset_id=asset.id,
                episode_order=1,
                duration_us=5_000_000,
                width=1080,
                height=1920,
                codec_name="h264",
                avg_frame_rate="25/1",
                has_audio=True,
                probe_json={},
            )
        )
        db.commit()
        source = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_VIDEO,
            namespace=ArtifactNamespace.SOURCE,
            label="原片素材（1 集）",
            input_fingerprint="b" * 64,
            skill_id=project["root_skill_id"],
            skill_version=project["root_skill_version"],
            metadata_json={"episodes": []},
        )
        return source


def _camera():
    return SimpleNamespace(
        shot_size="中景",
        composition="双人构图",
        angle_or_type="平视",
        movement="固定",
        focal_length_dof="标准焦段",
    )


def _fact(
    shot_id: str,
    number: int,
    start: int,
    end: int,
    *,
    dialogue=None,
    visual_description: str | None = None,
):
    return SimpleNamespace(
        shot_anchor_id=shot_id,
        shot_number=number,
        start_us=start,
        end_us=end,
        duration_us=end - start,
        visual_description=visual_description or f"镜头 {number} 动作",
        camera_language=_camera(),
        dialogue=list(dialogue or []),
    )


def _dialogue(utterance_id: str, number: int, text: str):
    return SimpleNamespace(
        utterance_id=utterance_id,
        utterance_number=number,
        utterance_start_us=100,
        utterance_end_us=200,
        text=text,
        delivery="DIALOGUE",
    )


def test_source_analysis_get_is_read_only_and_one_command_creates_one_master_task(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    source = _seed_source(session_factory, project)

    response = client.get(f'/api/v3/projects/{project["id"]}/source-analysis')
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "NOT_READY"

    with session_factory() as db:
        assert db.scalar(select(func.count(Task.id))) == 0
        first = create_source_analysis_task(db, project_id=project["id"], idempotency_key="one-click-1")
        assert first is not None
        assert first.task_type == SOURCE_ANALYSIS_TASK_TYPE
        assert first.task_name == "解析原片"
        assert first.status == TaskStatus.QUEUED
        assert first.input_artifact_ids_json == [source.id]
        first_id = first.id

    with session_factory() as db:
        second = create_source_analysis_task(db, project_id=project["id"], idempotency_key="one-click-2")
        assert second is not None
        assert second.id == first_id
        assert db.scalar(select(func.count(Task.id))) == 1


def test_source_script_and_storyboard_draft_gets_are_read_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    _seed_source(session_factory, project)

    with session_factory() as db:
        before = (
            int(db.scalar(select(func.count(ArtifactNode.id))) or 0),
            int(db.scalar(select(func.count(Task.id))) or 0),
            int(db.scalar(select(func.count(ProviderJob.id))) or 0),
            int(db.scalar(select(func.count(SourceStoryboardDraftRevision.id))) or 0),
        )

    script = client.get(f'/api/v3/projects/{project["id"]}/source-script')
    draft = client.get(f'/api/v3/projects/{project["id"]}/storyboard-draft')

    assert script.status_code == 200, script.text
    assert script.json()["state"] == "NOT_READY"
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "NOT_BUILT"
    with session_factory() as db:
        after = (
            int(db.scalar(select(func.count(ArtifactNode.id))) or 0),
            int(db.scalar(select(func.count(Task.id))) or 0),
            int(db.scalar(select(func.count(ProviderJob.id))) or 0),
            int(db.scalar(select(func.count(SourceStoryboardDraftRevision.id))) or 0),
        )
    assert after == before


def test_source_analysis_skips_current_snapshot_without_creating_task(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    project = _project(client)
    _seed_source(session_factory, project)
    monkeypatch.setattr(
        source_analysis_service,
        "get_source_video_snapshot",
        lambda db, project_id: SimpleNamespace(status="CURRENT"),
    )

    with session_factory() as db:
        task = create_source_analysis_task(db, project_id=project["id"], idempotency_key="already-current")
        assert task is None
        assert db.scalar(select(func.count(Task.id))) == 0


def test_source_analysis_schedules_new_pipeline_after_success_becomes_stale(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    project = _project(client)
    _seed_source(session_factory, project)
    monkeypatch.setattr(
        source_analysis_service,
        "get_source_video_snapshot",
        lambda db, project_id: SimpleNamespace(status="STALE"),
    )

    with session_factory() as db:
        first = create_source_analysis_task(db, project_id=project["id"], idempotency_key="pipeline-first")
        assert first is not None
        first.status = TaskStatus.SUCCEEDED
        first.attempt = 1
        db.commit()
        first_id = first.id

    with session_factory() as db:
        second = create_source_analysis_task(db, project_id=project["id"], idempotency_key="pipeline-after-stale")
        assert second is not None
        assert second.id != first_id
        assert second.status == TaskStatus.QUEUED
        assert db.scalar(select(func.count(Task.id))) == 2


def test_source_analysis_child_failure_fails_top_level_task(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    project = _project(client)
    _seed_source(session_factory, project)
    monkeypatch.setattr(
        source_analysis_service,
        "get_source_video_snapshot",
        lambda db, project_id: SimpleNamespace(status="NOT_BUILT"),
    )
    with session_factory() as db:
        task = create_source_analysis_task(db, project_id=project["id"], idempotency_key="pipeline-fails")
        assert task is not None
        task_id = task.id

    def fail_pipeline(context, task):
        raise source_analysis_service.AppError("SOURCE_ANALYSIS_CHILD_FAILED", "对白识别失败", status_code=409)

    monkeypatch.setattr(source_analysis_service, "_execute_pipeline", fail_pipeline)
    source_analysis_service.run_source_analysis_task(session_factory, task_id)

    with session_factory() as db:
        failed = db.get(Task, task_id)
        assert failed is not None
        assert failed.status == TaskStatus.FAILED
        assert failed.last_error == "原片解析失败：对白识别失败"


def test_source_script_splits_scene_runs_at_episode_boundaries_and_dedupes_dialogue(monkeypatch) -> None:
    monkeypatch.setattr(
        script_service,
        "get_source_analysis_status",
        lambda db, project_id: SimpleNamespace(state=SourceAnalysisState.READY),
    )
    repeated = _dialogue("utt-1", 1, "同一句 canonical 台词")
    breakdown = SimpleNamespace(
        status="CURRENT",
        content=SimpleNamespace(
            title="原片剧本",
            episodes=[
                SimpleNamespace(
                    episode_id="episode-1",
                    shots=[
                        _fact("shot-1", 1, 0, 1_000_000, dialogue=[repeated]),
                        _fact("shot-2", 2, 1_000_000, 2_000_000, dialogue=[repeated]),
                    ],
                ),
                SimpleNamespace(
                    episode_id="episode-2",
                    shots=[_fact("shot-3", 3, 0, 1_000_000)],
                ),
            ],
        ),
    )
    resolution = SimpleNamespace(
        characters=SimpleNamespace(
            content=SimpleNamespace(
                entities=[SimpleNamespace(character_id="char-1", display_name="徐然", shot_anchor_ids=["shot-1", "shot-2", "shot-3"], notes=["手持手机"], evidence_refs=[])],
            )
        ),
        speakers=SimpleNamespace(
            content=SimpleNamespace(
                entities=[SimpleNamespace(speaker_id="speaker-1", display_name="徐然", character_id="char-1", utterance_ids=["utt-1"])],
                attributions=[SimpleNamespace(utterance_id="utt-1", speaker_id="speaker-1", text="同一句 canonical 台词")],
            )
        ),
        scenes=SimpleNamespace(
            content=SimpleNamespace(
                entities=[SimpleNamespace(scene_id="scene-home", display_name="徐然家客厅", shot_anchor_ids=["shot-1", "shot-2", "shot-3"], notes=[], evidence_refs=[])],
                assignments=[
                    SimpleNamespace(shot_anchor_id="shot-1", scene_id="scene-home"),
                    SimpleNamespace(shot_anchor_id="shot-2", scene_id="scene-home"),
                    SimpleNamespace(shot_anchor_id="shot-3", scene_id="scene-home"),
                ],
            )
        ),
        props=SimpleNamespace(content=SimpleNamespace(entities=[SimpleNamespace(prop_id="prop-1", display_name="手机", shot_anchor_ids=["shot-2"], notes=[], evidence_refs=[])])),
    )
    monkeypatch.setattr(script_service, "get_shot_breakdown", lambda db, project_id: breakdown)
    monkeypatch.setattr(script_service, "get_source_resolution", lambda db, project_id: resolution)

    result = script_service.get_source_script(SimpleNamespace(), "project-1")

    assert result.state == SourceAnalysisState.READY
    assert len(result.scenes) == 2
    assert [len(item.shots) for item in result.scenes] == [2, 1]
    assert result.scenes[0].scene_name == "徐然家客厅"
    assert sum(len(shot.dialogues) for scene in result.scenes for shot in scene.shots) == 1
    assert result.scenes[0].shots[0].dialogues[0].speaker_name == "徐然"
    assert result.characters[0].name == "徐然"
    assert result.props[0].name == "手机"
    assert result.character_assets[0].dialogue_count == 1
    assert result.character_assets[0].source_facts == ["手持手机"]
    assert [item.shot_number for item in result.character_assets[0].related_shots] == [1, 2, 3]
    assert result.scene_assets[0].shot_ranges == ["第1集 #001–#002", "第2集 #003"]
    assert result.prop_assets[0].representative_frame is not None
    assert result.prop_assets[0].representative_frame.thumbnail_url.endswith("/shot-2/thumbnail")


def test_source_script_action_summary_is_deterministic_and_does_not_treat_speaker_as_present(monkeypatch) -> None:
    monkeypatch.setattr(
        script_service,
        "get_source_analysis_status",
        lambda db, project_id: SimpleNamespace(state=SourceAnalysisState.READY),
    )
    breakdown = SimpleNamespace(
        status="CURRENT",
        content=SimpleNamespace(
            title="原片剧本",
            episodes=[SimpleNamespace(episode_id="episode-1", shots=[
                _fact(
                    "shot-1",
                    1,
                    0,
                    800_000,
                    dialogue=[_dialogue("utt-1", 1, "canonical 原文")],
                    visual_description="居民楼里摆着鞋柜。徐然站在王桂香门口。镜头类型：平视。构图：人物居中。",
                ),
            ])],
        ),
    )
    resolution = SimpleNamespace(
        characters=SimpleNamespace(content=SimpleNamespace(entities=[
            SimpleNamespace(character_id="char-xu", display_name="徐然", shot_anchor_ids=["shot-1"]),
            SimpleNamespace(character_id="char-wang", display_name="王桂香", shot_anchor_ids=[]),
        ])),
        speakers=SimpleNamespace(content=SimpleNamespace(
            entities=[SimpleNamespace(speaker_id="speaker-wang", display_name="王桂香", character_id="char-wang")],
            attributions=[SimpleNamespace(utterance_id="utt-1", speaker_id="speaker-wang", text="不得覆盖 canonical")],
        )),
        scenes=SimpleNamespace(content=SimpleNamespace(
            entities=[SimpleNamespace(scene_id="scene-hall", display_name="居民楼公共楼道")],
            assignments=[SimpleNamespace(shot_anchor_id="shot-1", scene_id="scene-hall")],
        )),
        props=SimpleNamespace(content=SimpleNamespace(entities=[])),
    )
    monkeypatch.setattr(script_service, "get_shot_breakdown", lambda db, project_id: breakdown)
    monkeypatch.setattr(script_service, "get_source_resolution", lambda db, project_id: resolution)

    result = script_service.get_source_script(SimpleNamespace(), "project-1")

    shot = result.scenes[0].shots[0]
    assert shot.action_summary == "徐然站在王桂香门口。"
    assert shot.visual_description.endswith("构图：人物居中。")
    assert shot.dialogues[0].text == "canonical 原文"
    assert result.scenes[0].character_names == ["徐然"]


def test_storyboard_edit_contract_is_full_or_reset_and_working_copy_is_not_artifact() -> None:
    with pytest.raises(ValidationError):
        StoryboardShotEditCommand(
            expected_revision=None,
            shot_anchor_id="shot-1",
            visual_description="只改了一半",
        )
    with pytest.raises(ValidationError):
        StoryboardShotEditCommand.model_validate(
            {
                "expected_revision": None,
                "shot_anchor_id": "shot-1",
                "reset_to_source": True,
                "dialogue": "对白不可通过分镜草稿修改",
            }
        )

    reset = StoryboardShotEditCommand(
        expected_revision=1,
        shot_anchor_id="shot-1",
        reset_to_source=True,
    )
    assert reset.reset_to_source is True
    assert SourceStoryboardDraftRevision.__tablename__ == "source_storyboard_draft_revisions"
    assert "artifact_id" not in SourceStoryboardDraftRevision.__table__.columns
    assert "source_snapshot_artifact_id" in SourceStoryboardDraftRevision.__table__.columns


def test_storyboard_draft_persists_resets_conflicts_and_stales_with_source(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    project = _project(client)
    _seed_source(session_factory, project)
    monkeypatch.setattr(
        draft_service,
        "get_source_video_snapshot",
        lambda db, project_id: SimpleNamespace(status="CURRENT"),
    )
    source_shot = SimpleNamespace(
        shot_anchor_id="shot-1",
        visual_description="原始视觉描述",
        shot_size="中景",
        composition="人物居中",
        angle_or_type="平视",
        movement="固定",
        focal_length_dof="标准焦段",
    )
    monkeypatch.setattr(
        draft_service,
        "get_source_script",
        lambda db, project_id: SimpleNamespace(
            scenes=[SimpleNamespace(shots=[source_shot])],
        ),
    )

    with session_factory() as db:
        first_snapshot = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
            namespace=ArtifactNamespace.SOURCE,
            label="原片解析结果 rev1",
            input_fingerprint="c" * 64,
            skill_id=project["root_skill_id"],
            skill_version=project["root_skill_version"],
            metadata_json={},
        )
        edited = draft_service.edit_storyboard_draft(
            db,
            project_id=project["id"],
            command=StoryboardShotEditCommand(
                expected_revision=None,
                shot_anchor_id="shot-1",
                visual_description="修改后的视觉描述",
                shot_size="近景",
                composition="人物偏右",
                angle_or_type="轻微仰拍",
                movement="缓慢推进",
                focal_length_dof="浅景深",
            ),
        )
        assert edited.status.value == "CURRENT"
        assert edited.revision == 1
        assert edited.overrides[0].visual_description == "修改后的视觉描述"
        refreshed = draft_service.get_storyboard_draft(db, project["id"])
        assert refreshed == edited

        with pytest.raises(AppError) as conflict:
            draft_service.edit_storyboard_draft(
                db,
                project_id=project["id"],
                command=StoryboardShotEditCommand(
                    expected_revision=None,
                    shot_anchor_id="shot-1",
                    reset_to_source=True,
                ),
            )
        assert conflict.value.code == "STORYBOARD_DRAFT_REVISION_CONFLICT"

        reset = draft_service.edit_storyboard_draft(
            db,
            project_id=project["id"],
            command=StoryboardShotEditCommand(
                expected_revision=1,
                shot_anchor_id="shot-1",
                reset_to_source=True,
            ),
        )
        assert reset.revision == 2
        assert reset.overrides == []

        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
            namespace=ArtifactNamespace.SOURCE,
            label="原片解析结果 rev2",
            input_fingerprint="d" * 64,
            skill_id=project["root_skill_id"],
            skill_version=project["root_skill_version"],
            metadata_json={},
        )
        db.expire(first_snapshot)
        stale = draft_service.get_storyboard_draft(db, project["id"])
        assert stale.status.value == "STALE"
        assert stale.revision == 2


def test_source_analysis_product_routes_are_registered(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v3/projects/{project_id}/source-analysis" in paths
    assert "/api/v3/projects/{project_id}/commands/source-analysis" in paths
    assert "/api/v3/projects/{project_id}/source-script" in paths
    assert "/api/v3/projects/{project_id}/storyboard-draft" in paths
    assert "/api/v3/projects/{project_id}/storyboard-draft/commands/edit-shot" in paths
