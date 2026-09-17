import pytest

from app.api.routes.source_analysis import _require_episode_id
from app.core.errors import AppError


def test_source_analysis_requires_episode_id() -> None:
    for value in (None, "", "   "):
        with pytest.raises(AppError) as exc_info:
            _require_episode_id(value)

        assert exc_info.value.code == "EPISODE_REQUIRED"
        assert exc_info.value.status_code == 422


def test_source_analysis_preserves_valid_episode_id() -> None:
    assert _require_episode_id("episode-001") == "episode-001"
