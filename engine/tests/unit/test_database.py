"""应用数据库初始化测试；持续保护 F01/F02 冻结 Contract。"""

from pathlib import Path
import sqlite3

from engine.app.core.database import init_database

EXPECTED_PROJECT_COLUMNS = {
    "id",
    "name",
    "source_language",
    "target_language",
    "target_region",
    "workspace_path",
    "project_format_version",
    "status",
    "created_at",
    "last_opened_at",
}

CURRENT_BUSINESS_TABLES = {"projects", "source_videos", "source_preprocess"}


def _read_table_names(database_path: Path) -> set[str]:
    """读取当前 SQLite 表名，用于确认 Migration 得到预期业务表。"""

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def _insert_project(
    connection: sqlite3.Connection,
    project_id: str,
    workspace_path: str,
    status: str = "ready",
) -> None:
    """测试辅助：插入最小项目记录，用于持续验证 F01 数据库约束。"""

    connection.execute(
        """
        INSERT INTO projects (
            id, name, source_language, target_language, target_region,
            workspace_path, project_format_version, status, created_at, last_opened_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            "测试项目",
            "zh",
            "en",
            "US",
            workspace_path,
            1,
            status,
            "2026-08-23T08:00:00+00:00",
            None,
        ),
    )


def test_init_database_creates_app_db_and_current_business_tables(tmp_path: Path) -> None:
    """新数据库必须创建 F01/F02 冻结表以及当前 F03 Additive 表。"""

    app_data_dir = tmp_path / "app-data"
    database_path = init_database(app_data_dir)

    assert database_path == (app_data_dir / "app.db").resolve()
    assert database_path.is_file()
    assert _read_table_names(database_path) == {"alembic_version", *CURRENT_BUSINESS_TABLES}


def test_init_database_keeps_exact_f01_project_columns(tmp_path: Path) -> None:
    """F03 Additive Migration 不得静默改变已冻结的 F01 projects 字段。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("PRAGMA table_info(projects)").fetchall()

    assert {row[1] for row in rows} == EXPECTED_PROJECT_COLUMNS


def test_init_database_records_current_alembic_revision(tmp_path: Path) -> None:
    """F03 开始后当前 schema head 必须是 0003。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

    assert revision == ("0003_create_source_preprocess",)


def test_init_database_is_safe_to_run_more_than_once(tmp_path: Path) -> None:
    """软件多次启动时不能重复建表或损坏 F01/F02/F03 数据库。"""

    app_data_dir = tmp_path / "app-data"
    first_path = init_database(app_data_dir)
    second_path = init_database(app_data_dir)

    assert second_path == first_path
    assert _read_table_names(second_path) == {"alembic_version", *CURRENT_BUSINESS_TABLES}


def test_projects_table_rejects_invalid_status(tmp_path: Path) -> None:
    """F01 冻结 status 仍然只允许 creating / ready。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        try:
            _insert_project(
                connection,
                "PROJECT_A",
                "C:/projects/a",
                status="broken",
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("projects.status 必须只允许 creating / ready")


def test_projects_table_rejects_duplicate_workspace_path(tmp_path: Path) -> None:
    """F03 Migration 后仍必须保持 F01 workspace_path 唯一约束。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        _insert_project(connection, "PROJECT_A", "C:/projects/same")
        connection.commit()

        try:
            _insert_project(connection, "PROJECT_B", "C:/projects/same")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("不同项目不能指向同一个 workspace_path")
