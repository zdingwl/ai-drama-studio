"""Mock-model tests prove task/artifact plumbing, not real Provider quality or video generation."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.script_to_drama.service as service
from app.script_localization.schemas import AnalysisSemantic
from app.script_to_drama.schemas import StoryboardChunk, WorldChunk
from app.workflow.dispatcher import run_dispatcher_once


class MockProvider:
    provider_name = "mock-text"
    model_name = "mock-script-model"
    invalid_quote = False

    def __init__(self, _settings, _selection):
        pass

    def profile(self):
        return {"provider": self.provider_name, "model": self.model_name}

    def generate(self, *, skill_id, prompt, output_model, max_output_tokens=None):
        assert max_output_tokens == 8192
        if output_model is AnalysisSemantic:
            return AnalysisSemantic(
                title="测试剧本", synopsis="甲在办公室发现真相。",
                characters=[{"name": "甲", "role": "主角", "speech_style": "果断", "relations": []}],
                scenes=[{"number": 1, "heading": "内景·办公室", "summary": "甲行动", "characters": ["甲"]}],
                story_beats=[{"order": 1, "function": "ACTION", "summary": "甲行动", "must_preserve": True}],
                rhythm_beats=[{"order": 1, "function": "ACTION", "summary": "转折", "must_preserve": True}],
                cultural_elements=[], preservation_locks=[], unresolved_questions=[],
            ), "analysis-remote"
        if output_model is WorldChunk:
            chunk = prompt.rsplit("本段原文：\n", 1)[1]
            return WorldChunk(
                characters=[{"name": "甲", "visual_description": "短发黑色外套",
                             "source_evidence": chunk[:8], "source_fact": "甲出现"}],
                locations=[{"name": "办公室", "visual_description": "现代办公室有一张桌子",
                            "source_evidence": chunk[:8], "source_fact": "办公室"}],
                props=[], unresolved_decisions=[],
            ), "world-remote"
        if output_model is StoryboardChunk:
            chunk = prompt.rsplit("本段原文：\n", 1)[1]
            return StoryboardChunk(shots=[{
                "source_quote": "不存在的原文" if self.invalid_quote else chunk[:8],
                "narrative_beat": "主角行动", "character_ids": [service._id("CHARACTER", "甲")],
                "scene_id": service._id("SCENE", "办公室"), "prop_ids": [],
                "shot_size": "中景", "camera_angle": "平视", "composition": "甲在画面中央",
                "camera_motion": "固定机位", "visible_action": "甲走进办公室",
                "dialogue_or_voiceover": "", "estimated_seconds": 5.0,
                "continuity_notes": "人物方向保持一致",
            }]), "storyboard-remote"
        raise AssertionError(f"unexpected output model {output_model}, skill {skill_id}")


def create_project(client: TestClient, kind: str = "SCRIPT_TO_DRAMA") -> str:
    payload = {"name": "剧本短剧测试", "project_type": kind, "target_language": "zh-CN", "target_region": "CN"}
    if kind == "REPLICA":
        payload["source_language"] = "zh-CN"
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def execute(client: TestClient, factory: sessionmaker[Session], project_id: str, stage: str) -> dict:
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    response = client.post(f"{base}/commands/run/{stage}", headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 202, response.text
    run_dispatcher_once(factory)
    result = client.get(f"/api/v3/projects/{project_id}/tasks/{response.json()['id']}").json()
    return result


def approve_assets(client: TestClient, project_id: str) -> dict:
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    before = client.get(f"{base}/state").json()
    assert before["world"]["status"] == "CURRENT"
    response = client.post(f"{base}/commands/review-world", json={
        "expected_world_artifact_id": before["world"]["artifact_id"],
        "approve": True,
        "reason": "人工检查并确认测试剧本的当前人物与场景清单",
    })
    assert response.status_code == 200, response.text
    assert response.json()["world"]["content"]["review_status"] == "APPROVED"
    return response.json()


def test_preproduction_pipeline_two_chunks_and_source_staleness(client: TestClient, session_factory, monkeypatch) -> None:
    monkeypatch.setattr(service, "ScriptLocalizationProvider", MockProvider)
    project_id = create_project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    source_text = "内景·办公室·日\n甲：我会回来。\n" * 360
    assert len(source_text) > 4000
    response = client.post(f"{base}/paste", json={"text": source_text})
    assert response.status_code == 201, response.text
    assert client.get(f"{base}/source").json()["text"] == source_text

    assert execute(client, session_factory, project_id, "analyze")["status"] == "succeeded"
    state = client.get(f"{base}/state").json()
    assert state["analysis"]["status"] == "CURRENT"
    assert len(state["analysis"]["content"]["chunk_analyses"]) >= 2
    assert execute(client, session_factory, project_id, "world")["status"] == "succeeded"
    state = client.get(f"{base}/state").json()
    assert state["world"]["status"] == "CURRENT"
    assert state["assets"]["content"]["status"] == "DEFINITIONS_ONLY"
    denied = client.post(f"{base}/commands/run/storyboard", headers={"Idempotency-Key": str(uuid4())})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "SCRIPT_TO_DRAMA_ASSETS_NOT_APPROVED"
    approve_assets(client, project_id)
    assert execute(client, session_factory, project_id, "storyboard")["status"] == "succeeded"
    state = client.get(f"{base}/state").json()
    assert state["storyboard"]["status"] == "CURRENT"
    shots = state["storyboard"]["content"]["shots"]
    assert {shot["source_chunk_index"] for shot in shots} == set(range(1, len(state["analysis"]["content"]["chunk_analyses"]) + 1))
    assert state["video_runtime_status"] == "PRODUCTION_PIPELINE_CONNECTED"

    assert client.post(f"{base}/paste", json={"text": "内景·办公室·夜\n甲：晚安。"}).status_code == 201
    state = client.get(f"{base}/state").json()
    assert all(state[key]["status"] == "STALE" for key in ("analysis", "world", "assets", "storyboard"))
    assert all(state[key]["status"] == "NOT_BUILT" for key in ("asset_images", "prompts", "generated_video", "selection", "final_output"))
    assert client.post(f"{base}/commands/run/storyboard", headers={"Idempotency-Key": str(uuid4())}).status_code == 409


def test_wrong_project_type_cannot_invoke_preproduction(client: TestClient, session_factory, monkeypatch) -> None:
    monkeypatch.setattr(service, "ScriptLocalizationProvider", MockProvider)
    replica = create_project(client, "REPLICA")
    script_localization = create_project(client, "SCRIPT_LOCALIZATION")
    for project_id in (replica, script_localization):
        base = f"/api/v3/projects/{project_id}/script-to-drama"
        assert client.get(f"{base}/source").status_code == 422
        assert client.get(f"{base}/state").status_code == 422
        response = client.post(f"{base}/commands/run/analyze", headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SCRIPT_TO_DRAMA_NOT_ALLOWED"


def test_unknown_quote_refuses_storyboard_publication(client: TestClient, session_factory, monkeypatch) -> None:
    class InvalidProvider(MockProvider):
        invalid_quote = True
    monkeypatch.setattr(service, "ScriptLocalizationProvider", InvalidProvider)
    project_id = create_project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    assert client.post(f"{base}/paste", json={"text": "内景·办公室\n甲：你好。"}).status_code == 201
    assert execute(client, session_factory, project_id, "analyze")["status"] == "succeeded"
    assert execute(client, session_factory, project_id, "world")["status"] == "succeeded"
    approve_assets(client, project_id)
    assert execute(client, session_factory, project_id, "storyboard")["status"] == "failed"
    assert client.get(f"{base}/state").json()["storyboard"]["status"] == "NOT_BUILT"
    assert client.post(f"{base}/commands/run/generate", headers={"Idempotency-Key": str(uuid4())}).status_code == 422
