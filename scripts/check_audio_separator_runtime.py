"""Real R10.1 audio-separator runtime acceptance.

This script intentionally performs one actual separation request. `/health` alone proves only that
the worker process/import stack exists; it does not prove the configured model can load and infer.
The script uses only the Python standard library so it can run from the project environment.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import urllib.error
import urllib.request
import wave


def _request_json(url: str, *, payload: dict | None = None, timeout: float = 30.0) -> dict:
    data = None
    headers: dict[str, str] = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach {url}: {exc}") from exc
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid JSON object from {url}")
    return value


def _write_probe_wav(path: Path, *, seconds: float = 2.0, rate: int = 44_100) -> None:
    """Write a deterministic stereo tone mixture with enough spectral content for inference."""
    frame_count = int(seconds * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(frame_count):
            t = index / rate
            sample = (
                0.30 * math.sin(2.0 * math.pi * 220.0 * t)
                + 0.20 * math.sin(2.0 * math.pi * 440.0 * t)
                + 0.12 * math.sin(2.0 * math.pi * 880.0 * t)
            )
            value = max(-32767, min(32767, int(sample * 32767)))
            packed = struct.pack("<h", value)
            frames.extend(packed)
            frames.extend(packed)
        handle.writeframes(frames)


def _ffprobe_audio(path: Path) -> None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    info = json.loads(result.stdout or "{}")
    streams = info.get("streams") or []
    if not streams:
        raise RuntimeError("separator output has no decodable audio stream")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.getenv("AI_DRAMA_BACKGROUND_AUDIO_BASE_URL", "http://127.0.0.1:7863"),
    )
    parser.add_argument(
        "--model",
        default=os.getenv("AI_DRAMA_BACKGROUND_AUDIO_MODEL", "UVR-MDX-NET-Inst_HQ_5.onnx"),
    )
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print("[R10.1 Audio Separator] health check")
    health = _request_json(f"{base_url}/health", timeout=10.0)
    print(json.dumps(health, ensure_ascii=False, indent=2))
    if not health.get("ready"):
        raise RuntimeError(f"audio-separator worker is not import-ready: {health.get('error') or health}")

    with tempfile.TemporaryDirectory(prefix="ai-drama-audio-separator-") as tmp:
        root = Path(tmp)
        source = root / "probe.wav"
        output = root / "instrumental.wav"
        _write_probe_wav(source)
        print(f"[R10.1 Audio Separator] real separation · model={args.model}")
        result = _request_json(
            f"{base_url}/separate-background",
            payload={
                "input_path": str(source.resolve()),
                "output_path": str(output.resolve()),
                "model_filename": args.model,
            },
            timeout=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise RuntimeError("audio-separator worker returned ok=false")
        if not output.is_file() or output.stat().st_size <= 44:
            raise RuntimeError("audio-separator did not materialize a usable output file")
        _ffprobe_audio(output)

    print("[R10.1 Audio Separator] READY - model loaded and one real separation completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
