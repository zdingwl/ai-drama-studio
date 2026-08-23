"""F01 剩余核心函数和 Controller 的真实行为测试。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.app.core.database import init_database
from engine.app.projects import (
    PROJECT_FORMAT_VERSION,
    ProjectError,
    create_project,
    create_project_workspace,
    list_projects,
    open_project,
    recover_creating_projects,
)

PROJECT_ID = "PROJECT_1234567890abcdef1234567890abcdef"


def _db_rows(app_data: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(app_data / "app.db")
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
    finally:
        connection.close()


def _insert_creating(app_data: Path, project_id: str, workspace: Path) -> None:
    init_database(app_data)
    connection = sqlite3.connect(app_data / "app.db")
    try:
        connection.execute(
            """INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, "恢复测试", "zh", "en", "US", str(workspace), 1, "creating", "2026-08-23 10:00:00", None),
        )
        connection.commit()
    finally:
        connection.close()


def test_create_project_workspace_writes_exact_v1_manifest(tmp_path: Path) -> None:
    workspace = create_project_workspace(
        workspace_root=tmp_path, project_id=PROJECT_ID, name="测试短剧",
        source_language="zh", target_language="en", target_region="US",
    )
    assert workspace == tmp_path / PROJECT_ID
    assert {p.name for p in workspace.iterdir()} == {"project.json"}
    assert json.loads((workspace / "project.json").read_text(encoding="utf-8")) == {
        "project_id": PROJECT_ID,
        "project_format_version": PROJECT_FORMAT_VERSION,
        "name": "测试短剧",
        "source_language": "zh",
        "target_language": "en",
        "target_region": "US",
    }


def test_create_project_workspace_never_overwrites_existing_project_dir(tmp_path: Path) -> None:
    existing = tmp_path / PROJECT_ID
    existing.mkdir()
    sentinel = existing / "user-file.txt"
    sentinel.write_text("不要删除", encoding="utf-8")
    with pytest.raises(ProjectError, match="不会覆盖"):
        create_project_workspace(
            workspace_root=tmp_path, project_id=PROJECT_ID, name="测试",
            source_language=None, target_language="en", target_region="US",
        )
    assert sentinel.read_text(encoding="utf-8") == "不要删除"


def test_create_project_creates_ready_db_row_and_workspace(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    project = create_project(
        name="  测试短剧  ", source_language="ZH", target_language="EN", target_region="us",
        workspace_root=tmp_path / "projects", app_data_path=app_data,
    )
    rows = _db_rows(app_data)
    assert len(rows) == 1 and rows[0]["status"] == "ready" and rows[0]["id"] == project.id
    assert project.name == "测试短剧"
    assert project.source_language == "zh"
    assert project.target_language == "en"
    assert project.target_region == "US"
    assert project.last_opened_at is not None
    assert (Path(project.workspace_path) / "project.json").is_file()


def test_create_project_allows_duplicate_names_but_ids_and_paths_differ(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    root = tmp_path / "projects"
    first = create_project(name="同名", target_language="en", target_region="US", workspace_root=root, app_data_path=app_data)
    second = create_project(name="同名", target_language="en", target_region="US", workspace_root=root, app_data_path=app_data)
    assert first.id != second.id
    assert first.workspace_path != second.workspace_path
    assert len(_db_rows(app_data)) == 2


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"name": "   ", "target_language": "en", "target_region": "US"}, "PROJECT_NAME_REQUIRED"),
        ({"name": "x", "target_language": " ", "target_region": "US"}, "PROJECT_TARGET_LANGUAGE_REQUIRED"),
        ({"name": "x", "target_language": "en", "target_region": " "}, "PROJECT_TARGET_REGION_REQUIRED"),
    ],
)
def test_create_project_rejects_required_field_errors_without_touching_database(tmp_path: Path, kwargs: dict, code: str) -> None:
    app_data = tmp_path / "app-data"
    with pytest.raises(ProjectError) as caught:
        create_project(**kwargs, workspace_root=tmp_path / "projects", app_data_path=app_data)
    assert caught.value.code == code
    assert not (app_data / "app.db").exists()


