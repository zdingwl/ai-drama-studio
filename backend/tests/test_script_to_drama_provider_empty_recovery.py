"""Regression tests for reasoning-only / truncated Ark responses in script extraction."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, SecretStr

from app.core.errors import AppError
from app.script_localization import providers


class _Result(BaseModel):
    name: str


def _provider() -> providers.ScriptLocalizationProvider:
    provider = providers.ScriptLocalizationProvider.__new__(providers.ScriptLocalizationProvider)
    provider.provider_name = "volcengine-ark"
    provider.model_name = "test-text-model"
    provider.base_url = "https://example.invalid/api/v3"
    provider.api_key = SecretStr("test-key")
    provider.settings = SimpleNamespace(p7_doubao_request_timeout_seconds=30)
    return provider


def _response(*, status: str = "completed", text: str = "", response_id: str = "response"):
    return SimpleNamespace(status=status, output_text=text, output=[], id=response_id)


@pytest.mark.parametrize("first", [
    _response(response_id="reasoning-only"),
    _response(status="incomplete", response_id="truncated"),
])
def test_ark_empty_or_incomplete_response_recovers_once(monkeypatch, first) -> None:
    calls = []
    responses = [first, _response(text='{"name":"林诗语"}', response_id="final-response")]

    def create(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(providers, "Ark", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(providers, "get_professional_skill_detail", lambda _name: SimpleNamespace(
        name="资产提取", id="script-analysis", version="1", manual="只返回 JSON",
    ))
    parsed, remote_id = _provider().generate(
        skill_id="script-analysis", prompt="剧本", output_model=_Result, max_output_tokens=8192,
    )

    assert parsed.name == "林诗语"
    assert remote_id == "final-response"
    assert len(calls) == 2
    assert calls[0]["thinking"] == {"type": "enabled"}
    assert calls[0]["max_output_tokens"] == 8192
    assert calls[1]["thinking"] == {"type": "disabled"}
    assert calls[1]["max_output_tokens"] == 16384
    assert calls[0]["input"] == calls[1]["input"]


def test_ark_double_empty_does_not_publish_or_retry_unboundedly(monkeypatch) -> None:
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return _response(response_id=f"attempt-{len(calls)}")

    monkeypatch.setattr(providers, "Ark", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(providers, "get_professional_skill_detail", lambda _name: SimpleNamespace(
        name="资产提取", id="script-analysis", version="1", manual="只返回 JSON",
    ))
    with pytest.raises(AppError) as error:
        _provider().generate(skill_id="script-analysis", prompt="剧本", output_model=_Result,
                             max_output_tokens=8192)
    assert error.value.code == "SCRIPT_LOCALIZATION_PROVIDER_EMPTY"
    assert len(calls) == 2


def test_ark_valid_first_response_does_not_retry(monkeypatch) -> None:
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return _response(text='{"name":"赵教授"}', response_id="first-response")

    monkeypatch.setattr(providers, "Ark", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(providers, "get_professional_skill_detail", lambda _name: SimpleNamespace(
        name="资产提取", id="script-analysis", version="1", manual="只返回 JSON",
    ))
    parsed, remote_id = _provider().generate(
        skill_id="script-analysis", prompt="剧本", output_model=_Result, max_output_tokens=8192,
    )
    assert parsed.name == "赵教授"
    assert remote_id == "first-response"
    assert len(calls) == 1
