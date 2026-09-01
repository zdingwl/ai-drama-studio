"""Client for the isolated local Qwen3-TTS worker.

The main AI Drama Studio environment does not import qwen-tts directly.  Official Qwen3-TTS
recommends an isolated environment; the worker can therefore own its speech dependencies
without destabilizing the video-analysis/H3 environment.
"""
from __future__ import annotations

import os
from pathlib import Path
import wave
from typing import Any

import httpx


RUNTIME_PROFILE = "QWEN3_TTS_VOICE_DESIGN_CLONE_V1"
DEFAULT_BASE_URL = "http://127.0.0.1:7861"

_LANGUAGE_MAP = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

_REFERENCE_TEXT = {
    "Chinese": "今天的事情虽然有些意外，但我会冷静下来，一步一步把问题处理好。",
    "English": "Today took an unexpected turn, but I can handle it calmly, one step at a time.",
    "Japanese": "今日は思いがけないことがあったけれど、落ち着いて一つずつ向き合っていく。",
    "Korean": "오늘은 예상하지 못한 일이 있었지만, 침착하게 하나씩 해결해 나갈 거야.",
    "German": "Heute kam vieles unerwartet, aber ich werde ruhig bleiben und alles Schritt für Schritt lösen.",
    "French": "La journée a pris une tournure inattendue, mais je vais rester calme et avancer étape par étape.",
    "Russian": "Сегодня всё пошло неожиданно, но я сохраню спокойствие и разберусь со всем шаг за шагом.",
    "Portuguese": "Hoje as coisas tomaram um rumo inesperado, mas vou manter a calma e resolver tudo passo a passo.",
    "Spanish": "Hoy todo tomó un giro inesperado, pero mantendré la calma y resolveré las cosas paso a paso.",
    "Italian": "Oggi le cose hanno preso una piega inaspettata, ma resterò calmo e affronterò tutto passo dopo passo.",
}


class Qwen3TTSRuntimeError(RuntimeError):
    pass


def tts_language(target_language: str) -> str | None:
    normalized = target_language.strip().lower().replace("_", "-")
    prefix = normalized.split("-", 1)[0]
    return _LANGUAGE_MAP.get(prefix)


def reference_text_for_language(target_language: str) -> str | None:
    language = tts_language(target_language)
    return _REFERENCE_TEXT.get(language or "")


def runtime_base_url() -> str:
    return os.getenv("AI_DRAMA_TTS_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL


def runtime_status() -> dict[str, Any]:
    language_support = sorted(_LANGUAGE_MAP)
    base_url = runtime_base_url()
    try:
        with httpx.Client(timeout=2.5) as client:
            response = client.get(f"{base_url}/health")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid health response")
        return {
            "ready": bool(payload.get("ready")),
            "reachable": True,
            "base_url": base_url,
            "runtime_profile": RUNTIME_PROFILE,
            "supported_language_prefixes": language_support,
            "worker": payload,
        }
    except Exception as exc:
        return {
            "ready": False,
            "reachable": False,
            "base_url": base_url,
            "runtime_profile": RUNTIME_PROFILE,
            "supported_language_prefixes": language_support,
            "error": str(exc),
        }


def design_voice_reference(*, language: str, voice_design_prompt: str, reference_text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "language": language,
        "voice_design_prompt": voice_design_prompt,
        "reference_text": reference_text,
        "output_path": str(output_path.resolve()),
    }
    try:
        with httpx.Client(timeout=600.0) as client:
            response = client.post(f"{runtime_base_url()}/voice-design", json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        raise Qwen3TTSRuntimeError(f"Qwen3-TTS VoiceDesign failed: {exc}") from exc
    if not isinstance(body, dict) or not body.get("ok") or not output_path.is_file():
        raise Qwen3TTSRuntimeError("Qwen3-TTS worker did not materialize voice reference audio")


def synthesize_clone(*, language: str, text: str, reference_audio_path: Path, reference_text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "language": language,
        "text": text,
        "reference_audio_path": str(reference_audio_path.resolve()),
        "reference_text": reference_text,
        "output_path": str(output_path.resolve()),
    }
    try:
        with httpx.Client(timeout=600.0) as client:
            response = client.post(f"{runtime_base_url()}/synthesize", json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        raise Qwen3TTSRuntimeError(f"Qwen3-TTS VoiceClone failed: {exc}") from exc
    if not isinstance(body, dict) or not body.get("ok") or not output_path.is_file():
        raise Qwen3TTSRuntimeError("Qwen3-TTS worker did not materialize dialogue audio")


def wav_duration_us(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
    except (wave.Error, OSError) as exc:
        raise Qwen3TTSRuntimeError(f"cannot read generated WAV: {exc}") from exc
    if rate <= 0 or frames <= 0:
        raise Qwen3TTSRuntimeError("generated WAV has invalid duration")
    return max(1, int(round(frames / rate * 1_000_000)))


__all__ = [
    "Qwen3TTSRuntimeError",
    "RUNTIME_PROFILE",
    "design_voice_reference",
    "reference_text_for_language",
    "runtime_status",
    "synthesize_clone",
    "tts_language",
    "wav_duration_us",
]
