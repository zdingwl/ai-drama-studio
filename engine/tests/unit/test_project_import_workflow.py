from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.app import project_import_workflow as workflow
from engine.app.preprocess import SourcePreprocessRecord
from engine.app.projects import ProjectRecord
from engine.app.source_videos import SourceVideoRecord

NOW = datetime.now(timezone.utc)


class FakeUpload:
    async def read(self, size: int = -1) -> bytes:
        return b""


def _project() -> ProjectRecord:
    return ProjectRecord(
        id="PROJECT_test",
        name="测试项目",
        source_language="zh",
        target_language="en",
        target_region="US",
        workspace_path="D:/projects/PROJECT_test",
        project_format_version=1,
        status="ready",
        created_at=NOW,
        last_opened_at=NOW,
    )


def _source() -> SourceVideoRecord:
    return SourceVideoRecord(
        id="SOURCE_test",
        project_id="PROJECT_test",
        original_filename="source.mp4",
        relative_path="source/SOURCE_test/original.mp4",
        file_size_bytes=123,
        sha256="a" * 64,
        status="ready",
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        duration_us=10_000_000,
        source_start_time_us=0,
        video_stream_index=0,
        video_codec="h264",
        width=1920,
        height=1080,
        fps_num=25,
        fps_den=1,
        audio_stream_index=1,
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_channels=2,
        created_at=NOW,
    )


def _preprocess() -> SourcePreprocessRecord:
    return SourcePreprocessRecord(
        source_video_id="SOURCE_test",
        project_id="PROJECT_test",
        status="ready",
        profile_version=1,
        source_sha256_snapshot="a" * 64,
        proxy_relative_path="preprocess/SOURCE_test/proxy.mp4",
        proxy_file_size_bytes=100,
        proxy_sha256="b" * 64,
        proxy_duration_us=10_000_000,
        proxy_video_time_base_num=1,
        proxy_video_time_base_den=12800,
        proxy_fps_num=25,
        proxy_fps_den=1,
        proxy_to_source_offset_us=0,
        audio_relative_path="preprocess/SOURCE_test/audio.wav",
        audio_file_size_bytes=50,
        audio_sha256="c" * 64,
        audio_duration_us=10_000_000,
        audio_sample_rate=16000,
        audio_channels=1,
        audio_to_source_offset_us=0,
        thumbnail_relative_path="preprocess/SOURCE_test/thumbnail.jpg",
        thumbnail_file_size_bytes=10,
        thumbnail_sha256="d" * 64,
        thumbnail_source_time_us=5_000_000,
        source_video_time_base_num=1,
        source_video_time_base_den=12800,
        created_at=NOW,
        completed_at=NOW,
    )


@pytest.mark.asyncio
async def test_import_project_source_workflow_only_orchestrates_f01_f02_f03(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []
    project = _project()
    source = _source()
    preprocess = _preprocess()

    def fake_create_project(**kwargs):
        calls.append(("create_project", kwargs))
        return project

    async def fake_import_source_video(**kwargs):
        calls.append(("import_source_video", kwargs["project_id"]))
        return source

    def fake_preprocess_source_video(**kwargs):
        calls.append(("preprocess_source_video", kwargs["project_id"]))
        return preprocess

    monkeypatch.setattr(workflow, "create_project", fake_create_project)
    monkeypatch.setattr(workflow, "import_source_video", fake_import_source_video)
    monkeypatch.setattr(workflow, "preprocess_source_video", fake_preprocess_source_video)

    result = await workflow.import_project_source_workflow(
        name="测试项目",
        source_language="zh",
        target_language="en",
        target_region="US",
        workspace_root=Path("D:/projects"),
        upload_file=FakeUpload(),
        original_filename="source.mp4",
    )

    assert result.status == "ready"
    assert result.project.id == project.id
    assert result.source_video.id == source.id
    assert result.preprocess.source_video_id == source.id
    assert [name for name, _ in calls] == [
        "create_project",
        "import_source_video",
        "preprocess_source_video",
    ]
