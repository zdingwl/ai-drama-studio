from fastapi.testclient import TestClient

from app.core.config import DEFAULT_P14_TTS_VOICE_CATALOG_JSON
from app.p14.provider import _load_voice_catalog


EXPECTED_OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
}


def test_default_p14_voice_catalog_contains_documented_openai_builtin_voices() -> None:
    catalog = _load_voice_catalog(DEFAULT_P14_TTS_VOICE_CATALOG_JSON)
    assert {item.voice_key for item in catalog} == EXPECTED_OPENAI_VOICES
    assert {item.provider_voice_id for item in catalog} == EXPECTED_OPENAI_VOICES
    assert all(item.tags == ("openai", "built-in") for item in catalog)


def test_p14_voice_catalog_api_is_read_only_public_shape(client: TestClient) -> None:
    project = client.post(
        "/api/v3/projects",
        json={
            "name": "P14 Voice Catalog",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    response = client.get(f"/api/v3/projects/{project_id}/target-audio/voices")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["provider"] == "openai-compatible-tts"
    assert body["target_language"] == "en-US"
    assert {item["voice_key"] for item in body["voices"]} == EXPECTED_OPENAI_VOICES
    assert all("provider_voice_id" not in item for item in body["voices"])
