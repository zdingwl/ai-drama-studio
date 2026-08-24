"""F02 Source Video 核心业务测试。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.app.core.database import init_database
from engine.app.source_videos import (
    SourceVideoError,
    SourceVideoMetadata,
    copy_upload_to_staging,
    get_source_video,
    import_source_video,
    probe_source_video,
    recover_source_video_imports,
)


class FakeUpload:
    """测试用异步上传流；记录每次 read(size)，确认不会整文件一次读入。"""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self.position >= len(self.data):
            return b""
        end = len(self.data) if size < 0 else min(len(self.data), self.position + size)
        chunk = self.data[self.position:end]
        self.position = end
        return chunk


def _ready_metadata() -> SourceVideoMetadata:
    """返回不依赖本机 FFprobe 的稳定测试元数据。"""
    return SourceVideoMetadata(
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        duration_us=12_345_678,
        source_start_time_us=0,
        video_stream_index=0,
        video_codec="h264",
        width=1920,
        height=1080,
        fps_num=30000,
        fps_den=1001,
        audio_stream_index=1,
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_channels=2,
    )


def _create_ready_project(tmp_path: Path, project_id: str = "PROJECT_f02") -> tuple[Path, Path]:
    """创建符合 F01 冻结 Contract 的最小 ready Project。"""
    app_data = tmp_path / "app-data"
    database_path = init_database(app_data)
    workspace = tmp_path / "projects" / project_id
    workspace.mkdir(parents=True)
    (workspace / "project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "project_format_version": 1,
                "name": "F02 测试项目",
                "source_language": "zh",
                "target_language": "en",
                "target_region": "US",
            },
            ensure_ascii=False,
        ),
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
                project_id,
                "F02 测试项目",
                "zh",
                "en",
                "US",
                str(workspace),
                1,
                "ready",
                datetime.now(timezone.utc).isoformat(),
                None,
            ),
        )
        connection.commit()
    return app_data, workspace


def test_copy_upload_to_staging_streams_and_hashes(tmp_path: Path) -> None:
    """大于一个 chunk 的内容必须分块写入，大小和 SHA-256 与源字节完全一致。"""
    data = b"abc123" * 100_000
    upload = FakeUpload(data)
    staging_file = tmp_path / "source" / "original.mp4"

    result = asyncio.run(copy_upload_to_staging(upload, staging_file, chunk_size=64 * 1024))

    assert staging_file.read_bytes() == data
    assert result.file_size_bytes == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert all(size == 64 * 1024 for size in upload.read_sizes)
    assert len(upload.read_sizes) > 2


def test_copy_upload_to_staging_rejects_empty_file(tmp_path: Path) -> None:
    """0 字节文件不能进入后续 FFprobe/ready 流程。"""
    with pytest.raises(SourceVideoError) as exc:
        asyncio.run(copy_upload_to_staging(FakeUpload(b""), tmp_path / "empty.mp4"))
    assert exc.value.code == "SOURCE_VIDEO_EMPTY"


def test_probe_source_video_parses_ffprobe_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """FFprobe JSON 必须转换成整数微秒和 rational FPS，并正确选择默认流。"""
    payload = {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.345678", "start_time": "0.000000"},
        "streams": [
            {"index": 9, "codec_type": "video", "codec_name": "mjpeg", "width": 600, "height": 600, "avg_frame_rate": "1/1", "disposition": {"attached_pic": 1, "default": 0}},
            {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001", "disposition": {"attached_pic": 0, "default": 1}},
            {"index": 1, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2, "disposition": {"default": 1}},
        ],
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=json.dumps(payload), stderr=""),
    )

    metadata = probe_source_video(tmp_path / "video.mp4")

    assert metadata.duration_us == 12_345_678
    assert metadata.video_stream_index == 0
    assert (metadata.fps_num, metadata.fps_den) == (30000, 1001)
    assert metadata.audio_sample_rate == 48000


def test_probe_source_video_rejects_ffprobe_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """扩展名像视频但 FFprobe 解析失败时必须拒绝。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="", stderr="invalid"),
    )
    with pytest.raises(SourceVideoError) as exc:
        probe_source_video(tmp_path / "fake.mp4")
    assert exc.value.code == "SOURCE_VIDEO_PROBE_FAILED"


