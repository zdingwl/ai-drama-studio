from __future__ import annotations

from pathlib import Path
import wave

from engine.app.qwen3_tts_runtime_v1 import reference_text_for_language, tts_language, wav_duration_us


def _write_wav(path: Path, frames: int, rate: int = 16_000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)


def test_supported_project_language_codes_map_to_qwen3_tts() -> None:
    assert tts_language("zh-CN") == "Chinese"
    assert tts_language("en-US") == "English"
    assert tts_language("ja-JP") == "Japanese"
    assert tts_language("ko-KR") == "Korean"
    assert tts_language("de-DE") == "German"
    assert tts_language("fr-FR") == "French"
    assert tts_language("ru-RU") == "Russian"
    assert tts_language("pt-BR") == "Portuguese"
    assert tts_language("es-MX") == "Spanish"
    assert tts_language("it-IT") == "Italian"
    assert tts_language("ar-SA") is None


def test_reference_text_matches_supported_language() -> None:
    assert reference_text_for_language("en-US")
    assert reference_text_for_language("ja-JP")
    assert reference_text_for_language("ar-SA") is None


def test_wav_duration_uses_real_pcm_duration(tmp_path: Path) -> None:
    path = tmp_path / "line.wav"
    _write_wav(path, frames=20_000, rate=16_000)
    assert wav_duration_us(path) == 1_250_000
