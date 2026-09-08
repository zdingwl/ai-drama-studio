from datetime import datetime
from pathlib import Path

import pytest

from app.core.config import BACKEND_ROOT, Settings
from app.core.time import ensure_utc


def test_settings_create_runtime_directories(tmp_path) -> None:
    artifact_root = tmp_path / "artifacts"
    database_path = tmp_path / "data" / "app.db"
    settings = Settings(
        _env_file=None,
        artifact_root=artifact_root,
        database_url=f"sqlite:///{database_path.as_posix()}",
    )

    settings.ensure_runtime_directories()

    assert artifact_root.is_dir()
    assert database_path.parent.is_dir()


def test_relative_runtime_paths_are_anchored_to_backend() -> None:
    settings = Settings(
        _env_file=None,
        artifact_root=Path("./custom-artifacts"),
        database_url="sqlite:///./custom-data/app.db",
    )

    assert settings.artifact_root == (BACKEND_ROOT / "custom-artifacts").resolve()
    assert settings.database_url == f"sqlite:///{(BACKEND_ROOT / 'custom-data' / 'app.db').resolve().as_posix()}"


def test_default_runtime_paths_do_not_depend_on_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AI_DRAMA_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("AI_DRAMA_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)

    assert settings.artifact_root == (BACKEND_ROOT / "artifacts").resolve()
    assert settings.database_url == f"sqlite:///{(BACKEND_ROOT / 'data' / 'ai_drama_studio.db').resolve().as_posix()}"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2026, 9, 8, 12, 0, 0))
