"""LatentSync 1.6 provider adapter for R10.

The diffusion stack runs in a dedicated localhost worker. The main Studio environment only sends
absolute input/output paths over HTTP and never imports LatentSync, torch/diffusers, Whisper or
its face-alignment dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from engine.app.lip_sync_provider_v1 import LipSyncProvider, LipSyncRequestV1


RUNTIME_PROFILE = "LATENTSYNC_LOCAL_V1_6"
DEFAULT_BASE_URL = "http://127.0.0.1:7862"


class LatentSyncProviderError(RuntimeError):
    pass


def runtime_base_url() -> str:
    return os.getenv("AI_DRAMA_LIPSYNC_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL


class LatentSyncProviderV1(LipSyncProvider):
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
                "worker": worker,
                "error": worker.get("error"),
            }
        except Exception as exc:
            return {
                "runtime_profile": RUNTIME_PROFILE,
                "ready": False,
                "reachable": False,
                "base_url": base_url,
                "worker": {},
                "error": str(exc),
            }

    def render(self, request: LipSyncRequestV1) -> Path:
        video = request.video_path.expanduser().resolve()
        audio = request.audio_path.expanduser().resolve()
        output = request.output_path.expanduser().resolve()
        if not video.is_file() or video.stat().st_size <= 0:
            raise LatentSyncProviderError("LipSync input video does not exist")
        if not audio.is_file() or audio.stat().st_size <= 0:
            raise LatentSyncProviderError("LipSync input audio does not exist")
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "video_path": str(video),
            "audio_path": str(audio),
            "output_path": str(output),
            "seed": int(request.seed),
            "inference_steps": int(request.inference_steps),
            "guidance_scale": float(request.guidance_scale),
        }
        try:
            with httpx.Client(timeout=float(os.getenv("AI_DRAMA_LIPSYNC_TIMEOUT", "3600"))) as client:
                response = client.post(f"{runtime_base_url()}/lip-sync", json=payload)
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            raise LatentSyncProviderError(f"LatentSync worker request failed: {exc}") from exc
        if not isinstance(body, dict) or not body.get("ok"):
            raise LatentSyncProviderError("LatentSync worker returned an invalid response")
        if not output.is_file() or output.stat().st_size <= 0:
            raise LatentSyncProviderError("LatentSync worker did not materialize output video")
        return output


_provider = LatentSyncProviderV1()


def get_lip_sync_provider_v1(name: str = RUNTIME_PROFILE) -> LipSyncProvider:
    if name.strip().upper() != RUNTIME_PROFILE:
        raise ValueError(f"unsupported lip-sync provider: {name}")
    return _provider


__all__ = [
    "DEFAULT_BASE_URL",
    "LatentSyncProviderError",
    "LatentSyncProviderV1",
    "RUNTIME_PROFILE",
    "get_lip_sync_provider_v1",
    "runtime_base_url",
]
