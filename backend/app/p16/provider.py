import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.errors import AppError
from app.p15.schemas import GenerationSegment


@dataclass(frozen=True)
class MiniMaxH3Config:
    api_key: str
    base_url: str
    model: str
    resolution: str
    timeout_seconds: float
    poll_interval_seconds: float

    @classmethod
    def from_env(cls) -> "MiniMaxH3Config":
        api_key = (os.getenv("AI_DRAMA_P16_MINIMAX_API_KEY") or os.getenv("MINIMAX_API_KEY") or "").strip()
        if not api_key:
            raise AppError("P16_PROVIDER_NOT_CONFIGURED", "MiniMax H3 API Key 尚未配置", status_code=409)
        base_url = (os.getenv("AI_DRAMA_P16_MINIMAX_BASE_URL") or "https://api.minimax.io").rstrip("/")
        model = (os.getenv("AI_DRAMA_P16_MINIMAX_MODEL") or "MiniMax-H3").strip()
        resolution = (os.getenv("AI_DRAMA_P16_MINIMAX_RESOLUTION") or "768P").strip().upper()
        if model not in {"MiniMax-H3", "MiniMax-H3-Max"}:
            raise AppError("P16_PROVIDER_CONFIG_INVALID", "MiniMax H3 model 配置无效", status_code=500)
        if resolution not in {"480P", "768P", "2K"}:
            raise AppError("P16_PROVIDER_CONFIG_INVALID", "MiniMax H3 resolution 配置无效", status_code=500)
        if model == "MiniMax-H3" and resolution == "480P":
            raise AppError("P16_PROVIDER_CONFIG_INVALID", "MiniMax-H3 不支持 480P", status_code=500)
        if model == "MiniMax-H3-Max" and resolution == "2K":
            raise AppError("P16_PROVIDER_CONFIG_INVALID", "MiniMax-H3-Max 不支持 2K", status_code=500)
        timeout = float(os.getenv("AI_DRAMA_P16_MINIMAX_TIMEOUT_SECONDS") or "1800")
        poll = float(os.getenv("AI_DRAMA_P16_MINIMAX_POLL_INTERVAL_SECONDS") or "3")
        if timeout <= 0 or poll <= 0:
            raise AppError("P16_PROVIDER_CONFIG_INVALID", "MiniMax H3 timeout/poll 配置无效", status_code=500)
        return cls(api_key=api_key, base_url=base_url, model=model, resolution=resolution, timeout_seconds=timeout, poll_interval_seconds=poll)


@dataclass(frozen=True)
class MiniMaxH3GenerationResult:
    remote_job_id: str
    remote_media_url: str
    requested_duration_seconds: int
    returned_ratio: str | None
    returned_resolution: str | None


class MiniMaxH3Provider:
    provider_name = "minimax"

    def __init__(self, config: MiniMaxH3Config):
        self.config = config
        self.model_name = config.model

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "base_url": self.config.base_url,
            "create_path": "/v2/video_generation",
            "query_path": "/v2/query/video_generation/{task_id}",
            "resolution": self.config.resolution,
            "api_contract": "minimax-h3-v2-2026-09",
        }

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
