"""F01 应用数据路径函数测试。"""

from pathlib import Path

import pytest

from engine.app.core.paths import get_app_data_path


def test_get_app_data_path_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """测试专用覆盖路径必须优先于 Windows LOCALAPPDATA。"""

    override = tmp_path / "test-app-data"
    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(override))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "should-not-be-used"))

    result = get_app_data_path()

    assert result == override.resolve()
    assert not result.exists(), "路径解析函数不应该偷偷创建目录"


def test_get_app_data_path_uses_windows_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """没有测试覆盖值时，正式规则应落到 LOCALAPPDATA/AI Drama Studio。"""

    monkeypatch.delenv("AI_DRAMA_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    result = get_app_data_path()

    assert result == (tmp_path / "AI Drama Studio").resolve()
    assert not result.exists(), "该函数只解析路径，不负责 mkdir"


def test_get_app_data_path_ignores_blank_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """空白覆盖值不应把应用数据目录解析成当前目录。"""

    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", "   ")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert get_app_data_path() == (tmp_path / "AI Drama Studio").resolve()


def test_get_app_data_path_fails_when_no_location_can_be_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无法确定正式路径时必须明确失败，不能静默写到不确定位置。"""

    monkeypatch.delenv("AI_DRAMA_APP_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(RuntimeError, match="无法确定 AI Drama Studio 应用数据目录"):
        get_app_data_path()
