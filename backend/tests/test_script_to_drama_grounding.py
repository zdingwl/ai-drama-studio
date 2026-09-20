"""Asset evidence is either an actual source span or a failed world task."""

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.script_to_drama.service as service
from app.core.errors import AppError
from app.script_localization.long_text import SourceChunk
from app.script_localization.schemas import AnalysisSemantic
from app.script_to_drama.schemas import WorldChunk
from app.workflow.dispatcher import run_dispatcher_once
from app.workflow.models import ProviderJob, ProviderJobStatus


def _chunk(text: str) -> SourceChunk:
    return SourceChunk(index=1, start=0, end=len(text), text=text)


def _world(evidence: str) -> dict:
    return WorldChunk(
        characters=[{"name": "甲", "visual_description": "短发", "source_evidence": evidence}],
        locations=[{"name": "办公室", "visual_description": "现代办公室", "source_evidence": evidence}],
    ).model_dump(mode="json")


def test_world_evidence_quotes_are_repaired_to_real_source_span() -> None:
    text = "内景·办公室\n甲：我会回来。"
    value = _world(" “甲：我会回来。” ")
    service._validate_part("world", _chunk(text), value, None)
    assert value["characters"][0]["source_evidence"] == "甲：我会回来。"
    assert value["locations"][0]["source_evidence"] == "甲：我会回来。"


def test_world_evidence_whitespace_repair_preserves_original_source() -> None:
    text = "内景·办公室\n甲：\n 我会回来。"
    value = _world("甲： 我会回来。")
    service._validate_part("world", _chunk(text), value, None)
    assert value["characters"][0]["source_evidence"] == "甲：\n 我会回来。"


def test_world_evidence_missing_is_rejected_with_asset_and_chunk() -> None:
    value = _world("甲在火星开会。")
    with pytest.raises(AppError) as captured:
        service._validate_part("world", _chunk("甲在办公室。"), value, None)
    assert captured.value.code == "SCRIPT_TO_DRAMA_UNGROUNDED_WORLD"
    assert "第 1 段" in captured.value.message
    assert "人物「甲」" in captured.value.message
    assert value["characters"][0]["source_evidence"] == "甲在火星开会。"


class FlakyGroundingProvider:
    provider_name = "mock-text"
    model_name = "mock-world-grounding"
    calls = 0
    always_invent = False

    def __init__(self, _settings, _selection):
        pass

    def profile(self):
        return {"provider": self.provider_name, "model": self.model_name}

    def generate(self, *, skill_id, prompt, output_model, max_output_tokens=None):
        assert max_output_tokens == 8192
        if output_model is AnalysisSemantic:
            return AnalysisSemantic(
                title="测试剧本", synopsis="甲在办公室说话。",
                characters=[{"name": "甲", "role": "主角", "speech_style": "果断", "relations": []}],
                scenes=[{"number": 1, "heading": "内景·办公室", "summary": "甲行动", "characters": ["甲"]}],
                story_beats=[{"order": 1, "function": "ACTION", "summary": "甲行动", "must_preserve": True}],
                rhythm_beats=[{"order": 1, "function": "ACTION", "summary": "转折", "must_preserve": True}],
                cultural_elements=[], preservation_locks=[], unresolved_questions=[],
            ), "analysis-remote"
        if output_model is WorldChunk:
            type(self).calls += 1
            evidence = ("不存在于剧本的角色和地点" if self.always_invent or self.calls == 1
                        else "“甲：我会回来。”")
            return WorldChunk.model_validate(_world(evidence)), f"world-remote-{self.calls}"
        raise AssertionError(f"unexpected output model: {output_model}")


def _execute(client: TestClient, factory: sessionmaker[Session], project_id: str, stage: str) -> dict:
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    response = client.post(f"{base}/commands/run/{stage}", headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 202, response.text
    url = f"/api/v3/projects/{project_id}/tasks/{response.json()['id']}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run_dispatcher_once(factory)
        result = client.get(url).json()
        if result["status"] in {"succeeded", "failed", "cancelled"}:
            return result
        time.sleep(0.05)
    raise AssertionError(f"task did not finish: {client.get(url).json()}")


def _run_world(client, factory, monkeypatch, *, always_invent: bool):
    FlakyGroundingProvider.calls = 0
    FlakyGroundingProvider.always_invent = always_invent
    monkeypatch.setattr(service, "ScriptLocalizationProvider", FlakyGroundingProvider)
    project = client.post("/api/v3/projects", json={
        "name": "原文证据回归", "project_type": "SCRIPT_TO_DRAMA",
        "target_language": "zh-CN", "target_region": "CN",
    })
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    assert client.post(f"{base}/paste", json={"text": "内景·办公室\n甲：我会回来。"}).status_code == 201
    assert _execute(client, factory, project_id, "analyze")["status"] == "succeeded"
    world_task = _execute(client, factory, project_id, "world")
    with factory() as db:
        jobs = list(db.scalars(select(ProviderJob).where(
            ProviderJob.task_id == world_task["id"]
        ).order_by(ProviderJob.created_at, ProviderJob.id)).all())
    state = client.get(f"{base}/state").json()
    return world_task, jobs, state


def test_world_retry_uses_separate_jobs_and_publishes_only_grounded_results(client, session_factory, monkeypatch) -> None:
    task, jobs, state = _run_world(client, session_factory, monkeypatch, always_invent=False)
    assert task["status"] == "succeeded"
    assert FlakyGroundingProvider.calls == 2
    assert len(jobs) == 2
    assert {job.status for job in jobs} == {ProviderJobStatus.FAILED, ProviderJobStatus.SUCCEEDED}
    assert state["world"]["status"] == "CURRENT"
    assert state["world"]["content"]["characters"][0]["source_evidence"] == ["甲：我会回来。"]


def test_world_retry_never_accepts_invented_source_evidence(client, session_factory, monkeypatch) -> None:
    task, jobs, state = _run_world(client, session_factory, monkeypatch, always_invent=True)
    assert task["status"] == "failed"
    assert FlakyGroundingProvider.calls == 2
    assert len(jobs) == 2
    assert all(job.status == ProviderJobStatus.FAILED for job in jobs)
    assert "人物「甲」" in task["last_error"]
    assert state["analysis"]["status"] == "CURRENT"
    assert state["world"]["status"] == "NOT_BUILT"
