"""F02 0002 Migration 与共享升级前 SQLite 备份回归测试。"""

from pathlib import Path
import sqlite3

from alembic import command

from engine.app.core.database import _build_alembic_config, init_database

EXPECTED_SOURCE_VIDEO_COLUMNS = {
    "id",
    "project_id",
    "original_filename",
    "relative_path",
    "file_size_bytes",
    "sha256",
    "status",
    "container_format",
    "duration_us",
    "source_start_time_us",
    "video_stream_index",
    "video_codec",
    "width",
    "height",
    "fps_num",
    "fps_den",
    "audio_stream_index",
    "audio_codec",
    "audio_sample_rate",
    "audio_channels",
    "created_at",
}

CURRENT_HEAD = "0003_create_source_preprocess"


def _create_f01_database(app_data_dir: Path) -> Path:
    """构造真实 0001 数据库，用于模拟已经被用户使用过的 F01 app.db。"""

    app_data_dir.mkdir(parents=True, exist_ok=True)
    database_path = app_data_dir / "app.db"
    command.upgrade(_build_alembic_config(database_path), "0001_create_projects")
    return database_path


def _insert_f01_project(database_path: Path) -> None:
    """在升级前写入一条 F01 项目，验证 Backup/Upgrade 都不会丢历史数据。"""

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PROJECT_F01_EXISTING",
                "F01 已有项目",
                "zh",
                "en",
                "US",
                "C:/projects/f01-existing",
                1,
                "ready",
                "2026-08-24T00:00:00+00:00",
                None,
            ),
        )
        connection.commit()


def test_fresh_database_reaches_current_head_without_creating_backup(tmp_path: Path) -> None:
    """全新安装直接建到当前 head，不制造无意义备份，同时必须包含 F02 表。"""

    app_data_dir = tmp_path / "app-data"
    database_path = init_database(app_data_dir)

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        source_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_videos'"
        ).fetchone()

    assert revision == (CURRENT_HEAD,)
    assert source_table == ("source_videos",)
    assert not (app_data_dir / "backups").exists()


def test_upgrade_from_0001_creates_safe_backup_before_current_head(tmp_path: Path) -> None:
    """真实 F01 数据库升级当前 head 前必须保留一份仍停留在 0001 的一致性 SQLite 快照。"""

    app_data_dir = tmp_path / "app-data"
    database_path = _create_f01_database(app_data_dir)
    _insert_f01_project(database_path)

    init_database(app_data_dir)

    backups = list((app_data_dir / "backups").glob("*.db"))
    assert len(backups) == 1

    with sqlite3.connect(backups[0]) as backup_connection:
        assert backup_connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0001_create_projects",)
        assert backup_connection.execute(
            "SELECT name FROM projects WHERE id = 'PROJECT_F01_EXISTING'"
        ).fetchone() == ("F01 已有项目",)
        assert backup_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_videos'"
        ).fetchone() is None

    with sqlite3.connect(database_path) as upgraded_connection:
        assert upgraded_connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_HEAD,)
        assert upgraded_connection.execute(
            "SELECT name FROM projects WHERE id = 'PROJECT_F01_EXISTING'"
        ).fetchone() == ("F01 已有项目",)
        assert upgraded_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_videos'"
        ).fetchone() == ("source_videos",)


def test_database_at_current_head_does_not_repeat_backup(tmp_path: Path) -> None:
    """旧库升级只备份一次；到达当前 head 后重复启动不能不断生成备份。"""

    app_data_dir = tmp_path / "app-data"
    database_path = _create_f01_database(app_data_dir)
    _insert_f01_project(database_path)

    init_database(app_data_dir)
    first_backups = list((app_data_dir / "backups").glob("*.db"))
    init_database(app_data_dir)
    second_backups = list((app_data_dir / "backups").glob("*.db"))

    assert len(first_backups) == 1
    assert second_backups == first_backups


def test_source_videos_table_has_exact_f02_columns(tmp_path: Path) -> None:
    """后续 Additive Migration 后仍必须保留 F02 Contract 定义的 Source Video 字段。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        columns = connection.execute("PRAGMA table_info(source_videos)").fetchall()

    assert {column[1] for column in columns} == EXPECTED_SOURCE_VIDEO_COLUMNS


def test_importing_row_can_exist_before_media_metadata_is_known(tmp_path: Path) -> None:
    """导入开始时只知道 Source/Project/文件名/目标路径，媒体元数据允许暂时为空。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PROJECT_A",
                "测试项目",
                "zh",
                "en",
                "US",
                "C:/projects/a",
                1,
                "ready",
                "2026-08-24T00:00:00+00:00",
                None,
            ),
        )
        connection.execute(
            """
            INSERT INTO source_videos (
                id, project_id, original_filename, relative_path, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "SOURCE_A",
                "PROJECT_A",
                "原片.mp4",
                "source/SOURCE_A/original.mp4",
                "importing",
                "2026-08-24T00:01:00+00:00",
            ),
        )
        connection.commit()

        row = connection.execute(
            "SELECT status, sha256, duration_us FROM source_videos WHERE id='SOURCE_A'"
        ).fetchone()

    assert row == ("importing", None, None)


def test_ready_row_requires_complete_core_media_metadata(tmp_path: Path) -> None:
    """不能把缺少 SHA/时长/主视频流信息的 Source 冒充为 ready。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, source_language, target_language, target_region,
                workspace_path, project_format_version, status, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PROJECT_A",
                "测试项目",
                "zh",
                "en",
                "US",
                "C:/projects/a",
                1,
                "ready",
                "2026-08-24T00:00:00+00:00",
                None,
            ),
        )

        try:
            connection.execute(
                """
                INSERT INTO source_videos (
                    id, project_id, original_filename, relative_path, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "SOURCE_A",
                    "PROJECT_A",
                    "原片.mp4",
                    "source/SOURCE_A/original.mp4",
                    "ready",
                    "2026-08-24T00:01:00+00:00",
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("ready Source 必须具备完整核心媒体元数据")
