from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.skills.models import Capability
from app.source_resolution.providers import (
    P9_MAX_OUTPUT_TOKENS,
    P9_PROMPT_VERSION,
    _parse_semantic,
    _provider_json_schema,
    _structured_text_config,
)
from app.workflow import provider_service
from app.workflow.models import ProviderJobStatus
from app.workflow.worker import _app_error_task_message


class _FakeProviderDb:
    def __init__(self, job: SimpleNamespace):
        self.job = job
        self.commit_count = 0

    def get(self, model, object_id):
        assert object_id == self.job.id
        return self.job

    def add(self, value) -> None:
        assert value is self.job

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, value) -> None:
        assert value is self.job


def _dispatch_failure(monkeypatch, exc: Exception):
    job = SimpleNamespace(
        id="provider-job-1",
        status=ProviderJobStatus.RUNNING,
        safe_error=None,
        finished_at=None,
        updated_at=None,
    )
    db = _FakeProviderDb(job)
    monkeypatch.setattr(
        provider_service,
        "create_provider_job_before_remote",
        lambda *args, **kwargs: job,
    )

    def remote_call(_job):
        raise exc

    with pytest.raises(AppError) as captured:
        provider_service.dispatch_provider_call(
            db,
            task_id="task-1",
            provider="provider",
            model="model",
            capability=Capability.IDENTITY_RESOLUTION,
            payload={"safe": "payload"},
            remote_call=remote_call,
        )
    return captured.value, job, db


def _string_schema(field_schema: dict) -> dict:
    if field_schema.get("type") == "string":
        return field_schema
    for branch in field_schema.get("anyOf", []):
        if branch.get("type") == "string":
            return branch
    raise AssertionError(f"string branch missing: {field_schema}")


def test_scene_provider_invalid_output_gets_stage_specific_safe_error() -> None:
    raw_provider_text = "provider accidentally returned prose with secret-like-value"

    with pytest.raises(AppError) as captured:
        _parse_semantic("scene-resolution", raw_provider_text)

    assert captured.value.code == "P9_SCENE_PROVIDER_RESPONSE_INVALID"
    assert "scene-resolution" in captured.value.message
    assert "secret-like-value" not in captured.value.message


def test_p9_ark_requests_strict_json_schema_output() -> None:
    config = _structured_text_config("character-resolution")

    assert config["format"]["type"] == "json_schema"
    assert config["format"]["name"] == "p9_character_resolution"
    assert config["format"]["strict"] is True
    assert config["format"]["schema"]["type"] == "object"
    status_enum = config["format"]["schema"]["$defs"]["ResolutionStatus"]["enum"]
    assert status_enum == ["RESOLVED", "UNKNOWN", "UNRESOLVED"]
    assert P9_MAX_OUTPUT_TOKENS == 65536
    assert P9_PROMPT_VERSION == "p9-source-resolution-v6"


def test_p9_prop_request_schema_matches_pydantic_string_guards() -> None:
    schema = _provider_json_schema("prop-resolution")
    defs = schema["$defs"]

    group_key = defs["EntityGroupSemantic"]["properties"]["group_key"]
    assert group_key["minLength"] == 1
    assert group_key["maxLength"] == 96

    evidence_note = _string_schema(defs["EvidenceRef"]["properties"]["note"])
    assert evidence_note["maxLength"] == 400

    observation_reason = _string_schema(defs["PropObservationSemantic"]["properties"]["reason"])
    assert observation_reason["maxLength"] == 500

    status_enum = defs["ResolutionStatus"]["enum"]
    assert "MANUAL_CONFIRMED" not in status_enum


def test_prop_provider_validation_hint_exposes_constraint_not_raw_text() -> None:
    oversized_reason = "x" * 501
    raw = (
        '{"groups":[],"observations":['
        '{"shot_anchor_id":"shot-1","source_candidate_id":"prop-1",'
        '"group_key":null,"resolution_status":"UNRESOLVED","reason":"'
        + oversized_reason
        + '"}]}'
    )

    with pytest.raises(AppError) as captured:
        _parse_semantic("prop-resolution", raw)

    assert captured.value.code == "P9_PROP_PROVIDER_RESPONSE_INVALID"
    assert "observations.0.reason:string_too_long" in captured.value.message
    assert "max_length=500" in captured.value.message
    assert oversized_reason not in captured.value.message


def test_dispatch_preserves_authored_provider_app_error_after_marking_job_failed(monkeypatch) -> None:
    authored = AppError(
        "P9_SCENE_PROVIDER_RESPONSE_INVALID",
        "scene-resolution Provider 返回结果未通过 P9 数据契约校验",
        status_code=502,
    )

    captured, job, db = _dispatch_failure(monkeypatch, authored)

    assert captured is authored
    assert job.status == ProviderJobStatus.FAILED
    assert job.safe_error == (
        "P9_SCENE_PROVIDER_RESPONSE_INVALID: "
        "scene-resolution Provider 返回结果未通过 P9 数据契约校验"
    )
    assert db.commit_count == 1


def test_dispatch_keeps_transport_failure_generic_but_exposes_safe_exception_type(monkeypatch) -> None:
    captured, job, _db = _dispatch_failure(monkeypatch, TimeoutError("raw network detail must stay hidden"))

    assert captured.code == "PROVIDER_REQUEST_FAILED"
    assert captured.message == "Provider 请求失败（TimeoutError）"
    assert "raw network detail" not in captured.message
    assert job.status == ProviderJobStatus.FAILED
    assert job.safe_error == "Provider 请求失败（TimeoutError）"


def test_worker_task_error_includes_authored_safe_code_and_message() -> None:
    error = AppError(
        "P9_SCENE_PROVIDER_RESPONSE_INVALID",
        "scene-resolution Provider 返回结果未通过 P9 数据契约校验",
        status_code=502,
    )

    message = _app_error_task_message(error)

    assert message == (
        "任务执行失败（P9_SCENE_PROVIDER_RESPONSE_INVALID）："
        "scene-resolution Provider 返回结果未通过 P9 数据契约校验"
    )
