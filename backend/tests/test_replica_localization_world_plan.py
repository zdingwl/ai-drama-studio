from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.artifacts.enums import ArtifactNamespace, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.projects.enums import AudioPolicy, ProjectType, SceneStrategy
from app.projects.models import Project
from app.replica_pipeline import localized_storyboard as module
from app.replica_pipeline.schemas import LocalizedStoryboardSemantic
from app.shot_breakdown.schemas import CameraLanguage, DialogueDelivery
from app.skills.models import ArtifactType
from app.workflow.models import ProviderJob, ProviderJobStatus, Task
from app.workflow.schemas import TaskWorkerRead
from app.workflow.worker import TaskExecutionContext


def plan():
    return LocalizedStoryboardSemantic.model_validate({
        "world_design_zh": "故事位于美国城市公寓，重新设计人物与家居环境，保持邻里矛盾和夫妻关系。",
        "continuity_rules_zh": ["夫妻住在同一套公寓，姓名与门牌在所有镜头中保持一致。"],
        "characters": [{"source_character_id": "c", "localized_name": "Alex Carter", "identity_description_zh": "公寓业主，与邻居因物品争执", "appearance_description_zh": "棕色卷发的青年女性，穿蓝色棉布衬衫"}],
        "scenes": [{"source_scene_id": "s", "localized_name": "Unit 5B", "setting_description_zh": "城市公寓五楼的自有住宅", "visual_description_zh": "浅色木地板与米色布艺沙发的客厅"}],
        "props": [], "dialogue": [], "shots": [],
    })


def payload():
    return module.LocalizationProviderInput(
        target_language="en-US", target_region="US", scene_strategy="LOCALIZE", visual_style="写实电影感",
        source_view={
            "characters": [{"source_character_id": "c", "name": "原人物"}],
            "scenes": [{"source_scene_id": "s", "name": "原场景"}], "props": [],
            "dialogue": [{"utterance_id": f"d{i}", "utterance_number": i, "text": "你好", "language": "zh", "speaker_character_id": "c", "start_us": (i-1)*2_000_000, "end_us": i*2_000_000, "duration_us": 2_000_000, "max_spoken_words": 8, "max_spoken_cjk_chars": 12} for i in (1, 2)],
            "shots": [{"episode_id": "e", "episode_order": 1, "shot_number": i, "shot_anchor_id": f"s{i}", "character_ids": ["c"], "scene_ids": ["s"], "prop_ids": [], "dialogue": [{"utterance_id": f"d{i}", "overlap_start_us": (i-1)*2_000_000, "overlap_end_us": i*2_000_000}]} for i in (1, 2)],
        }, expected_character_ids=("c",), expected_scene_ids=("s",), expected_prop_ids=(), expected_dialogue_ids=("d1", "d2"), expected_shot_ids=("s1", "s2"),
    )


def shot_result(batch):
    return LocalizedStoryboardSemantic.model_validate({
        "dialogue": [{"utterance_id": item, "target_dialogue": "Hi!", "target_dialogue_zh": "你好"} for item in batch.expected_dialogue_ids],
        "shots": [{"shot_anchor_id": item, "target_duration_ms": 2_000, "localized_visual_description_zh": "Alex身穿蓝色衬衫站在米色布艺沙发旁，向邻居问好。", "camera_description_zh": "固定平视镜头保持原片构图"} for item in batch.expected_shot_ids],
    })


def test_world_planning_requires_complete_design_and_no_shot_output():
    planning = replace(payload(), operation="PLAN_WORLD", expected_dialogue_ids=(), expected_shot_ids=())
    assert module._validate_semantic(planning, plan()) == plan()
    with pytest.raises(AppError):
        module._validate_semantic(planning, plan().model_copy(update={"world_design_zh": ""}))
    with pytest.raises(AppError) as error:
        module._validate_semantic(planning, plan().model_copy(update={"shots": shot_result(payload()).shots}))
    assert error.value.code == "LOCALIZED_STORYBOARD_PROVIDER_COVERAGE_INVALID"


def test_coverage_error_reports_exact_ids_for_targeted_correction():
    data = replace(payload(), frozen_world_plan=plan())
    incomplete = shot_result(data).model_copy(deep=True)
    incomplete.shots = [incomplete.shots[0], incomplete.shots[0]]

    with pytest.raises(AppError) as error:
        module._validate_semantic(data, incomplete)

    assert error.value.code == "LOCALIZED_STORYBOARD_PROVIDER_COVERAGE_INVALID"
    assert error.value.details["missing"] == ["s2"]
    assert error.value.details["duplicates"] == ["s1"]
    assert error.value.details["unexpected"] == []
    assert error.value.details["issues"][0]["field"] == "shot"


