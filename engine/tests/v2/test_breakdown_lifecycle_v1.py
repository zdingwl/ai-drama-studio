from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_service_v1, shot_revision_v2, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.breakdown_validator_v1 import (
    BreakdownValidationIssue,
    BreakdownValidationResult,
)
from engine.app.shot_revision_v2 import ShotRevision


def setup_episode(monkeypatch, tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    with factory() as session:
        project = studio_v2.Project(
            id="PROJECT_1",
            name="Breakdown Lifecycle Test",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        )
        episode = studio_v2.Episode(
            id="EPISODE_1",
            project_id=project.id,
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="x" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=2_000_000,
        )
        session.add_all([project, episode])
        session.flush()
        for ordinal, start_us, end_us in [(1, 0, 1_000_000), (2, 1_000_000, 2_000_000)]:
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}",
                episode_id=episode.id,
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(tmp_path / f"r{ordinal}.mp4"),
                thumbnail_path=str(tmp_path / f"t{ordinal}.jpg"),
                keyframes_json="[]",
                status="READY",
            ))
        session.commit()
    return factory


def stub_validation(monkeypatch, *, passed: bool = True, error: str = "fixture validator error") -> None:
    issues = () if passed else (
        BreakdownValidationIssue(code="FIXTURE_INVALID", message=error),
    )
    result = BreakdownValidationResult(
        run_id="fixture",
        errors=issues,
        warnings=(),
        counts={"shot": 2},
    )
    monkeypatch.setattr(
        breakdown_service_v1.breakdown_validator_v1,
        "validate_breakdown_run_in_session",
        lambda _session, _run: result,
    )


def new_payloads(tmp_path: Path):
    return [
        {
            "ordinal": 1,
            "start_us": 0,
            "end_us": 800_000,
            "duration_us": 800_000,
            "reference_clip_path": str(tmp_path / "new1.mp4"),
            "thumbnail_path": str(tmp_path / "new1.jpg"),
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        },
        {
            "ordinal": 2,
            "start_us": 800_000,
            "end_us": 2_000_000,
            "duration_us": 1_200_000,
            "reference_clip_path": str(tmp_path / "new2.mp4"),
            "thumbnail_path": str(tmp_path / "new2.jpg"),
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        },
    ]


def test_current_shot_revision_creates_processing_run(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)

    run = breakdown_service_v1.create_breakdown_run(
        "EPISODE_1",
        pipeline_profile="fixture-v1",
        component_status={"draft": "PENDING"},
    )

    assert run.status == "PROCESSING"
    assert run.is_current is False
    assert run.project_id == "PROJECT_1"
    assert run.episode_id == "EPISODE_1"
    assert run.pipeline_profile == "fixture-v1"
    assert run.completed_at is None

    with factory() as session:
        current_revision = session.scalar(
            select(ShotRevision).where(
                ShotRevision.episode_id == "EPISODE_1",
                ShotRevision.is_current.is_(True),
            )
        )
        assert current_revision is not None
        assert run.source_shot_revision_id == current_revision.id


def test_ready_publish_switches_single_current_without_staling_same_revision_history(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    stub_validation(monkeypatch)

    first = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    published_first = breakdown_service_v1.publish_breakdown_run(first.id)
    assert published_first.status == "READY"
    assert published_first.is_current is True

    second = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    published_second = breakdown_service_v1.publish_breakdown_run(
        second.id,
        warnings=["fixture warning"],
    )
    assert published_second.status == "READY_WITH_WARNINGS"
    assert published_second.is_current is True

    with factory() as session:
        rows = session.scalars(
            select(BreakdownRun).where(BreakdownRun.episode_id == "EPISODE_1")
        ).all()
        by_id = {item.id: item for item in rows}
        assert sum(1 for item in rows if item.is_current) == 1
        assert by_id[first.id].status == "READY"
        assert by_id[first.id].is_current is False
        assert by_id[second.id].is_current is True


def test_failed_validation_does_not_replace_old_current(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    stub_validation(monkeypatch)

    stable = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    breakdown_service_v1.publish_breakdown_run(stable.id)

    failed = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    stub_validation(monkeypatch, passed=False)
    with pytest.raises(breakdown_service_v1.BreakdownValidationGateError, match="fixture validator error"):
        breakdown_service_v1.publish_breakdown_run(failed.id)

    with factory() as session:
        stable_row = session.get(BreakdownRun, stable.id)
        failed_row = session.get(BreakdownRun, failed.id)
        assert stable_row is not None and stable_row.status == "READY" and stable_row.is_current is True
        assert failed_row is not None and failed_row.status == "FAILED" and failed_row.is_current is False
        assert failed_row.completed_at is not None


def test_old_processing_run_is_automatically_staled_when_shot_revision_changes(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    stub_validation(monkeypatch)

    run = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    old_revision_id = run.source_shot_revision_id
    shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_payloads(tmp_path))

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        current_revision = session.scalar(
            select(ShotRevision).where(
                ShotRevision.episode_id == "EPISODE_1",
                ShotRevision.is_current.is_(True),
            )
        )
        assert row is not None and row.status == "STALE" and row.is_current is False
        assert row.completed_at is not None
        assert row.source_shot_revision_id == old_revision_id
        assert current_revision is not None and current_revision.id != old_revision_id

    with pytest.raises(breakdown_service_v1.BreakdownRunLifecycleError, match="当前状态为 STALE"):
        breakdown_service_v1.publish_breakdown_run(run.id)


def test_stale_primitive_is_idempotent_after_automatic_stale_and_preserves_history(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    stub_validation(monkeypatch)

    old_run = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    breakdown_service_v1.publish_breakdown_run(old_run.id)
    old_revision_id = old_run.source_shot_revision_id

    shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_payloads(tmp_path))
    with factory() as session:
        automatically_staled = session.get(BreakdownRun, old_run.id)
        assert automatically_staled is not None
        assert automatically_staled.status == "STALE"
        assert automatically_staled.is_current is False

    assert breakdown_service_v1.mark_episode_breakdown_runs_stale("EPISODE_1") == []

    new_run = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    breakdown_service_v1.publish_breakdown_run(new_run.id)
    assert breakdown_service_v1.mark_episode_breakdown_runs_stale("EPISODE_1") == []

    with factory() as session:
        old_row = session.get(BreakdownRun, old_run.id)
        new_row = session.get(BreakdownRun, new_run.id)
        old_revision = session.get(ShotRevision, old_revision_id)
        assert old_row is not None and old_row.status == "STALE" and old_row.is_current is False
        assert new_row is not None and new_row.status == "READY" and new_row.is_current is True
        assert old_revision is not None
