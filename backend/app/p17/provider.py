import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.errors import AppError


@dataclass(frozen=True)
class LipSyncConfig:
    base_url: str
    path: str
    model: str
    api_key: str | None
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "LipSyncConfig":
        base_url = (os.getenv("AI_DRAMA_P17_LIP_SYNC_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            raise AppError("P17_LIP_SYNC_NOT_CONFIGURED", "本地 Lip Sync Runtime 尚未配置", status_code=409)
        if not base_url.startswith(("http://", "https://")):
            raise AppError("P17_LIP_SYNC_CONFIG_INVALID", "Lip Sync base URL 必须是 http(s)", status_code=500)
        path = (os.getenv("AI_DRAMA_P17_LIP_SYNC_PATH") or "/v1/lip-sync").strip()
        if not path.startswith("/"):
            path = "/" + path
        model = (os.getenv("AI_DRAMA_P17_LIP_SYNC_MODEL") or "local-lip-sync-v1").strip()
        api_key = (os.getenv("AI_DRAMA_P17_LIP_SYNC_API_KEY") or "").strip() or None
        try:
            timeout = float(os.getenv("AI_DRAMA_P17_LIP_SYNC_TIMEOUT_SECONDS") or "900")
        except ValueError as exc:
            raise AppError("P17_LIP_SYNC_CONFIG_INVALID", "Lip Sync timeout 配置无效", status_code=500) from exc
        if timeout <= 0:
            raise AppError("P17_LIP_SYNC_CONFIG_INVALID", "Lip Sync timeout 必须大于 0", status_code=500)
        return cls(base_url=base_url, path=path, model=model, api_key=api_key, timeout_seconds=timeout)


@dataclass(frozen=True)
class LipSyncResult:
    remote_job_id: str | None
    output_bytes: bytes
    mime_type: str


class LocalHttpLipSyncProvider:
    provider_name = "local-http-lip-sync"

    def __init__(self, config: LipSyncConfig):
        self.config = config
        self.model_name = config.model

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "base_url": self.config.base_url,
            "path": self.config.path,
            "contract": "local-http-lip-sync-v1",
        }

    def run(self, *, video_path: Path, audio_path: Path, segment_id: str) -> LipSyncResult:
        headers: dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        with httpx.Client(timeout=httpx.Timeout(self.config.timeout_seconds)) as client:
            with video_path.open("rb") as video_handle, audio_path.open("rb") as audio_handle:
                response = client.post(
                    f"{self.config.base_url}{self.config.path}",
                    headers=headers,
                    data={"segment_id": segment_id, "model": self.model_name},
                    files={
                        "video": (video_path.name, video_handle, "video/mp4"),
                        "audio": (audio_path.name, audio_handle, "audio/wav"),
                    },
                )
            if response.status_code >= 400:
                raise AppError(
                    "P17_LIP_SYNC_FAILED",
                    f"Lip Sync Runtime 请求失败：HTTP {response.status_code}",
                    status_code=502,
                )
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            remote_job_id = response.headers.get("x-job-id") or None
            if content_type.startswith("video/"):
                payload = bytes(response.content)
                if not payload:
                    raise AppError("P17_LIP_SYNC_RESPONSE_EMPTY", "Lip Sync Runtime 返回空视频", status_code=502)
                return LipSyncResult(remote_job_id=remote_job_id, output_bytes=payload, mime_type=content_type)
            try:
                body = response.json()
            except Exception as exc:
                raise AppError("P17_LIP_SYNC_RESPONSE_INVALID", "Lip Sync Runtime 未返回视频或 JSON", status_code=502) from exc
            if not isinstance(body, dict):
                raise AppError("P17_LIP_SYNC_RESPONSE_INVALID", "Lip Sync Runtime JSON 结构无效", status_code=502)
            remote_job_id = str(body.get("job_id") or body.get("task_id") or remote_job_id or "").strip() or None
            remote_url = str(body.get("video_url") or body.get("url") or "").strip()
            if not remote_url.startswith(("http://", "https://")):
                raise AppError("P17_LIP_SYNC_MEDIA_MISSING", "Lip Sync Runtime JSON 缺少可下载视频 URL", status_code=502)
            download = client.get(remote_url, follow_redirects=True, timeout=httpx.Timeout(min(self.config.timeout_seconds, 300.0)))
            download.raise_for_status()
            payload = bytes(download.content)
            if not payload:
                raise AppError("P17_LIP_SYNC_RESPONSE_EMPTY", "Lip Sync Runtime 下载结果为空", status_code=502)
            if len(payload) > 512 * 1024 * 1024:
                raise AppError("P17_LIP_SYNC_MEDIA_TOO_LARGE", "Lip Sync Runtime 视频超过 512MB 安全上限", status_code=502)
            mime = download.headers.get("content-type", "video/mp4").split(";", 1)[0].strip() or "video/mp4"
            return LipSyncResult(remote_job_id=remote_job_id, output_bytes=payload, mime_type=mime)
