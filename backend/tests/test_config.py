from datetime import datetime

import pytest

from app.core.config import Settings
from app.core.time import ensure_utc


def test_settings_create_runtime_directories(tmp_path) -> None:
    artifact_root = tmp_path / "artifacts"
    database_path = tmp_path / "data" / "app.db"
    settings = Settings(
        artifact_root=artifact_root,
        database_url=f"sqlite:///{database_path}",
    )

    settings.ensure_runtime_directories()

    assert artifact_root.is_dir()
    assert database_path.parent.is_dir()


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2026, 9, 8, 12, 0, 0))
