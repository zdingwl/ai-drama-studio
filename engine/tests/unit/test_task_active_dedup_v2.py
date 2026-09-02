from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2, task_progress_v2


def _use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(task_progress_v2, "get_session", lambda: factory())


def test_formal_heavy_task_cannot_opt_out_of_active_dedup(monkeypatch, tmp_path: Path) -> None:
    _use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="Task Dedup",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )

    first = task_progress_v2.create_task(
        project_id=project["id"],
        task_type="H3_GENERATE_READY_V1",
        title="H3",
        deduplicate_active=False,
    )
    second = task_progress_v2.create_task(
        project_id=project["id"],
        task_type="H3_GENERATE_READY_V1",
        title="H3 duplicate click",
        deduplicate_active=False,
    )

    assert first["id"] == second["id"]
    assert first["status"] == "QUEUED"
    assert len(task_progress_v2.list_project_tasks(project["id"])) == 1


def test_non_formal_diagnostic_task_can_explicitly_opt_out(monkeypatch, tmp_path: Path) -> None:
    _use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="Diagnostic Task",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )

    first = task_progress_v2.create_task(
        project_id=project["id"],
        task_type="DIAGNOSTIC_TEST_TASK",
        title="diagnostic 1",
        deduplicate_active=False,
    )
    second = task_progress_v2.create_task(
        project_id=project["id"],
        task_type="DIAGNOSTIC_TEST_TASK",
        title="diagnostic 2",
        deduplicate_active=False,
    )

    assert first["id"] != second["id"]
    assert len(task_progress_v2.list_project_tasks(project["id"])) == 2
