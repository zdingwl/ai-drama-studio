import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.source_resolution.providers import (
    ProjectResolutionInput,
    ResolutionEpisodeVideo,
    _parse_semantic,
    _prompt,
    _provider_json_schema,
    _reference_token_maps,
    _restore_reference_tokens,
)
from app.source_resolution.providers_v9 import P9_PROP_WIRE_CONTRACT
from app.source_resolution.schemas import PropResolutionSemantic


def _payload() -> ProjectResolutionInput:
    return ProjectResolutionInput(
        episodes=(
            ResolutionEpisodeVideo(
                source_path=Path("episode.mp4"),
                source_filename="episode.mp4",
                mime_type="video/mp4",
                episode_id="episode-1",
                episode_order=1,
                duration_us=2_000_000,
                source_asset_sha256="a" * 64,
            ),
        ),
        source_language="zh-CN",
        source_bible={"episodes": []},
        source_shot_facts={
            "episodes": [
                {
                    "episode_id": "episode-1",
                    "shots": [
                        {
                            "shot_anchor_id": "shot-1",
                            "bindings": {
                                "characters": [],
                                "scenes": [],
                                "props": [
                                    {"id": "prop-blue-rose", "label": "蓝玫瑰花束"},
                                    {"id": "prop-phone", "label": "手机"},
                                ],
                            },
                            "visual_text_evidence_ids": [],
                        },
                        {
                            "shot_anchor_id": "shot-2",
                            "bindings": {
                                "characters": [],
                                "scenes": [],
                                "props": [{"id": "prop-phone", "label": "手机"}],
                            },
                            "visual_text_evidence_ids": [],
                        },
                    ],
                }
            ]
        },
        canonical_dialogue=[],
    )


def _expected_keys(payload: ProjectResolutionInput) -> list[str]:
    source_to_token, _token_to_source = _reference_token_maps(payload)
    return [
        f'{source_to_token["shot-1"]}__{source_to_token["prop-blue-rose"]}',
        f'{source_to_token["shot-1"]}__{source_to_token["prop-phone"]}',
        f'{source_to_token["shot-2"]}__{source_to_token["prop-phone"]}',
    ]


def test_prop_wire_schema_owns_every_p8_pair_as_required_object_key() -> None:
    payload = _payload()
    expected_keys = _expected_keys(payload)

    schema = _provider_json_schema("prop-resolution", payload)
    observations = schema["properties"]["observations"]

    assert observations["type"] == "object"
    assert observations["required"] == expected_keys
    assert list(observations["properties"]) == expected_keys
    assert observations["minProperties"] == len(expected_keys)
    assert observations["maxProperties"] == len(expected_keys)
    assert observations["additionalProperties"] is False

    for decision in observations["properties"].values():
        assert "shot_anchor_id" not in decision["properties"]
        assert "source_candidate_id" not in decision["properties"]
        assert "resolution_status" in decision["properties"]
        assert "group_key" in decision["properties"]
        assert "reason" in decision["properties"]
        assert decision["additionalProperties"] is False


def test_prop_wire_parser_reconstructs_authoritative_p8_pairs_before_restore() -> None:
    payload = _payload()
    expected_keys = _expected_keys(payload)
    raw = json.dumps(
        {
            "groups": [],
            "observations": {
                key: {
                    "group_key": None,
                    "resolution_status": "UNRESOLVED",
                    "reason": "证据不足，保留未决",
                }
                for key in expected_keys
            },
        },
        ensure_ascii=False,
    )

    semantic = _parse_semantic("prop-resolution", raw)
    assert isinstance(semantic, PropResolutionSemantic)
    assert len(semantic.observations) == 3

    restored = _restore_reference_tokens("prop-resolution", semantic, payload)
    assert isinstance(restored, PropResolutionSemantic)
    assert {
        (item.shot_anchor_id, item.source_candidate_id)
        for item in restored.observations
    } == {
        ("shot-1", "prop-blue-rose"),
        ("shot-1", "prop-phone"),
        ("shot-2", "prop-phone"),
    }


def test_prop_wire_rejects_malformed_or_provider_owned_source_pair_key() -> None:
    raw = json.dumps(
        {
            "groups": [],
            "observations": {
                "shot-1__prop-phone": {
                    "group_key": None,
                    "resolution_status": "UNRESOLVED",
                    "reason": "invalid wire key",
                }
            },
        }
    )

    with pytest.raises(AppError) as captured:
        _parse_semantic("prop-resolution", raw)

    assert captured.value.code == "P9_PROP_PROVIDER_RESPONSE_INVALID"
    assert "Source-owned" in captured.value.message
    assert "shot-1__prop-phone" not in captured.value.message


def test_prop_prompt_declares_source_owned_wire_and_fixed_keys() -> None:
    payload = _payload()
    expected_keys = _expected_keys(payload)

    prompt = _prompt("prop-resolution", payload)

    assert P9_PROP_WIRE_CONTRACT in prompt
    assert "服务端固定键 object" in prompt
    assert "value 只做归一判断" in prompt
    for key in expected_keys:
        assert key in prompt
