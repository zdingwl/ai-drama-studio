"""One-click asset extraction is a real two-task chain, not a frontend button alias."""
from uuid import uuid4

from fastapi.testclient import TestClient

import app.script_to_drama.extraction as extraction
import app.script_to_drama.service as service
from app.script_localization.schemas import AnalysisSemantic
from app.script_to_drama.schemas import WorldChunk
from app.workflow.dispatcher import run_dispatcher_once


class MockProvider:
    provider_name = "mock-asset-extraction"
    model_name = "mock-analysis-model"

    def __init__(self, *_args):
        pass

    def profile(self):
        return {"provider": self.provider_name, "model": self.model_name}

    def generate(self, *, skill_id, prompt, output_model, max_output_tokens=None):
        if output_model is AnalysisSemantic:
            return AnalysisSemantic(
                title="剧本", synopsis="甲走进办公室。",
                characters=[{"name": "甲", "role": "主角", "speech_style": "自然", "relations": []}],
                scenes=[{"number": 1, "heading": "内景·办公室", "summary": "甲走进", "characters": ["甲"]}],
                story_beats=[{"order": 1, "function": "ACTION", "summary": "甲走进", "must_preserve": True}],
                rhythm_beats=[{"order": 1, "function": "ACTION", "summary": "甲行动", "must_preserve": True}],
                cultural_elements=[], preservation_locks=[], unresolved_questions=[],
            ), "analysis-remote"
        if output_model is WorldChunk:
            chunk = prompt.rsplit("本段原文：\n", 1)[1]
            return WorldChunk(
                characters=[{"name": "甲", "visual_description": "短发", "source_evidence": chunk[:8]}],
                locations=[{"name": "办公室", "visual_description": "明亮的办公室", "source_evidence": chunk[:8]}],
                props=[], unresolved_decisions=[],
            ), "world-remote"
        raise AssertionError(f"unexpected {output_model}")


def new_project(client: TestClient, project_type="SCRIPT_TO_DRAMA") -> str:
    payload = {"name": "一键提取资产", "project_type": project_type,
               "target_language": "zh-CN", "target_region": "CN"}
    if project_type == "REPLICA":
        payload["source_language"] = "zh-CN"
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_one_click_extraction_queues_world_after_analysis_then_requires_approval(client, session_factory, monkeypatch):
    monkeypatch.setattr(service, "ScriptLocalizationProvider", MockProvider)
    monkeypatch.setattr(extraction, "ScriptLocalizationProvider", MockProvider)
    project_id = new_project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    assert client.post(f"{base}/paste", json={"text": "内景·办公室\n甲走进办公室。"}).status_code == 201

    response = client.post(f"{base}/commands/extract-assets", headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 202, response.text
    assert response.json()["task_type"] == "SCRIPT_TO_DRAMA_ASSET_EXTRACTION"
    assert run_dispatcher_once(session_factory)
    interim = client.get(f"{base}/state").json()
    assert interim["analysis"]["status"] == "CURRENT"
    assert interim["world"]["status"] == "NOT_BUILT"
    # The second step is already queued by the backend; no second UI button required.
    assert run_dispatcher_once(session_factory)
    extracted = client.get(f"{base}/state").json()
    assert extracted["world"]["status"] == "CURRENT"
    assert extracted["assets"]["status"] == "CURRENT"
    assert extracted["world"]["content"].get("review_status") != "APPROVED"

    denied = client.post(f"{base}/commands/run/storyboard", headers={"Idempotency-Key": str(uuid4())})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "SCRIPT_TO_DRAMA_ASSETS_NOT_APPROVED"
    denied_images = client.post(f"{base}/commands/production/asset_images", headers={"Idempotency-Key": str(uuid4())})
    assert denied_images.status_code == 409
    assert denied_images.json()["error"]["code"] == "SCRIPT_TO_DRAMA_ASSETS_NOT_APPROVED"

    approve = client.post(f"{base}/commands/review-world", json={
        "expected_world_artifact_id": extracted["world"]["artifact_id"],
        "approve": True, "reason": "已人工核对当前人物场景道具清单",
    })
    assert approve.status_code == 200, approve.text
    confirmed = approve.json()
    assert confirmed["world"]["content"]["review_status"] == "APPROVED"
    assert confirmed["assets"]["content"]["review_status"] == "APPROVED"
    assert confirmed["analysis"]["status"] == "CURRENT"
    assert client.post(f"{base}/commands/run/storyboard", headers={"Idempotency-Key": str(uuid4())}).status_code == 202


def test_reject_other_project_types_and_empty_script(client):
    replica = new_project(client, "REPLICA")
    denied = client.post(f"/api/v3/projects/{replica}/script-to-drama/commands/extract-assets",
                         headers={"Idempotency-Key": str(uuid4())})
    assert denied.status_code == 422
    assert denied.json()["error"]["code"] == "SCRIPT_TO_DRAMA_NOT_ALLOWED"
    text_project = new_project(client)
    empty = client.post(f"/api/v3/projects/{text_project}/script-to-drama/commands/extract-assets",
                        headers={"Idempotency-Key": str(uuid4())})
    assert empty.status_code == 409
