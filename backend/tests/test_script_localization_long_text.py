"""Long-script model calls use a fake Provider. Real model quality is separately accepted."""

import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.script_localization import long_pipeline
from app.script_localization.long_text import MAX_LONG_CHARS, assert_complete, split_source
from app.script_localization.schemas import AnalysisSemantic, LocalizedScriptSemantic, PlanSemantic
from app.workflow.dispatcher import run_dispatcher_once


class LongMockProvider:
    provider_name = "long-test-provider"
    model_name = "long-test-model"
    calls = []
    fail_at: int | None = None

    def __init__(self, _settings, _selection):
        pass

    def profile(self):
        return {"provider": self.provider_name, "model": self.model_name}

    def generate(self, *, skill_id, prompt, output_model, max_output_tokens=None):
        assert max_output_tokens == 8192
        self.__class__.calls.append((skill_id, output_model.__name__))
        if self.__class__.fail_at == len(self.__class__.calls):
            raise AppError("SIMULATED_PROVIDER_FAILURE", "模拟第 3 段失败", status_code=502)
        if output_model is AnalysisSemantic:
            return AnalysisSemantic(
                title="长剧本", synopsis="主角经历事件", characters=[{"name": "甲"}],
                scenes=[{"number": 1, "summary": "人物发生冲突"}],
                story_beats=[{"order": 1, "function": "CONFLICT", "summary": "角色遭遇挑战"}],
                rhythm_beats=[{"order": 1, "function": "HOOK", "summary": "保留节奏"}],
            ), "mock-analysis"
        if output_model is PlanSemantic:
            return PlanSemantic(
                creative_intent="保留因果和角色关系", preservation_locks=["角色关系"],
                mappings=[{"category": "CHARACTER_NAME", "source": "甲", "target": "Alex", "reason": "全剧统一"}],
            ), "mock-plan"
        if output_model is LocalizedScriptSemantic:
            return LocalizedScriptSemantic(title="Localized", script_text="INT. OFFICE - DAY\nALEX: Hello!\n" * 45), "mock-script"
        raise AssertionError(output_model)


@pytest.fixture(autouse=True)
def clear_mock_state(monkeypatch):
    LongMockProvider.calls = []
    LongMockProvider.fail_at = None
    monkeypatch.setattr(long_pipeline, "ScriptLocalizationProvider", LongMockProvider)


def project(client: TestClient, kind: str = "SCRIPT_LOCALIZATION") -> str:
    payload = {"name": "长剧本", "project_type": kind, "target_language": "en-US", "target_region": "US"}
    if kind == "REPLICA":
        payload["source_language"] = "zh-CN"
    result = client.post("/api/v3/projects", json=payload)
    assert result.status_code == 201, result.text
    return result.json()["id"]


def long_script() -> str:
    return "内景·办公室·日\n甲：你好！\n" * 1800


def run_stage(client: TestClient, factory: sessionmaker[Session], project_id: str, stage: str) -> dict:
    base = f"/api/v3/projects/{project_id}/script-localization"
    started = client.post(f"{base}/commands/run/{stage}", headers={"Idempotency-Key": str(uuid4())})
    assert started.status_code == 202, started.text
    assert started.json()["task_type"] == long_pipeline.TASK_TYPE
    run_dispatcher_once(factory)
    task = client.get(f"/api/v3/projects/{project_id}/tasks/{started.json()['id']}").json()
    assert task["status"] == "succeeded", task
    return task


def test_chunk_split_is_lossless_and_detects_omission() -> None:
    text = ("场景·甲\n对白\n\n" * 1600) + "最后一场"
    chunks = split_source(text, max_chars=420)
    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == text
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    outputs = [{**part.manifest(), "chunk_index": part.index, "text": "result"} for part in chunks]
    assert_complete(chunks, original=text, results=outputs)
    with pytest.raises(AppError, match="模型生成分段数量不足"):
        assert_complete(chunks, original=text, results=outputs[:-1])
    with pytest.raises(AppError, match="不对应"):
        assert_complete(chunks, original=text, results=[{**outputs[0], "source_sha256": "bad"}, *outputs[1:]])
    with pytest.raises(AppError, match="最多处理"):
        split_source("甲" * (MAX_LONG_CHARS + 1))


