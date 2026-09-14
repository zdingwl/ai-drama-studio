import math
import hashlib
import secrets
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.p15.schemas import GenerationSegment
from app.p16.schemas import H3RuntimeReadinessRead, H3RuntimeReadinessState


class H3RuntimeMode(StrEnum):
    LOCAL_COMFYUI = "LOCAL_COMFYUI"
    LOCAL_SGLANG = "LOCAL_SGLANG"
    MINIMAX_CLOUD = "MINIMAX_CLOUD"


@dataclass(frozen=True)
class LocalSGLangH3Config:
    base_url: str
    model: str
    short_edge: int
    num_inference_steps: int
    flow_shift: float
    audio_flow_shift: float
    timeout_seconds: float
    poll_interval_seconds: float
    readiness_timeout_seconds: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalSGLangH3Config":
        return cls(
            base_url=settings.p16_h3_local_base_url.rstrip("/"),
            model=settings.p16_h3_local_model.strip(),
            short_edge=settings.p16_h3_local_short_edge,
            num_inference_steps=settings.p16_h3_local_inference_steps,
            flow_shift=settings.p16_h3_local_flow_shift,
            audio_flow_shift=settings.p16_h3_local_audio_flow_shift,
            timeout_seconds=settings.p16_h3_local_timeout_seconds,
            poll_interval_seconds=settings.p16_h3_local_poll_interval_seconds,
            readiness_timeout_seconds=settings.p16_h3_readiness_timeout_seconds,
        )


@dataclass(frozen=True)
class LocalComfyUIH3Config:
    base_url: str
    model: str
    unet_name: str
    clip_name: str
    video_vae_name: str
    audio_vae_name: str
    short_edge: int
    num_inference_steps: int
    timeout_seconds: float
    poll_interval_seconds: float
    readiness_timeout_seconds: float
    output_prefix: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalComfyUIH3Config":
        return cls(
            base_url=settings.p16_h3_comfyui_base_url.rstrip("/"),
            model=settings.p16_h3_local_model.strip(),
            unet_name=settings.p16_h3_comfyui_unet_name.strip(),
            clip_name=settings.p16_h3_comfyui_clip_name.strip(),
            video_vae_name=settings.p16_h3_comfyui_video_vae_name.strip(),
            audio_vae_name=settings.p16_h3_comfyui_audio_vae_name.strip(),
            short_edge=settings.p16_h3_local_short_edge,
            num_inference_steps=settings.p16_h3_comfyui_inference_steps,
            timeout_seconds=settings.p16_h3_comfyui_timeout_seconds,
            poll_interval_seconds=settings.p16_h3_comfyui_poll_interval_seconds,
            readiness_timeout_seconds=settings.p16_h3_readiness_timeout_seconds,
            output_prefix=settings.p16_h3_comfyui_output_prefix.strip().strip("/\\"),
        )


@dataclass(frozen=True)
class MiniMaxH3Config:
    api_key: str
    base_url: str
    model: str
    resolution: str
    timeout_seconds: float
    poll_interval_seconds: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "MiniMaxH3Config":
        secret = settings.p16_minimax_api_key
        api_key = secret.get_secret_value().strip() if secret is not None else ""
        if not api_key:
            raise AppError("P16_PROVIDER_NOT_CONFIGURED", "MiniMax H3 API Key 尚未配置", status_code=409)
        return cls(
            api_key=api_key,
            base_url=settings.p16_minimax_base_url.rstrip("/"),
            model=settings.p16_minimax_model,
            resolution=settings.p16_minimax_resolution,
            timeout_seconds=settings.p16_minimax_timeout_seconds,
            poll_interval_seconds=settings.p16_minimax_poll_interval_seconds,
        )


@dataclass(frozen=True)
class MiniMaxH3GenerationResult:
    remote_job_id: str
    remote_media_url: str
    requested_duration_seconds: int
    returned_ratio: str | None
    returned_resolution: str | None


class H3GenerationProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...

    def readiness(self) -> H3RuntimeReadinessRead: ...

    def assert_ready(self) -> None: ...

    def requested_duration(self, segment: GenerationSegment) -> int: ...

    def generate_to_file(self, segment: GenerationSegment, output_path: Path) -> MiniMaxH3GenerationResult: ...


