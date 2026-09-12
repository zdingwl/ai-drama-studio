import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "ai_drama_studio.db"
DEFAULT_ARTIFACT_ROOT = BACKEND_ROOT / "artifacts"

# IndexTTS-2.5 ships no text-only preset speakers. These are the official demo reference
# recordings used by the upstream IndexTTS repository. They are useful for local engineering
# validation only; formal production acceptance should replace them with authorized references.
_INDEXTTS_DEMO_BASE = "https://hf-mirror.com/spaces/IndexTeam/IndexTTS-2-Demo/resolve/main/examples"
_CREMAD_AUDIO_BASE = "https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/AudioWAV"
_CREMAD_SOURCE_URL = "https://github.com/CheyneyComputerScience/CREMA-D"
_CREMAD_LICENSE_URL = "https://raw.githubusercontent.com/CheyneyComputerScience/CREMA-D/master/LICENSE.txt"


def _cremad_neutral_references(actor_id: int) -> list[str]:
    return [
        f"{_CREMAD_AUDIO_BASE}/{actor_id}_{sentence}_NEU_XX.wav"
        for sentence in ("IEO", "IOM", "IWW", "ITH")
    ]


_INDEXTTS_DEMO_VOICES = tuple(
    {
        "voice_key": f"indextts-demo-{number:02d}",
        "display_name": f"IndexTTS 示例声线 {number:02d}",
        "reference_audio_url": f"{_INDEXTTS_DEMO_BASE}/voice_{number:02d}.wav",
        "locale": None,
        "tags": ["IndexTTS-2.5", "官方示例", "开发验收"],
        "source_name": "IndexTTS-2.5 官方 Demo",
        "source_url": "https://huggingface.co/spaces/IndexTeam/IndexTTS-2-Demo/tree/main/examples",
        "usage_notice": "上游未提供可作为产品事实使用的性别、年龄或风格标签；仅用于工程联调与试听。",
    }
    for number in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12)
)

_CREMAD_VOICE_DEMOGRAPHICS = (
    (1091, "FEMALE", "YOUNG_ADULT", 29),
    (1011, "MALE", "ADULT", 32),
    (1020, "FEMALE", "MATURE", 61),
    (1024, "FEMALE", "MATURE", 59),
)

_CREMAD_VOICES = tuple(
    {
        "voice_key": f"cremad-{actor_id}-neutral",
        "display_name": f"CREMA-D Actor {actor_id}",
        "reference_audio_urls": _cremad_neutral_references(actor_id),
        "locale": "en-US",
        "tags": ["IndexTTS-2.5", "CREMA-D", "英语", "授权数据集"],
        "catalog_gender": gender,
        "catalog_age_range": age_range,
        "catalog_style_tags": ["中性情绪", "英语"],
        "catalog_description": (
            f"CREMA-D 人口学记录：演员录制时 {age_years} 岁，"
            f"{'女性' if gender == 'FEMALE' else '男性'}；参考音频由同一演员 4 条英语 Neutral WAV 片段拼接。"
        ),
        "source_name": "CREMA-D (Crowd-sourced Emotional Multimodal Actors Dataset)",
        "source_url": _CREMAD_SOURCE_URL,
        "license_name": "ODbL 1.0 / DbCL 1.0",
        "license_url": _CREMAD_LICENSE_URL,
        "usage_notice": "数据集与内容许可可复核；真人声纹、人格权及具体商用场景仍需使用者另行确认。",
    }
    for actor_id, gender, age_range, age_years in _CREMAD_VOICE_DEMOGRAPHICS
)

DEFAULT_P14_INDEXTTS_VOICE_CATALOG = _INDEXTTS_DEMO_VOICES + _CREMAD_VOICES
DEFAULT_P14_INDEXTTS_VOICE_CATALOG_JSON = json.dumps(
    DEFAULT_P14_INDEXTTS_VOICE_CATALOG,
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

    # P14 has exactly one TTS implementation: IndexTTS-2.5 served locally by vLLM-Omni.
    p14_indextts_base_url: str = "http://127.0.0.1:8092/v1"
    p14_indextts_model: str = "IndexTeam/IndexTTS-2.5"
    p14_indextts_request_timeout_seconds: float = 600.0
    p14_indextts_default_speed: float = 1.0
    p14_indextts_default_emo_alpha: float = 0.6
    p14_indextts_voice_catalog_json: str = DEFAULT_P14_INDEXTTS_VOICE_CATALOG_JSON

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
            ("p14_indextts_base_url", self.p14_indextts_base_url),
        ):
            if not value.startswith(("http://", "https://")):
                raise ValueError(f"{name} must be http(s)")
        if not self.p7_qwen38_local_model.strip():
            raise ValueError("p7_qwen38_local_model must not be empty")
        if not self.p7_qwen3_vl_8b_local_model.strip():
            raise ValueError("p7_qwen3_vl_8b_local_model must not be empty")
        if self.p14_indextts_model != "IndexTeam/IndexTTS-2.5":
            raise ValueError("p14_indextts_model is fixed to IndexTeam/IndexTTS-2.5")
        if self.p14_indextts_request_timeout_seconds <= 0:
            raise ValueError("p14_indextts_request_timeout_seconds must be positive")
        if not 0.5 <= self.p14_indextts_default_speed <= 2.0:
            raise ValueError("p14_indextts_default_speed must be between 0.5 and 2.0")
        if not 0.0 <= self.p14_indextts_default_emo_alpha <= 1.0:
            raise ValueError("p14_indextts_default_emo_alpha must be between 0 and 1")
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
