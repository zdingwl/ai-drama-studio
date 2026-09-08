import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.config import get_settings
from app.sources.models import SourceAsset
from app.sources.storage import resolve_source_asset_path


def _project_payload(project_type: str) -> dict:
    payload = {
        "name": f"P3-{project_type}",
        "project_type": project_type,
        "target_language": "en-US",
        "target_region": "US",
    }
    if project_type in {"REPLICA", "REDRAW", "TRANSLATION"}:
        payload["source_language"] = "zh-CN"
    return payload


def _create_project(client: TestClient, project_type: str) -> dict:
    response = client.post("/api/v3/projects", json=_project_payload(project_type))
    assert response.status_code == 201, response.text
    return response.json()


def _make_video(path: Path, color: str) -> bytes:
    subprocess.run(
        [
            get_settings().ffmpeg_binary,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=160x90:d=0.3:r=10",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


@pytest.fixture()
def two_videos(tmp_path: Path) -> tuple[bytes, bytes]:
    return _make_video(tmp_path / "first.mp4", "red"), _make_video(tmp_path / "second.mp4", "blue")


def test_video_batch_upload_preserves_order_and_binds_source_artifact(
    client: TestClient,
    two_videos: tuple[bytes, bytes],
) -> None:
    project = _create_project(client, "REPLICA")
    first, second = two_videos
    response = client.post(
        f"/api/v3/projects/{project['id']}/sources/videos",
        files=[
            ("files", ("02.mp4", second, "video/mp4")),
            ("files", ("01.mp4", first, "video/mp4")),
        ],
    )
    assert response.status_code == 201, response.text
    rows = response.json()
    assert [row["source_asset"]["original_filename"] for row in rows] == ["02.mp4", "01.mp4"]
    assert [row["episode_order"] for row in rows] == [1, 2]
    assert all(row["duration_us"] > 0 for row in rows)
    assert all(row["width"] == 160 and row["height"] == 90 for row in rows)

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    source_video = [node for node in graph["nodes"] if node["artifact_type"] == "SOURCE_VIDEO" and node["is_current"]]
    assert len(source_video) == 1
    assert source_video[0]["metadata_json"]["episode_ids"] == [row["id"] for row in rows]

    assert client.get(f"/api/v3/projects/{project['id']}/plan").status_code == 404
    compiled = client.post(f"/api/v3/projects/{project['id']}/commands/compile-plan").json()
    assert compiled["steps"][0]["status"] == "COMPLETED"
    assert compiled["steps"][1]["status"] == "WAITING_CAPABILITY"


def test_video_upload_is_idempotent_and_raw_file_is_immutable(
    client: TestClient,
    session_factory: sessionmaker[Session],
    two_videos: tuple[bytes, bytes],
) -> None:
    project = _create_project(client, "REDRAW")
    first, _ = two_videos
    files = [("files", ("episode.mp4", first, "video/mp4"))]
    one = client.post(f"/api/v3/projects/{project['id']}/sources/videos", files=files)
    two = client.post(f"/api/v3/projects/{project['id']}/sources/videos", files=files)
    assert one.status_code == two.status_code == 201
    assert one.json()[0]["id"] == two.json()[0]["id"]

    with session_factory() as db:
        assets = list(db.scalars(select(SourceAsset).where(SourceAsset.project_id == project["id"])).all())
        assert len(assets) == 1
        assert assets[0].immutable is True
        stored = resolve_source_asset_path(assets[0].relative_path)
        assert stored.exists()
        assert stored.read_bytes() == first


def test_reorder_creates_new_source_video_revision_and_stales_previous(
    client: TestClient,
    two_videos: tuple[bytes, bytes],
) -> None:
    project = _create_project(client, "TRANSLATION")
    first, second = two_videos
    rows = client.post(
        f"/api/v3/projects/{project['id']}/sources/videos",
        files=[
            ("files", ("a.mp4", first, "video/mp4")),
            ("files", ("b.mp4", second, "video/mp4")),
        ],
    ).json()
    client.post(f"/api/v3/projects/{project['id']}/commands/compile-plan")

    response = client.post(
        f"/api/v3/projects/{project['id']}/sources/episodes/reorder",
        json={"episode_ids": [rows[1]["id"], rows[0]["id"]]},
    )
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [rows[1]["id"], rows[0]["id"]]
    assert client.get(f"/api/v3/projects/{project['id']}/plan").status_code == 404

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    versions = [node for node in graph["nodes"] if node["artifact_type"] == "SOURCE_VIDEO"]
    assert [node["revision"] for node in versions] == [1, 2]
    assert versions[0]["validity"] == ArtifactValidity.STALE.value
    assert versions[1]["validity"] == ArtifactValidity.CURRENT.value


def test_corrupt_video_and_path_traversal_are_rejected(client: TestClient) -> None:
    project = _create_project(client, "REPLICA")
    corrupt = client.post(
        f"/api/v3/projects/{project['id']}/sources/videos",
        files=[("files", ("bad.mp4", b"not a video", "video/mp4"))],
    )
    assert corrupt.status_code == 422
    assert corrupt.json()["error"]["code"] == "VIDEO_PROBE_FAILED"

    traversal = client.post(
        f"/api/v3/projects/{project['id']}/sources/videos",
        files=[("files", ("../escape.mp4", b"bad", "video/mp4"))],
    )
    assert traversal.status_code == 422
    assert traversal.json()["error"]["code"] == "SOURCE_PATH_TRAVERSAL"


def test_text_upload_revision_idempotency_and_encoding_validation(client: TestClient) -> None:
    project = _create_project(client, "SCRIPT_LOCALIZATION")
    first = client.post(
        f"/api/v3/projects/{project['id']}/sources/document",
        files={"file": ("script.md", "# 第一版\n你好".encode(), "text/markdown")},
    )
    assert first.status_code == 201, first.text
    assert first.json()["revision"] == 1
    assert first.json()["document_format"] == "MARKDOWN"

    duplicate = client.post(
        f"/api/v3/projects/{project['id']}/sources/document",
        files={"file": ("script.md", "# 第一版\n你好".encode(), "text/markdown")},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["revision"] == 1

    replacement = client.post(
        f"/api/v3/projects/{project['id']}/sources/document",
        files={"file": ("script.txt", "第二版剧本".encode(), "text/plain")},
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["revision"] == 2
    current = client.get(f"/api/v3/projects/{project['id']}/sources/document").json()
    assert current["id"] == replacement.json()["id"]

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    versions = [node for node in graph["nodes"] if node["artifact_type"] == "SOURCE_TEXT"]
    assert [node["revision"] for node in versions] == [1, 2]
    assert versions[0]["validity"] == "STALE"
    assert versions[1]["validity"] == "CURRENT"

    invalid_encoding = client.post(
        f"/api/v3/projects/{project['id']}/sources/document",
        files={"file": ("legacy.txt", b"\xff\xfe\xfd", "text/plain")},
    )
    assert invalid_encoding.status_code == 422
    assert invalid_encoding.json()["error"]["code"] == "TEXT_ENCODING_UNSUPPORTED"


def test_source_kind_must_match_project_type(client: TestClient, two_videos: tuple[bytes, bytes]) -> None:
    text_project = _create_project(client, "NOVEL_TO_DRAMA")
    first, _ = two_videos
    video_response = client.post(
        f"/api/v3/projects/{text_project['id']}/sources/videos",
        files=[("files", ("episode.mp4", first, "video/mp4"))],
    )
    assert video_response.status_code == 422
    assert video_response.json()["error"]["code"] == "VIDEO_SOURCE_NOT_ALLOWED"

    video_project = _create_project(client, "REPLICA")
    text_response = client.post(
        f"/api/v3/projects/{video_project['id']}/sources/document",
        files={"file": ("script.txt", b"hello", "text/plain")},
    )
    assert text_response.status_code == 422
    assert text_response.json()["error"]["code"] == "TEXT_SOURCE_NOT_ALLOWED"
