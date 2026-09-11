from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.skills.models import Capability
from app.source_resolution import service_v2
from app.source_resolution.providers import (
    P9_MAX_OUTPUT_TOKENS,
    P9_PROMPT_VERSION,
    ProjectResolutionInput,
    ResolutionEpisodeVideo,
    _parse_semantic,
    _prompt,
    _provider_json_schema,
    _reference_token_maps,
    _restore_reference_tokens,
    _structured_text_config,
)
from app.source_resolution.schemas import CharacterResolutionSemantic
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
    assert P9_PROMPT_VERSION == "p9-source-resolution-v9"


def _multi_episode_payload() -> ProjectResolutionInput:
    shot_id = "1328bbf0-9ccb-4501-8af8-5a0a44e9fa8f"
    return ProjectResolutionInput(
        episodes=(
            ResolutionEpisodeVideo(
                source_path=Path("episode-1.mp4"),
                source_filename="episode-1.mp4",
                mime_type="video/mp4",
                episode_id="episode-1",
                episode_order=1,
                duration_us=1_000_000,
                source_asset_sha256="a" * 64,
            ),
            ResolutionEpisodeVideo(
                source_path=Path("episode-2.mp4"),
                source_filename="episode-2.mp4",
                mime_type="video/mp4",
                episode_id="episode-2",
                episode_order=2,
                duration_us=1_000_000,
                source_asset_sha256="b" * 64,
            ),
        ),
        source_language="zh",
        source_bible={"episodes": []},
        source_shot_facts={
            "episodes": [
                {
                    "episode_id": "episode-1",
                    "shots": [
                        {
                            "shot_anchor_id": shot_id,
                            "bindings": {
                                "characters": [{"id": "C001", "label": "人物"}],
                                "scenes": [{"id": "S001", "label": "场景"}],
                                "props": [{"id": "P001", "label": "道具"}],
                            },
                            "visual_text_evidence_ids": ["ocr-1"],
                        }
                    ],
                },
                {
                    "episode_id": "episode-2",
                    "shots": [
                        {
                            "shot_anchor_id": "shot-episode-2",
                            "bindings": {"characters": [], "scenes": [], "props": []},
                            "visual_text_evidence_ids": [],
                        }
                    ],
                },
            ]
        },
        canonical_dialogue=[{"episode_id": "episode-1", "utterance_id": "utt-1"}],
    )


def test_p9_dynamic_schema_binds_character_observations_to_exact_source_ids() -> None:
    payload = _multi_episode_payload()
    source_to_token, _token_to_source = _reference_token_maps(payload)
    schema = _provider_json_schema("character-resolution", payload)
    observation = schema["$defs"]["CharacterObservationSemantic"]["properties"]
    observations = schema["properties"]["observations"]

    assert observation["shot_anchor_id"]["enum"] == [
        source_to_token["1328bbf0-9ccb-4501-8af8-5a0a44e9fa8f"],
        source_to_token["shot-episode-2"],
    ]
    assert "1328bbf0-9ccb-4501-8af8-5a0a44e9fa8" not in observation["shot_anchor_id"]["enum"]
    assert "1328bbf0-9ccb-4501-8af8-5a0a44e9fa8f" not in observation["shot_anchor_id"]["enum"]
    assert observation["source_candidate_id"]["enum"] == [source_to_token["C001"]]
    assert observations["minItems"] == 1
    assert observations["maxItems"] == 1


def test_p9_prompt_carries_exact_coverage_manifest() -> None:
    payload = _multi_episode_payload()
    source_to_token, _token_to_source = _reference_token_maps(payload)
    prompt = _prompt("character-resolution", payload)

    assert "强制覆盖清单" in prompt
    assert "Source 引用令牌表" in prompt
    assert f'"{source_to_token["1328bbf0-9ccb-4501-8af8-5a0a44e9fa8f"]}":"1328bbf0-9ccb-4501-8af8-5a0a44e9fa8f"' in prompt
    assert f'"source_candidate_id":"{source_to_token["C001"]}"' in prompt


def test_p9_reference_tokens_restore_to_authoritative_source_ids() -> None:
    payload = _multi_episode_payload()
    source_to_token, _token_to_source = _reference_token_maps(payload)
    shot_id = "1328bbf0-9ccb-4501-8af8-5a0a44e9fa8f"
    semantic = CharacterResolutionSemantic.model_validate(
        {
            "groups": [
                {
                    "group_key": "person",
                    "display_name": "人物",
                    "confidence": 0.9,
                    "resolution_status": "RESOLVED",
                    "evidence_refs": [
                        {
                            "ref_type": "SHOT",
                            "ref_id": source_to_token[shot_id],
                            "episode_id": source_to_token["episode-1"],
                            "shot_anchor_id": source_to_token[shot_id],
                        }
                    ],
                }
            ],
            "observations": [
                {
                    "shot_anchor_id": source_to_token[shot_id],
                    "source_candidate_id": source_to_token["C001"],
                    "group_key": "person",
                    "resolution_status": "RESOLVED",
                }
            ],
        }
    )

    restored = _restore_reference_tokens("character-resolution", semantic, payload)

    assert isinstance(restored, CharacterResolutionSemantic)
    assert restored.observations[0].shot_anchor_id == shot_id
    assert restored.observations[0].source_candidate_id == "C001"
    assert restored.groups[0].evidence_refs[0].ref_id == shot_id
    assert restored.groups[0].evidence_refs[0].episode_id == "episode-1"


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
        '{"groups":[],"observations":{"R0001__R0002":'
        '{"group_key":null,"resolution_status":"UNRESOLVED","reason":"'
        + oversized_reason
        + '"}}}'
    )

    with pytest.raises(AppError) as captured:
        _parse_semantic("prop-resolution", raw)

    assert captured.value.code == "P9_PROP_PROVIDER_RESPONSE_INVALID"
    assert "observations.0.reason:string_too_long" in captured.value.message
    assert "max_length=500" in captured.value.message
    assert oversized_reason not in captured.value.message


def test_p9_custom_runner_error_message_keeps_safe_validation_hint() -> None:
    error = AppError(
        "P9_PROP_PROVIDER_RESPONSE_INVALID",
        "prop-resolution Provider 返回结果未通过 P9 数据契约校验（observations.0.reason:string_too_long[max_length=500]）",
        status_code=502,
    )

    message = service_v2._p9_task_error_message(error)

    assert message == (
        "P9 最终归一失败（P9_PROP_PROVIDER_RESPONSE_INVALID）："
        "prop-resolution Provider 返回结果未通过 P9 数据契约校验"
        "（observations.0.reason:string_too_long[max_length=500]）"
    )


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