class LocalSGLangH3Provider:
    provider_name = "local-sglang"

    def __init__(self, config: LocalSGLangH3Config):
        self.config = config
        self.model_name = config.model

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "runtime_mode": H3RuntimeMode.LOCAL_SGLANG.value,
            "model": self.model_name,
            "base_url": self.config.base_url,
            "create_path": "/v1/videos",
            "query_path": "/v1/videos/{video_id}",
            "content_path": "/v1/videos/{video_id}/content",
            "task": "t2va",
            "model_variant": "fl2va",
            "short_edge": self.config.short_edge,
            "num_inference_steps": self.config.num_inference_steps,
            "flow_shift": self.config.flow_shift,
            "audio_flow_shift": self.config.audio_flow_shift,
            "api_contract": "sglang-openai-video-v1",
        }

    def requested_duration(self, segment: GenerationSegment) -> int:
        return max(4, min(15, int(math.ceil(segment.duration_us / 1_000_000))))

    def request_payload(self, segment: GenerationSegment) -> dict:
        duration = self.requested_duration(segment)
        prompt = segment.generation_prompt
        if segment.negative_prompt.strip():
            prompt = f"{prompt}\nAvoid: {segment.negative_prompt.strip()}"
        return {
            "model": self.model_name,
            "prompt": prompt,
            "seconds": duration,
            "task": "t2va",
            "conditions": [],
            "target": {
                "short_edge": self.config.short_edge,
                "aspect_ratio": segment.output_ratio,
                "duration_seconds": float(duration),
            },
            "num_outputs_per_prompt": 1,
            "num_inference_steps": self.config.num_inference_steps,
            "flow_shift": self.config.flow_shift,
            "audio_flow_shift": self.config.audio_flow_shift,
        }

    @staticmethod
    def _safe_preview(response: httpx.Response) -> str:
        try:
            text = " ".join(response.text.split())
        except Exception:
            return "<unreadable body>"
        if not text:
            return "<empty body>"
        return text[:300]

    def _readiness(self, state: H3RuntimeReadinessState, message: str) -> H3RuntimeReadinessRead:
        return H3RuntimeReadinessRead(
            runtime_mode=H3RuntimeMode.LOCAL_SGLANG.value,
            state=state,
            ready=state == H3RuntimeReadinessState.READY,
            provider=self.provider_name,
            model=self.model_name,
            base_url=self.config.base_url,
            message=message,
        )

    def readiness(self, client: httpx.Client | None = None) -> H3RuntimeReadinessRead:
        owns_client = client is None
        active_client = client or httpx.Client(
            timeout=httpx.Timeout(self.config.readiness_timeout_seconds),
            trust_env=False,
        )
        try:
            try:
                health = active_client.get(f"{self.config.base_url}/health")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
                return self._readiness(
                    H3RuntimeReadinessState.UNAVAILABLE,
                    f"本地视频生成服务未启动，无法连接 {self.config.base_url}。请先启动 MiniMax-H3 SGLang Runtime。",
                )
            if health.status_code == 503:
                return self._readiness(
                    H3RuntimeReadinessState.WARMING_UP,
                    "本地视频生成服务正在加载 MiniMax-H3 模型，请等待服务就绪后再生成。",
                )
            if health.status_code != 200:
                return self._readiness(
                    H3RuntimeReadinessState.INCOMPATIBLE,
                    f"配置的本地生成地址不是可用的 H3 Runtime：/health 返回 HTTP {health.status_code}；{self._safe_preview(health)}",
                )
            try:
                models = active_client.get(f"{self.config.base_url}/v1/models")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
                return self._readiness(
                    H3RuntimeReadinessState.UNAVAILABLE,
                    "本地视频生成服务在模型检查时失去连接，请确认 H3 Runtime 仍在运行。",
                )
            if models.status_code != 200:
                return self._readiness(
                    H3RuntimeReadinessState.INCOMPATIBLE,
                    f"本地生成服务未提供 SGLang 的 /v1/models 接口（HTTP {models.status_code}）。",
                )
            try:
                models_body = models.json()
            except Exception:
                return self._readiness(
                    H3RuntimeReadinessState.INCOMPATIBLE,
                    "本地生成服务 /v1/models 未返回 JSON，当前地址不是兼容的 SGLang Diffusion 服务。",
                )
            data = models_body.get("data") if isinstance(models_body, dict) else None
            model_ids = {
                str(item.get("id") or "").strip()
                for item in (data if isinstance(data, list) else [])
                if isinstance(item, dict)
            }
            model_ids.discard("")
            if self.model_name not in model_ids:
                available = "、".join(sorted(model_ids)) or "未报告模型"
                return self._readiness(
                    H3RuntimeReadinessState.MODEL_MISMATCH,
                    f"本地生成服务已启动，但当前加载模型与 Studio 配置不一致：需要 {self.model_name}，服务报告 {available}。",
                )
            return self._readiness(H3RuntimeReadinessState.READY, "本地 MiniMax-H3 视频生成服务已就绪。")
        finally:
            if owns_client:
                active_client.close()

    def assert_ready(self) -> None:
        readiness = self.readiness()
        if readiness.ready:
            return
        status_code = 503 if readiness.state in {
            H3RuntimeReadinessState.UNAVAILABLE,
            H3RuntimeReadinessState.WARMING_UP,
        } else 502
        raise AppError(
            "P16_LOCAL_RUNTIME_NOT_READY",
            readiness.message,
            status_code=status_code,
            details={"state": readiness.state.value, "base_url": readiness.base_url},
        )

    def _request_json(self, response: httpx.Response, *, code: str, action: str) -> dict:
        content_type = response.headers.get("content-type", "unknown")
        try:
            body = response.json()
        except Exception as exc:
            preview = self._safe_preview(response)
            raise AppError(
                code,
                f"本地 H3 Runtime {action} 返回非 JSON：HTTP {response.status_code}；Content-Type={content_type}；body={preview}",
                status_code=502,
            ) from exc
        if not isinstance(body, dict):
            raise AppError(code, f"本地 H3 Runtime {action} 返回格式无效：HTTP {response.status_code}", status_code=502)
        if response.status_code >= 400:
            message = str(body.get("detail") or body.get("message") or body.get("error") or f"HTTP {response.status_code}")
            raise AppError(code, f"本地 H3 Runtime {action} 失败：HTTP {response.status_code}；{message}", status_code=502)
        return body

    def _create(self, client: httpx.Client, segment: GenerationSegment) -> tuple[str, int]:
        payload = self.request_payload(segment)
        try:
            response = client.post(f"{self.config.base_url}/v1/videos", json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AppError(
                "P16_LOCAL_RUNTIME_UNAVAILABLE",
                "本地 MiniMax H3 SGLang Runtime 不可用，请先启动 Runtime 或显式切换到 MINIMAX_CLOUD",
                status_code=503,
            ) from exc
        body = self._request_json(response, code="P16_LOCAL_RUNTIME_CREATE_FAILED", action="create")
        video_id = str(body.get("id") or "").strip()
        if not video_id:
            raise AppError("P16_LOCAL_RUNTIME_RESPONSE_INVALID", "本地 H3 create 缺少 id", status_code=502)
        return video_id, int(payload["seconds"])

    def _wait(self, client: httpx.Client, video_id: str) -> dict:
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{self.config.base_url}/v1/videos/{video_id}")
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise AppError("P16_LOCAL_RUNTIME_UNAVAILABLE", "本地 H3 Runtime 查询中断", status_code=503) from exc
            body = self._request_json(response, code="P16_LOCAL_RUNTIME_QUERY_FAILED", action="query")
            state = str(body.get("status") or "").lower()
            if state == "completed":
                return body
            if state in {"failed", "cancelled"}:
                raise AppError("P16_PROVIDER_GENERATION_FAILED", f"本地 H3 generation {state}", status_code=502)
            time.sleep(self.config.poll_interval_seconds)
        raise AppError("P16_PROVIDER_TIMEOUT", "本地 MiniMax H3 生成等待超时", status_code=504)

    def _download(self, client: httpx.Client, video_id: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(output_path.suffix + ".tmp")
        size = 0
        try:
            with client.stream(
                "GET",
                f"{self.config.base_url}/v1/videos/{video_id}/content",
                follow_redirects=True,
                timeout=httpx.Timeout(300.0),
            ) as download:
                download.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        size += len(chunk)
                        if size > 512 * 1024 * 1024:
                            raise AppError("P16_PROVIDER_MEDIA_TOO_LARGE", "本地 H3 视频超过 512MB 安全上限", status_code=502)
                        handle.write(chunk)
        except AppError:
            tmp.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError) as exc:
            tmp.unlink(missing_ok=True)
            raise AppError("P16_LOCAL_RUNTIME_MEDIA_FAILED", "本地 H3 输出媒体读取失败", status_code=502) from exc
        if size <= 0:
            tmp.unlink(missing_ok=True)
            raise AppError("P16_PROVIDER_MEDIA_EMPTY", "本地 H3 返回空视频", status_code=502)
        tmp.replace(output_path)

    def generate_to_file(self, segment: GenerationSegment, output_path: Path) -> MiniMaxH3GenerationResult:
        with httpx.Client(
            timeout=httpx.Timeout(min(120.0, self.config.timeout_seconds)),
            trust_env=False,
        ) as client:
            video_id, duration = self._create(client, segment)
            task = self._wait(client, video_id)
            self._download(client, video_id, output_path)
        return MiniMaxH3GenerationResult(
            remote_job_id=video_id,
            remote_media_url=f"{self.config.base_url}/v1/videos/{video_id}/content",
            requested_duration_seconds=duration,
            returned_ratio=str(task.get("aspect_ratio") or task.get("ratio") or "") or None,
            returned_resolution=str(task.get("resolution") or "") or None,
        )


class LocalComfyUIH3Provider:
    provider_name = "local-comfyui"
    ref2va_unet_name = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    _required_nodes = {
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        "MiniMaxH3ImageToVideo",
        "MiniMaxH3ReferenceToVideo",
        "LoadImage",
        "RandomNoise",
        "BasicGuider",
        "KSamplerSelect",
        "BasicScheduler",
        "SamplerCustomAdvanced",
        "VAEDecode",
        "VAEDecodeAudio",
        "CreateVideo",
        "SaveVideo",
    }

    def __init__(self, config: LocalComfyUIH3Config):
        self.config = config
        self.model_name = config.model

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "runtime_mode": H3RuntimeMode.LOCAL_COMFYUI.value,
            "model": self.model_name,
            "base_url": self.config.base_url,
            "unet_name": self.config.unet_name,
            "ref2va_unet_name": self.ref2va_unet_name,
            "clip_name": self.config.clip_name,
            "video_vae_name": self.config.video_vae_name,
            "audio_vae_name": self.config.audio_vae_name,
            "model_variant": "ref2va-primary/fl2va-legacy",
            "task": "multi-reference-native-av",
            "short_edge": self.config.short_edge,
            "num_inference_steps": self.config.num_inference_steps,
            "sampler": "res_multistep",
            "scheduler": "simple",
            "prompt_path": "/prompt",
            "history_path": "/history/{prompt_id}",
            "content_path": "/view",
            "api_contract": "comfyui-h3-native-prompt-v1",
        }

    def requested_duration(self, segment: GenerationSegment) -> int:
        return max(4, min(15, int(math.ceil(segment.duration_us / 1_000_000))))

    @staticmethod
    def _safe_preview(response: httpx.Response) -> str:
        try:
            text = " ".join(response.text.split())
        except Exception:
            return "<unreadable body>"
        return text[:300] if text else "<empty body>"

    @staticmethod
    def _combo_options(node: dict, field: str) -> set[str]:
        required = ((node.get("input") or {}).get("required") or {}).get(field)
        if not isinstance(required, list) or not required:
            return set()
        first = required[0]
        if isinstance(first, list):
            return {str(value) for value in first}
        if len(required) > 1 and isinstance(required[1], dict):
            options = required[1].get("options")
            if isinstance(options, list):
                return {str(value) for value in options}
        return set()

    def _readiness(self, state: H3RuntimeReadinessState, message: str) -> H3RuntimeReadinessRead:
        return H3RuntimeReadinessRead(
            runtime_mode=H3RuntimeMode.LOCAL_COMFYUI.value,
            state=state,
            ready=state == H3RuntimeReadinessState.READY,
            provider=self.provider_name,
            model=self.model_name,
            base_url=self.config.base_url,
            message=message,
        )

    def readiness(self, client: httpx.Client | None = None) -> H3RuntimeReadinessRead:
        owns_client = client is None
        active_client = client or httpx.Client(
            timeout=httpx.Timeout(self.config.readiness_timeout_seconds),
            trust_env=False,
        )
        try:
            try:
                stats = active_client.get(f"{self.config.base_url}/system_stats")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
                return self._readiness(
                    H3RuntimeReadinessState.UNAVAILABLE,
                    f"ComfyUI 未启动，无法连接 {self.config.base_url}。请先启动本机 ComfyUI。",
                )
            if stats.status_code == 503:
                return self._readiness(H3RuntimeReadinessState.WARMING_UP, "ComfyUI 正在启动，请等待服务就绪。")
            if stats.status_code != 200:
                return self._readiness(
                    H3RuntimeReadinessState.INCOMPATIBLE,
                    f"配置的 ComfyUI 地址不可用：/system_stats 返回 HTTP {stats.status_code}；{self._safe_preview(stats)}",
                )
            try:
                stats_body = stats.json()
            except Exception:
                return self._readiness(H3RuntimeReadinessState.INCOMPATIBLE, "ComfyUI /system_stats 未返回 JSON。")
            system = stats_body.get("system") if isinstance(stats_body, dict) else None
            if not isinstance(system, dict) or not str(system.get("comfyui_version") or "").strip():
                return self._readiness(H3RuntimeReadinessState.INCOMPATIBLE, "当前地址不是可识别的 ComfyUI Runtime。")

            try:
                object_info = active_client.get(f"{self.config.base_url}/object_info")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
                return self._readiness(H3RuntimeReadinessState.UNAVAILABLE, "ComfyUI 在检查 H3 节点时失去连接。")
            if object_info.status_code == 503:
                return self._readiness(H3RuntimeReadinessState.WARMING_UP, "ComfyUI 正在加载节点，请稍后重试。")
            if object_info.status_code != 200:
                return self._readiness(
                    H3RuntimeReadinessState.INCOMPATIBLE,
                    f"ComfyUI 未提供 /object_info（HTTP {object_info.status_code}）。",
                )
            try:
                nodes = object_info.json()
            except Exception:
                return self._readiness(H3RuntimeReadinessState.INCOMPATIBLE, "ComfyUI /object_info 未返回 JSON。")
            if not isinstance(nodes, dict):
                return self._readiness(H3RuntimeReadinessState.INCOMPATIBLE, "ComfyUI /object_info 返回格式无效。")
            missing_nodes = sorted(self._required_nodes - set(nodes))
            if missing_nodes:
                return self._readiness(
                    H3RuntimeReadinessState.INCOMPATIBLE,
                    "当前 ComfyUI 缺少 MiniMax H3 本地工作流所需节点：" + "、".join(missing_nodes),
                )

            required_models = (
                ("UNETLoader", "unet_name", self.config.unet_name),
                ("UNETLoader", "unet_name", self.ref2va_unet_name),
                ("CLIPLoader", "clip_name", self.config.clip_name),
                ("VAELoader", "vae_name", self.config.video_vae_name),
                ("VAELoader", "vae_name", self.config.audio_vae_name),
            )
            missing_models = [
                filename
                for node_name, field, filename in required_models
                if filename not in self._combo_options(nodes[node_name], field)
            ]
            if missing_models:
                return self._readiness(
                    H3RuntimeReadinessState.MODEL_MISMATCH,
                    "ComfyUI 已启动，但缺少 P16 配置的 MiniMax H3 模型文件：" + "、".join(missing_models),
                )
            return self._readiness(
                H3RuntimeReadinessState.READY,
                f"ComfyUI MiniMax-H3 已就绪（{system.get('comfyui_version')}，Ref2VA 多参考音画生成可用）。",
            )
        finally:
            if owns_client:
                active_client.close()

    def assert_ready(self) -> None:
        readiness = self.readiness()
        if readiness.ready:
            return
        status_code = 503 if readiness.state in {
            H3RuntimeReadinessState.UNAVAILABLE,
            H3RuntimeReadinessState.WARMING_UP,
        } else 502
        raise AppError(
            "P16_LOCAL_RUNTIME_NOT_READY",
            readiness.message,
            status_code=status_code,
            details={"state": readiness.state.value, "base_url": readiness.base_url},
        )

    def _dimensions(self, ratio: str) -> tuple[int, int]:
        ratios = {
            "21:9": (21, 9),
            "16:9": (16, 9),
            "4:3": (4, 3),
            "1:1": (1, 1),
            "3:4": (3, 4),
            "9:16": (9, 16),
        }
        if ratio not in ratios:
            raise AppError("P16_PROVIDER_RATIO_UNSUPPORTED", f"ComfyUI H3 不支持输出比例 {ratio}", status_code=422)
        rw, rh = ratios[ratio]
        short = self.config.short_edge
        if rw >= rh:
            height = short
            width = max(32, int((short * rw / rh) // 32) * 32)
        else:
            width = short
            height = max(32, int((short * rh / rw) // 32) * 32)
        return width, height

    @staticmethod
    def _frame_length(duration_seconds: int) -> int:
        frames = max(5, round(duration_seconds * 24))
        return frames + (5 - (frames % 17)) % 17

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _managed_reference_path(self, condition) -> Path:
        root = self.config_settings_artifact_root.resolve()
        path = (root / condition.storage_relpath).resolve()
        if root not in path.parents or not path.is_file():
            raise AppError("P16_REFERENCE_MEDIA_NOT_FOUND", "H3 正式参考图不存在", status_code=409, details={"reference_id": condition.reference_id})
        if self._file_sha256(path) != condition.reference_sha256:
            raise AppError("P16_REFERENCE_MEDIA_HASH_MISMATCH", "H3 正式参考图 hash 与 Prompt Skill 合同不一致", status_code=409, details={"reference_id": condition.reference_id})
        return path

    @property
    def config_settings_artifact_root(self) -> Path:
        from app.core.config import get_settings

        return get_settings().artifact_root

    def _upload_reference_images(self, client: httpx.Client, segment: GenerationSegment) -> list[str]:
        uploaded: list[str] = []
        for condition in segment.reference_conditions:
            path = self._managed_reference_path(condition)
            subfolder = f"ai_drama_studio/h3_refs/{condition.reference_sha256[:16]}"
            with path.open("rb") as handle:
                try:
                    response = client.post(
                        f"{self.config.base_url}/upload/image",
                        data={"type": "input", "overwrite": "true", "subfolder": subfolder},
                        files={"image": (path.name, handle, "image/png")},
                        timeout=httpx.Timeout(300.0),
                    )
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    raise AppError("P16_REFERENCE_UPLOAD_FAILED", "上传 H3 正式参考图到 ComfyUI 失败", status_code=503) from exc
            body = self._request_json(response, code="P16_REFERENCE_UPLOAD_FAILED", action="upload reference image")
            name = str(body.get("name") or "").strip()
            actual_subfolder = str(body.get("subfolder") or subfolder).strip("/\\")
            if not name:
                raise AppError("P16_REFERENCE_UPLOAD_FAILED", "ComfyUI 参考图上传响应缺少 name", status_code=502)
            uploaded.append(f"{actual_subfolder}/{name}" if actual_subfolder else name)
        if len(uploaded) != len(segment.reference_conditions):
            raise AppError("P16_REFERENCE_UPLOAD_FAILED", "H3 reference slot 上传覆盖不完整", status_code=502)
        return uploaded

    def workflow_payload(self, segment: GenerationSegment, *, seed: int | None = None, uploaded_images: list[str] | None = None) -> dict:
        duration = self.requested_duration(segment)
        width, height = self._dimensions(segment.output_ratio)
        prompt = segment.generation_prompt
        if not segment.prompt_skill_id and segment.negative_prompt.strip():
            prompt = f"{prompt}\nAvoid: {segment.negative_prompt.strip()}"
        noise_seed = seed if seed is not None else secrets.randbelow((1 << 63) - 1)
        filename_prefix = f"{self.config.output_prefix}/{segment.episode_id}-{segment.segment_number}-{uuid4().hex[:10]}"
        reference_mode = bool(segment.reference_conditions)
        uploaded = uploaded_images or []
        if reference_mode and len(uploaded) != len(segment.reference_conditions):
            raise AppError("P16_REFERENCE_SLOTS_INVALID", "H3 Prompt Skill reference slots 与 Runtime 上传图片数量不一致", status_code=409)
        graph = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": self.ref2va_unet_name if reference_mode else self.config.unet_name, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.config.clip_name, "type": "minimax", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": self.config.video_vae_name}},
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": self.config.audio_vae_name}},
            "5": {
                "class_type": "MiniMaxH3ReferenceToVideo" if reference_mode else "MiniMaxH3ImageToVideo",
                "inputs": {
                    "clip": ["2", 0],
                    "vae": ["3", 0],
                    **({"audio_vae": ["4", 0], "ref_image_size": "match"} if reference_mode else {}),
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "length": self._frame_length(duration),
                },
            },
            "6": {"class_type": "RandomNoise", "inputs": {"noise_seed": noise_seed}},
            "7": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["5", 0]}},
            "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
            "9": {
                "class_type": "BasicScheduler",
                "inputs": {"model": ["1", 0], "scheduler": "simple", "steps": self.config.num_inference_steps, "denoise": 1.0},
            },
            "10": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["6", 0],
                    "guider": ["7", 0],
                    "sampler": ["8", 0],
                    "sigmas": ["9", 0],
                    "latent_image": ["5", 1],
                },
            },
            "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
            "12": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["10", 0], "vae": ["4", 0]}},
            "13": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "audio": ["12", 0], "fps": 24.0, "bit_depth": 8}},
            "14": {"class_type": "SaveVideo", "inputs": {"video": ["13", 0], "filename_prefix": filename_prefix, "format": "mp4"}},
        }
        for index, image_name in enumerate(uploaded, 1):
            node_id = str(14 + index)
            graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
            graph["5"]["inputs"][f"ref_image_{index}"] = [node_id, 0]
        return {"prompt": graph, "client_id": f"ai-drama-studio-{uuid4()}"}

    def _request_json(self, response: httpx.Response, *, code: str, action: str) -> dict:
        try:
            body = response.json()
        except Exception as exc:
            raise AppError(
                code,
                f"ComfyUI {action} 返回非 JSON：HTTP {response.status_code}；body={self._safe_preview(response)}",
                status_code=502,
            ) from exc
        if not isinstance(body, dict):
            raise AppError(code, f"ComfyUI {action} 返回格式无效", status_code=502)
        if response.status_code >= 400:
            message = str(body.get("error") or body.get("message") or body.get("node_errors") or f"HTTP {response.status_code}")
            raise AppError(code, f"ComfyUI {action} 失败：HTTP {response.status_code}；{message[:600]}", status_code=502)
        return body

    def _create(self, client: httpx.Client, segment: GenerationSegment) -> tuple[str, int]:
        uploaded_images = self._upload_reference_images(client, segment) if segment.reference_conditions else []
        payload = self.workflow_payload(segment, uploaded_images=uploaded_images)
        try:
            response = client.post(f"{self.config.base_url}/prompt", json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AppError("P16_LOCAL_RUNTIME_UNAVAILABLE", "本地 ComfyUI H3 Runtime 不可用", status_code=503) from exc
        body = self._request_json(response, code="P16_LOCAL_RUNTIME_CREATE_FAILED", action="queue prompt")
        prompt_id = str(body.get("prompt_id") or "").strip()
        if not prompt_id:
            raise AppError("P16_LOCAL_RUNTIME_RESPONSE_INVALID", "ComfyUI /prompt 缺少 prompt_id", status_code=502)
        return prompt_id, self.requested_duration(segment)

    @staticmethod
    def _history_entry(body: dict, prompt_id: str) -> dict | None:
        if isinstance(body.get(prompt_id), dict):
            return body[prompt_id]
        history = body.get("history")
        if isinstance(history, dict) and isinstance(history.get(prompt_id), dict):
            return history[prompt_id]
        return None

    @staticmethod
    def _find_saved_media(entry: dict) -> dict | None:
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict):
            return None
        candidates: list[dict] = []

        def visit(value) -> None:
            if isinstance(value, dict):
                filename = value.get("filename")
                if isinstance(filename, str):
                    candidates.append(value)
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        save_video = outputs.get("14")
        if isinstance(save_video, dict):
            visit(save_video)
        if not candidates:
            visit(outputs)
        for item in candidates:
            filename = str(item.get("filename") or "")
            if Path(filename).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
                return {
                    "filename": filename,
                    "subfolder": str(item.get("subfolder") or ""),
                    "type": str(item.get("type") or "output"),
                }
        return None

    def _wait(self, client: httpx.Client, prompt_id: str) -> tuple[dict, dict]:
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{self.config.base_url}/history/{prompt_id}")
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise AppError("P16_LOCAL_RUNTIME_UNAVAILABLE", "ComfyUI 生成查询中断", status_code=503) from exc
            body = self._request_json(response, code="P16_LOCAL_RUNTIME_QUERY_FAILED", action="query history")
            entry = self._history_entry(body, prompt_id)
            if entry is None:
                time.sleep(self.config.poll_interval_seconds)
                continue
            status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
            status_str = str(status.get("status_str") or "").lower()
            if status_str in {"error", "failed"}:
                messages = status.get("messages")
                summary = str(messages)[:800] if messages else status_str
                raise AppError("P16_PROVIDER_GENERATION_FAILED", f"ComfyUI H3 workflow failed：{summary}", status_code=502)
            media = self._find_saved_media(entry)
            if media is not None:
                return entry, media
            if status.get("completed") is True:
                raise AppError("P16_PROVIDER_MEDIA_MISSING", "ComfyUI H3 workflow 已完成但没有 SaveVideo 输出", status_code=502)
            time.sleep(self.config.poll_interval_seconds)
        raise AppError("P16_PROVIDER_TIMEOUT", "本地 ComfyUI MiniMax-H3 生成等待超时", status_code=504)

    def _download(self, client: httpx.Client, media: dict, output_path: Path) -> str:
        params = {
            "filename": media["filename"],
            "subfolder": media["subfolder"],
            "type": media["type"],
        }
        remote_url = f"{self.config.base_url}/view?{urlencode(params)}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(output_path.suffix + ".tmp")
        size = 0
        try:
            with client.stream("GET", f"{self.config.base_url}/view", params=params, timeout=httpx.Timeout(300.0)) as download:
                download.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        size += len(chunk)
                        if size > 512 * 1024 * 1024:
                            raise AppError("P16_PROVIDER_MEDIA_TOO_LARGE", "ComfyUI H3 视频超过 512MB 安全上限", status_code=502)
                        handle.write(chunk)
        except AppError:
            tmp.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError) as exc:
            tmp.unlink(missing_ok=True)
            raise AppError("P16_LOCAL_RUNTIME_MEDIA_FAILED", "ComfyUI H3 输出媒体读取失败", status_code=502) from exc
        if size <= 0:
            tmp.unlink(missing_ok=True)
            raise AppError("P16_PROVIDER_MEDIA_EMPTY", "ComfyUI H3 返回空视频", status_code=502)
        tmp.replace(output_path)
        return remote_url

    def generate_to_file(self, segment: GenerationSegment, output_path: Path) -> MiniMaxH3GenerationResult:
        width, height = self._dimensions(segment.output_ratio)
        with httpx.Client(
            timeout=httpx.Timeout(min(120.0, self.config.timeout_seconds)),
            trust_env=False,
        ) as client:
            prompt_id, duration = self._create(client, segment)
            _, media = self._wait(client, prompt_id)
            remote_url = self._download(client, media, output_path)
        return MiniMaxH3GenerationResult(
            remote_job_id=prompt_id,
            remote_media_url=remote_url,
            requested_duration_seconds=duration,
            returned_ratio=segment.output_ratio,
            returned_resolution=f"{width}x{height}",
        )


