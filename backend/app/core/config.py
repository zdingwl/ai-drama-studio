import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "ai_drama_studio.db"
DEFAULT_ARTIFACT_ROOT = BACKEND_ROOT / "artifacts"

# OpenAI's documented built-in /v1/audio/speech voices, verified 2026-09-12.
# The application still exposes only voice_key/display_name/locale/tags to the browser;
# provider_voice_id remains server-side. Override the catalog for a different compatible provider.
DEFAULT_P14_TTS_VOICE_CATALOG = (
    {"voice_key": "alloy", "display_name": "Alloy", "provider_voice_id": "alloy", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "ash", "display_name": "Ash", "provider_voice_id": "ash", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "ballad", "display_name": "Ballad", "provider_voice_id": "ballad", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "coral", "display_name": "Coral", "provider_voice_id": "coral", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "echo", "display_name": "Echo", "provider_voice_id": "echo", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "fable", "display_name": "Fable", "provider_voice_id": "fable", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "onyx", "display_name": "Onyx", "provider_voice_id": "onyx", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "nova", "display_name": "Nova", "provider_voice_id": "nova", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "sage", "display_name": "Sage", "provider_voice_id": "sage", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "shimmer", "display_name": "Shimmer", "provider_voice_id": "shimmer", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "verse", "display_name": "Verse", "provider_voice_id": "verse", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "marin", "display_name": "Marin", "provider_voice_id": "marin", "locale": None, "tags": ["openai", "built-in"]},
    {"voice_key": "cedar", "display_name": "Cedar", "provider_voice_id": "cedar", "locale": None, "tags": ["openai", "built-in"]},
)
DEFAULT_P14_TTS_VOICE_CATALOG_JSON = json.dumps(
    DEFAULT_P14_TTS_VOICE_CATALOG,
    ensure_ascii=False,
    separators=(",", ":"),
)


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_DRAMA_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Drama Studio V3"
    environment: str = "development"
    api_prefix: str = "/api/v3"
    database_url: str = _sqlite_url(DEFAULT_DATABASE_PATH)
    artifact_root: Path = Field(default=DEFAULT_ARTIFACT_ROOT)
    timezone: str = "UTC"
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    upload_chunk_bytes: int = 1024 * 1024
    max_text_source_bytes: int = 32 * 1024 * 1024
    max_video_source_bytes: int = 20 * 1024 * 1024 * 1024
    media_probe_timeout_seconds: int = 60
    media_decode_timeout_seconds: int = 120
    p6_asr_provider: str = "faster-whisper"
    p6_asr_model: str = "large-v3-turbo"
    p6_asr_device: str = "auto"
    p6_asr_compute_type: str = "default"
    p6_asr_download_root: Path | None = None
    p6_ocr_provider: str = "rapidocr"
    p6_ocr_sample_interval_ms: int = 500
    p6_ocr_min_confidence: float = 0.45

    # P7 model A: Volcengine Ark / Doubao Seed 2.1 Pro. The project stores only the model choice.
    # Credentials stay server-side and never enter Project/Artifact/ProviderJob payloads.
    p7_doubao_api_key: SecretStr | None = None
    p7_doubao_model: str = "doubao-seed-2-1-pro-260628"
    p7_doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    p7_doubao_request_timeout_seconds: float = 1800.0
    p7_doubao_video_fps: float = 1.0

    # P7 model B: Qwen3.8-27B on a user-operated local/shared vLLM service.
    p7_qwen38_local_base_url: str = "http://127.0.0.1:8000/v1"
    p7_qwen38_local_api_key: SecretStr | None = None
    p7_qwen38_local_model: str = "Qwen/Qwen3.8-27B"

    # P7 model C: Qwen3-VL-8B-Thinking on a second local/shared vLLM service.
    p7_qwen3_vl_8b_local_base_url: str = "http://127.0.0.1:8001/v1"
    p7_qwen3_vl_8b_local_api_key: SecretStr | None = None
    p7_qwen3_vl_8b_local_model: str = "Qwen/Qwen3-VL-8B-Thinking"
    p7_qwen_local_request_timeout_seconds: float = 3600.0

    # P14 Target Audio: OpenAI-compatible /audio/speech runtime. This is engineering-ready
    # configuration only; TTS/TIMING stay PLANNED until real provider and human acceptance pass.
    p14_tts_base_url: str = "http://127.0.0.1:8002/v1"
    p14_tts_api_key: SecretStr | None = None
    p14_tts_model: str = "tts-1"
    p14_tts_response_format: str = "wav"
    p14_tts_request_timeout_seconds: float = 300.0
    # Defaults to the official OpenAI built-in voice names. Override for another provider.
    p14_tts_voice_catalog_json: str = DEFAULT_P14_TTS_VOICE_CATALOG_JSON

    @model_validator(mode="after")
    def anchor_runtime_paths(self) -> "Settings":
        sqlite_prefix = "sqlite:///"
        if self.database_url.startswith(sqlite_prefix):
            database_path = self.database_url[len(sqlite_prefix) :]
            if database_path and database_path != ":memory:":
                path = Path(database_path)
                if not path.is_absolute():
                    self.database_url = _sqlite_url((BACKEND_ROOT / path).resolve())

        if not self.artifact_root.is_absolute():
            self.artifact_root = (BACKEND_ROOT / self.artifact_root).resolve()
        if self.p6_asr_download_root is not None and not self.p6_asr_download_root.is_absolute():
            self.p6_asr_download_root = (BACKEND_ROOT / self.p6_asr_download_root).resolve()
        if self.p6_ocr_sample_interval_ms < 100:
            raise ValueError("p6_ocr_sample_interval_ms must be >= 100")
        if not 0 <= self.p6_ocr_min_confidence <= 1:
            raise ValueError("p6_ocr_min_confidence must be between 0 and 1")
        if self.p7_doubao_request_timeout_seconds <= 0:
            raise ValueError("p7_doubao_request_timeout_seconds must be positive")
        if not 0.1 <= self.p7_doubao_video_fps <= 10:
            raise ValueError("p7_doubao_video_fps must be between 0.1 and 10")
        if self.p7_qwen_local_request_timeout_seconds <= 0:
            raise ValueError("p7_qwen_local_request_timeout_seconds must be positive")
        for name, value in (
            ("p7_qwen38_local_base_url", self.p7_qwen38_local_base_url),
            ("p7_qwen3_vl_8b_local_base_url", self.p7_qwen3_vl_8b_local_base_url),
            ("p14_tts_base_url", self.p14_tts_base_url),
        ):
            if not value.startswith(("http://", "https://")):
                raise ValueError(f"{name} must be http(s)")
        if not self.p7_qwen38_local_model.strip():
            raise ValueError("p7_qwen38_local_model must not be empty")
        if not self.p7_qwen3_vl_8b_local_model.strip():
            raise ValueError("p7_qwen3_vl_8b_local_model must not be empty")
        if not self.p14_tts_model.strip():
            raise ValueError("p14_tts_model must not be empty")
        if self.p14_tts_request_timeout_seconds <= 0:
            raise ValueError("p14_tts_request_timeout_seconds must be positive")
        if self.p14_tts_response_format not in {"wav", "mp3", "ogg", "flac", "aac"}:
            raise ValueError("p14_tts_response_format must be wav/mp3/ogg/flac/aac")
        return self

    def ensure_runtime_directories(self) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if self.p6_asr_download_root is not None:
            self.p6_asr_download_root.mkdir(parents=True, exist_ok=True)
        sqlite_prefix = "sqlite:///"
        if self.database_url.startswith(sqlite_prefix):
            database_path = self.database_url[len(sqlite_prefix) :]
            if database_path and database_path != ":memory:":
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
