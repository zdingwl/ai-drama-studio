import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.evidence.providers import AsrSegmentResult, EvidenceProviders, OcrDetectionResult
from app.understanding.providers import EpisodeUnderstandingInput, EpisodeUnderstandingProviderResult
from app.understanding.schemas import EpisodeUnderstandingSemantic
from app.workflow.models import ProviderJob, ProviderJobStatus


class FakeAsrProvider:
    profile = {"provider": "fake-asr", "model": "p7-test", "continuous_episode_input": True}

    def transcribe(self, source_path: Path, *, language_hint: str | None, duration_us: int, on_progress=None):
        assert source_path.is_file()
        if on_progress:
            on_progress(1.0)
        return [
            AsrSegmentResult(
                start_us=300_000,
                end_us=900_000,
                text="你终于来了。",
                language="zh",
                confidence=0.98,
                provenance={"provider": "fake-asr"},
            )
        ]


class FakeOcrProvider:
    profile = {"provider": "fake-ocr", "engine": "p7-test"}

    def recognize(self, image: object):
        return [
            OcrDetectionResult(
                text="三年前",
                confidence=0.97,
                bbox=[[8, 8], [90, 8], [90, 34], [8, 34]],
            )
        ]


class FakeUnderstandingProvider:
    provider_name = "fake-multimodal"
    model_name = "fake-full-episode-v1"

    def __init__(self, factory: sessionmaker[Session], *, hallucinate_evidence: bool = False):
        self.factory = factory
        self.hallucinate_evidence = hallucinate_evidence
        self.calls: list[EpisodeUnderstandingInput] = []
        self.provider_job_seen_before_call = False

    @property
    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "video_input": "FULL_EPISODE_FILE",
            "structured_output": "JSON_SCHEMA",
        }

    def analyze(self, payload: EpisodeUnderstandingInput) -> EpisodeUnderstandingProviderResult:
        self.calls.append(payload)
        assert payload.source_path.is_file()
        assert "reference" not in payload.source_path.name.lower()
        assert "shot-boundary" not in payload.source_path.as_posix()
        with self.factory() as db:
            job = db.scalar(
                select(ProviderJob)
                .where(ProviderJob.episode_id == payload.episode_id)
                .order_by(ProviderJob.created_at.desc())
                .limit(1)
            )
            self.provider_job_seen_before_call = bool(job and job.status == ProviderJobStatus.RUNNING)
        dialogue_ids = [item["id"] for item in payload.evidence_payload["dialogue"]]
        visual_ids = [item["id"] for item in payload.evidence_payload["visual_text"]]
        dialogue_ref = "invented-evidence-id" if self.hallucinate_evidence else dialogue_ids[0]
        semantic = EpisodeUnderstandingSemantic.model_validate(
            {
                "effective_content_range": {"start_us": 0, "end_us": payload.duration_us},
                "visual_format_notes": ["竖屏短剧，快节奏剪辑"],
                "overall_analysis": {
                    "story_summary": "女主赴约后发现旧事再次牵动当前冲突。",
                    "story_background": "现代都市，角色之间有未解决的三年前旧事。",
                    "genre": ["都市", "情感"],
                    "world_rules": ["现实都市环境"],
                    "narrative_structure": "以赴约为开端，通过旧事提示建立冲突。",
                    "audiovisual_style": "竖屏近景为主，反应镜头推动情绪。",
                    "rhythm_overview": "开场快速建立信息，中段留反应停顿。",
                },
                "timed_script": [
                    {
                        "segment_number": 1,
                        "time_range": {"start_us": 150_000, "end_us": 1_150_000},
                        "visual_description": "人物进入画面并面对另一角色。",
                        "story_summary": "见面触发旧事相关的第一轮信息交换。",
                        "narrative_function": "Hook 与冲突建立",
                        "dialogue_evidence_ids": [dialogue_ref],
                        "visual_text_evidence_ids": visual_ids[:1],
                    }
                ],
                "characters": [
                    {
                        "character_id": "char-female-lead",
                        "name": "女主候选",
                        "story_function": "当前冲突的主要承受者与推进者。",
                        "appearance_baseline": "年轻女性，都市装束。",
                        "states": [
                            {
                                "time_range": {"start_us": 150_000, "end_us": 1_150_000},
                                "state": "警惕并压抑情绪",
                            }
                        ],
                    },
                    {
                        "character_id": "char-counterpart",
                        "name": "对手候选",
                        "story_function": "抛出旧事并推动冲突。",
                        "appearance_baseline": "都市装束。",
                        "states": [],
                    },
                ],
                "relationships": [
                    {
                        "source_character_id": "char-female-lead",
                        "target_character_id": "char-counterpart",
                        "relationship": "存在旧日纠葛，当前关系紧张。",
                        "change_summary": "见面后矛盾重新显性化。",
                    }
                ],
                "scenes": [
                    {
                        "scene_id": "scene-meeting",
                        "name": "会面地点",
                        "time_ranges": [{"start_us": 0, "end_us": payload.duration_us}],
                        "spatial_relationship": "两名主要角色在同一会面空间对峙。",
                        "environment_details": "现代室内环境。",
                    }
                ],
                "key_props": [],
                "story_events": [
                    {
                        "event_id": "event-meet",
                        "time_range": {"start_us": 150_000, "end_us": 1_150_000},
                        "summary": "两人见面并开始谈及旧事。",
                        "participants": ["char-female-lead", "char-counterpart"],
                        "consequences": "旧矛盾被重新打开。",
                    }
                ],
                "emotion_timeline": [
                    {
                        "time_range": {"start_us": 150_000, "end_us": 1_150_000},
                        "subject": "女主候选",
                        "emotion": "警惕",
                        "change": "从克制转向明显防御。",
                    }
                ],
                "story_skeleton": {
                    "premise": "一次会面重新激活三年前留下的关系矛盾。",
                    "central_conflict": "主要角色必须面对旧事与当前利益的冲突。",
                    "beats": [
                        {
                            "beat_type": "HOOK",
                            "time_range": {"start_us": 150_000, "end_us": 850_000},
                            "summary": "见面与旧事提示建立悬念。",
                            "importance": 5,
                        }
                    ],
                },
                "rhythm_skeleton": {
                    "overall_pace": "快速建立信息，关键反应处短暂停顿。",
                    "phases": [
                        {
                            "time_range": {"start_us": 0, "end_us": payload.duration_us},
                            "pace": "快",
                            "scene_rhythm": "单场景内快速进入人物关系。",
                            "dialogue_reaction_rhythm": "对白后保留反应时间。",
                            "cut_timing_notes": "冲突信息后切反应镜头。",
                            "key_beat_refs": ["HOOK"],
                            "allowable_deviation_ms": 250,
                        }
                    ],
                },
            }
        )
        return EpisodeUnderstandingProviderResult(semantic=semantic, remote_job_id="fake-upload-file")


