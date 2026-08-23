"""F01 创建项目固定语言/地区选项的 API 防御测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.app.main import create_app


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_code"),
    [
        ("source_language", "Chinese", "PROJECT_SOURCE_LANGUAGE_UNSUPPORTED"),
        ("target_language", "english", "PROJECT_TARGET_LANGUAGE_UNSUPPORTED"),
        ("target_region", "USA", "PROJECT_TARGET_REGION_UNSUPPORTED"),
    ],
)
def test_create_project_api_rejects_noncanonical_fixed_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    invalid_value: str,
    expected_code: str,
) -> None:
    """绕过前端直接请求 API 时，非标准固定值也不能写入项目。"""

    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    payload = {
        "name": "固定选项校验",
        "source_language": "zh",
        "target_language": "en",
        "target_region": "US",
        "workspace_root": str(tmp_path / "projects"),
    }
    payload[field] = invalid_value

    with TestClient(create_app()) as client:
        response = client.post("/api/projects", json=payload)
        projects = client.get("/api/projects").json()

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": expected_code,
            "message": {
                "PROJECT_SOURCE_LANGUAGE_UNSUPPORTED": "原片语言不是系统支持的标准语言",
                "PROJECT_TARGET_LANGUAGE_UNSUPPORTED": "目标语言不是系统支持的标准语言",
                "PROJECT_TARGET_REGION_UNSUPPORTED": "目标地区不是系统支持的标准地区",
            }[expected_code],
        }
    }
    assert projects == []


def test_create_project_api_accepts_canonical_fixed_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """前端下拉框提交的标准代码必须正常创建并原样保存。"""

    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/projects",
            json={
                "name": "日本本土化测试",
                "source_language": "zh",
                "target_language": "ja",
                "target_region": "JP",
                "workspace_root": str(tmp_path / "projects"),
            },
        )

    assert response.status_code == 201
    created = response.json()
    assert created["source_language"] == "zh"
    assert created["target_language"] == "ja"
    assert created["target_region"] == "JP"