def test_execute_retries_incomplete_provider_coverage_before_failing_task(session_factory, monkeypatch):
    data = payload()
    camera = CameraLanguage(shot_size="中景", composition="居中", angle_or_type="平视", movement="固定", focal_length_dof="未知")
    lines = [SimpleNamespace(**item) for item in data.source_view["dialogue"]]
    shots = [SimpleNamespace(shot_anchor_id=f"s{i}", shot_number=i, start_us=(i-1)*2_000_000, end_us=i*2_000_000, duration_us=2_000_000, camera_language=camera, visual_description="原片画面", sound_effects=[], ambience=[], dialogue=[SimpleNamespace(utterance_id=f"d{i}", delivery=DialogueDelivery.DIALOGUE, overlap_start_us=(i-1)*2_000_000, overlap_end_us=i*2_000_000)]) for i in (1, 2)]
    snapshot = SimpleNamespace(episodes=[SimpleNamespace(episode_id="e", canonical_dialogue=lines, width=1080, height=1920)], source_shot_facts=SimpleNamespace(episodes=[SimpleNamespace(episode_id="e", episode_order=1, shots=shots)]))
    monkeypatch.setattr(module, "_payload", lambda *_: data)
    monkeypatch.setattr(module, "_source_view", lambda *_: (data.source_view, {"d1": "c", "d2": "c"}))
    correction_calls = []

    class Provider:
        provider_name = "test"
        model_name = "test"

        def profile(self):
            return {"provider": "test", "model": "test"}

        def localize(self, batch, *, correction_issues=None):
            if batch.operation == "PLAN_WORLD":
                return module.LocalizationProviderResult(semantic=plan())
            correction_calls.append(correction_issues)
            result = shot_result(batch)
            if not correction_issues:
                result.shots = result.shots[:-1]
            return module.LocalizationProviderResult(semantic=result)

    monkeypatch.setattr(module, "_provider", lambda *_: Provider())
    with session_factory() as db:
        project = Project(name="coverage retry", project_type=ProjectType.REPLICA, source_language="zh-CN", target_language="en-US", target_region="US", scene_strategy=SceneStrategy.LOCALIZE, audio_policy=AudioPolicy.REGENERATE_AUDIO, root_skill_id="replica", root_skill_version="1.0.0")
        db.add(project)
        db.flush()
        artifact = ArtifactNode(project_id=project.id, artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT.value, namespace=ArtifactNamespace.SOURCE, label="source", revision=1, input_fingerprint="b"*64, skill_id="source-video-snapshot", skill_version="1.0.0", validity=ArtifactValidity.CURRENT, is_current=True, metadata_json={})
        db.add(artifact)
        db.commit()
        artifact_id = artifact.id
        monkeypatch.setattr(module, "_load_snapshot", lambda db, _: (db.get(ArtifactNode, artifact_id), snapshot))
        task = module.create_localized_storyboard_task(db, project_id=project.id, idempotency_key="coverage-retry-test")
        task_id = task.id
        worker_read = TaskWorkerRead.model_validate(module._claim(db, task_id, "test-worker"))

    content, _ = module._execute(TaskExecutionContext(session_factory, task_id, "test-worker"), worker_read)

    assert len(content.shots) == 2
    assert correction_calls[0] is None
    assert correction_calls[1][0]["field"] == "shot"
    assert correction_calls[1][0]["missing_ids"] == ["s2"]


def test_shot_batches_bind_complete_plan_and_reject_appearance_drift():
    batch = replace(payload(), frozen_world_plan=plan())
    result = module._validate_semantic(batch, shot_result(batch))
    assert result.characters == plan().characters
    assert result.scenes == plan().scenes
    changed = result.model_copy(deep=True)
    changed.characters[0].appearance_description_zh = "沿用原片演员外形以及原片服装"
    with pytest.raises(AppError) as error:
        module._validate_semantic(batch, changed)
    assert error.value.code == "LOCALIZED_STORYBOARD_WORLD_PLAN_DRIFT"