def _project(client: TestClient, project_type: str = "REPLICA") -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P7-source-bible",
            "project_type": project_type,
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


def _task(client: TestClient, project_id: str, task_id: str) -> dict:
    response = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _build_p6(client: TestClient, project_id: str, episode_id: str, monkeypatch) -> dict:
    providers = EvidenceProviders(asr=FakeAsrProvider(), ocr=FakeOcrProvider())
    monkeypatch.setattr("app.evidence.service.build_evidence_providers", lambda settings: providers)
    response = client.post(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/commands/source-evidence",
        headers={"Idempotency-Key": "p7-precondition-p6"},
    )
    assert response.status_code == 202, response.text
    assert _task(client, project_id, response.json()["id"])["status"] == "succeeded"
    evidence = client.get(f"/api/v3/projects/{project_id}/episodes/{episode_id}/source-evidence")
    assert evidence.status_code == 200 and evidence.json()["status"] == "CURRENT"
    return evidence.json()


def _start_p7(client: TestClient, project_id: str, key: str) -> dict:
    response = client.post(
        f"/api/v3/projects/{project_id}/commands/source-bible",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return _task(client, project_id, response.json()["id"])


def test_p7_requires_current_source_evidence_and_get_is_read_only(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    _upload(client, project["id"], _video(tmp_path / "episode.mp4"))
    fake = FakeUnderstandingProvider(session_factory)
    monkeypatch.setattr(
        "app.understanding.service.build_source_episode_understanding_provider",
        lambda settings, selection: fake,
    )

    before = client.get(f"/api/v3/projects/{project['id']}/source-bible")
    assert before.status_code == 200 and before.json()["status"] == "NOT_BUILT"
    assert client.get(f"/api/v3/projects/{project['id']}/tasks").json() == []

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/source-bible",
        headers={"Idempotency-Key": "p7-no-evidence"},
    )
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "SOURCE_DIALOGUE_REQUIRED"


def test_p7_uses_full_episode_provider_job_first_and_publishes_typed_artifacts(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    episode = _upload(client, project["id"], _video(tmp_path / "full-episode.mp4"))
    evidence = _build_p6(client, project["id"], episode["id"], monkeypatch)
    fake = FakeUnderstandingProvider(session_factory)
    monkeypatch.setattr(
        "app.understanding.service.build_source_episode_understanding_provider",
        lambda settings, selection: fake,
    )

    task = _start_p7(client, project["id"], "p7-full-episode")
    assert task["status"] == "succeeded"
    assert len(fake.calls) == 1
    assert fake.calls[0].episode_id == episode["id"]
    assert fake.calls[0].source_path.name == "source.mp4"
    assert fake.calls[0].source_filename == "episode.mp4"
    assert fake.provider_job_seen_before_call is True
    assert fake.calls[0].shot_hints == []

    result = client.get(f"/api/v3/projects/{project['id']}/source-bible")
    assert result.status_code == 200, result.text
    bible = result.json()
    assert bible["status"] == "CURRENT" and bible["revision"] == 1
    assert bible["content"]["schema_version"] == "1.0"
    assert bible["content"]["episodes"][0]["material_baseline"]["episode_id"] == episode["id"]
    assert bible["content"]["episodes"][0]["timed_script"][0]["dialogue_evidence_ids"] == [evidence["dialogue"][0]["id"]]
    assert bible["provenance"]["source_dialogue_artifact_id"]
    assert bible["provenance"]["episode_evidence_sets"][0]["source_evidence_set_id"]
    assert len(bible["provenance"]["provider_jobs"]) == 1
    assert bible["story_skeleton_artifact_id"]
    assert bible["rhythm_skeleton_artifact_id"]

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    current_types = set(graph["available_artifact_types"])
    assert {"SOURCE_BIBLE", "STORY_SKELETON", "RHYTHM_SKELETON"}.issubset(current_types)
    bible_node = next(node for node in graph["nodes"] if node["id"] == bible["artifact_id"])
    assert "content" not in bible_node["metadata_json"]


def test_p7_rejects_hallucinated_evidence_reference_and_does_not_publish(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    episode = _upload(client, project["id"], _video(tmp_path / "invalid-evidence.mp4"))
    _build_p6(client, project["id"], episode["id"], monkeypatch)
    fake = FakeUnderstandingProvider(session_factory, hallucinate_evidence=True)
    monkeypatch.setattr(
        "app.understanding.service.build_source_episode_understanding_provider",
        lambda settings, selection: fake,
    )

    task = _start_p7(client, project["id"], "p7-invalid-evidence")
    assert task["status"] == "failed"
    assert "SOURCE_BIBLE_EVIDENCE_REF_INVALID" in (task["last_error"] or "")
    result = client.get(f"/api/v3/projects/{project['id']}/source-bible").json()
    assert result["status"] == "NOT_BUILT"


def test_p7_edit_creates_new_revision_stales_old_derivatives_and_preserves_evidence(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    episode = _upload(client, project["id"], _video(tmp_path / "edit.mp4"))
    _build_p6(client, project["id"], episode["id"], monkeypatch)
    evidence_before = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence"
    ).json()
    fake = FakeUnderstandingProvider(session_factory)
    monkeypatch.setattr(
        "app.understanding.service.build_source_episode_understanding_provider",
        lambda settings, selection: fake,
    )
    assert _start_p7(client, project["id"], "p7-before-edit")["status"] == "succeeded"

    first = client.get(f"/api/v3/projects/{project['id']}/source-bible").json()
    old_story_id = first["story_skeleton_artifact_id"]
    old_rhythm_id = first["rhythm_skeleton_artifact_id"]
    edited_content = first["content"]
    edited_content["episodes"][0]["overall_analysis"]["story_summary"] = "人工修订后的源作故事概述。"
    edit = client.post(
        f"/api/v3/projects/{project['id']}/source-bible/commands/edit",
        json={"content": edited_content},
    )
    assert edit.status_code == 201, edit.text
    second = edit.json()
    assert second["status"] == "CURRENT" and second["revision"] == 2
    assert second["artifact_id"] != first["artifact_id"]
    assert second["content"]["episodes"][0]["overall_analysis"]["story_summary"] == "人工修订后的源作故事概述。"
    assert second["provenance"]["edit_parent_artifact_id"] == first["artifact_id"]
    assert second["provenance"]["provider_jobs"] == []

    revisions = client.get(f"/api/v3/projects/{project['id']}/source-bible/revisions").json()
    assert [(item["revision"], item["status"]) for item in revisions[:2]] == [(2, "CURRENT"), (1, "STALE")]

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    by_id = {node["id"]: node for node in graph["nodes"]}
    assert by_id[first["artifact_id"]]["validity"] == "STALE"
    assert by_id[old_story_id]["validity"] == "STALE"
    assert by_id[old_rhythm_id]["validity"] == "STALE"
    assert by_id[second["story_skeleton_artifact_id"]]["validity"] == "CURRENT"
    assert by_id[second["rhythm_skeleton_artifact_id"]]["validity"] == "CURRENT"
    assert any(
        edge["source_node_id"] == second["artifact_id"]
        and edge["target_node_id"] == first["artifact_id"]
        and edge["relation_type"] == "SUPERSEDES"
        for edge in graph["edges"]
    )

    evidence_after = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence"
    ).json()
    assert evidence_after["status"] == "CURRENT"
    assert evidence_after["dialogue"] == evidence_before["dialogue"]
    assert evidence_after["visual_text"] == evidence_before["visual_text"]


def test_p7_switching_provider_stales_source_bible_but_preserves_source_evidence(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    assert project["source_understanding_provider"] == "DOUBAO_SEED_2_1_PRO_API"
    episode = _upload(client, project["id"], _video(tmp_path / "provider-switch.mp4"))
    evidence_before = _build_p6(client, project["id"], episode["id"], monkeypatch)
    fake = FakeUnderstandingProvider(session_factory)
    selections: list[str] = []

    def build_fake(settings, selection):
        selections.append(selection.value)
        return fake

    monkeypatch.setattr("app.understanding.service.build_source_episode_understanding_provider", build_fake)
    assert _start_p7(client, project["id"], "p7-provider-before-switch")["status"] == "succeeded"
    current = client.get(f"/api/v3/projects/{project['id']}/source-bible").json()
    assert current["status"] == "CURRENT"
    old_story_id = current["story_skeleton_artifact_id"]
    old_rhythm_id = current["rhythm_skeleton_artifact_id"]
    assert selections and set(selections) == {"DOUBAO_SEED_2_1_PRO_API"}

    changed = client.patch(
        f"/api/v3/projects/{project['id']}",
        json={"source_understanding_provider": "QWEN3_VL_LOCAL"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["source_understanding_provider"] == "QWEN3_VL_LOCAL"

    stale = client.get(f"/api/v3/projects/{project['id']}/source-bible").json()
    assert stale["status"] == "STALE"
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    by_id = {node["id"]: node for node in graph["nodes"]}
    assert by_id[current["artifact_id"]]["validity"] == "STALE"
    assert by_id[old_story_id]["validity"] == "STALE"
    assert by_id[old_rhythm_id]["validity"] == "STALE"

    evidence_after = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence"
    ).json()
    assert evidence_after["status"] == "CURRENT"
    assert evidence_after["dialogue"] == evidence_before["dialogue"]
    assert evidence_after["visual_text"] == evidence_before["visual_text"]


def test_p7_does_not_run_for_translation(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client, "TRANSLATION")
    episode = _upload(client, project["id"], _video(tmp_path / "translation.mp4"))
    _build_p6(client, project["id"], episode["id"], monkeypatch)
    fake = FakeUnderstandingProvider(session_factory)
    monkeypatch.setattr(
        "app.understanding.service.build_source_episode_understanding_provider",
        lambda settings, selection: fake,
    )
    response = client.post(
        f"/api/v3/projects/{project['id']}/commands/source-bible",
        headers={"Idempotency-Key": "p7-translation-rejected"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SOURCE_BIBLE_NOT_ALLOWED"
