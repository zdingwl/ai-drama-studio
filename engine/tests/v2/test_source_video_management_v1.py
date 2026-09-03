from __future__ import annotations

import io
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import (
    breakdown_models_v1,
    content_analysis_v2,  # noqa: F401 - register production table before create_all
    shot_revision_v2,
    source_video_management_v1,
    studio_v2,
)


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(
        studio_v2,
        "SessionLocal",
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def upload(name: str, payload: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(payload))


def test_source_video_list_returns_real_file_size(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="视频管理测试",
        source_language="zh",
        target_language="en",
        target_region="US",
    )
    episode = source_video_management_v1.import_project_source_video(
        project["id"],
        upload("ep01.mp4", b"source-video-bytes"),
    )

    listed = source_video_management_v1.list_project_source_videos(project["id"])

    assert [item["id"] for item in listed] == [episode["id"]]
    assert listed[0]["file_size_bytes"] == len(b"source-video-bytes")


def test_replace_source_preserves_episode_identity_and_invalidates_old_current_results(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="替换原片测试",
        source_language="zh",
        target_language="en",
        target_region="US",
    )
    episode_payload = source_video_management_v1.import_project_source_video(
        project["id"],
        upload("ep01.mp4", b"old-source"),
    )
    episode_id = episode_payload["id"]

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, episode_id)
        assert episode is not None
        preprocess = studio_v2.Preprocess(
            id=studio_v2.new_id("PREPROCESS"),
            episode_id=episode_id,
            status="READY",
            proxy_path=str(tmp_path / "proxy.mp4"),
            audio_path=str(tmp_path / "audio.wav"),
        )
        shot = studio_v2.Shot(
            id=studio_v2.new_id("SHOT"),
            episode_id=episode_id,
            ordinal=1,
            start_us=0,
            end_us=1_000_000,
            duration_us=1_000_000,
            reference_clip_path=str(tmp_path / "reference.mp4"),
            thumbnail_path=None,
            keyframes_json="[]",
            status="READY",
        )
        revision = shot_revision_v2.ShotRevision(
            id=studio_v2.new_id("SHOTREV"),
            episode_id=episode_id,
            revision=1,
            kind="AUTO",
            is_current=True,
            source_revision_id=None,
            note="old current",
        )
        session.add_all([preprocess, shot, revision])
        session.flush()
        run = breakdown_models_v1.BreakdownRun(
            id=studio_v2.new_id("BREAKDOWNRUN"),
            project_id=project["id"],
            episode_id=episode_id,
            source_shot_revision_id=revision.id,
            status="READY",
            is_current=True,
            schema_version=breakdown_models_v1.BREAKDOWN_DRAFT_SCHEMA_VERSION,
            component_status_json="{}",
            provider_metadata_json="{}",
            counts_json="{}",
            warning_json="{}",
        )
        session.add(run)
        episode.status = "SHOTS_READY"
        episode.duration_us = 1_000_000
        episode.width = 1920
        episode.height = 1080
        episode.fps = 25.0
        session.commit()
        run_id = run.id
        revision_id = revision.id

    replaced = source_video_management_v1.replace_episode_source_video(
        episode_id,
        upload("replacement.mkv", b"new-source-content"),
    )

    assert replaced["id"] == episode_id
    assert replaced["sort_order"] == episode_payload["sort_order"]
    assert replaced["original_filename"] == "replacement.mkv"
    assert replaced["status"] == "IMPORTED"
    assert replaced["preprocess_status"] is None
    assert replaced["shot_count"] == 0
    assert replaced["duration_us"] is None
    assert replaced["width"] is None
    assert replaced["height"] is None
    assert replaced["fps"] is None
    assert replaced["file_size_bytes"] == len(b"new-source-content")

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, episode_id)
        assert episode is not None
        assert Path(episode.source_path).read_bytes() == b"new-source-content"
        assert episode.preprocess is None
        assert episode.shots == []

        revision = session.get(shot_revision_v2.ShotRevision, revision_id)
        assert revision is not None
        assert revision.is_current is False

        run = session.get(breakdown_models_v1.BreakdownRun, run_id)
        assert run is not None
        assert run.status == "STALE"
        assert run.is_current is False

        current_revisions = session.scalars(
            select(shot_revision_v2.ShotRevision).where(
                shot_revision_v2.ShotRevision.episode_id == episode_id,
                shot_revision_v2.ShotRevision.is_current.is_(True),
            )
        ).all()
        assert current_revisions == []


def test_source_video_management_rejects_unsupported_extension(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="格式校验测试",
        source_language="zh",
        target_language="en",
        target_region="US",
    )

    try:
        source_video_management_v1.import_project_source_video(
            project["id"],
            upload("episode.avi", b"not-supported"),
        )
    except source_video_management_v1.SourceVideoManagementError as exc:
        assert exc.code == "VIDEO_FORMAT_UNSUPPORTED"
    else:
        raise AssertionError("AVI 应被项目视频管理正式入口拒绝")