def test_create_project_workspace_failure_removes_creating_db_row(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    workspace_root_file = tmp_path / "not-a-directory"
    workspace_root_file.write_text("file", encoding="utf-8")
    with pytest.raises(ProjectError) as caught:
        create_project(
            name="失败测试", target_language="en", target_region="US",
            workspace_root=workspace_root_file, app_data_path=app_data,
        )
    assert caught.value.code == "PROJECT_WORKSPACE_INVALID"
    assert _db_rows(app_data) == []


def test_list_projects_returns_recent_open_first(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    root = tmp_path / "projects"
    first = create_project(name="A", target_language="en", target_region="US", workspace_root=root, app_data_path=app_data)
    time.sleep(0.01)
    second = create_project(name="B", target_language="en", target_region="US", workspace_root=root, app_data_path=app_data)
    assert [project.id for project in list_projects(app_data_path=app_data)] == [second.id, first.id]


def test_open_project_validates_manifest_and_updates_last_opened_at(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    project = create_project(name="A", target_language="en", target_region="US", workspace_root=tmp_path / "projects", app_data_path=app_data)
    before = project.last_opened_at
    time.sleep(0.01)
    opened = open_project(project_id=project.id, app_data_path=app_data)
    assert before is not None and opened.last_opened_at is not None and opened.last_opened_at > before


def test_open_project_reports_missing_workspace_without_deleting_db_row(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    project = create_project(name="A", target_language="en", target_region="US", workspace_root=tmp_path / "projects", app_data_path=app_data)
    workspace = Path(project.workspace_path)
    (workspace / "project.json").unlink()
    workspace.rmdir()
    with pytest.raises(ProjectError) as caught:
        open_project(project_id=project.id, app_data_path=app_data)
    assert caught.value.code == "PROJECT_WORKSPACE_MISSING"
    assert len(_db_rows(app_data)) == 1


def test_open_project_reports_manifest_id_mismatch(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    project = create_project(name="A", target_language="en", target_region="US", workspace_root=tmp_path / "projects", app_data_path=app_data)
    manifest_path = Path(project.workspace_path) / "project.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["project_id"] = "PROJECT_wrong"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProjectError) as caught:
        open_project(project_id=project.id, app_data_path=app_data)
    assert caught.value.code == "PROJECT_MANIFEST_INVALID"


def test_recover_creating_project_marks_valid_workspace_ready(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    workspace = create_project_workspace(
        workspace_root=tmp_path / "projects", project_id=PROJECT_ID, name="恢复测试",
        source_language="zh", target_language="en", target_region="US",
    )
    _insert_creating(app_data, PROJECT_ID, workspace)
    assert recover_creating_projects(app_data_path=app_data) == {"recovered": 1, "removed": 0, "preserved": 0}
    assert _db_rows(app_data)[0]["status"] == "ready"


def test_recover_creating_project_removes_row_when_workspace_missing(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    _insert_creating(app_data, PROJECT_ID, tmp_path / "projects" / PROJECT_ID)
    assert recover_creating_projects(app_data_path=app_data) == {"recovered": 0, "removed": 1, "preserved": 0}
    assert _db_rows(app_data) == []


def test_recover_preserves_workspace_with_unknown_user_file(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    workspace = tmp_path / "projects" / PROJECT_ID
    workspace.mkdir(parents=True)
    (workspace / "user-note.txt").write_text("保留", encoding="utf-8")
    _insert_creating(app_data, PROJECT_ID, workspace)
    assert recover_creating_projects(app_data_path=app_data) == {"recovered": 0, "removed": 0, "preserved": 1}
    assert (workspace / "user-note.txt").is_file()
    assert len(_db_rows(app_data)) == 1


def test_fastapi_controllers_cover_health_create_list_and_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_DRAMA_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    from engine.app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/projects").json() == []
        created_response = client.post(
            "/api/projects",
            json={
                "name": "接口测试", "source_language": "zh", "target_language": "en",
                "target_region": "US", "workspace_root": str(tmp_path / "projects"),
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()
        assert created["status"] == "ready"
        assert [item["id"] for item in client.get("/api/projects").json()] == [created["id"]]
        opened = client.post(f"/api/projects/{created['id']}/open")
        assert opened.status_code == 200 and opened.json()["id"] == created["id"]
        invalid = client.post("/api/projects", json={"name": " ", "target_language": "en", "target_region": "US"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "PROJECT_NAME_REQUIRED"
