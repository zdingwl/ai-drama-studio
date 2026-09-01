"""Isolated LatentSync 1.6 worker for AI Drama Studio R10.

Run this script inside the official LatentSync environment, not the Studio engine environment.
It loads the official 1.6 pipeline once and serializes GPU jobs behind one process-local lock.

Required:
  AI_DRAMA_LATENTSYNC_ROOT=/path/to/LatentSync

Optional:
  AI_DRAMA_LATENTSYNC_CONFIG=configs/unet/stage2_512.yaml
  AI_DRAMA_LATENTSYNC_CHECKPOINT=checkpoints/latentsync_unet.pt
  AI_DRAMA_LATENTSYNC_HOST=127.0.0.1
  AI_DRAMA_LATENTSYNC_PORT=7862
  AI_DRAMA_LATENTSYNC_DEEPCACHE=0

The worker intentionally binds localhost by default and accepts only explicit local paths.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from threading import RLock
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


ROOT = Path(os.getenv("AI_DRAMA_LATENTSYNC_ROOT", "")).expanduser()
CONFIG_REL = os.getenv("AI_DRAMA_LATENTSYNC_CONFIG", "configs/unet/stage2_512.yaml").strip()
CHECKPOINT_REL = os.getenv("AI_DRAMA_LATENTSYNC_CHECKPOINT", "checkpoints/latentsync_unet.pt").strip()
USE_DEEPCACHE = os.getenv("AI_DRAMA_LATENTSYNC_DEEPCACHE", "0").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(title="AI Drama Studio LatentSync Worker", version="1.0")
_lock = RLock()
_engine: Any = None


class LipSyncRequest(BaseModel):
    video_path: str = Field(min_length=1)
    audio_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    seed: int = 1247
    inference_steps: int = Field(default=20, ge=20, le=50)
    guidance_scale: float = Field(default=1.5, ge=1.0, le=3.0)


def _root_ready() -> bool:
    return ROOT.is_dir() and (ROOT / CONFIG_REL).is_file() and (ROOT / CHECKPOINT_REL).is_file()


def _imports() -> dict[str, Any]:
    if not ROOT.is_dir():
        raise RuntimeError("AI_DRAMA_LATENTSYNC_ROOT is not configured or does not exist")
    root_string = str(ROOT.resolve())
    if root_string not in sys.path:
        sys.path.insert(0, root_string)
    try:
        import torch
        from accelerate.utils import set_seed
        from diffusers import AutoencoderKL, DDIMScheduler
        from omegaconf import OmegaConf
        from latentsync.models.unet import UNet3DConditionModel
        from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
        from latentsync.whisper.audio2feature import Audio2Feature
    except ImportError as exc:
        raise RuntimeError("Install the official LatentSync 1.6 environment before starting this worker") from exc
    return {
        "torch": torch,
        "set_seed": set_seed,
        "AutoencoderKL": AutoencoderKL,
        "DDIMScheduler": DDIMScheduler,
        "OmegaConf": OmegaConf,
        "UNet3DConditionModel": UNet3DConditionModel,
        "LipsyncPipeline": LipsyncPipeline,
        "Audio2Feature": Audio2Feature,
    }


class _Engine:
    def __init__(self) -> None:
        imports = _imports()
        torch = imports["torch"]
        if not torch.cuda.is_available():
            raise RuntimeError("LatentSync 1.6 requires CUDA; no CUDA device is available")
        self.imports = imports
        self.config = imports["OmegaConf"].load(str((ROOT / CONFIG_REL).resolve()))
        self.dtype = torch.float16 if torch.cuda.get_device_capability()[0] > 7 else torch.float32

        previous = Path.cwd()
        try:
            os.chdir(ROOT)
            scheduler = imports["DDIMScheduler"].from_pretrained("configs")
            cross_dim = int(self.config.model.cross_attention_dim)
            if cross_dim == 768:
                whisper_path = ROOT / "checkpoints/whisper/small.pt"
            elif cross_dim == 384:
                whisper_path = ROOT / "checkpoints/whisper/tiny.pt"
            else:
                raise RuntimeError("LatentSync cross_attention_dim must be 384 or 768")
            if not whisper_path.is_file():
                raise RuntimeError(f"LatentSync Whisper checkpoint is missing: {whisper_path}")
            audio_encoder = imports["Audio2Feature"](
                model_path=str(whisper_path),
                device="cuda",
                num_frames=self.config.data.num_frames,
                audio_feat_length=self.config.data.audio_feat_length,
            )
            vae = imports["AutoencoderKL"].from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=self.dtype)
            vae.config.scaling_factor = 0.18215
            vae.config.shift_factor = 0
            unet, _ = imports["UNet3DConditionModel"].from_pretrained(
                imports["OmegaConf"].to_container(self.config.model),
                str((ROOT / CHECKPOINT_REL).resolve()),
                device="cpu",
            )
            unet = unet.to(dtype=self.dtype)
            self.pipeline = imports["LipsyncPipeline"](
                vae=vae,
                audio_encoder=audio_encoder,
                unet=unet,
                scheduler=scheduler,
            ).to("cuda")
            self.deepcache = None
            if USE_DEEPCACHE:
                from DeepCache import DeepCacheSDHelper

                helper = DeepCacheSDHelper(pipe=self.pipeline)
                helper.set_params(cache_interval=3, cache_branch_id=0)
                helper.enable()
                self.deepcache = helper
        finally:
            os.chdir(previous)

    def render(self, payload: LipSyncRequest) -> Path:
        video = Path(payload.video_path).expanduser().resolve()
        audio = Path(payload.audio_path).expanduser().resolve()
        output = Path(payload.output_path).expanduser().resolve()
        if not video.is_file():
            raise RuntimeError("input video does not exist")
        if not audio.is_file():
            raise RuntimeError("input audio does not exist")
        output.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = output.parent / f".{output.stem}.latentsync-temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.imports["set_seed"](int(payload.seed))
        previous = Path.cwd()
        try:
            os.chdir(ROOT)
            self.pipeline(
                video_path=str(video),
                audio_path=str(audio),
                video_out_path=str(output),
                num_frames=int(self.config.data.num_frames),
                num_inference_steps=int(payload.inference_steps),
                guidance_scale=float(payload.guidance_scale),
                weight_dtype=self.dtype,
                width=int(self.config.data.resolution),
                height=int(self.config.data.resolution),
                mask_image_path=str((ROOT / str(self.config.data.mask_image_path)).resolve()),
                temp_dir=str(temp_dir.resolve()),
            )
        finally:
            os.chdir(previous)
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("LatentSync did not create output video")
        return output


def _get_engine() -> _Engine:
    global _engine
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is None:
            _engine = _Engine()
    return _engine


@app.get("/health")
def health() -> dict[str, Any]:
    import_ready = True
    error = None
    try:
        imports = _imports()
        cuda_ready = bool(imports["torch"].cuda.is_available())
    except Exception as exc:
        import_ready = False
        cuda_ready = False
        error = str(exc)
    config = ROOT / CONFIG_REL
    checkpoint = ROOT / CHECKPOINT_REL
    return {
        "ready": import_ready and cuda_ready and _root_ready(),
        "profile": "LATENTSYNC_LOCAL_V1_6",
        "root": str(ROOT.resolve()) if ROOT else "",
        "config": str(config),
        "checkpoint": str(checkpoint),
        "root_ready": _root_ready(),
        "cuda_ready": cuda_ready,
        "loaded": _engine is not None,
        "resolution": 512,
        "error": error,
    }


@app.post("/lip-sync")
def lip_sync(payload: LipSyncRequest) -> dict[str, Any]:
    try:
        with _lock:
            output = _get_engine().render(payload)
        return {"ok": True, "output_path": str(output)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("AI_DRAMA_LATENTSYNC_HOST", "127.0.0.1"),
        port=int(os.getenv("AI_DRAMA_LATENTSYNC_PORT", "7862")),
    )
