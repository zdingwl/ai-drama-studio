from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.app import target_dialogue_routes_v1
from engine.app.target_localization_routes_v1 import router as target_router


def _empty_bundle(project_id: str = "PROJECT_1") -> dict:
    return {
        "schema_version": "target-dialogue-v1",
        "project_id": project_id,
        "source_fingerprint": "a" * 64,
        "target_language": "en-US",
        "target_region": "US",
        "status": "READY",
        "voice_profile_count": 0,
        "dialogue_count": 0,
        "review_count": 0,
        "audio_ready_count": 0,
        "voice_profiles": [],
        "dialogues": [],
    }


def test_target_dialogue_router_is_mounted_under_api(monkeypatch) -> None:
    monkeypatch.setattr(
        target_dialogue_routes_v1,
        "run_target_dialogue_pipeline_v1",
        lambda project_id, synthesize_audio=True: _empty_bundle(project_id),
    )
    app = FastAPI()
    app.include_router(target_router)
    client = TestClient(app)

    response = client.post(
        "/api/projects/PROJECT_1/target-dialogue/generate",
        json={"synthesize_audio": True},
    )

    assert response.status_code == 200
    assert response.json()["schema_version"] == "target-dialogue-v1"
    assert response.json()["project_id"] == "PROJECT_1"


def test_tts_runtime_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        target_dialogue_routes_v1,
        "runtime_status",
        lambda: {
            "ready": False,
            "reachable": False,
            "base_url": "http://127.0.0.1:7861",
            "runtime_profile": "QWEN3_TTS_VOICE_DESIGN_CLONE_V1",
            "supported_language_prefixes": ["en", "zh"],
        },
    )
    app = FastAPI()
    app.include_router(target_router)
    client = TestClient(app)

    response = client.get("/api/tts/runtime-status")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["runtime_profile"] == "QWEN3_TTS_VOICE_DESIGN_CLONE_V1"