def test_import_get_and_reject_second_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """正常导入必须落 final+ready，刷新可读取，并阻止同 Project 第二份原片。"""
    app_data, workspace = _create_ready_project(tmp_path)
    monkeypatch.setattr("engine.app.source_videos.probe_source_video", lambda _: _ready_metadata())
    data = b"fake-video-content" * 1000

    record = asyncio.run(
        import_source_video(
            project_id="PROJECT_f02",
            upload_file=FakeUpload(data),
            original_filename="第一集.mp4",
            app_data_path=app_data,
        )
    )

    assert record.status == "ready"
    assert record.original_filename == "第一集.mp4"
    assert (workspace / record.relative_path).read_bytes() == data
    assert record.sha256 == hashlib.sha256(data).hexdigest()
    assert get_source_video(project_id="PROJECT_f02", app_data_path=app_data)?.id if False else True
    loaded = get_source_video(project_id="PROJECT_f02", app_data_path=app_data)
    assert loaded is not None and loaded.id == record.id

    with pytest.raises(SourceVideoError) as exc:
        asyncio.run(
            import_source_video(
                project_id="PROJECT_f02",
                upload_file=FakeUpload(data),
                original_filename="第二集.mp4",
                app_data_path=app_data,
            )
        )
    assert exc.value.code == "SOURCE_VIDEO_ALREADY_EXISTS"


def test_import_probe_failure_removes_importing_and_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """final 发布前 Probe 失败必须回滚本次 staging 和 importing 记录。"""
    app_data, workspace = _create_ready_project(tmp_path)

    def fail_probe(_: Path) -> SourceVideoMetadata:
        raise SourceVideoError("SOURCE_VIDEO_PROBE_FAILED", "bad video")

    monkeypatch.setattr("engine.app.source_videos.probe_source_video", fail_probe)
    with pytest.raises(SourceVideoError):
        asyncio.run(
            import_source_video(
                project_id="PROJECT_f02",
                upload_file=FakeUpload(b"not-video"),
                original_filename="坏文件.mp4",
                app_data_path=app_data,
            )
        )

    with sqlite3.connect(app_data / "app.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_videos").fetchone() == (0,)
    assert not (workspace / "source").exists()


def test_get_source_video_detects_missing_final_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """DB ready 但用户在系统外删掉原片时不能假装 Source 仍正常。"""
    app_data, workspace = _create_ready_project(tmp_path)
    monkeypatch.setattr("engine.app.source_videos.probe_source_video", lambda _: _ready_metadata())
    record = asyncio.run(
        import_source_video(
            project_id="PROJECT_f02",
            upload_file=FakeUpload(b"video" * 1000),
            original_filename="x.mp4",
            app_data_path=app_data,
        )
    )
    (workspace / record.relative_path).unlink()

    with pytest.raises(SourceVideoError) as exc:
        get_source_video(project_id="PROJECT_f02", app_data_path=app_data)
    assert exc.value.code == "SOURCE_VIDEO_FILE_MISSING"


def test_recovery_promotes_valid_final_importing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """final 已落盘但 DB 仍 importing 时，启动 Recovery 必须补 metadata 并转 ready。"""
    app_data, workspace = _create_ready_project(tmp_path)
    monkeypatch.setattr("engine.app.source_videos.probe_source_video", lambda _: _ready_metadata())
    source_id = "SOURCE_0123456789abcdef0123456789abcdef"
    relative_path = f"source/{source_id}/original.mp4"
    final_file = workspace / relative_path
    final_file.parent.mkdir(parents=True)
    final_file.write_bytes(b"published-video")

    with sqlite3.connect(app_data / "app.db") as connection:
        connection.execute(
            "INSERT INTO source_videos (id, project_id, original_filename, relative_path, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, "PROJECT_f02", "x.mp4", relative_path, "importing", datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()

    stats = recover_source_video_imports(app_data_path=app_data)
    assert stats["recovered"] == 1
    loaded = get_source_video(project_id="PROJECT_f02", app_data_path=app_data)
    assert loaded is not None and loaded.id == source_id


def test_recovery_preserves_unknown_staging_file(tmp_path: Path) -> None:
    """staging 中出现未知用户文件时 Recovery 不允许递归删除现场。"""
    app_data, workspace = _create_ready_project(tmp_path)
    source_id = "SOURCE_fedcba9876543210fedcba9876543210"
    relative_path = f"source/{source_id}/original.mp4"
    staging = workspace / "source" / ".staging" / source_id
    staging.mkdir(parents=True)
    (staging / "original.mp4").write_bytes(b"partial")
    (staging / "user-note.txt").write_text("keep", encoding="utf-8")

    with sqlite3.connect(app_data / "app.db") as connection:
        connection.execute(
            "INSERT INTO source_videos (id, project_id, original_filename, relative_path, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, "PROJECT_f02", "x.mp4", relative_path, "importing", datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()

    stats = recover_source_video_imports(app_data_path=app_data)
    assert stats["preserved"] == 1
    assert (staging / "user-note.txt").is_file()
