import json
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.target_script.providers import (
    P12_MAX_OUTPUT_TOKENS,
    TargetScriptProviderInput,
    _assert_ark_response_completed,
    _parse,
    _prompt,
    _provider_json_schema,
    _structured_text_config,
)


def _payload() -> TargetScriptProviderInput:
    return TargetScriptProviderInput(
        target_language="en-US",
        target_region="US",
        adaptation_plan={"strategy": "preserve story"},
        target_bible={"characters": []},
        canonical_dialogue_manifest=[
            {
                "episode_id": "ep-1",
                "episode_order": 1,
                "utterance_id": "4dd79a85-c3ce-4dcf-9dd5-b901fc6a9982",
                "utterance_number": 1,
                "source_start_us": 1_000_000,
                "source_end_us": 2_000_000,
                "source_text": "你别替我做决定。",
                "source_language": "zh-CN",
            },
            {
                "episode_id": "ep-1",
                "episode_order": 1,
                "utterance_id": "352ef2bf-76fb-4a71-95b8-bf3f6bbfd009",
                "utterance_number": 2,
                "source_start_us": 2_100_000,
                "source_end_us": 3_000_000,
                "source_text": "我只是想帮你。",
                "source_language": "zh-CN",
            },
        ],
    )


def test_p12_ark_requests_strict_schema_bound_to_exact_dialogue_coverage() -> None:
    payload = _payload()
    config = _structured_text_config(payload)
    schema = config["format"]["schema"]

    assert config["format"]["type"] == "json_schema"
    assert config["format"]["name"] == "p12_target_script_localization"
    assert config["format"]["strict"] is True
    assert schema["type"] == "object"
    assert schema["properties"]["dialogue"]["minItems"] == 2
    assert schema["properties"]["dialogue"]["maxItems"] == 2
    utterance_id = schema["$defs"]["ProviderLocalizedDialogue"]["properties"]["utterance_id"]
    assert utterance_id["enum"] == [
        "4dd79a85-c3ce-4dcf-9dd5-b901fc6a9982",
        "352ef2bf-76fb-4a71-95b8-bf3f6bbfd009",
    ]
    final_dialogue = schema["$defs"]["ProviderLocalizedDialogue"]["properties"]["final_target_dialogue"]
    assert final_dialogue["minLength"] == 1
    assert final_dialogue["maxLength"] == 4000
    assert P12_MAX_OUTPUT_TOKENS == 65536


def test_p12_prompt_contains_explicit_ordered_coverage_manifest() -> None:
    prompt = _prompt(_payload())
    assert "强制覆盖清单" in prompt
    assert prompt.index("4dd79a85-c3ce-4dcf-9dd5-b901fc6a9982") < prompt.index(
        "352ef2bf-76fb-4a71-95b8-bf3f6bbfd009"
    )
    schema = _provider_json_schema(_payload())
    assert json.dumps(schema, ensure_ascii=False, separators=(",", ":")) in prompt


def test_p12_invalid_provider_output_reports_safe_contract_location() -> None:
    raw = json.dumps(
        {
            "dialogue": [
                {
                    "utterance_id": "4dd79a85-c3ce-4dcf-9dd5-b901fc6a9982",
                    "translation_text": "Don't decide for me.",
                    "localization_text": "Don't make that call for me.",
                }
            ]
        }
    )
    with pytest.raises(AppError) as captured:
        _parse(raw)

    assert captured.value.code == "P12_PROVIDER_RESPONSE_INVALID"
    assert "final_target_dialogue" in captured.value.message
    assert "Don't decide for me" not in captured.value.message


def test_p12_incomplete_ark_response_handles_dict_details() -> None:
    response = SimpleNamespace(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    with pytest.raises(AppError) as captured:
        _assert_ark_response_completed(response)

    assert captured.value.code == "P12_PROVIDER_RESPONSE_INCOMPLETE"
    assert "max_output_tokens" in captured.value.message
    assert captured.value.details["incomplete_reason"] == "max_output_tokens"
