"""Local audio-separator provider adapter for R10.1.

The heavy separation stack runs in a dedicated localhost worker. The main Studio process only
passes absolute paths and a model name over HTTP. This keeps audio-separator/UVR/Torch model
requirements out of the main backend environment.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from engine.app.background_audio_provider_v1 import BackgroundAudioProvider, BackgroundSeparationRequestV1


RUNTIME_PROFILE = "AUDIO_SEPARATOR_LOCAL_V1"
DEFAULT_BASE_URL = "http://127.0.0.1:7863"
DEFAULT_MODEL_FILENAME = "UVR-MDX-NET-Inst_HQ_5.onnx"


class AudioSeparatorProviderError(RuntimeError):
    pass


def runtime_base_url() -> str:
    return os.getenv("AI_DRAMA_BACKGROUND_AUDIO_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL


def model_filename() -> str:
    return os.getenv("AI_DRAMA_BACKGROUND_AUDIO_MODEL", DEFAULT_MODEL_FILENAME).strip() or DEFAULT_MODEL_FILENAME


class AudioSeparatorBackgroundProviderV1(BackgroundAudioProvider):
    provider_name = RUNTIME_PROFILE

    def status(self) -> dict[str, Any]:
        base_url = runtime_base_url()
        try:
            with httpx.Client(timeout=2.5) as client:
                response = client.get(f"{base_url}/health")
                response.raise_for_status()
                worker = response.json()
            if not isinstance(worker, dict):
                raise ValueError("invalid health response")
            return {
                "runtime_profile": RUNTIME_PROFILE,
                "ready": bool(worker.get("ready")),
                "reachable": True,
                "base_url": base_url,
                "model_filename": model_filename(),
                "worker": worker,
                "error": worker.get("error"),
            }
        except Exception as exc:
            return {
                "runtime_profile": RUNTIME_PROFILE,
                "ready": False,
                "reachable": False,
                "base_url": base_url,
                "model_filename": model_filename(),
                "worker": {},
                "error": str(exc),
            }

    def separate_background(self, request: BackgroundSeparationRequestV1) -> Path:
        source = request.input_path.expanduser().resolve()
        output = request.output_path.expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise AudioSeparatorProviderError("background separation input does not exist")
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "input_path": str(source),
            "output_path": str(output),
            "model_filename": request.model_filename or model_filename(),
        }
        try:
            with httpx.Client(timeout=float(os.getenv("AI_DRAMA_BACKGROUND_AUDIO_TIMEOUT", "3600"))) as client:
                response = client.post(f"{runtime_base_url()}/separate-background", json=payload)
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            raise AudioSeparatorProviderError(f"audio-separator worker request failed: {exc}") from exc
        if not isinstance(body, dict) or not body.get("ok"):
            raise AudioSeparatorProviderError("audio-separator worker returned an invalid response")
        if not output.is_file() or output.stat().st_size <= 0:
            raise AudioSeparatorProviderError("audio-separator worker did not materialize background stem")
        return output


_provider = AudioSeparatorBackgroundProviderV1()


def get_background_audio_provider_v1(name: str = RUNTIME_PROFILE) -> BackgroundAudioProvider:
    if name.strip().upper() != RUNTIME_PROFILE:
        raise ValueError(f"unsupported background audio provider: {name}")
    return _provider


__all__ = [
    "AudioSeparatorBackgroundProviderV1",
    "AudioSeparatorProviderError",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL_FILENAME",
    "RUNTIME_PROFILE",
    "get_background_audio_provider_v1",
    "model_filename",
    "runtime_base_url",
]
