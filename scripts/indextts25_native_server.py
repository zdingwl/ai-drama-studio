#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import torch
import uvicorn

from indextts.infer_v2_5 import IndexTTS2

MODEL_ID = "IndexTeam/IndexTTS-2.5"


class SpeechRequest(BaseModel):
    model: str
    input: str = Field(min_length=1)
    response_format: str = "wav"
    ref_audio: str
    speed: float = 1.0
    extra_params: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="AI Drama Studio IndexTTS-2.5 Native Adapter")
_engine: IndexTTS2 | None = None
_model_dir: Path | None = None
_infer_lock = threading.Lock()


def _config_path(model_dir: Path) -> Path:
    for name in ("config_v2_5.yaml", "config.yaml"):
        candidate = model_dir / name
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        f"IndexTTS-2.5 model bundle at {model_dir} is missing config_v2_5.yaml/config.yaml"
    )


def _load_engine(model_dir: Path) -> IndexTTS2:
    if not torch.cuda.is_available():
        raise RuntimeError(
            "IndexTTS-2.5 Windows native runtime requires a CUDA-capable NVIDIA GPU. "
            "PyTorch cannot see CUDA on this machine."
        )
    use_bf16 = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    print(f"[IndexTTS native] loading {MODEL_ID} from {model_dir}")
    print(f"[IndexTTS native] CUDA={torch.cuda.get_device_name(0)} bf16={use_bf16}")
    return IndexTTS2(
        cfg_path=str(_config_path(model_dir)),
        model_dir=str(model_dir),
        use_bf16=use_bf16,
        use_cuda_kernel=False,
        use_deepspeed=False,
        use_accel=False,
        use_torch_compile=False,
        use_qwen_emo=True,
    )


def _decode_reference(data_url: str, directory: Path) -> Path:
    if not data_url.startswith("data:audio/") or "," not in data_url:
        raise HTTPException(status_code=422, detail="ref_audio must be an audio data URL")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise HTTPException(status_code=422, detail="ref_audio must use base64 encoding")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="ref_audio base64 is invalid") from exc
    if not raw:
        raise HTTPException(status_code=422, detail="ref_audio is empty")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ref_audio exceeds 25MB")
    suffix = ".wav"
    if "mpeg" in header or "mp3" in header:
        suffix = ".mp3"
    elif "flac" in header:
        suffix = ".flac"
    reference = directory / f"reference{suffix}"
    reference.write_bytes(raw)
    return reference


@app.get("/health")
def health() -> dict[str, str]:
    if _engine is None:
        raise HTTPException(status_code=503, detail="IndexTTS-2.5 model is not loaded")
    return {"status": "ok", "model": MODEL_ID, "runtime": "windows-native"}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    if _engine is None:
        raise HTTPException(status_code=503, detail="IndexTTS-2.5 model is not loaded")
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "owned_by": "IndexTeam",
                "runtime": "windows-native",
            }
        ],
    }


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest) -> Response:
    engine = _engine
    if engine is None:
        raise HTTPException(status_code=503, detail="IndexTTS-2.5 model is not loaded")
    if request.model != MODEL_ID:
        raise HTTPException(status_code=422, detail=f"model must be {MODEL_ID}")
    if request.response_format.lower() != "wav":
        raise HTTPException(status_code=422, detail="Windows native IndexTTS adapter currently outputs wav only")
    if not 0.5 <= request.speed <= 2.0:
        raise HTTPException(status_code=422, detail="speed/duration factor must be between 0.5 and 2.0")

    extra = request.extra_params or {}
    lang = str(extra.get("lang") or "").strip().upper()
    if lang not in {"ZH", "EN", "JA", "ES", "AR"}:
        raise HTTPException(status_code=422, detail="lang must be one of ZH/EN/JA/ES/AR")
    emo_alpha = float(extra.get("emo_alpha", 0.6))
    if not 0.0 <= emo_alpha <= 1.0:
        raise HTTPException(status_code=422, detail="emo_alpha must be between 0 and 1")
    use_emo_text = bool(extra.get("use_emo_text", True))
    emo_text = extra.get("emo_text")
    text_normalization = bool(extra.get("text_normalization", True))

    with tempfile.TemporaryDirectory(prefix="ai-drama-indextts-") as tmp:
        tmp_dir = Path(tmp)
        reference = _decode_reference(request.ref_audio, tmp_dir)
        output = tmp_dir / "output.wav"
        try:
            with _infer_lock:
                engine.infer(
                    spk_audio_prompt=str(reference),
                    text=request.input,
                    output_path=str(output),
                    lang=lang,
                    emo_alpha=emo_alpha,
                    use_emo_text=use_emo_text,
                    emo_text=str(emo_text) if emo_text else None,
                    use_random=False,
                    duration_factor=request.speed,
                    text_normalization=text_normalization,
                    verbose=False,
                )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"IndexTTS inference failed: {type(exc).__name__}: {exc}") from exc
        if not output.is_file() or output.stat().st_size == 0:
            raise HTTPException(status_code=500, detail="IndexTTS inference produced no audio")
        audio = output.read_bytes()
    return Response(content=audio, media_type="audio/wav", headers={"X-AI-Drama-Runtime": "windows-native"})


def main() -> int:
    global _engine, _model_dir
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()

    _model_dir = Path(args.model_dir).resolve()
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    _engine = _load_engine(_model_dir)
    print(f"[IndexTTS native] READY on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
