import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.p14.delivery import synthesize_with_delivery
from app.p14.provider import IndexTTS25Provider
from app.p14.schemas import (
    TargetAudioGenerateCommand,
    TargetAudioRetakeCommand,
    TargetDialogueDeliveryControl,
    TargetVoiceBinding,
    VoiceBindingScope,
)


def _settings() -> Settings:
    return Settings(
        p14_indextts_base_url="http://127.0.0.1:8092/v1",
        p14_indextts_model="IndexTeam/IndexTTS-2.5",
        p14_indextts_voice_catalog_json=json.dumps([
            {
                "voice_key": "voice-a",
                "display_name": "Voice A",
                "reference_audio_url": "data:audio/wav;base64,UklGRg==",
                "locale": "en-US",
                "tags": ["test"],
            }
        ]),
    )


def test_delivery_control_uses_product_safe_duration_range() -> None:
    control = TargetDialogueDeliveryControl(
        utterance_id="utt-1",
        acting_direction="  restrained   anger  ",
        emo_alpha=0.8,
        duration_factor=0.9,
    )
    assert control.acting_direction == "restrained anger"
    assert control.duration_factor == 0.9

    with pytest.raises(ValidationError):
        TargetDialogueDeliveryControl(utterance_id="utt-1", duration_factor=0.5)
    with pytest.raises(ValidationError):
        TargetDialogueDeliveryControl(utterance_id="utt-1", duration_factor=1.5)


def test_generation_and_retake_reject_duplicate_delivery_controls() -> None:
    binding = TargetVoiceBinding(
        scope=VoiceBindingScope.UTTERANCE,
        utterance_id="utt-1",
        voice_id="voice-a",
    )
    controls = [
        TargetDialogueDeliveryControl(utterance_id="utt-1"),
        TargetDialogueDeliveryControl(utterance_id="utt-1", emo_alpha=0.7),
    ]
    with pytest.raises(ValidationError):
        TargetAudioGenerateCommand(bindings=[binding], delivery_controls=controls)
    with pytest.raises(ValidationError):
        TargetAudioRetakeCommand(
            expected_target_script_artifact_id="script",
            expected_target_bible_artifact_id="bible",
            expected_generation_sequence=1,
            retakes=controls,
        )


def test_retake_command_requires_at_least_one_line() -> None:
    with pytest.raises(ValidationError):
        TargetAudioRetakeCommand(
            expected_target_script_artifact_id="script",
            expected_target_bible_artifact_id="bible",
            expected_generation_sequence=1,
            retakes=[],
        )


def test_indextts_delivery_keeps_dialogue_and_acting_direction_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        status_code = 200
        content = b"RIFF-real-wave"
        headers = {"content-type": "audio/wav", "x-request-id": "req-retake"}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = IndexTTS25Provider(_settings(), target_language="en-US")
    result = synthesize_with_delivery(
        provider,
        text="I told you not to touch her.",
        voice_id="voice-a",
        acting_direction="restrained anger, low voice, do not shout",
        emo_alpha=0.75,
        duration_factor=0.9,
    )

    payload = captured["json"]
    assert payload["input"] == "I told you not to touch her."
    assert payload["speed"] == 0.9
    assert payload["extra_params"]["emo_text"] == "restrained anger, low voice, do not shout"
    assert payload["extra_params"]["emo_alpha"] == 0.75
    assert payload["extra_params"]["use_emo_text"] is True
    assert "restrained anger" not in payload["input"]
    assert result.remote_job_id == "req-retake"
