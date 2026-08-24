"""F02 Source Video HTTP Controller 测试。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from engine.app.core.database import init_database
from engine.app.source_videos import SourceVideoError, SourceVideoMetadata


def _metadata() -> SourceVideoMetadata:
    return SourceVideoMetadata(
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        duration_us=5_000_000,
        source_start_time_us=0,
        video_stream_index=0,
        video_codec="h264",
        width=1280,
        height=720,
        fps_num=25,
        fps_den=1,
        audio_stream_index=1,
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_channels=2,
    )


def _insert_project(app_data: Path, workspace_root: Path, project_id: str) -> None:
    database_path = init_database(app_data)
    workspace = workspace_root / project_id
    workspace.mkdir(parents=True)
    (workspace / "project.json").write_text(
        json.dumps({"project_id": project_id, "project_format_version": 1}),
        encoding="utf-8",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, "API 测试", "zh", "en", "US", str(workspace),
                1, "ready", datetime.now(timezone.utc).isoformat(), None,
            ),
        )
        connection.commit()


def test_source_video_api_roundtrip(monkeypatch, tmp_path: Path) -> None:
    """GET null → POST 201 → GET ready → 第二次 POST 409。"""
    app_data = tmp_path / "app-data"
    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(app_data))
    _insert_project(app_data, tmp_path / "projects", "PROJECT_api")
    monkeypatch.setattr("engine.app.source_videos.probe_source_video", lambda _: _metadata())

    from engine.app.main import create_app

    with TestClient(create_app()) as client:
        empty = client.get("/api/projects/PROJECT_api/source-video")
        assert empty.status_code == 200
        assert empty.json() is None

        created = client.post(
            "/api/projects/PROJECT_api/source-video",
            files={"file": ("第一集.mp4", b"video-bytes" * 1000, "video/mp4")},
        )
        assert created.status_code == 201
        assert created.json()["status"] == "ready"
        assert created.json()["original_filename"] == "第一集.mp4"

        loaded = client.get("/api/projects/PROJECT_api/source-video")
        assert loaded.status_code == 200
        assert loaded.json()["id"] == created.json()["id"]

        duplicate = client.post(
            "/api/projects/PROJECT_api/source-video",
            files={"file": ("第二集.mp4", b"another-video", "video/mp4")},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "SOURCE_VIDEO_ALREADY_EXISTS"


def test_source_video_api_probe_error_uses_standard_envelope(monkeypatch, tmp_path: Path) -> None:
    """媒体校验失败必须返回稳定 Source error envelope，不能留下 ready 原片。"""
    app_data = tmp_path / "app-data"
    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(app_data))
    _insert_project(app_data, tmp_path / "projects", "PROJECT_bad")

    def fail_probe(_: Path) -> SourceVideoMetadata:
        raise SourceVideoError("SOURCE_VIDEO_PROBE_FAILED", "FFprobe 无法读取该视频文件")

    monkeypatch.setattr("engine.app.source_videos.probe_source_video", fail_probe)
    from engine.app.main import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/projects/PROJECT_bad/source-video",
            files={"file": ("bad.mp4", b"not-video", "video/mp4")},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SOURCE_VIDEO_PROBE_FAILED"
        assert client.get("/api/projects/PROJECT_bad/source-video").json() is None
