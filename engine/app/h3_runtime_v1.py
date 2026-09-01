"""Local MiniMax H3 SGLang runtime client.

The FastAPI process never imports H3 model weights. FL2VA and Ref2VA stay isolated in
local SGLang services while this adapter owns health checks, validated async submission,
status polling and atomic output download.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any, Literal, Mapping

import httpx


H3Mode = Literal["FL2VA", "REF2VA"]


class H3RuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class H3EndpointConfig:
    mode: H3Mode
    base_url: str


class H3RuntimeManager:
    def __init__(self) -> None:
        self._configs: dict[H3Mode, H3EndpointConfig] = {
            "FL2VA": H3EndpointConfig(
                mode="FL2VA",
                base_url=os.getenv("AI_DRAMA_H3_FL2VA_URL", "http://127.0.0.1:30010").rstrip("/"),
            ),
            "REF2VA": H3EndpointConfig(
                mode="REF2VA",
                base_url=os.getenv("AI_DRAMA_H3_REF2VA_URL", "http://127.0.0.1:30011").rstrip("/"),
            ),
        }
        self._model_name = os.getenv("AI_DRAMA_H3_MODEL", "MiniMaxAI/MiniMax-H3").strip() or "MiniMaxAI/MiniMax-H3"
        self._request_timeout = max(5.0, float(os.getenv("AI_DRAMA_H3_REQUEST_TIMEOUT", "30")))
        self._download_timeout = max(60.0, float(os.getenv("AI_DRAMA_H3_DOWNLOAD_TIMEOUT", "900")))
        self._num_inference_steps = max(1, int(os.getenv("AI_DRAMA_H3_NUM_INFERENCE_STEPS", "50")))
        self._flow_shift = float(os.getenv("AI_DRAMA_H3_FLOW_SHIFT", "12.0"))
        self._audio_flow_shift = float(os.getenv("AI_DRAMA_H3_AUDIO_FLOW_SHIFT", "3.0"))

    def config(self, mode: H3Mode) -> H3EndpointConfig:
        try:
            return self._configs[mode]
        except KeyError as exc:
            raise ValueError(f"Unsupported H3 mode: {mode}") from exc

    def _health_one(self, mode: H3Mode) -> dict[str, Any]:
        config = self.config(mode)
        errors: list[str] = []
        for path in ("/health", "/v1/models"):
            try:
                with httpx.Client(timeout=self._request_timeout) as client:
                    response = client.get(f"{config.base_url}{path}")
                if response.is_success:
                    return {
                        "mode": mode,
                        "base_url": config.base_url,
                        "ready": True,
                        "probe": path,
                        "status_code": response.status_code,
                        "error": None,
                    }
                errors.append(f"{path}: HTTP {response.status_code}")
            except httpx.HTTPError as exc:
                errors.append(f"{path}: {exc}")
        return {
            "mode": mode,
            "base_url": config.base_url,
            "ready": False,
            "probe": None,
            "status_code": None,
            "error": " | ".join(errors)[-1200:] if errors else "H3 runtime unavailable",
        }

    def status(self) -> dict[str, Any]:
        fl2va = self._health_one("FL2VA")
        ref2va = self._health_one("REF2VA")
        return {
            "runtime_profile": "MINIMAX_H3_SGLANG_LOCAL_V2",
            "model": self._model_name,
            "ready": bool(fl2va["ready"] and ref2va["ready"]),
            "fl2va": fl2va,
            "ref2va": ref2va,
        }

    @staticmethod
    def _validate_conditions(mode: H3Mode, conditions: list[Mapping[str, Any]]) -> None:
        if len(conditions) > 12:
            raise ValueError("H3 conditions 最多 12 个文件")
        image_count = sum(str(item.get("type") or "") == "image" for item in conditions)
        video_count = sum(str(item.get("type") or "") == "video" for item in conditions)
        audio_count = sum(str(item.get("type") or "") == "audio" for item in conditions)
        if mode == "REF2VA":
            if image_count > 9 or video_count > 3 or audio_count > 3:
                raise ValueError("Ref2VA 输入超过官方 image/video/audio 数量限制")
            if audio_count and not (image_count or video_count):
                raise ValueError("Ref2VA audio 不能作为唯一条件")
        else:
            if video_count or audio_count:
                raise ValueError("FL2VA 只接受 0-2 张 keyframe image")
            if image_count > 2:
                raise ValueError("FL2VA 最多接受两张 keyframe image")
        frame_indices: list[int] = []
        for item in conditions:
            if not str(item.get("uri") or "").strip():
                raise ValueError("H3 condition.uri 不能为空")
            item_type = str(item.get("type") or "")
            frame_index = item.get("frame_index")
            if frame_index is not None:
                if item_type != "image" or int(frame_index) not in {-1, 0}:
                    raise ValueError("H3 frame_index 只允许 image 的 0/-1")
                frame_indices.append(int(frame_index))
            start_time = item.get("start_time_seconds")
            if start_time is not None:
                if item_type not in {"video", "audio"} or float(start_time) < 0:
                    raise ValueError("H3 start_time_seconds 只允许非负 video/audio seek")
        if mode == "FL2VA" and len(frame_indices) != len(set(frame_indices)):
            raise ValueError("FL2VA first/last frame_index 不能重复")

    def _request_body(
        self,
        *,
        mode: H3Mode,
        prompt: str,
        conditions: list[Mapping[str, Any]],
        duration_seconds: int,
        short_edge: int,
        aspect_ratio: str,
        seed: int,
    ) -> dict[str, Any]:
        normalized_conditions = [dict(item) for item in conditions]
        self._validate_conditions(mode, normalized_conditions)
        image_count = sum(str(item.get("type") or "") == "image" for item in normalized_conditions)
        task = "ref2va" if mode == "REF2VA" else "fl2va" if image_count else "t2va"
        return {
            "model": self._model_name,
            "prompt": prompt,
            "seconds": float(duration_seconds),
            "task": task,
            "conditions": normalized_conditions,
            "target": {
                "short_edge": int(short_edge),
                "aspect_ratio": aspect_ratio or "auto",
                "duration_seconds": float(duration_seconds),
            },
            "num_outputs_per_prompt": 1,
            "num_inference_steps": self._num_inference_steps,
            "flow_shift": self._flow_shift,
            "audio_flow_shift": self._audio_flow_shift,
            "seed": int(seed),
        }

    def submit_video(
        self,
        *,
        mode: H3Mode,
        prompt: str,
        conditions: list[Mapping[str, Any]],
        duration_seconds: int,
        short_edge: int = 768,
        aspect_ratio: str = "auto",
        seed: int = 0,
    ) -> dict[str, Any]:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("H3 prompt 不能为空")
        if not 4 <= duration_seconds <= 15:
            raise ValueError("H3 duration_seconds 必须为 4-15 秒")
        if short_edge != 768:
            raise ValueError("MiniMax H3 当前正式 768p runtime 要求 short_edge=768")
        body = self._request_body(
            mode=mode,
            prompt=clean_prompt,
            conditions=conditions,
            duration_seconds=duration_seconds,
            short_edge=short_edge,
            aspect_ratio=aspect_ratio,
            seed=seed,
        )
        config = self.config(mode)
        try:
            with httpx.Client(timeout=self._request_timeout) as client:
                response = client.post(f"{config.base_url}/v1/videos", json=body)
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise H3RuntimeError(f"H3 {mode} 提交失败：{exc}") from exc
        video_id = str(result.get("id") or "") if isinstance(result, Mapping) else ""
        if not video_id:
            raise H3RuntimeError(f"H3 {mode} 提交成功但未返回 video id")
        return dict(result)

    def get_video_status(self, mode: H3Mode, video_id: str) -> dict[str, Any]:
        clean_id = video_id.strip()
        if not clean_id:
            raise ValueError("H3 video_id 不能为空")
        config = self.config(mode)
        try:
            with httpx.Client(timeout=self._request_timeout) as client:
                response = client.get(f"{config.base_url}/v1/videos/{clean_id}")
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise H3RuntimeError(f"H3 {mode} 状态查询失败：{exc}") from exc
        if not isinstance(result, Mapping):
            raise H3RuntimeError("H3 状态接口返回格式错误")
        return dict(result)

    def download_video(self, mode: H3Mode, video_id: str, destination: Path) -> Path:
        clean_id = video_id.strip()
        if not clean_id:
            raise ValueError("H3 video_id 不能为空")
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        config = self.config(mode)
        tmp_path: Path | None = None
        try:
            with httpx.Client(timeout=self._download_timeout) as client:
                with client.stream("GET", f"{config.base_url}/v1/videos/{clean_id}/content") as response:
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        delete=False,
                        dir=destination.parent,
                        prefix=f".{destination.name}.",
                        suffix=".part",
                    ) as handle:
                        tmp_path = Path(handle.name)
                        for chunk in response.iter_bytes(1024 * 1024):
                            if chunk:
                                handle.write(chunk)
            if tmp_path is None or not tmp_path.is_file() or tmp_path.stat().st_size <= 0:
                raise H3RuntimeError("H3 输出下载为空")
            tmp_path.replace(destination)
            return destination
        except (httpx.HTTPError, OSError) as exc:
            raise H3RuntimeError(f"H3 {mode} 输出下载失败：{exc}") from exc
        finally:
            if tmp_path is not None and tmp_path.exists() and tmp_path != destination:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


_RUNTIME = H3RuntimeManager()


def h3_runtime_status_v1() -> dict[str, Any]:
    return _RUNTIME.status()


def h3_runtime_manager_v1() -> H3RuntimeManager:
    return _RUNTIME


__all__ = [
    "H3EndpointConfig",
    "H3Mode",
    "H3RuntimeError",
    "H3RuntimeManager",
    "h3_runtime_manager_v1",
    "h3_runtime_status_v1",
]
