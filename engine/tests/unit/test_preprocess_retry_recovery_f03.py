"""F03 用户重试预处理时的 processing 残留恢复回归测试。"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.app.core.database import init_database
from engine.app.preprocess import PreprocessAssetMetadata, PreprocessError, preprocess_source_video


def _create_processing_project(tmp_path: Path) -> tuple[Path, Path, str]:
    """构造一份超过 30 秒的旧 processing 记录，用来模拟用户截图中的残留状态。"""

    app_data = tmp_path / "app-data"
    database_path = init_database(app_data)
    project_id = "PROJECT_retry_f03"
    source_id = "SOURCE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    workspace = tmp_path / "projects" / project_id
    source_file = workspace / "source" / source_id / "original.mp4"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"retry-source" * 1000)
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    (workspace / "project.json").write_text(
        json.dumps({"project_id": project_id, "project_format_version": 1}),
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=5)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?, NULL)
            """,
            (project_id, "Retry", "zh", "en", "US", str(workspace), 1, now.isoformat()),
        )
        connection.execute(
            """
            INSERT INTO source_videos (
                id, project_id, original_filename, relative_path, file_size_bytes, sha256,
                status, container_format, duration_us, source_start_time_us,
                video_stream_index, video_codec, width, height, fps_num, fps_den,
                audio_stream_index, audio_codec, audio_sample_rate, audio_channels, created_at
            ) VALUES (?, ?, 'retry.mp4', ?, ?, ?, 'ready', 'mov,mp4', 10000000, 0,
                0, 'h264', 1280, 720, 25, 1, 1, 'aac', 48000, 2, ?)
            """,
            (
                source_id,
                project_id,
                f"source/{source_id}/original.mp4",
                source_file.stat().st_size,
                source_hash,
                now.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO source_preprocess (
                source_video_id, project_id, status, profile_version, source_sha256_snapshot,
                proxy_relative_path, audio_relative_path, thumbnail_relative_path, created_at
            ) VALUES (?, ?, 'processing', 1, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                project_id,
                source_hash,
                f"preprocess/{source_id}/proxy.mp4",
                f"preprocess/{source_id}/audio.wav",
                f"preprocess/{source_id}/thumbnail.jpg",
                old.isoformat(),
            ),
        )
        connection.commit()

    return app_data, workspace, source_id


def _fake_ready_metadata() -> PreprocessAssetMetadata:
    return PreprocessAssetMetadata(
        proxy_file_size_bytes=5,
        proxy_sha256="a" * 64,
        proxy_duration_us=10_000_000,
        proxy_video_time_base_num=1,
        proxy_video_time_base_den=90_000,
        proxy_fps_num=25,
        proxy_fps_den=1,
        proxy_to_source_offset_us=0,
        audio_file_size_bytes=5,
        audio_sha256="b" * 64,
        audio_duration_us=10_000_000,
        audio_sample_rate=16_000,
        audio_channels=1,
        audio_to_source_offset_us=0,
        thumbnail_file_size_bytes=5,
        thumbnail_sha256="c" * 64,
        thumbnail_source_time_us=1_000_000,
        source_video_time_base_num=1,
        source_video_time_base_den=90_000,
    )


def _mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_proxy(**kwargs) -> None:
        kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target_path"].write_bytes(b"proxy")

    def write_audio(**kwargs) -> None:
        kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target_path"].write_bytes(b"audio")

    def write_thumbnail(**kwargs) -> None:
        kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target_path"].write_bytes(b"thumb")

    monkeypatch.setattr("engine.app.preprocess.generate_proxy_video", write_proxy)
    monkeypatch.setattr("engine.app.preprocess.extract_analysis_audio", write_audio)
    monkeypatch.setattr("engine.app.preprocess.generate_thumbnail", write_thumbnail)
    monkeypatch.setattr("engine.app.preprocess._probe_proxy_duration_us", lambda _: 10_000_000)
    monkeypatch.setattr("engine.app.preprocess.inspect_preprocess_assets", lambda **_: _fake_ready_metadata())


def test_stale_processing_without_files_is_removed_and_retry_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """旧 DB processing 没有任何文件时，用户再次点击应自动清理并重新处理。"""

    app_data, workspace, source_id = _create_processing_project(tmp_path)
    _mock_pipeline(monkeypatch)

    record = preprocess_source_video(project_id="PROJECT_retry_f03", app_data_path=app_data)

    assert record.status == "ready"
    assert record.source_video_id == source_id
    assert (workspace / "preprocess" / source_id / "proxy.mp4").is_file()
    with sqlite3.connect(app_data / "app.db") as connection:
        assert connection.execute(
            "SELECT status FROM source_preprocess WHERE source_video_id=?", (source_id,)
        ).fetchone() == ("ready",)


def test_recent_staging_is_treated_as_active_and_not_deleted(tmp_path: Path) -> None:
    """最近仍有写入的 staging 可能对应正在运行的 FFmpeg，重试不能误删。"""

    app_data, workspace, source_id = _create_processing_project(tmp_path)
    staging = workspace / "preprocess" / ".staging" / source_id
    staging.mkdir(parents=True)
    proxy = staging / "proxy.mp4"
    proxy.write_bytes(b"still-writing")
    os.utime(proxy, None)

    with pytest.raises(PreprocessError) as exc:
        preprocess_source_video(project_id="PROJECT_retry_f03", app_data_path=app_data)

    assert exc.value.code == "PREPROCESS_IN_PROGRESS"
    assert proxy.is_file()


def test_unknown_staging_file_is_preserved_and_requires_manual_check(tmp_path: Path) -> None:
    """出现用户/未知文件时宁可阻止重试，也不能递归删除现场。"""

    app_data, workspace, source_id = _create_processing_project(tmp_path)
    staging = workspace / "preprocess" / ".staging" / source_id
    staging.mkdir(parents=True)
    (staging / "proxy.mp4").write_bytes(b"partial")
    note = staging / "user-note.txt"
    note.write_text("do not delete", encoding="utf-8")

    with pytest.raises(PreprocessError) as exc:
        preprocess_source_video(project_id="PROJECT_retry_f03", app_data_path=app_data)

    assert exc.value.code == "PREPROCESS_RECOVERY_REQUIRED"
    assert note.is_file()