class MiniMaxH3Provider:
    provider_name = "minimax-cloud"

    def __init__(self, config: MiniMaxH3Config):
        self.config = config
        self.model_name = config.model

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "runtime_mode": H3RuntimeMode.MINIMAX_CLOUD.value,
            "model": self.model_name,
            "base_url": self.config.base_url,
            "create_path": "/v2/video_generation",
            "query_path": "/v2/query/video_generation/{task_id}",
            "resolution": self.config.resolution,
            "api_contract": "minimax-h3-v2-2026-09",
        }

    def readiness(self) -> H3RuntimeReadinessRead:
        return H3RuntimeReadinessRead(
            runtime_mode=H3RuntimeMode.MINIMAX_CLOUD.value,
            state=H3RuntimeReadinessState.READY,
            ready=True,
            provider=self.provider_name,
            model=self.model_name,
            base_url=self.config.base_url,
            message="MiniMax Cloud H3 已配置；网络连通性会在实际生成请求时校验。",
        )

    def assert_ready(self) -> None:
        return None

    def requested_duration(self, segment: GenerationSegment) -> int:
        minimum = 5 if self.model_name == "MiniMax-H3-Max" else 4
        return max(minimum, min(15, int(math.ceil(segment.duration_us / 1_000_000))))

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}

    def _create(self, client: httpx.Client, segment: GenerationSegment) -> tuple[str, int]:
        duration = self.requested_duration(segment)
        prompt = segment.generation_prompt
        if segment.negative_prompt.strip():
            prompt = f"{prompt}\nAvoid: {segment.negative_prompt.strip()}"
        response = client.post(
            f"{self.config.base_url}/v2/video_generation",
            headers=self._headers,
            json={
                "model": self.model_name,
                "content": [{"type": "text", "text": prompt}],
                "resolution": self.config.resolution,
                "duration": duration,
                "ratio": segment.output_ratio,
            },
        )
        try:
            body = response.json()
        except Exception as exc:
            raise AppError("P16_PROVIDER_RESPONSE_INVALID", "MiniMax H3 create 未返回 JSON", status_code=502) from exc
        if response.status_code >= 400:
            message = ((body.get("error") or {}).get("message") if isinstance(body, dict) else None) or f"HTTP {response.status_code}"
            raise AppError("P16_PROVIDER_CREATE_FAILED", f"MiniMax H3 create 失败：{message}", status_code=502)
        task_id = str(body.get("task_id") or "").strip()
        if not task_id:
            raise AppError("P16_PROVIDER_RESPONSE_INVALID", "MiniMax H3 create 缺少 task_id", status_code=502)
        return task_id, duration

    def _wait(self, client: httpx.Client, task_id: str) -> dict:
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            response = client.get(
                f"{self.config.base_url}/v2/query/video_generation/{task_id}",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
            try:
                body = response.json()
            except Exception as exc:
                raise AppError("P16_PROVIDER_RESPONSE_INVALID", "MiniMax H3 query 未返回 JSON", status_code=502) from exc
            if response.status_code >= 400:
                message = ((body.get("error") or {}).get("message") if isinstance(body, dict) else None) or f"HTTP {response.status_code}"
                raise AppError("P16_PROVIDER_QUERY_FAILED", f"MiniMax H3 query 失败：{message}", status_code=502)
            task = body.get("task") or {}
            state = str(task.get("status") or "").lower()
            if state == "succeeded":
                return task
            if state in {"failed", "cancelled"}:
                raise AppError("P16_PROVIDER_GENERATION_FAILED", f"MiniMax H3 task {state}", status_code=502)
            time.sleep(self.config.poll_interval_seconds)
        raise AppError("P16_PROVIDER_TIMEOUT", "MiniMax H3 生成等待超时", status_code=504)

    def generate_to_file(self, segment: GenerationSegment, output_path: Path) -> MiniMaxH3GenerationResult:
        with httpx.Client(timeout=httpx.Timeout(min(120.0, self.config.timeout_seconds))) as client:
            task_id, duration = self._create(client, segment)
            task = self._wait(client, task_id)
            remote_url = str((task.get("content") or {}).get("url") or "").strip()
            if not remote_url.startswith(("https://", "http://")):
                raise AppError("P16_PROVIDER_MEDIA_MISSING", "MiniMax H3 成功任务缺少可下载视频 URL", status_code=502)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = output_path.with_suffix(output_path.suffix + ".tmp")
            size = 0
            with client.stream("GET", remote_url, follow_redirects=True, timeout=httpx.Timeout(300.0)) as download:
                download.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        size += len(chunk)
                        if size > 512 * 1024 * 1024:
                            raise AppError("P16_PROVIDER_MEDIA_TOO_LARGE", "MiniMax H3 视频超过 512MB 安全上限", status_code=502)
                        handle.write(chunk)
            if size <= 0:
                tmp.unlink(missing_ok=True)
                raise AppError("P16_PROVIDER_MEDIA_EMPTY", "MiniMax H3 返回空视频", status_code=502)
            tmp.replace(output_path)
        return MiniMaxH3GenerationResult(
            remote_job_id=task_id,
            remote_media_url=remote_url,
            requested_duration_seconds=duration,
            returned_ratio=str(task.get("ratio") or "") or None,
            returned_resolution=str(task.get("resolution") or "") or None,
        )


def build_h3_generation_provider(settings: Settings | None = None) -> H3GenerationProvider:
    resolved = settings or Settings()
    try:
        mode = H3RuntimeMode(resolved.p16_h3_runtime)
    except ValueError as exc:
        raise AppError(
            "P16_PROVIDER_CONFIG_INVALID",
            "AI_DRAMA_P16_H3_RUNTIME 只允许 LOCAL_COMFYUI、LOCAL_SGLANG 或 MINIMAX_CLOUD",
            status_code=500,
        ) from exc
    if mode == H3RuntimeMode.LOCAL_COMFYUI:
        return LocalComfyUIH3Provider(LocalComfyUIH3Config.from_settings(resolved))
    if mode == H3RuntimeMode.LOCAL_SGLANG:
        return LocalSGLangH3Provider(LocalSGLangH3Config.from_settings(resolved))
    return MiniMaxH3Provider(MiniMaxH3Config.from_settings(resolved))