def test_execute_plans_once_and_resumes_without_repeating_paid_plan_or_completed_batch(session_factory, monkeypatch):
    data = payload()
    camera = CameraLanguage(shot_size="中景", composition="居中", angle_or_type="平视", movement="固定", focal_length_dof="未知")
    lines = [SimpleNamespace(**item) for item in data.source_view["dialogue"]]
    shots = [SimpleNamespace(shot_anchor_id=f"s{i}", shot_number=i, start_us=(i-1)*2_000_000, end_us=i*2_000_000, duration_us=2_000_000, camera_language=camera, visual_description="原片画面", sound_effects=[], ambience=[], dialogue=[SimpleNamespace(utterance_id=f"d{i}", delivery=DialogueDelivery.DIALOGUE, overlap_start_us=(i-1)*2_000_000, overlap_end_us=i*2_000_000)]) for i in (1, 2)]
    snapshot = SimpleNamespace(episodes=[SimpleNamespace(episode_id="e", canonical_dialogue=lines, width=1080, height=1920)], source_shot_facts=SimpleNamespace(episodes=[SimpleNamespace(episode_id="e", episode_order=1, shots=shots)]))
    monkeypatch.setattr(module, "LOCALIZATION_BATCH_SHOTS", 1)
    monkeypatch.setattr(module, "_payload", lambda *_: data)
    monkeypatch.setattr(module, "_source_view", lambda *_: (data.source_view, {"d1": "c", "d2": "c"}))
    calls = []
    fail_once = [True]

    class Provider:
        provider_name = "test"
        model_name = "test"

        def profile(self):
            return {"provider": "test", "model": "test"}

        def localize(self, batch, **_):
            with session_factory() as db:
                assert db.scalar(select(ProviderJob).where(ProviderJob.task_id == task_id, ProviderJob.status == ProviderJobStatus.RUNNING)) is not None
                if batch.operation != "PLAN_WORLD":
                    assert db.get(Task, task_id).checkpoint_json["localized_world_plan"]["world_design_zh"]
            calls.append((batch.operation, batch.expected_shot_ids))
            if batch.operation == "PLAN_WORLD":
                assert len(batch.source_view["shots"]) == 2
                return module.LocalizationProviderResult(semantic=plan())
            assert batch.frozen_world_plan == plan()
            if batch.expected_shot_ids == ("s2",) and fail_once[0]:
                fail_once[0] = False
                raise RuntimeError("simulated interrupted request")
            return module.LocalizationProviderResult(semantic=shot_result(batch))

    monkeypatch.setattr(module, "_provider", lambda *_: Provider())
    with session_factory() as db:
        project = Project(name="world planning", project_type=ProjectType.REPLICA, source_language="zh-CN", target_language="en-US", target_region="US", scene_strategy=SceneStrategy.LOCALIZE, audio_policy=AudioPolicy.REGENERATE_AUDIO, root_skill_id="replica", root_skill_version="1.0.0")
        db.add(project)
        db.flush()
        artifact = ArtifactNode(project_id=project.id, artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT.value, namespace=ArtifactNamespace.SOURCE, label="source", revision=1, input_fingerprint="a"*64, skill_id="source-video-snapshot", skill_version="1.0.0", validity=ArtifactValidity.CURRENT, is_current=True, metadata_json={})
        db.add(artifact)
        db.commit()
        artifact_id = artifact.id
        monkeypatch.setattr(module, "_load_snapshot", lambda db, _: (db.get(ArtifactNode, artifact_id), snapshot))
        task = module.create_localized_storyboard_task(db, project_id=project.id, idempotency_key="world-plan-test")
        task_id = task.id
        claimed = module._claim(db, task_id, "test-worker")
        worker_read = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory, task_id, "test-worker")
    with pytest.raises(AppError) as interruption:
        module._execute(context, worker_read)
    assert interruption.value.code == "PROVIDER_REQUEST_FAILED"
    with session_factory() as db:
        saved = db.get(Task, task_id)
        assert saved.checkpoint_json["completed_batches"] == 1
        resumed = TaskWorkerRead.model_validate(saved)
    content, provenance = module._execute(context, resumed)
    assert [item[0] for item in calls].count("PLAN_WORLD") == 1
    assert calls.count(("LOCALIZE_SHOTS", ("s1",))) == 1
    assert len(content.shots) == 2
    assert content.world_design_zh == plan().world_design_zh
    assert content.characters[0].appearance_description_zh == plan().characters[0].appearance_description_zh
    assert len(provenance.provider_jobs) == 3
    assert [(shot.start_us, shot.end_us) for shot in content.shots] == [(0, 2_000_000), (2_000_000, 4_000_000)]
    assert [(shot.source_start_us, shot.source_end_us) for shot in content.shots] == [(0, 2_000_000), (2_000_000, 4_000_000)]
    assert [line.source_text for line in content.dialogue] == ["你好", "你好"]
    assert data.source_view["characters"][0]["name"] == "原人物"
    calls_before = len(calls)
    with session_factory() as db:
        saved = db.get(Task, task_id)
        saved.checkpoint_json = {**saved.checkpoint_json, "planning_fingerprint": "old-config"}
        db.commit()
        changed_config_task = TaskWorkerRead.model_validate(saved)
    with pytest.raises(AppError) as changed_config:
        module._execute(context, changed_config_task)
    assert changed_config.value.code == "LOCALIZED_STORYBOARD_INPUT_CHANGED"
    assert len(calls) == calls_before
