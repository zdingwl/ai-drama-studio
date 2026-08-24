"""F03 视频预处理核心业务、Recovery 与真实 FFmpeg 技术链路测试。"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.app.core.database import init_database
from engine.app.preprocess import (
    PreprocessAssetMetadata,
    PreprocessError,
    extract_analysis_audio,
    generate_proxy_video,
    generate_thumbnail,
    get_source_preprocess,
    inspect_preprocess_assets,
    preprocess_source_video,
    recover_source_preprocesses,
)
from engine.app.source_videos import SourceVideoRecord


def _ready_metadata(*, with_audio: bool = True) -> PreprocessAssetMetadata:
    return PreprocessAssetMetadata(
        proxy_file_size_bytes=100,
        proxy_sha256="a" * 64,
        proxy_duration_us=10_000_000,
        proxy_video_time_base_num=1,
        proxy_video_time_base_den=90_000,
        proxy_fps_num=25,
        proxy_fps_den=1,
        proxy_to_source_offset_us=0,
        audio_file_size_bytes=80 if with_audio else None,
        audio_sha256="b" * 64 if with_audio else None,
        audio_duration_us=10_000_000 if with_audio else None,
        audio_sample_rate=16_000 if with_audio else None,
        audio_channels=1 if with_audio else None,
        audio_to_source_offset_us=0 if with_audio else None,
        thumbnail_file_size_bytes=50,
        thumbnail_sha256="c" * 64,
        thumbnail_source_time_us=1_000_000,
        source_video_time_base_num=1,
        source_video_time_base_den=90_000,
    )


def _create_ready_project_source(tmp_path: Path, *, with_audio: bool = True) -> tuple[Path, Path, str, Path]:
    """构造真实 F01/F02 ready 数据，但 Source 字节可由 F03 单测自行控制。"""

    app_data = tmp_path / "app-data"
    database_path = init_database(app_data)
    project_id = "PROJECT_f03"
    source_id = "SOURCE_0123456789abcdef0123456789abcdef"
    workspace = tmp_path / "projects" / project_id
    source_file = workspace / "source" / source_id / "original.mp4"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"f03-source-bytes" * 1000)
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()

    (workspace / "project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "project_format_version": 1,
                "name": "F03 测试项目",
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
            (project_id, "F03 测试项目", "zh", "en", "US", str(workspace), 1, "ready", now, None),
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
                "第一集.mp4",
                f"source/{source_id}/original.mp4",
                source_file.stat().st_size,
                source_hash,
                "ready",
                "mov,mp4",
                10_000_000,
                0,
                0,
                "h264",
                1920,
                1080,
                25,
                1,
                1 if with_audio else None,
                "aac" if with_audio else None,
                48_000 if with_audio else None,
                2 if with_audio else None,
                now,
            ),
        )
        connection.commit()

    return app_data, workspace, source_id, source_file


def _mock_media_pipeline(monkeypatch: pytest.MonkeyPatch, *, with_audio: bool = True) -> None:
    """业务状态机测试不依赖 FFmpeg；真实 FFmpeg 由文件末尾独立测试。"""

    def fake_proxy(**kwargs) -> None:
        kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target_path"].write_bytes(b"proxy")

    def fake_audio(**kwargs) -> None:
        kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target_path"].write_bytes(b"audio")

    def fake_thumbnail(**kwargs) -> None:
        kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target_path"].write_bytes(b"thumb")

    monkeypatch.setattr("engine.app.preprocess.generate_proxy_video", fake_proxy)
    monkeypatch.setattr("engine.app.preprocess.extract_analysis_audio", fake_audio)
    monkeypatch.setattr("engine.app.preprocess.generate_thumbnail", fake_thumbnail)
    monkeypatch.setattr("engine.app.preprocess._probe_proxy_duration_us", lambda _: 10_000_000)
    monkeypatch.setattr(
        "engine.app.preprocess.inspect_preprocess_assets",
        lambda **_: _ready_metadata(with_audio=with_audio),
    )


def test_preprocess_business_flow_publishes_ready_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_data, workspace, source_id, _ = _create_ready_project_source(tmp_path, with_audio=True)
    _mock_media_pipeline(monkeypatch, with_audio=True)

    record = preprocess_source_video(project_id="PROJECT_f03", app_data_path=app_data)

    assert record.status == "ready"
    assert record.source_video_id == source_id
    final_dir = workspace / "preprocess" / source_id
    assert (final_dir / "proxy.mp4").read_bytes() == b"proxy"
    assert (final_dir / "audio.wav").read_bytes() == b"audio"
    assert (final_dir / "thumbnail.jpg").read_bytes() == b"thumb"
    assert not (workspace / "preprocess" / ".staging" / source_id).exists()

    loaded = get_source_preprocess(project_id="PROJECT_f03", app_data_path=app_data)
    assert loaded is not None and loaded.source_video_id == source_id

    with pytest.raises(PreprocessError) as exc:
        preprocess_source_video(project_id="PROJECT_f03", app_data_path=app_data)
    assert exc.value.code == "PREPROCESS_ALREADY_EXISTS"


def test_preprocess_without_source_audio_does_not_create_fake_wav(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_data, workspace, source_id, _ = _create_ready_project_source(tmp_path, with_audio=False)
    _mock_media_pipeline(monkeypatch, with_audio=False)

    record = preprocess_source_video(project_id="PROJECT_f03", app_data_path=app_data)

    assert record.audio_relative_path is None
    assert record.audio_file_size_bytes is None
    assert not (workspace / "preprocess" / source_id / "audio.wav").exists()


def test_source_integrity_mismatch_stops_before_processing_row(tmp_path: Path) -> None:
    app_data, _, _, source_file = _create_ready_project_source(tmp_path)
    source_file.write_bytes(b"external-replacement")

    with pytest.raises(PreprocessError) as exc:
        preprocess_source_video(project_id="PROJECT_f03", app_data_path=app_data)
    assert exc.value.code == "SOURCE_VIDEO_INTEGRITY_MISMATCH"

    with sqlite3.connect(app_data / "app.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_preprocess").fetchone() == (0,)


def test_recovery_promotes_valid_final(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_data, workspace, source_id, source_file = _create_ready_project_source(tmp_path)
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    final_dir = workspace / "preprocess" / source_id
    final_dir.mkdir(parents=True)
    (final_dir / "proxy.mp4").write_bytes(b"proxy")
    (final_dir / "audio.wav").write_bytes(b"audio")
    (final_dir / "thumbnail.jpg").write_bytes(b"thumb")

    with sqlite3.connect(app_data / "app.db") as connection:
        connection.execute(
            """
            INSERT INTO source_preprocess (
                source_video_id, project_id, status, profile_version, source_sha256_snapshot,
                proxy_relative_path, audio_relative_path, thumbnail_relative_path, created_at
            ) VALUES (?, ?, 'processing', 1, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                "PROJECT_f03",
                source_hash,
                f"preprocess/{source_id}/proxy.mp4",
                f"preprocess/{source_id}/audio.wav",
                f"preprocess/{source_id}/thumbnail.jpg",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()

    monkeypatch.setattr(
        "engine.app.preprocess.inspect_preprocess_assets",
        lambda **_: _ready_metadata(with_audio=True),
    )
    stats = recover_source_preprocesses(app_data_path=app_data)
    assert stats["recovered"] == 1
    with sqlite3.connect(app_data / "app.db") as connection:
        assert connection.execute(
            "SELECT status FROM source_preprocess WHERE source_video_id=?", (source_id,)
        ).fetchone() == ("ready",)


def test_recovery_preserves_unknown_staging_file(tmp_path: Path) -> None:
    app_data, workspace, source_id, source_file = _create_ready_project_source(tmp_path)
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    staging_dir = workspace / "preprocess" / ".staging" / source_id
    staging_dir.mkdir(parents=True)
    (staging_dir / "proxy.mp4").write_bytes(b"partial")
    (staging_dir / "user-note.txt").write_text("不要删除", encoding="utf-8")

    with sqlite3.connect(app_data / "app.db") as connection:
        connection.execute(
            """
            INSERT INTO source_preprocess (
                source_video_id, project_id, status, profile_version, source_sha256_snapshot,
                proxy_relative_path, audio_relative_path, thumbnail_relative_path, created_at
            ) VALUES (?, ?, 'processing', 1, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                "PROJECT_f03",
                source_hash,
                f"preprocess/{source_id}/proxy.mp4",
                f"preprocess/{source_id}/audio.wav",
                f"preprocess/{source_id}/thumbnail.jpg",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()

    stats = recover_source_preprocesses(app_data_path=app_data)
    assert stats["preserved"] == 1
    assert (staging_dir / "user-note.txt").is_file()
    with sqlite3.connect(app_data / "app.db") as connection:
        assert connection.execute(
            "SELECT status FROM source_preprocess WHERE source_video_id=?", (source_id,)
        ).fetchone() == ("processing",)


def test_preprocess_http_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_data, _, _, _ = _create_ready_project_source(tmp_path)
    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(app_data))
    _mock_media_pipeline(monkeypatch, with_audio=True)

    from engine.app.main import create_app

    with TestClient(create_app()) as client:
        empty = client.get("/api/projects/PROJECT_f03/preprocess")
        assert empty.status_code == 200
        assert empty.json() is None

        created = client.post("/api/projects/PROJECT_f03/preprocess")
        assert created.status_code == 201
        assert created.json()["status"] == "ready"
        assert created.json()["profile_version"] == 1

        loaded = client.get("/api/projects/PROJECT_f03/preprocess")
        assert loaded.status_code == 200
        assert loaded.json()["source_video_id"] == created.json()["source_video_id"]

        duplicate = client.post("/api/projects/PROJECT_f03/preprocess")
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "PREPROCESS_ALREADY_EXISTS"


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="本测试需要本机 FFmpeg/FFprobe",
)
def test_real_ffmpeg_proxy_audio_thumbnail_and_mapping(tmp_path: Path) -> None:
    """真实媒体链路验证固定 Proxy Profile、16k mono WAV、Thumbnail 和非零 Source offset。"""

    source_path = tmp_path / "source.mp4"
    proxy_path = tmp_path / "staging" / "proxy.mp4"
    audio_path = tmp_path / "staging" / "audio.wav"
    thumbnail_path = tmp_path / "staging" / "thumbnail.jpg"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30000/1001",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-output_ts_offset", "2", str(source_path),
        ],
        check=True,
    )

    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source = SourceVideoRecord(
        id="SOURCE_REAL",
        project_id="PROJECT_REAL",
        original_filename="source.mp4",
        relative_path="source/SOURCE_REAL/original.mp4",
        file_size_bytes=source_path.stat().st_size,
        sha256=source_hash,
        status="ready",
        container_format="mov,mp4",
        duration_us=2_000_000,
        source_start_time_us=2_000_000,
        video_stream_index=0,
        video_codec="h264",
        width=1920,
        height=1080,
        fps_num=30000,
        fps_den=1001,
        audio_stream_index=1,
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_channels=1,
        created_at=datetime.now(timezone.utc),
    )

    generate_proxy_video(
        source_path=source_path,
        target_path=proxy_path,
        video_stream_index=0,
        audio_stream_index=1,
    )
    extract_analysis_audio(source_path=source_path, target_path=audio_path, audio_stream_index=1)

    # 实际 Proxy 时长由 FFprobe 得到；Thumbnail 选取规则与业务层相同：10%，最多 5 秒。
    probe = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(proxy_path)],
        text=True,
    )
    proxy_duration_us = round(float(json.loads(probe)["format"]["duration"]) * 1_000_000)
    generate_thumbnail(
        proxy_path=proxy_path,
        target_path=thumbnail_path,
        proxy_time_us=min(proxy_duration_us // 10, 5_000_000),
    )

    metadata = inspect_preprocess_assets(
        source_path=source_path,
        source_video=source,
        proxy_path=proxy_path,
        audio_path=audio_path,
        thumbnail_path=thumbnail_path,
    )

    assert proxy_path.stat().st_size > 0
    assert audio_path.stat().st_size > 0
    assert thumbnail_path.stat().st_size > 0
    assert metadata.audio_sample_rate == 16000
    assert metadata.audio_channels == 1
    assert metadata.proxy_to_source_offset_us == 2_000_000
    assert metadata.thumbnail_source_time_us > 2_000_000
    assert metadata.proxy_video_time_base_num != 0
    assert metadata.proxy_video_time_base_den > 0
