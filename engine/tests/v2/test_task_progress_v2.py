from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2, task_progress_v2


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", session_factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(task_progress_v2, "get_session", lambda: session_factory())


def seed_project(monkeypatch, tmp_path: Path) -> str:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="Task 测试",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    return project["id"]


def test_task_progress_is_persisted_and_queryable(monkeypatch, tmp_path: Path) -> None:
    project_id = seed_project(monkeypatch, tmp_path)
    task = task_progress_v2.create_task(
        project_id=project_id,
        task_type="BATCH_SHOTS",
        title="批量拉片",
        total_items=10,
    )

    task_progress_v2.start_task(task["id"], stage_key="shots", stage_label="拉片")
    task_progress_v2.update_task(
        task["id"],
        progress_percent=40,
        current_item="EP04",
        current_index=4,
        total_items=10,
        message="已完成 4 / 10 集",
    )

    loaded = task_progress_v2.get_task(task["id"])
    assert loaded is not None
    assert loaded["status"] == "PROCESSING"
    assert loaded["progress_percent"] == 40
    assert loaded["current_item"] == "EP04"
    assert loaded["current_index"] == 4
    assert loaded["total_items"] == 10

    task_progress_v2.finish_task(task["id"], result={"ok": True})
    finished = task_progress_v2.get_task(task["id"])
    assert finished is not None
    assert finished["status"] == "READY"
    assert finished["progress_percent"] == 100
    assert finished["result"] == {"ok": True}


def test_same_scope_active_task_is_deduplicated(monkeypatch, tmp_path: Path) -> None:
    project_id = seed_project(monkeypatch, tmp_path)
    first = task_progress_v2.create_task(
        project_id=project_id,
        task_type="ASSET_EXTRACTION",
        title="资产提取",
        progress_mode="indeterminate",
    )
    task_progress_v2.start_task(first["id"])

    second = task_progress_v2.create_task(
        project_id=project_id,
        task_type="ASSET_EXTRACTION",
        title="资产提取",
        progress_mode="indeterminate",
    )

    assert second["id"] == first["id"]
    assert len(task_progress_v2.list_project_tasks(project_id)) == 1


def test_process_restart_marks_active_tasks_failed(monkeypatch, tmp_path: Path) -> None:
    project_id = seed_project(monkeypatch, tmp_path)
    task = task_progress_v2.create_task(
        project_id=project_id,
        task_type="BATCH_PREPROCESS",
        title="批量初始化",
    )
    task_progress_v2.start_task(task["id"])

    recovered = task_progress_v2.recover_interrupted_tasks()
    assert recovered == 1

    loaded = task_progress_v2.get_task(task["id"])
    assert loaded is not None
    assert loaded["status"] == "FAILED"
    assert loaded["error_message"] == "TASK_INTERRUPTED_BY_PROCESS_RESTART"