def test_long_full_pipeline_generates_every_chunk_and_exports(client: TestClient, session_factory) -> None:
    pid = project(client)
    base = f"/api/v3/projects/{pid}/script-localization"
    text = long_script()
    chunks = split_source(text)
    upload = client.post(f"{base}/paste", json={"text": text})
    assert upload.status_code == 201, upload.text
    run_stage(client, session_factory, pid, "analyze")
    state = client.get(f"{base}/state").json()
    analysis = state["analysis"]["content"]
    assert analysis["source_chunk_manifest"] == [c.manifest() for c in chunks]
    assert len(analysis["chunk_analyses"]) == len(chunks)
    assert len(analysis["semantic"]["story_beats"]) == len(chunks)
    run_stage(client, session_factory, pid, "plan")
    plan = client.get(f"{base}/state").json()["plan"]["content"]
    assert len(plan["chunk_plans"]) == len(chunks)
    assert plan["semantic"]["mappings"][0]["target"] == "Alex"
    run_stage(client, session_factory, pid, "generate")
    state = client.get(f"{base}/state").json()
    target = state["target_script"]["content"]
    assert len(target["source_chunk_manifest"]) == len(chunks)
    assert target["text"].count("INT. OFFICE") == len(chunks) * 45
    assert len(LongMockProvider.calls) == len(chunks) * 3
    assert client.get(f"{base}/source").json()["text"] == text
    exported = client.post(f"{base}/commands/export")
    assert exported.status_code == 200
    assert exported.json()["content"]["text"] == target["text"]
    replacement = client.post(f"{base}/paste", json={"text": text + "\n新增场景"})
    assert replacement.status_code == 201
    after = client.get(f"{base}/state").json()
    assert all(after[key]["status"] == "STALE" for key in ("analysis", "plan", "target_script", "final_output"))
    blocked = client.post(f"{base}/commands/run/generate", headers={"Idempotency-Key": str(uuid4())})
    assert blocked.status_code == 409


def test_long_retry_resumes_after_last_committed_chunk(client: TestClient, session_factory) -> None:
    pid = project(client)
    base = f"/api/v3/projects/{pid}/script-localization"
    assert client.post(f"{base}/paste", json={"text": long_script()}).status_code == 201
    LongMockProvider.fail_at = 3
    response = client.post(f"{base}/commands/run/analyze", headers={"Idempotency-Key": "first-attempt"})
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    run_dispatcher_once(session_factory)
    failed = client.get(f"/api/v3/projects/{pid}/tasks/{task_id}").json()
    assert failed["status"] == "failed"
    with session_factory() as db:
        from app.workflow.models import Task
        checkpoint = db.get(Task, task_id).checkpoint_json
        assert len(checkpoint["parts"]) == 2 and len(checkpoint["job_ids"]) == 2
    LongMockProvider.fail_at = None
    retry = client.post(f"{base}/commands/run/analyze", headers={"Idempotency-Key": "resume-attempt"})
    assert retry.status_code == 202 and retry.json()["id"] == task_id
    run_dispatcher_once(session_factory)
    assert client.get(f"/api/v3/projects/{pid}/tasks/{task_id}").json()["status"] == "succeeded"
    assert len(LongMockProvider.calls) == len(split_source(long_script())) + 1


def test_long_pipeline_rejects_replica_and_over_budget_without_calling_provider(client: TestClient) -> None:
    replica = project(client, "REPLICA")
    rejected = client.post(f"/api/v3/projects/{replica}/script-localization/commands/run/analyze",
                           headers={"Idempotency-Key": str(uuid4())})
    assert rejected.status_code == 422
    pid = project(client)
    base = f"/api/v3/projects/{pid}/script-localization"
    assert client.post(f"{base}/paste", json={"text": "甲" * (MAX_LONG_CHARS + 1)}).status_code == 201
    blocked = client.post(f"{base}/commands/run/analyze", headers={"Idempotency-Key": str(uuid4())})
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "SCRIPT_LOCALIZATION_SOURCE_TOO_LONG"
    assert not LongMockProvider.calls
