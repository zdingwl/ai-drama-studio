from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.service import expected_namespace
from app.p14 import common, timing_service
from app.p14.schemas import (
    ReplicaTargetAudioContent,
    TargetAudioClip,
    TargetVoiceBinding,
    TimingFitStatus,
    VoiceBindingScope,
)
from app.p14.service import _compose_timing, _text_sha
from app.projects.enums import ProjectType
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.skills.registry import get_root_skill
from app.target_script.schemas import ReplicaTargetScriptContent, TargetScriptDialogueLine, TargetScriptEpisode


def _script() -> ReplicaTargetScriptContent:
    return ReplicaTargetScriptContent(
        target_language="en-US",
        target_region="US",
        source_snapshot_artifact_id="snapshot",
        adaptation_plan_artifact_id="plan",
        target_bible_artifact_id="bible",
        episodes=[TargetScriptEpisode(
            episode_id="ep-1",
            episode_order=1,
            dialogue=[TargetScriptDialogueLine(
                utterance_id="utt-1",
                utterance_number=1,
                source_start_us=1_000_000,
                source_end_us=2_000_000,
                source_text="你好",
                source_language="zh-CN",
                target_character_id="tchr-1",
                translation_text="Hello",
                localization_text="Hey there",
                final_target_dialogue="Hey there",
            )],
        )],
    )


def _audio(duration_us: int) -> ReplicaTargetAudioContent:
    return ReplicaTargetAudioContent(
        target_language="en-US",
        target_region="US",
        target_script_artifact_id="script",
        target_bible_artifact_id="bible",
        clips=[TargetAudioClip(
            clip_id="clip-1",
            episode_id="ep-1",
            episode_order=1,
            utterance_id="utt-1",
            utterance_number=1,
            target_character_id="tchr-1",
            final_target_dialogue="Hey there",
            final_target_dialogue_sha256=_text_sha("Hey there"),
            voice_id="voice-a",
            provider="test-provider",
            model="test-model",
            provider_job_id="job-1",
            media_url="/media/clip-1",
            media_sha256="a" * 64,
            mime_type="audio/wav",
            actual_speech_duration_us=duration_us,
            sample_rate_hz=24000,
            channel_count=1,
        )],
    )


def test_p14_root_and_professional_skill_contracts_are_split_and_capabilities_stay_planned() -> None:
    root = get_root_skill(ProjectType.REPLICA)
    assert root.version == "1.4.0"
    audio = next(step for step in root.steps if step.id == "target_audio")
    timing = next(step for step in root.steps if step.id == "dialogue_timing")
    assert audio.phase == timing.phase == "配音与时序"
    assert audio.requires == (ArtifactType.TARGET_SCRIPT, ArtifactType.TARGET_BIBLE)
    assert audio.produces == (ArtifactType.TARGET_AUDIO,)
    assert timing.requires == (ArtifactType.TARGET_SCRIPT, ArtifactType.TARGET_AUDIO)
    assert timing.produces == (ArtifactType.TIMING_PLAN,)
    assert get_professional_skill("replica-target-audio").required_capabilities == (Capability.TTS,)
    assert get_professional_skill("replica-dialogue-timing").required_capabilities == (Capability.TIMING,)
    assert CAPABILITY_BY_ID[Capability.TTS].availability == CapabilityAvailability.PLANNED
    assert CAPABILITY_BY_ID[Capability.TIMING].availability == CapabilityAvailability.PLANNED
    assert expected_namespace(ArtifactType.TARGET_AUDIO) == ArtifactNamespace.PRODUCTION
    assert expected_namespace(ArtifactType.TIMING_PLAN) == ArtifactNamespace.PRODUCTION


def test_unknown_character_requires_utterance_binding_shape() -> None:
    with pytest.raises(ValidationError):
        TargetVoiceBinding(scope=VoiceBindingScope.CHARACTER, voice_id="voice-a")
    binding = TargetVoiceBinding(scope=VoiceBindingScope.UTTERANCE, utterance_id="utt-1", voice_id="voice-a")
    assert binding.target_character_id is None


def test_timing_is_deterministic_and_overflow_is_explicit() -> None:
    script_artifact = SimpleNamespace(id="script")
    audio_artifact = SimpleNamespace(id="audio")
    fit = _compose_timing(script_artifact, _script(), audio_artifact, _audio(800_000))
    assert fit.has_overflow is False
    assert fit.items[0].fit_status == TimingFitStatus.FIT
    assert fit.items[0].residual_hold_us == 200_000
    assert fit.items[0].overflow_us == 0

    overflow = _compose_timing(script_artifact, _script(), audio_artifact, _audio(1_250_000))
    assert overflow.has_overflow is True
    assert overflow.total_overflow_us == 250_000
    assert overflow.items[0].fit_status == TimingFitStatus.OVERFLOW
    assert overflow.items[0].overflow_us == 250_000


def test_timing_worker_uses_shared_checkpoint_helper() -> None:
    assert timing_service._checkpoint is common._checkpoint
