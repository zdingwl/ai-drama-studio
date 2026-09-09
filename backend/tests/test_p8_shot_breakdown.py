import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation
from app.core.config import get_settings
from app.evidence.models import SourceDialogueUtterance, SourceEvidenceSet, SourceVisualTextSpan
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.models import Project
from app.shot_breakdown.providers import EpisodeShotBreakdownInput, EpisodeShotBreakdownProviderResult
from app.shot_breakdown.schemas import EpisodeShotBreakdownSemantic
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.sources.models import Episode
from app.understanding.models import SourceBibleRevision
from app.understanding.schemas import SourceBibleContent, SourceBibleProvenance
from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P8-shot-breakdown",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _video(path: Path, duration: float = 2.0) -> bytes:
    subprocess.run(
        [
            get_settings().ffmpeg_binary,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x180:d={duration}:r=12",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}:sample_rate=16000",
            "-shortest",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


def _upload(client: TestClient, project_id: str, payload: bytes) -> dict:
    response = client.post(
        f"/api/v3/projects/{project_id}/sources/videos",
        files=[("files", ("episode.mp4", payload, "video/mp4"))],
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def _dummy_task(db: Session, project_id: str, name: str, fingerprint: str) -> Task:
    task = Task(
        project_id=project_id,
        task_type=name,
        task_name=name,
        idempotency_key=f"{name}-key",
        business_key=fingerprint,
        input_fingerprint=fingerprint,
        input_artifact_ids_json=[],
        status=TaskStatus.SUCCEEDED,
        progress_percent=100,
        attempt=1,
        max_attempts=3,
        checkpoint_json={},
        cancel_requested=False,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _source_bible_content(episode: Episode, dialogue_id: str, visual_id: str) -> SourceBibleContent:
    fact = {
        "support_level": "FACT",
        "video_time_ranges": [{"start_us": 0, "end_us": episode.duration_us}],
    }
    return SourceBibleContent.model_validate(
        {
            "schema_version": "1.1",
            "episodes": [
                {
                    "material_baseline": {
                        "episode_id": episode.id,
                        "episode_order": episode.episode_order,
                        "source_filename": "episode.mp4",
                        "media_duration_us": episode.duration_us,
                        "width": episode.width,
                        "height": episode.height,
                        "aspect_ratio": "16:9",
                        "avg_frame_rate": episode.avg_frame_rate,
                        "codec_name": episode.codec_name,
                        "has_audio": episode.has_audio,
                    },
                    "overall_analysis": {
                        "story_summary": "两名角色在室内对话并交换关键信息。",
                        "story_background": "当前 Episode 可确认发生在室内会面空间。",
                        "story_background_grounding": fact,
                        "genre": ["都市"],
                        "world_rules": [],
                        "world_rule_groundings": [],
                        "narrative_structure": "对话推动冲突。",
                        "audiovisual_style": "反应镜头与近景交替。",
                        "rhythm_overview": "对白与反应形成节奏。",
                    },
                    "timed_script": [
                        {
                            "segment_number": 1,
                            "time_range": {"start_us": 0, "end_us": episode.duration_us},
                            "visual_description": "人物在室内完成一轮对话。",
                            "story_summary": "关键信息在本段被说出。",
                            "narrative_function": "CONFLICT",
                            "dialogue_evidence_ids": [dialogue_id],
                            "visual_text_evidence_ids": [visual_id],
                        }
                    ],
                    "characters": [
                        {
                            "character_id": "char-lead",
                            "name": "未命名女性A",
                            "identity_grounding": fact,
                            "story_function": "主要对话参与者。",
                            "appearance_baseline": "都市装束。",
                            "states": [],
                        }
                    ],
                    "relationships": [],
                    "scenes": [
                        {
                            "scene_id": "scene-room",
                            "name": "室内会面空间",
                            "time_ranges": [{"start_us": 0, "end_us": episode.duration_us}],
                            "spatial_relationship": "角色位于同一室内空间。",
                            "environment_details": "室内背景。",
                            "grounding": fact,
                        }
                    ],
                    "key_props": [
                        {
                            "prop_id": "prop-phone",
                            "name": "手机",
                            "time_ranges": [{"start_us": 0, "end_us": episode.duration_us}],
                            "appearance_state": "角色手边可见手机。",
                            "appearance_grounding": fact,
                            "story_function": None,
                            "story_function_grounding": {"support_level": "UNKNOWN"},
                        }
                    ],
                    "story_events": [],
                    "emotion_timeline": [],
                    "story_skeleton": {
                        "premise": "一次室内会面交换关键信息。",
                        "central_conflict": "双方围绕关键信息发生冲突。",
                        "beats": [
                            {
                                "beat_type": "HOOK",
                                "time_range": {"start_us": 0, "end_us": episode.duration_us},
                                "summary": "对话建立悬念。",
                                "importance": 5,
                            }
                        ],
                    },
                    "rhythm_skeleton": {
                        "overall_pace": "中快",
                        "phases": [
                            {
                                "time_range": {"start_us": 0, "end_us": episode.duration_us},
                                "pace": "中快",
                                "scene_rhythm": "单场景对话推进。",
                                "dialogue_reaction_rhythm": "对白后切反应。",
                                "cut_timing_notes": "信息点附近切换镜头。",
                                "key_beat_refs": ["HOOK"],
                                "allowable_deviation_ms": 250,
                            }
                        ],
                    },
                }
            ],
        }
    )


def _seed_inputs(session_factory: sessionmaker[Session], project_id: str, episode_id: str) -> dict:
    with session_factory() as db:
        project = db.get(Project, project_id)
        episode = db.get(Episode, episode_id)
        assert project is not None and episode is not None
        source = db.scalar(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == ArtifactType.SOURCE_VIDEO.value,
                ArtifactNode.is_current.is_(True),
            )
        )
        assert source is not None

        p5_task = _dummy_task(db, project_id, "P8_TEST_P5", "1" * 64)
        boundary = ShotBoundarySet(
            project_id=project_id,
            episode_id=episode.id,
            source_video_artifact_id=source.id,
            task_id=p5_task.id,
            revision=1,
            input_fingerprint="2" * 64,
            detector_profile_json={"test": True},
            is_current=True,
        )
        db.add(boundary)
        db.flush()
        split = episode.duration_us // 2
        anchors = [
            ShotAnchor(
                project_id=project_id,
                episode_id=episode.id,
                shot_boundary_set_id=boundary.id,
                shot_number=1,
                start_us=0,
                end_us=split,
                duration_us=split,
                thumbnail_relative_path="test/shot1.jpg",
                reference_clip_relative_path="test/shot1.mp4",
            ),
            ShotAnchor(
                project_id=project_id,
                episode_id=episode.id,
                shot_boundary_set_id=boundary.id,
                shot_number=2,
                start_us=split,
                end_us=episode.duration_us,
                duration_us=episode.duration_us - split,
                thumbnail_relative_path="test/shot2.jpg",
                reference_clip_relative_path="test/shot2.mp4",
            ),
        ]
        db.add_all(anchors)
        db.commit()
        shots_artifact = create_artifact(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SHOT_ANCHORS,
            namespace=ArtifactNamespace.SOURCE,
            label="P8 test shot anchors",
            input_fingerprint="3" * 64,
            skill_id=project.root_skill_id,
            skill_version=project.root_skill_version,
            metadata_json={
                "source_video_artifact_id": source.id,
                "episode_sets": [
                    {
                        "episode_id": episode.id,
                        "episode_order": episode.episode_order,
                        "shot_boundary_set_id": boundary.id,
                        "set_revision": 1,
                        "set_fingerprint": boundary.input_fingerprint,
                        "shot_count": 2,
                    }
                ],
            },
        )
        create_artifact_relation(
            db,
            project_id=project_id,
            source_node_id=source.id,
            target_node_id=shots_artifact.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )

        p6_task = _dummy_task(db, project_id, "P8_TEST_P6", "4" * 64)
        evidence = SourceEvidenceSet(
            project_id=project_id,
            episode_id=episode.id,
            source_video_artifact_id=source.id,
            task_id=p6_task.id,
            revision=1,
            input_fingerprint="5" * 64,
            asr_profile_json={"test": True},
            ocr_profile_json={"test": True},
            sampling_hints_json={"timeline_source": "FULL_EPISODE"},
            is_current=True,
        )
        db.add(evidence)
        db.flush()
        utterance = SourceDialogueUtterance(
            project_id=project_id,
            episode_id=episode.id,
            source_evidence_set_id=evidence.id,
            utterance_number=1,
            start_us=max(0, split - 300_000),
            end_us=min(episode.duration_us, split + 300_000),
            text="这句话跨过两个镜头。",
            language="zh",
            source_segment_ids_json=[],
        )
        visual = SourceVisualTextSpan(
            project_id=project_id,
            episode_id=episode.id,
            source_evidence_set_id=evidence.id,
            span_number=1,
            start_us=100_000,
            end_us=min(episode.duration_us, split + 100_000),
            text="三年前",
            confidence=0.98,
            bbox_json=[],
            source_observation_ids_json=[],
        )
        db.add_all([utterance, visual])
        db.commit()
        dialogue_artifact = create_artifact(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_DIALOGUE,
            namespace=ArtifactNamespace.SOURCE,
            label="P8 test canonical evidence",
            input_fingerprint="6" * 64,
            skill_id=project.root_skill_id,
            skill_version=project.root_skill_version,
            metadata_json={
                "source_video_artifact_id": source.id,
                "episode_sets": [
                    {
                        "episode_id": episode.id,
                        "episode_order": episode.episode_order,
                        "source_evidence_set_id": evidence.id,
                        "set_revision": 1,
                        "set_fingerprint": evidence.input_fingerprint,
                        "dialogue_count": 1,
                        "visual_text_count": 1,
                    }
                ],
                "episode_count": 1,
                "complete": True,
                "canonical_policy": "ASR_OCR_IMMUTABLE_SOURCE_EVIDENCE",
            },
        )
        create_artifact_relation(
            db,
            project_id=project_id,
            source_node_id=source.id,
            target_node_id=dialogue_artifact.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )

        content = _source_bible_content(episode, utterance.id, visual.id)
        bible_artifact = create_artifact(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_BIBLE,
            namespace=ArtifactNamespace.SOURCE,
            label="P8 test source bible",
            input_fingerprint="7" * 64,
            skill_id="source-video-understanding",
            skill_version="1.1.0",
            metadata_json={"schema_version": "1.1"},
        )
        provenance = SourceBibleProvenance(
            source_video_artifact_id=source.id,
            source_video_fingerprint=source.input_fingerprint,
            source_dialogue_artifact_id=dialogue_artifact.id,
            source_dialogue_fingerprint=dialogue_artifact.input_fingerprint,
            shot_anchors_artifact_id=shots_artifact.id,
            shot_anchors_fingerprint=shots_artifact.input_fingerprint,
            episode_evidence_sets=[
                {
                    "episode_id": episode.id,
                    "source_evidence_set_id": evidence.id,
                    "evidence_fingerprint": evidence.input_fingerprint,
                }
            ],
            provider_jobs=[],
            provider="fake-p7",
            model="fake-p7-model",
            prompt_version="p7-source-bible-v2",
            schema_version="1.1",
            professional_skill_id="source-video-understanding",
            professional_skill_version="1.1.0",
            grounding_contract="grounded-source-truth-v2",
        )
        db.add(
            SourceBibleRevision(
                project_id=project_id,
                artifact_id=bible_artifact.id,
                source_video_artifact_id=source.id,
                source_dialogue_artifact_id=dialogue_artifact.id,
                shot_anchors_artifact_id=shots_artifact.id,
                generated_by_task_id=None,
                edit_parent_artifact_id=None,
                schema_version="1.1",
                content_json=content.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.commit()
        for upstream_id, relation in (
            (source.id, ArtifactRelationType.DERIVED_FROM),
            (dialogue_artifact.id, ArtifactRelationType.DERIVED_FROM),
            (shots_artifact.id, ArtifactRelationType.USES),
        ):
            create_artifact_relation(
                db,
                project_id=project_id,
                source_node_id=upstream_id,
                target_node_id=bible_artifact.id,
                relation_type=relation,
            )
        return {
            "source": source.id,
            "shots": shots_artifact.id,
            "dialogue": dialogue_artifact.id,
            "bible": bible_artifact.id,
            "utterance_id": utterance.id,
            "utterance_text": utterance.text,
            "visual_id": visual.id,
            "anchor_ids": [anchor.id for anchor in anchors],
            "split": split,
            "duration_us": episode.duration_us,
            "content": content.model_dump(mode="json"),
            "provenance": provenance.model_dump(mode="json"),
        }


class FakeShotBreakdownProvider:
    provider_name = "fake-p8-multimodal"
    model_name = "fake-p8-full-episode"

    def __init__(self, factory: sessionmaker[Session], *, invalid_character: bool = False):
        self.factory = factory
        self.invalid_character = invalid_character
        self.calls: list[EpisodeShotBreakdownInput] = []
        self.provider_job_seen_before_call = False

    @property
    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "video_input": "FULL_EPISODE_FILE",
            "prompt_version": "p8-shot-breakdown-v1",
            "professional_skill_id": "shot-breakdown",
            "professional_skill_version": "1.0.0",
            "source_truth_contract": "source-bible-shot-facts-v1",
        }

    def analyze(self, payload: EpisodeShotBreakdownInput) -> EpisodeShotBreakdownProviderResult:
        self.calls.append(payload)
        assert payload.source_path.is_file()
        assert "reference" not in payload.source_path.name.lower()
        with self.factory() as db:
            job = db.scalar(
                select(ProviderJob)
                .where(ProviderJob.episode_id == payload.episode_id)
                .order_by(ProviderJob.created_at.desc())
                .limit(1)
            )
            self.provider_job_seen_before_call = bool(job and job.status == ProviderJobStatus.RUNNING)
        character_id = "invented-character" if self.invalid_character else "char-lead"
        shots = []
        for shot in payload.shot_context:
            shots.append(
                {
                    "shot_number": shot["shot_number"],
                    "visual_description": f"镜头 {shot['shot_number']} 中角色完成反应与对话。",
                    "camera_language": {
                        "shot_size": "近景",
                        "composition": "人物居中偏侧构图",
                        "angle_or_type": "平视反应镜头",
                        "movement": "固定机位",
                        "focal_length_dof": "浅景深，焦点落在人物面部",
                    },
                    "bindings": {
                        "character_ids": [character_id],
                        "scene_ids": ["scene-room"],
                        "prop_ids": ["prop-phone"],
                        "unresolved_subject_notes": [],
                    },
                    "dialogue_annotations": [
                        {"utterance_number": item["utterance_number"], "delivery": "DIALOGUE"}
                        for item in shot["canonical_dialogue_overlaps"]
                    ],
                    "sound_effects": ["轻微衣物摩擦声"],
                    "ambience": ["室内底噪"],
                }
            )
        semantic = EpisodeShotBreakdownSemantic.model_validate({"shots": shots})
        return EpisodeShotBreakdownProviderResult(semantic=semantic, remote_job_id="fake-p8-job")


def _start(client: TestClient, project_id: str, key: str) -> dict:
    response = client.post(
        f"/api/v3/projects/{project_id}/commands/shot-breakdown",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    task = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}")
    assert task.status_code == 200
    return task.json()


def test_p8_get_is_read_only_and_post_requires_hard_inputs(client: TestClient, tmp_path: Path) -> None:
    project = _project(client)
    _upload(client, project["id"], _video(tmp_path / "missing-inputs.mp4"))
    before_tasks = client.get(f"/api/v3/projects/{project['id']}/tasks").json()
    result = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown")
    assert result.status_code == 200 and result.json()["status"] == "NOT_BUILT"
    assert client.get(f"/api/v3/projects/{project['id']}/tasks").json() == before_tasks

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/shot-breakdown",
        headers={"Idempotency-Key": "p8-missing-inputs"},
    )
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "SOURCE_DIALOGUE_REQUIRED"


def test_p8_provider_schema_forbids_shot_time_and_dialogue_text_fields() -> None:
    payload = {
        "shots": [
            {
                "shot_number": 1,
                "start_us": 0,
                "visual_description": "人物近景。",
                "camera_language": {
                    "shot_size": "近景",
                    "composition": "居中",
                    "angle_or_type": "平视",
                    "movement": "固定",
                    "focal_length_dof": "浅景深",
                },
                "bindings": {},
                "dialogue_annotations": [
                    {"utterance_number": 1, "delivery": "DIALOGUE", "text": "Provider 不得输出"}
                ],
            }
        ]
    }
    with pytest.raises(ValidationError):
        EpisodeShotBreakdownSemantic.model_validate(payload)


def test_p8_full_episode_provider_job_first_and_server_binds_p5_p6_p7(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    episode = _upload(client, project["id"], _video(tmp_path / "full-episode.mp4"))
    seeded = _seed_inputs(session_factory, project["id"], episode["id"])
    fake = FakeShotBreakdownProvider(session_factory)
    monkeypatch.setattr("app.shot_breakdown.service.build_shot_breakdown_provider", lambda settings, selection: fake)

    task = _start(client, project["id"], "p8-full-episode")
    assert task["status"] == "succeeded", task
    assert len(fake.calls) == 1
    assert fake.calls[0].episode_id == episode["id"]
    assert fake.calls[0].source_filename == "episode.mp4"
    assert fake.provider_job_seen_before_call is True
    assert len(fake.calls[0].shot_context) == 2

    response = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "CURRENT"
    assert result["revision"] == 1
    assert result["content"]["schema_version"] == "1.0"
    shots = result["content"]["episodes"][0]["shots"]
    assert [shot["shot_number"] for shot in shots] == [1, 2]
    assert [shot["shot_anchor_id"] for shot in shots] == seeded["anchor_ids"]
    assert shots[0]["start_us"] == 0 and shots[0]["end_us"] == seeded["split"]
    assert shots[1]["start_us"] == seeded["split"] and shots[1]["end_us"] == seeded["duration_us"]
    assert shots[0]["duration_us"] == shots[0]["end_us"] - shots[0]["start_us"]
    assert shots[1]["duration_us"] == shots[1]["end_us"] - shots[1]["start_us"]

    assert [shot["dialogue"][0]["utterance_id"] for shot in shots] == [seeded["utterance_id"], seeded["utterance_id"]]
    assert [shot["dialogue"][0]["text"] for shot in shots] == [seeded["utterance_text"], seeded["utterance_text"]]
    assert shots[0]["dialogue"][0]["overlap_end_us"] == seeded["split"]
    assert shots[1]["dialogue"][0]["overlap_start_us"] == seeded["split"]
    assert seeded["visual_id"] in shots[0]["visual_text_evidence_ids"]

    assert shots[0]["bindings"]["characters"] == [{"id": "char-lead", "label": "未命名女性A"}]
    assert shots[0]["bindings"]["scenes"] == [{"id": "scene-room", "label": "室内会面空间"}]
    assert shots[0]["bindings"]["props"] == [{"id": "prop-phone", "label": "手机"}]

    provenance = result["provenance"]
    assert provenance["source_video_artifact_id"] == seeded["source"]
    assert provenance["source_bible_artifact_id"] == seeded["bible"]
    assert provenance["shot_anchors_artifact_id"] == seeded["shots"]
    assert provenance["source_dialogue_artifact_id"] == seeded["dialogue"]
    assert provenance["prompt_version"] == "p8-shot-breakdown-v1"
    assert provenance["professional_skill_id"] == "shot-breakdown"
    assert provenance["professional_skill_version"] == "1.0.0"
    assert provenance["source_truth_contract"] == "source-bible-shot-facts-v1"
    assert len(provenance["provider_jobs"]) == 1
    assert len(provenance["episode_inputs"]) == 1

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    p8_id = result["artifact_id"]
    expected_edges = {
        (seeded["source"], "DERIVED_FROM"),
        (seeded["bible"], "USES"),
        (seeded["shots"], "DERIVED_FROM"),
        (seeded["dialogue"], "DERIVED_FROM"),
    }
    actual_edges = {
        (edge["source_node_id"], edge["relation_type"])
        for edge in graph["edges"]
        if edge["target_node_id"] == p8_id
    }
    assert expected_edges.issubset(actual_edges)
    node = next(item for item in graph["nodes"] if item["id"] == p8_id)
    assert node["skill_id"] == "shot-breakdown"
    assert node["skill_version"] == "1.0.0"
    assert node["metadata_json"]["source_truth_contract"] == "source-bible-shot-facts-v1"


def test_p8_rejects_unknown_source_bible_candidate_and_does_not_publish(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    episode = _upload(client, project["id"], _video(tmp_path / "invalid-binding.mp4"))
    _seed_inputs(session_factory, project["id"], episode["id"])
    fake = FakeShotBreakdownProvider(session_factory, invalid_character=True)
    monkeypatch.setattr("app.shot_breakdown.service.build_shot_breakdown_provider", lambda settings, selection: fake)

    task = _start(client, project["id"], "p8-invalid-binding")
    assert task["status"] == "failed"
    assert "P8_SOURCE_BIBLE_BINDING_INVALID" in (task["last_error"] or "")
    result = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown").json()
    assert result["status"] == "NOT_BUILT"


def test_p8_new_source_bible_revision_stales_old_and_new_p8_supersedes_it(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    episode = _upload(client, project["id"], _video(tmp_path / "revision.mp4"))
    seeded = _seed_inputs(session_factory, project["id"], episode["id"])
    fake = FakeShotBreakdownProvider(session_factory)
    monkeypatch.setattr("app.shot_breakdown.service.build_shot_breakdown_provider", lambda settings, selection: fake)
    assert _start(client, project["id"], "p8-rev1")["status"] == "succeeded"
    first = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown").json()

    with session_factory() as db:
        old_bible = db.get(ArtifactNode, seeded["bible"])
        source = db.get(ArtifactNode, seeded["source"])
        dialogue = db.get(ArtifactNode, seeded["dialogue"])
        shots = db.get(ArtifactNode, seeded["shots"])
        assert old_bible and source and dialogue and shots
        new_bible = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_BIBLE,
            namespace=ArtifactNamespace.SOURCE,
            label="P8 test source bible rev2",
            input_fingerprint="8" * 64,
            skill_id="source-video-understanding",
            skill_version="1.1.0",
            metadata_json={"schema_version": "1.1", "edited": True},
        )
        provenance = SourceBibleProvenance.model_validate(seeded["provenance"]).model_copy(
            update={"edit_parent_artifact_id": old_bible.id}
        )
        db.add(
            SourceBibleRevision(
                project_id=project["id"],
                artifact_id=new_bible.id,
                source_video_artifact_id=source.id,
                source_dialogue_artifact_id=dialogue.id,
                shot_anchors_artifact_id=shots.id,
                generated_by_task_id=None,
                edit_parent_artifact_id=old_bible.id,
                schema_version="1.1",
                content_json=seeded["content"],
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.commit()
        for upstream_id, relation in (
            (source.id, ArtifactRelationType.DERIVED_FROM),
            (dialogue.id, ArtifactRelationType.DERIVED_FROM),
            (shots.id, ArtifactRelationType.USES),
        ):
            create_artifact_relation(
                db,
                project_id=project["id"],
                source_node_id=upstream_id,
                target_node_id=new_bible.id,
                relation_type=relation,
            )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=new_bible.id,
            target_node_id=old_bible.id,
            relation_type=ArtifactRelationType.SUPERSEDES,
        )
        new_bible_id = new_bible.id

    stale = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown").json()
    assert stale["status"] == "STALE"
    assert stale["artifact_id"] == first["artifact_id"]

    assert _start(client, project["id"], "p8-rev2")["status"] == "succeeded"
    second = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown").json()
    assert second["status"] == "CURRENT"
    assert second["revision"] == 2
    assert second["artifact_id"] != first["artifact_id"]
    assert second["provenance"]["source_bible_artifact_id"] == new_bible_id
    assert second["provenance"]["supersedes_artifact_id"] == first["artifact_id"]

    revisions = client.get(f"/api/v3/projects/{project['id']}/shot-breakdown/revisions").json()
    assert [(item["revision"], item["status"]) for item in revisions[:2]] == [(2, "CURRENT"), (1, "STALE")]
    assert revisions[0]["supersedes_artifact_id"] == first["artifact_id"]
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    assert any(
        edge["source_node_id"] == second["artifact_id"]
        and edge["target_node_id"] == first["artifact_id"]
        and edge["relation_type"] == "SUPERSEDES"
        for edge in graph["edges"]
    )


def test_p8_capability_remains_planned_until_real_manual_acceptance() -> None:
    assert CAPABILITY_BY_ID[Capability.SHOT_BREAKDOWN].availability == CapabilityAvailability.PLANNED
