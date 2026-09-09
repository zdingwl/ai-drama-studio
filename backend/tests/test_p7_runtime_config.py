from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact
from app.core.config import get_settings
from app.skills.models import ArtifactType
from app.understanding import runtime_config


P7_ENV_KEYS = [
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
]


def _isolate_p7_env(monkeypatch, env_path: Path) -> None:
    for key in P7_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(runtime_config, "P7_RUNTIME_ENV_PATH", env_path)
    get_settings.cache_clear()


def _project_payload() -> dict:
    return {
        "name": "P7 runtime config",
        "project_type": "REPLICA",
        "source_language": "zh-CN",
        "target_language": "en-US",
        "target_region": "US",
        "visual_style": "SOURCE_LIKE",
    }


def test_runtime_config_get_and_put_round_trip_plaintext(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("AI_DRAMA_ENVIRONMENT=development\nCUSTOM_KEEP=1\n", encoding="utf-8")
    _isolate_p7_env(monkeypatch, env_path)

    initial = client.get("/api/v3/source-understanding/runtime-config")
    assert initial.status_code == 200
    assert initial.json()["doubao"]["api_key"] == ""

    payload = initial.json()
    payload["doubao"].update(
        {
            "api_key": "ark-plaintext-local-key",
            "model": "ep-seed-2.1-pro-test",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3/",
            "request_timeout_seconds": 1234,
            "video_fps": 1.5,
        }
    )
    payload["qwen38"].update(
        {
            "api_key": "local-qwen-key",
            "model": "Qwen/Qwen3.8-27B-FP8",
            "base_url": "http://127.0.0.1:9000/v1/",
        }
    )

    saved = client.put("/api/v3/source-understanding/runtime-config", json=payload)
    assert saved.status_code == 200
    body = saved.json()
    assert body["doubao"]["api_key"] == "ark-plaintext-local-key"
    assert body["doubao"]["model"] == "ep-seed-2.1-pro-test"
    assert body["doubao"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
    assert body["qwen38"]["api_key"] == "local-qwen-key"
    assert body["qwen38"]["base_url"] == "http://127.0.0.1:9000/v1"

    text = env_path.read_text(encoding="utf-8")
    assert "CUSTOM_KEEP=1" in text
    assert 'AI_DRAMA_P7_DOUBAO_API_KEY="ark-plaintext-local-key"' in text
    assert 'AI_DRAMA_P7_DOUBAO_MODEL="ep-seed-2.1-pro-test"' in text
    assert 'AI_DRAMA_P7_QWEN38_LOCAL_API_KEY="local-qwen-key"' in text

    loaded_again = client.get("/api/v3/source-understanding/runtime-config")
    assert loaded_again.status_code == 200
    assert loaded_again.json()["doubao"]["api_key"] == "ark-plaintext-local-key"


def test_runtime_config_empty_api_key_removes_secret_from_env_file(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    _isolate_p7_env(monkeypatch, env_path)

    payload = client.get("/api/v3/source-understanding/runtime-config").json()
    payload["doubao"]["api_key"] = "first-key"
    assert client.put("/api/v3/source-understanding/runtime-config", json=payload).status_code == 200
    assert "first-key" in env_path.read_text(encoding="utf-8")

    payload["doubao"]["api_key"] = ""
    cleared = client.put("/api/v3/source-understanding/runtime-config", json=payload)
    assert cleared.status_code == 200
    assert cleared.json()["doubao"]["api_key"] == ""
    assert "AI_DRAMA_P7_DOUBAO_API_KEY" not in env_path.read_text(encoding="utf-8")


def test_runtime_model_profile_change_stales_matching_source_bible_but_key_change_does_not(
    client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    _isolate_p7_env(monkeypatch, env_path)

    created = client.post("/api/v3/projects", json=_project_payload())
    assert created.status_code == 201
    project_id = created.json()["id"]

    with session_factory() as db:
        first = create_artifact(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_BIBLE,
            namespace=ArtifactNamespace.SOURCE,
            label="源作概览分析",
            input_fingerprint="a" * 64,
            skill_id="project.replica",
            skill_version="1.0.0",
        )
        first_id = first.id

    payload = client.get("/api/v3/source-understanding/runtime-config").json()
    payload["doubao"]["model"] = "changed-seed-model"
    changed = client.put("/api/v3/source-understanding/runtime-config", json=payload)
    assert changed.status_code == 200

    with session_factory() as db:
        first = db.get(ArtifactNode, first_id)
        assert first is not None
        assert first.validity == ArtifactValidity.STALE
        assert first.is_current is False
        second = create_artifact(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_BIBLE,
            namespace=ArtifactNamespace.SOURCE,
            label="源作概览分析",
            input_fingerprint="b" * 64,
            skill_id="project.replica",
            skill_version="1.0.0",
        )
        second_id = second.id

    payload = changed.json()
    payload["doubao"]["api_key"] = "replacement-key-only"
    key_only = client.put("/api/v3/source-understanding/runtime-config", json=payload)
    assert key_only.status_code == 200

    with session_factory() as db:
        second = db.get(ArtifactNode, second_id)
        assert second is not None
        assert second.validity == ArtifactValidity.CURRENT
        assert second.is_current is True
