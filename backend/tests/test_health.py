from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_utc_service_status() -> None:
    response = client.get("/api/v3/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "AI Drama Studio V3"
    assert payload["timezone"] == "UTC"
    parsed = datetime.fromisoformat(payload["time"].replace("Z", "+00:00"))
    assert parsed.utcoffset().total_seconds() == 0


def test_http_errors_use_unified_envelope() -> None:
    response = client.get("/api/v3/not-found")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "HTTP_ERROR"
    assert payload["error"]["message"] == "Not Found"
