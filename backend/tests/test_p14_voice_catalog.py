import base64

from fastapi.testclient import TestClient

import app.api.routes.p14_voices as voices_route
from app.core.config import DEFAULT_P14_INDEXTTS_VOICE_CATALOG_JSON
from app.p14.provider import IndexTTS25Provider, _load_voice_catalog


EXPECTED_INDEXTTS_DEMO_VOICES = {
    f"indextts-demo-{number:02d}"
    for number in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12)
}


def _create_project(client: TestClient, *, name: str = "P14 Voice Catalog") -> str:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": name,
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _ready(monkeypatch) -> None:
    monkeypatch.setattr(
        voices_route,
        "_runtime_readiness",
        lambda _provider: (True, "IndexTTS-2.5 READY"),
    )


def test_default_p14_voice_catalog_contains_indextts_demo_references() -> None:
    catalog = _load_voice_catalog(DEFAULT_P14_INDEXTTS_VOICE_CATALOG_JSON)
    assert {item.voice_key for item in catalog} == EXPECTED_INDEXTTS_DEMO_VOICES
    assert all(item.reference_audio_url.startswith(("http://", "https://")) for item in catalog)
    assert all(item.tags == ("IndexTTS-2.5", "官方示例", "开发验收") for item in catalog)


def test_p14_voice_catalog_api_exposes_preview_without_reference_source(
    client: TestClient,
    monkeypatch,
) -> None:
    _ready(monkeypatch)
    project_id = _create_project(client)

    response = client.get(f"/api/v3/projects/{project_id}/target-audio/voices")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["runtime_ready"] is True
    assert body["provider"] == "indextts-2.5-vllm-omni"
    assert body["target_language"] == "en-US"
    assert {item["voice_key"] for item in body["voices"]} == EXPECTED_INDEXTTS_DEMO_VOICES
    assert all("reference_audio_url" not in item for item in body["voices"])
    assert all(item["metadata_source"] == "CATALOG" for item in body["voices"])
    assert all(item["gender"] == "UNKNOWN" for item in body["voices"])
    assert all(item["age_range"] == "UNKNOWN" for item in body["voices"])
    assert all(
        item["preview_url"].startswith(f"/api/v3/projects/{project_id}/target-audio/voices/")
        and item["preview_url"].endswith("/preview")
        for item in body["voices"]
    )


def test_p14_voice_metadata_is_human_editable_and_shared_across_projects(
    client: TestClient,
    monkeypatch,
) -> None:
    _ready(monkeypatch)
    first_project_id = _create_project(client, name="Voice Metadata A")
    second_project_id = _create_project(client, name="Voice Metadata B")
    voice_key = "indextts-demo-01"

    update = client.put(
        f"/api/v3/projects/{first_project_id}/target-audio/voices/{voice_key}/metadata",
        json={
            "display_name": "清亮青年女声",
            "gender": "FEMALE",
            "age_range": "YOUNG_ADULT",
            "style_tags": ["清亮", "自然", "清亮"],
            "notes": "人工试听后标注，适合年轻女性角色。",
        },
    )
    assert update.status_code == 200, update.text
    updated = update.json()
    assert updated["display_name"] == "清亮青年女声"
    assert updated["default_display_name"] == "IndexTTS 示例声线 01"
    assert updated["gender"] == "FEMALE"
    assert updated["age_range"] == "YOUNG_ADULT"
    assert updated["style_tags"] == ["清亮", "自然"]
    assert updated["metadata_source"] == "USER"
    assert updated["metadata_updated_at"]

    response = client.get(f"/api/v3/projects/{second_project_id}/target-audio/voices")
    assert response.status_code == 200, response.text
    voice = next(item for item in response.json()["voices"] if item["voice_key"] == voice_key)
    assert voice["display_name"] == "清亮青年女声"
    assert voice["gender"] == "FEMALE"
    assert voice["style_tags"] == ["清亮", "自然"]
    assert voice["metadata_source"] == "USER"
    assert "reference_audio_url" not in voice

    reset = client.delete(f"/api/v3/projects/{second_project_id}/target-audio/voices/{voice_key}/metadata")
    assert reset.status_code == 200, reset.text
    assert reset.json()["metadata_source"] == "CATALOG"

    after_reset = client.get(f"/api/v3/projects/{first_project_id}/target-audio/voices")
    assert after_reset.status_code == 200, after_reset.text
    voice = next(item for item in after_reset.json()["voices"] if item["voice_key"] == voice_key)
    assert voice["display_name"] == "IndexTTS 示例声线 01"
    assert voice["metadata_source"] == "CATALOG"
    assert voice["gender"] == "UNKNOWN"


def test_p14_voice_metadata_rejects_invalid_human_labels(client: TestClient) -> None:
    project_id = _create_project(client)
    response = client.put(
        f"/api/v3/projects/{project_id}/target-audio/voices/indextts-demo-01/metadata",
        json={
            "display_name": "测试声线",
            "gender": "GUESSED",
            "age_range": "UNKNOWN",
            "style_tags": [],
        },
    )
    assert response.status_code == 422, response.text


def test_p14_voice_preview_proxies_reference_bytes_without_provider_job(
    client: TestClient,
    monkeypatch,
) -> None:
    project_id = _create_project(client)
    voice_key = "indextts-demo-01"
    fake_audio = b"RIFFfake-wave"
    data_url = f"data:audio/wav;base64,{base64.b64encode(fake_audio).decode('ascii')}"
    monkeypatch.setattr(
        IndexTTS25Provider,
        "_reference_data_url",
        lambda self, selected_voice_key: (data_url, "fake-sha"),
    )

    response = client.get(f"/api/v3/projects/{project_id}/target-audio/voices/{voice_key}/preview")
    assert response.status_code == 200, response.text
    assert response.content == fake_audio
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["cache-control"] == "private, max-age=3600"
