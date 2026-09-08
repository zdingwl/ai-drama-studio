from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "ai_drama_studio.db"
DEFAULT_ARTIFACT_ROOT = BACKEND_ROOT / "artifacts"


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
        return self

    def ensure_runtime_directories(self) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        sqlite_prefix = "sqlite:///"
        if self.database_url.startswith(sqlite_prefix):
            database_path = self.database_url[len(sqlite_prefix) :]
            if database_path and database_path != ":memory:":
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
