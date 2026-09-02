"""Dedicated local audio-separator worker for R10.1 background audio.

Run this worker in its own Python environment. The model is loaded lazily and cached in-process.
Only the Instrumental stem is returned to Studio; Studio still performs a second source-dialogue
suppression pass before the stem can enter any final mix.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


APP_TITLE = "AI Drama Studio Audio Separator Worker"
DEFAULT_PORT = 7863
DEFAULT_MODEL = "UVR-MDX-NET-Inst_HQ_5.onnx"

app = FastAPI(title=APP_TITLE, version="1.0.0")
_lock = threading.Lock()
_separator_cache: dict[str, Any] = {}
_import_error: str | None = None


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _work_root() -> Path:
    root = Path(os.getenv("AI_DRAMA_AUDIO_SEPARATOR_HOME", "data_v2/audio-separator-worker")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _model_dir() -> Path:
    root = Path(os.getenv("AI_DRAMA_AUDIO_SEPARATOR_MODEL_DIR", str(_work_root() / "models"))).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _output_dir() -> Path:
    root = _work_root() / "outputs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _separator_class():
    global _import_error
    try:
        from audio_separator.separator import Separator
        _import_error = None
        return Separator
    except Exception as exc:  # pragma: no cover - exercised in real worker environment
        _import_error = str(exc)
        return None


def _separator(model_filename: str):
    cached = _separator_cache.get(model_filename)
    if cached is not None:
        return cached
    Separator = _separator_class()
    if Separator is None:
        raise RuntimeError(_import_error or "audio-separator import failed")
    instance = Separator(
        model_file_dir=str(_model_dir()),
        output_dir=str(_output_dir()),
        output_format="WAV",
        output_single_stem="Instrumental",
        sample_rate=48_000,
        normalization_threshold=0.9,
        amplification_threshold=0.0,
        use_soundfile=True,
        use_autocast=_truthy("AI_DRAMA_AUDIO_SEPARATOR_AUTOCAST", True),
    )
    instance.load_model(model_filename=model_filename)
    _separator_cache[model_filename] = instance
    return instance


class SeparateBackgroundRequest(BaseModel):
    input_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    model_filename: str = Field(default=DEFAULT_MODEL, min_length=1)


@app.get("/health")
def health() -> dict[str, Any]:
    Separator = _separator_class()
    return {
        "ready": Separator is not None,
        "runtime": "audio-separator",
        "model_default": os.getenv("AI_DRAMA_BACKGROUND_AUDIO_MODEL", DEFAULT_MODEL),
        "model_dir": str(_model_dir()),
        "loaded_models": sorted(_separator_cache),
        "error": _import_error,
    }


@app.post("/separate-background")
def separate_background(request: SeparateBackgroundRequest) -> dict[str, Any]:
    source = Path(request.input_path).expanduser().resolve()
    output = Path(request.output_path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise HTTPException(status_code=400, detail="input audio does not exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    model = request.model_filename.strip() or DEFAULT_MODEL

    try:
        with _lock:
            separator = _separator(model)
            produced = separator.separate(str(source))
            candidates: list[Path] = []
            for value in produced or []:
                candidate = Path(str(value))
                if not candidate.is_absolute():
                    candidate = _output_dir() / candidate
                if candidate.is_file() and candidate.stat().st_size > 0:
                    candidates.append(candidate.resolve())
            if not candidates:
                raise RuntimeError("audio-separator produced no output stem")
            instrumental = next(
                (
                    candidate for candidate in candidates
                    if "instrumental" in candidate.name.lower() or "no_vocals" in candidate.name.lower()
                ),
                candidates[0] if len(candidates) == 1 else None,
            )
            if instrumental is None:
                raise RuntimeError(f"could not identify Instrumental stem: {[item.name for item in candidates]}")
            temp = output.with_name(f".{output.stem}.separating{output.suffix}")
            shutil.copy2(instrumental, temp)
            temp.replace(output)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": True,
        "output_path": str(output),
        "model_filename": model,
        "stem": "Instrumental",
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "scripts.audio_separator_worker_v1:app",
        host=os.getenv("AI_DRAMA_AUDIO_SEPARATOR_HOST", "127.0.0.1"),
        port=int(os.getenv("AI_DRAMA_AUDIO_SEPARATOR_PORT", str(DEFAULT_PORT))),
        reload=False,
    )
