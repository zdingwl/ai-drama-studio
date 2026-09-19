import time
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.script_localization.service as service
from app.script_localization.schemas import AnalysisSemantic, LocalizedScriptSemantic, PlanSemantic
from app.workflow.dispatcher import run_dispatcher_once


class MockProvider:
    provider_name = "mock-text-provider"
    model_name = "mock-model"

    def __init__(self, _settings, _selection):
        pass

    def profile(self):
        return {"provider": self.provider_name, "model": self.model_name}

    def generate(self, *, skill_id, prompt, output_model):
        if output_model is AnalysisSemantic:
            return AnalysisSemantic(
                title="测试短剧", synopsis="主角受到挑战并揭示真相。",
                characters=[{"name": "甲", "role": "主角", "speech_style": "直接", "relations": []}],
                scenes=[{"number": 1, "heading": "内景·办公室·日", "summary": "甲遇到冲突", "characters": ["甲"]}],
                story_beats=[{"order": 1, "function": "HOOK", "summary": "甲遇到冲突", "must_preserve": True}],
                rhythm_beats=[{"order": 1, "function": "HOOK", "summary": "开场悬念", "must_preserve": True}],
                cultural_elements=[], preservation_locks=["不得改变冲突顺序"], unresolved_questions=[],
            ), "mock-job-analysis"
        if output_model is PlanSemantic:
            return PlanSemantic(
                creative_intent="故事不变，文化表达自然化",
                preservation_locks=["冲突顺序"],
                mappings=[{"category": "CHARACTER_NAME", "source": "甲", "target": "Alex", "reason": "统一角色映射"}],
                terminology=[], dialogue_style_guide=["口语自然"], unresolved_decisions=[],
            ), "mock-job-plan"
        if output_model is LocalizedScriptSemantic:
            return LocalizedScriptSemantic(
                title="Localized script", script_text="INT. OFFICE - DAY\nALEX: Hello!",
                changes=[{"category": "CHARACTER_NAME", "source": "甲", "target": "Alex", "reason": "本地命名"}],
                consistency_notes=[],
            ), "mock-job-script"
        raise AssertionError(f"unexpected model: {output_model}")


def create_project(client: TestClient, kind: str = "SCRIPT_LOCALIZATION") -> str:
    payload = {"name": "剧本本土化验收", "project_type": kind, "target_language": "en-US", "target_region": "US"}
    if kind == "REPLICA":
        payload["source_language"] = "zh-CN"
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start_and_wait(client: TestClient, factory: sessionmaker[Session], project_id: str, stage: str) -> dict:
    base = f"/api/v3/projects/{project_id}/script-localization"
    response = client.post(f"{base}/commands/run/{stage}", headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    for _ in range(100):
        run_dispatcher_once(factory)
        task = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}").json()
        if task["status"] in {"succeeded", "failed", "cancelled"}:
            assert task["status"] == "succeeded", task
            return task
        time.sleep(0.02)
    raise AssertionError(f"stage {stage} did not finish")


def test_script_localization_full_pipeline_and_revision_staleness(client: TestClient, session_factory, monkeypatch) -> None:
    monkeypatch.setattr(service, "ScriptLocalizationProvider", MockProvider)
    project_id = create_project(client)
    base = f"/api/v3/projects/{project_id}/script-localization"
    pasted = client.post(f"{base}/paste", json={"text": "内景·办公室·日\n甲：你好！"})
    assert pasted.status_code == 201, pasted.text
    initial = client.get(f"{base}/state").json()
    assert initial["analysis"]["status"] == "NOT_BUILT"

    start_and_wait(client, session_factory, project_id, "analyze")
    analysis = client.get(f"{base}/state").json()
    assert analysis["analysis"]["status"] == "CURRENT"
    assert analysis["analysis"]["content"]["semantic"]["characters"][0]["name"] == "甲"
    assert client.get(f"{base}/source").json()["text"] == "内景·办公室·日\n甲：你好！"

    start_and_wait(client, session_factory, project_id, "plan")
    plan = client.get(f"{base}/state").json()
    assert plan["plan"]["status"] == "CURRENT"
    assert plan["plan"]["content"]["semantic"]["mappings"][0]["target"] == "Alex"

    start_and_wait(client, session_factory, project_id, "generate")
    generated = client.get(f"{base}/state").json()
    assert generated["target_script"]["status"] == "CURRENT"
    first_id = generated["target_script"]["artifact_id"]
    assert generated["target_script"]["content"]["text"].startswith("INT. OFFICE")

    saved = client.post(f"{base}/commands/save", json={
        "expected_artifact_id": first_id, "script_text": "INT. OFFICE - DAY\nALEX: Revised!",
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2
    assert saved.json()["content"]["text"].endswith("Revised!")
    stale_edit = client.post(f"{base}/commands/save", json={
        "expected_artifact_id": first_id, "script_text": "旧版覆盖",
    })
    assert stale_edit.status_code == 409
    assert stale_edit.json()["error"]["code"] == "SCRIPT_LOCALIZATION_EDIT_CONFLICT"

    exported = client.post(f"{base}/commands/export")
    assert exported.status_code == 200, exported.text
    assert exported.json()["content"]["text"].endswith("Revised!")
    assert exported.json()["content"]["source_target_script_artifact_id"] == saved.json()["artifact_id"]
    repeated = client.post(f"{base}/commands/export")
    assert repeated.json()["artifact_id"] == exported.json()["artifact_id"]

    updated = client.post(f"{base}/paste", json={"text": "内景·办公室·夜\n甲：晚安！"})
    assert updated.status_code == 201
    state = client.get(f"{base}/state").json()
    assert all(state[key]["status"] == "STALE" for key in ("analysis", "plan", "target_script", "final_output"))
    assert client.get(f"{base}/source").json()["text"] == "内景·办公室·夜\n甲：晚安！"
    blocked = client.post(f"{base}/commands/run/generate", headers={"Idempotency-Key": str(uuid4())})
    assert blocked.status_code == 409


def test_replica_cannot_access_script_localization_model_commands(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(service, "ScriptLocalizationProvider", MockProvider)
    project_id = create_project(client, "REPLICA")
    base = f"/api/v3/projects/{project_id}/script-localization"
    assert client.get(f"{base}/state").status_code == 422
    command = client.post(f"{base}/commands/run/analyze", headers={"Idempotency-Key": str(uuid4())})
    assert command.status_code == 422
    assert command.json()["error"]["code"] == "SCRIPT_LOCALIZATION_NOT_ALLOWED"
