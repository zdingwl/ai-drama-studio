"""Isolated local Qwen3-TTS worker for AI Drama Studio.

Run this script in a dedicated Python environment containing qwen-tts + FastAPI + Uvicorn.
It intentionally binds to localhost by default and writes only to explicit local output paths.

Required environment:
  AI_DRAMA_QWEN3_TTS_VOICE_DESIGN_MODEL_PATH
  AI_DRAMA_QWEN3_TTS_BASE_MODEL_PATH

Optional:
  AI_DRAMA_QWEN3_TTS_DEVICE=cuda:0
  AI_DRAMA_QWEN3_TTS_DTYPE=bfloat16
  AI_DRAMA_QWEN3_TTS_ATTN=flash_attention_2
  AI_DRAMA_QWEN3_TTS_HOST=127.0.0.1
  AI_DRAMA_QWEN3_TTS_PORT=7861
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


VOICE_DESIGN_PATH = os.getenv("AI_DRAMA_QWEN3_TTS_VOICE_DESIGN_MODEL_PATH", "").strip()
BASE_PATH = os.getenv("AI_DRAMA_QWEN3_TTS_BASE_MODEL_PATH", "").strip()
DEVICE = os.getenv("AI_DRAMA_QWEN3_TTS_DEVICE", "cuda:0").strip() or "cuda:0"
DTYPE_NAME = os.getenv("AI_DRAMA_QWEN3_TTS_DTYPE", "bfloat16").strip().lower()
ATTN = os.getenv("AI_DRAMA_QWEN3_TTS_ATTN", "flash_attention_2").strip() or "flash_attention_2"

app = FastAPI(title="AI Drama Studio Qwen3-TTS Worker", version="1.0")
_model_lock = Lock()
_design_model: Any = None
_clone_model: Any = None
_clone_prompt_cache: dict[tuple[str, int, str], Any] = {}


class VoiceDesignRequest(BaseModel):
    language: str = Field(min_length=1, max_length=64)
    voice_design_prompt: str = Field(min_length=1, max_length=8000)
    reference_text: str = Field(min_length=1, max_length=4000)
    output_path: str = Field(min_length=1)


class SynthesizeRequest(BaseModel):
    language: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=12000)
    reference_audio_path: str = Field(min_length=1)
    reference_text: str = Field(min_length=1, max_length=4000)
    output_path: str = Field(min_length=1)


def _model_ready_path(raw: str) -> bool:
    return bool(raw and Path(raw).expanduser().is_dir())


def _imports() -> tuple[Any, Any, Any]:
    try:
        import torch
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel
    except ImportError as exc:
        raise RuntimeError("Install qwen-tts, torch and soundfile in the worker environment") from exc
    return torch, sf, Qwen3TTSModel


def _dtype(torch: Any) -> Any:
    if DTYPE_NAME in {"float16", "fp16"}:
        return torch.float16
    if DTYPE_NAME in {"float32", "fp32"}:
        return torch.float32
    return torch.bfloat16


def _load_design_model() -> Any:
    global _design_model
    if _design_model is not None:
        return _design_model
    if not _model_ready_path(VOICE_DESIGN_PATH):
        raise RuntimeError("VoiceDesign model path is not configured or does not exist")
    torch, _sf, model_cls = _imports()
    kwargs: dict[str, Any] = {"device_map": DEVICE, "dtype": _dtype(torch)}
    if ATTN:
        kwargs["attn_implementation"] = ATTN
    with _model_lock:
        if _design_model is None:
            _design_model = model_cls.from_pretrained(str(Path(VOICE_DESIGN_PATH).expanduser()), **kwargs)
    return _design_model


def _load_clone_model() -> Any:
    global _clone_model
    if _clone_model is not None:
        return _clone_model
    if not _model_ready_path(BASE_PATH):
        raise RuntimeError("Base voice-clone model path is not configured or does not exist")
    torch, _sf, model_cls = _imports()
    kwargs: dict[str, Any] = {"device_map": DEVICE, "dtype": _dtype(torch)}
    if ATTN:
        kwargs["attn_implementation"] = ATTN
    with _model_lock:
        if _clone_model is None:
            _clone_model = model_cls.from_pretrained(str(Path(BASE_PATH).expanduser()), **kwargs)
    return _clone_model


def _materialize(path_string: str) -> Path:
    path = Path(path_string).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@app.get("/health")
def health() -> dict[str, Any]:
    import_ready = True
    import_error = None
    try:
        _imports()
    except Exception as exc:
        import_ready = False
        import_error = str(exc)
    design_ready = _model_ready_path(VOICE_DESIGN_PATH)
    clone_ready = _model_ready_path(BASE_PATH)
    return {
        "ready": import_ready and design_ready and clone_ready,
        "import_ready": import_ready,
        "voice_design_model_ready": design_ready,
        "base_model_ready": clone_ready,
        "device": DEVICE,
        "dtype": DTYPE_NAME,
        "attn_implementation": ATTN,
        "error": import_error,
    }


@app.post("/voice-design")
def voice_design(payload: VoiceDesignRequest) -> dict[str, Any]:
    try:
        model = _load_design_model()
        _torch, sf, _model_cls = _imports()
        output = _materialize(payload.output_path)
        with _model_lock:
            wavs, sample_rate = model.generate_voice_design(
                text=payload.reference_text,
                language=payload.language,
                instruct=payload.voice_design_prompt,
            )
        sf.write(str(output), wavs[0], sample_rate, format="WAV", subtype="PCM_16")
        return {"ok": True, "output_path": str(output), "sample_rate": int(sample_rate)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/synthesize")
def synthesize(payload: SynthesizeRequest) -> dict[str, Any]:
    try:
        model = _load_clone_model()
        _torch, sf, _model_cls = _imports()
        reference = Path(payload.reference_audio_path).expanduser().resolve()
        if not reference.is_file():
            raise RuntimeError("reference audio does not exist")
        output = _materialize(payload.output_path)
        cache_key = (str(reference), reference.stat().st_mtime_ns, payload.reference_text)
        with _model_lock:
            prompt = _clone_prompt_cache.get(cache_key)
            if prompt is None:
                prompt = model.create_voice_clone_prompt(
                    ref_audio=str(reference),
                    ref_text=payload.reference_text,
                    x_vector_only_mode=False,
                )
                _clone_prompt_cache.clear() if len(_clone_prompt_cache) > 64 else None
                _clone_prompt_cache[cache_key] = prompt
            wavs, sample_rate = model.generate_voice_clone(
                text=payload.text,
                language=payload.language,
                voice_clone_prompt=prompt,
            )
        sf.write(str(output), wavs[0], sample_rate, format="WAV", subtype="PCM_16")
        return {"ok": True, "output_path": str(output), "sample_rate": int(sample_rate)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("AI_DRAMA_QWEN3_TTS_HOST", "127.0.0.1")
    port = int(os.getenv("AI_DRAMA_QWEN3_TTS_PORT", "7861"))
    uvicorn.run(app, host=host, port=port)
