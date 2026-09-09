import os
import tempfile
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field, field_validator

from app.core.config import BACKEND_ROOT, Settings, get_settings


P7_RUNTIME_ENV_PATH = BACKEND_ROOT / ".env"
_ENV_LOCK = Lock()


class DoubaoRuntimeConfig(BaseModel):
    api_key: str = ""
    model: str
    base_url: str
    request_timeout_seconds: float = Field(gt=0)
    video_fps: float = Field(ge=0.1, le=10)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model must not be empty")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must be http(s)")
        return value


class LocalQwenRuntimeConfig(BaseModel):
    api_key: str = ""
    model: str
    base_url: str

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model must not be empty")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must be http(s)")
        return value


class P7RuntimeConfig(BaseModel):
    doubao: DoubaoRuntimeConfig
    qwen38: LocalQwenRuntimeConfig
    qwen3_vl_8b: LocalQwenRuntimeConfig
    qwen_request_timeout_seconds: float = Field(gt=0)


_ENV_FIELDS = {
    "AI_DRAMA_P7_DOUBAO_API_KEY",
    "AI_DRAMA_P7_DOUBAO_MODEL",
    "AI_DRAMA_P7_DOUBAO_BASE_URL",
    "AI_DRAMA_P7_DOUBAO_REQUEST_TIMEOUT_SECONDS",
    "AI_DRAMA_P7_DOUBAO_VIDEO_FPS",
    "AI_DRAMA_P7_QWEN38_LOCAL_BASE_URL",
    "AI_DRAMA_P7_QWEN38_LOCAL_API_KEY",
    "AI_DRAMA_P7_QWEN38_LOCAL_MODEL",
    "AI_DRAMA_P7_QWEN3_VL_8B_LOCAL_BASE_URL",
    "AI_DRAMA_P7_QWEN3_VL_8B_LOCAL_API_KEY",
    "AI_DRAMA_P7_QWEN3_VL_8B_LOCAL_MODEL",
    "AI_DRAMA_P7_QWEN_LOCAL_REQUEST_TIMEOUT_SECONDS",
}


def _secret_value(value) -> str:
    return value.get_secret_value() if value is not None else ""


def get_p7_runtime_config() -> P7RuntimeConfig:
    # Read from the same runtime file that this module updates.  Besides making
    # the read/write contract explicit, this keeps an isolated runtime-config
    # file from accidentally falling back to the workstation's real .env.
    settings = Settings(_env_file=P7_RUNTIME_ENV_PATH)
    return P7RuntimeConfig(
        doubao=DoubaoRuntimeConfig(
            api_key=_secret_value(settings.p7_doubao_api_key),
            model=settings.p7_doubao_model,
            base_url=settings.p7_doubao_base_url,
            request_timeout_seconds=settings.p7_doubao_request_timeout_seconds,
            video_fps=settings.p7_doubao_video_fps,
        ),
        qwen38=LocalQwenRuntimeConfig(
            api_key=_secret_value(settings.p7_qwen38_local_api_key),
            model=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
        ),
        qwen3_vl_8b=LocalQwenRuntimeConfig(
            api_key=_secret_value(settings.p7_qwen3_vl_8b_local_api_key),
            model=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
        ),
        qwen_request_timeout_seconds=settings.p7_qwen_local_request_timeout_seconds,
    )


def _dotenv_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _payload_to_env(payload: P7RuntimeConfig) -> dict[str, str | None]:
    return {
        "AI_DRAMA_P7_DOUBAO_API_KEY": payload.doubao.api_key.strip() or None,
        "AI_DRAMA_P7_DOUBAO_MODEL": payload.doubao.model,
        "AI_DRAMA_P7_DOUBAO_BASE_URL": payload.doubao.base_url,
        "AI_DRAMA_P7_DOUBAO_REQUEST_TIMEOUT_SECONDS": str(payload.doubao.request_timeout_seconds),
        "AI_DRAMA_P7_DOUBAO_VIDEO_FPS": str(payload.doubao.video_fps),
        "AI_DRAMA_P7_QWEN38_LOCAL_BASE_URL": payload.qwen38.base_url,
        "AI_DRAMA_P7_QWEN38_LOCAL_API_KEY": payload.qwen38.api_key.strip() or None,
        "AI_DRAMA_P7_QWEN38_LOCAL_MODEL": payload.qwen38.model,
        "AI_DRAMA_P7_QWEN3_VL_8B_LOCAL_BASE_URL": payload.qwen3_vl_8b.base_url,
        "AI_DRAMA_P7_QWEN3_VL_8B_LOCAL_API_KEY": payload.qwen3_vl_8b.api_key.strip() or None,
        "AI_DRAMA_P7_QWEN3_VL_8B_LOCAL_MODEL": payload.qwen3_vl_8b.model,
        "AI_DRAMA_P7_QWEN_LOCAL_REQUEST_TIMEOUT_SECONDS": str(payload.qwen_request_timeout_seconds),
    }


def _write_env_file(path: Path, updates: dict[str, str | None]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output: list[str] = []
    written: set[str] = set()

    for line in existing:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key not in updates:
            output.append(line)
            continue
        if key in written:
            continue
        written.add(key)
        value = updates[key]
        if value is not None:
            output.append(f"{key}={_dotenv_value(value)}")

    missing = [key for key in updates if key not in written and updates[key] is not None]
    if missing:
        if output and output[-1] != "":
            output.append("")
        output.append("# P7 runtime provider settings managed by the local UI.")
        for key in missing:
            value = updates[key]
            assert value is not None
            output.append(f"{key}={_dotenv_value(value)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".env.p7.", dir=path.parent, text=True)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(output).rstrip() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temp_path.chmod(0o600)
        except OSError:
            pass
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def update_p7_runtime_config(payload: P7RuntimeConfig) -> P7RuntimeConfig:
    updates = _payload_to_env(payload)
    with _ENV_LOCK:
        _write_env_file(P7_RUNTIME_ENV_PATH, updates)
        # The application is a local workstation service. Mirror the saved values into this
        # process so the next explicitly-created P7 Task uses the new settings immediately.
        for key in _ENV_FIELDS:
            value = updates.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        return get_p7_runtime_config()
