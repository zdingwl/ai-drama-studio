"""F03 验收前补漏：Source 处理中变化与媒体流时长语义回归。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.app.core.database import init_database
from engine.app.preprocess import (
    PreprocessAssetMetadata,
    PreprocessError,
    _duration_us,
    preprocess_source_video,
)


def _create_ready_source_without_audio(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """构造最小 F01/F02 ready 项目，专门测试 F03 Source 完整性边界。"""

    app_data = tmp_path / "app-data"
    database_path = init_database(app_data)
    project_id = "PROJECT_f03_integrity"
    source_id = "SOURCE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    workspace = tmp_path / "projects" / project_id
    source_file = workspace / "source" / source_id / "original.mp4"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"stable-source" * 1000)
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    (workspace / "project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "project_format_version": 1,
                "name": "F03 完整性测试",
                "source_language": "zh",
                "target_language": "en",
                "target_region": "US",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, "F03 完整性测试", "zh", "en", "US", str(workspace), 1, "ready", now, None),
        )
        connection.execute(
            """
            INSERT INTO source_videos (
                id, project_id, original_filename, relative_path, file_size_bytes, sha256,
                status, container_format, duration_us, source_start_time_us,
                video_stream_index, video_codec, width, height, fps_num, fps_den,
                audio_stream_index, audio_codec, audio_sample_rate, audio_channels, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                project_id,
                "original.mp4",
                f"source/{source_id}/original.mp4",
                source_file.stat().st_size,
                source_hash,
                "ready",
                "mov,mp4",
                10_000_000,
                0,
                0,
                "h264",
                1280,
                720,
                25,
                1,
                None,
                None,
                None,
                None,
                now,
            ),
        )
        connection.commit()

    return app_data, workspace, source_file, source_id


def _ready_metadata() -> PreprocessAssetMetadata:
    return PreprocessAssetMetadata(
        proxy_file_size_bytes=100,
        proxy_sha256="a" * 64,
        proxy_duration_us=10_000_000,
        proxy_video_time_base_num=1,
        proxy_video_time_base_den=90_000,
        proxy_fps_num=25,
        proxy_fps_den=1,
        proxy_to_source_offset_us=0,
        audio_file_size_bytes=None,
        audio_sha256=None,
        audio_duration_us=None,
        audio_sample_rate=None,
        audio_channels=None,
        audio_to_source_offset_us=None,
        thumbnail_file_size_bytes=50,
        thumbnail_sha256="b" * 64,
        thumbnail_source_time_us=1_000_000,
        source_video_time_base_num=1,
        source_video_time_base_den=90_000,
    )


def test_selected_stream_duration_has_priority_over_container_duration() -> None:
    """Proxy 视频时长必须以选中视频流为准，不能把更长的音频/容器尾巴算进去。"""

    payload = {"format": {"duration": "12.500000"}}
    video_stream = {"duration": "10.000000"}
    assert _duration_us(payload, video_stream) == 10_000_000


def test_duration_falls_back_to_container_when_stream_duration_missing() -> None:
    """部分容器没有 stream.duration 时，仍允许安全回退到 format.duration。"""

    payload = {"format": {"duration": "9.250000"}}
    assert _duration_us(payload, {}) == 9_250_000


def test_source_changed_during_preprocess_is_rejected_before_publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """长时间处理期间 Source 被外部替换时，F03 不能发布与快照不一致的派生资产。"""

    app_data, workspace, source_file, source_id = _create_ready_source_without_audio(tmp_path)

    def fake_proxy(**kwargs) -> None:
        target = kwargs["target_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"proxy")
        # 模拟外部程序在 FFmpeg 已开始后替换 F02 原片。
        source_file.write_bytes(b"source-was-replaced-during-processing")

    def fake_thumbnail(**kwargs) -> None:
        target = kwargs["target_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"thumbnail")

    monkeypatch.setattr("engine.app.preprocess.generate_proxy_video", fake_proxy)
    monkeypatch.setattr("engine.app.preprocess._probe_proxy_duration_us", lambda _: 10_000_000)
    monkeypatch.setattr("engine.app.preprocess.generate_thumbnail", fake_thumbnail)
    monkeypatch.setattr("engine.app.preprocess.inspect_preprocess_assets", lambda **_: _ready_metadata())

    with pytest.raises(PreprocessError) as exc:
        preprocess_source_video(project_id="PROJECT_f03_integrity", app_data_path=app_data)

    assert exc.value.code == "SOURCE_VIDEO_INTEGRITY_MISMATCH"
    assert "预处理过程中发生变化" in exc.value.message
    assert not (workspace / "preprocess" / source_id).exists()
    assert not (workspace / "preprocess" / ".staging" / source_id).exists()
    with sqlite3.connect(app_data / "app.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_preprocess").fetchone() == (0,)
