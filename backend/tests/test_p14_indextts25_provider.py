import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.p14.provider import IndexTTS25Provider


def _settings() -> Settings:
    catalog = [
        {
            "voice_key": "test-reference",
            "display_name": "Test Reference",
            "reference_audio_url": "data:audio/wav;base64,UklGRg==",
            "locale": "en-US",
            "tags": ["test"],
        }
    ]
    return Settings(
        p14_indextts_base_url="http://127.0.0.1:8092/v1",
        p14_indextts_model="IndexTeam/IndexTTS-2.5",
        p14_indextts_voice_catalog_json=json.dumps(catalog),
        p14_indextts_default_speed=1.0,
        p14_indextts_default_emo_alpha=0.6,
    )


def test_indextts_provider_uses_reference_audio_native_emotion_and_language(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        status_code = 200
        content = b"RIFF-real-wave"
        headers = {"content-type": "audio/wav", "x-request-id": "req-1"}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = IndexTTS25Provider(_settings(), target_language="en-US")
    result = provider.synthesize(text="I told you not to touch her.", voice_id="test-reference")

    assert provider.provider_name == "indextts-2.5-vllm-omni"
    assert provider.model_name == "IndexTeam/IndexTTS-2.5"
    assert captured["url"] == "http://127.0.0.1:8092/v1/audio/speech"
    payload = captured["json"]
    assert payload["model"] == "IndexTeam/IndexTTS-2.5"
    assert payload["response_format"] == "wav"
    assert payload["ref_audio"].startswith("data:audio/wav;base64,")
    assert payload["speed"] == 1.0
    assert payload["extra_params"] == {
        "lang": "en",
        "text_normalization": True,
        "use_emo_text": True,
        "emo_alpha": 0.6,
    }
    assert result.audio_bytes == b"RIFF-real-wave"
    assert result.remote_job_id == "req-1"


def test_indextts_provider_rejects_unsupported_target_language() -> None:
    with pytest.raises(AppError) as exc_info:
        IndexTTS25Provider(_settings(), target_language="ko-KR")
    assert exc_info.value.code == "P14_INDEXTTS_LANGUAGE_UNSUPPORTED"
