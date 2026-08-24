"""F03 Migration 与 F01/F02 Additive 兼容性测试。"""

from pathlib import Path
import sqlite3

from alembic import command

from engine.app.core.database import _build_alembic_config, init_database

CURRENT_F03_HEAD = "0004_repair_source_preprocess_audio_constraint"

EXPECTED_PREPROCESS_COLUMNS = {
    "source_video_id",
    "project_id",
    "status",
    "profile_version",
    "source_sha256_snapshot",
    "proxy_relative_path",
    "proxy_file_size_bytes",
    "proxy_sha256",
    "proxy_duration_us",
    "proxy_video_time_base_num",
    "proxy_video_time_base_den",
    "proxy_fps_num",
    "proxy_fps_den",
    "proxy_to_source_offset_us",
    "audio_relative_path",
    "audio_file_size_bytes",
    "audio_sha256",
    "audio_duration_us",
    "audio_sample_rate",
    "audio_channels",
    "audio_to_source_offset_us",
    "thumbnail_relative_path",
    "thumbnail_file_size_bytes",
    "thumbnail_sha256",
    "thumbnail_source_time_us",
    "source_video_time_base_num",
    "source_video_time_base_den",
    "created_at",
    "completed_at",
}


def _create_f02_database(app_data_dir: Path) -> Path:
    """构造真实 0002 数据库，模拟已经通过用户验收的 F01+F02 app.db。"""

    app_data_dir.mkdir(parents=True, exist_ok=True)
    database_path = app_data_dir / "app.db"
    command.upgrade(
        _build_alembic_config(database_path),
        "0002_create_source_videos",
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
                "PROJECT_F03",
                "F03 Migration 测试",
                "zh",
                "en",
                "US",
                "C:/projects/f03",
                1,
                "ready",
                "2026-08-24T00:00:00+00:00",
                None,
            ),
        )
        connection.execute(
            """
            INSERT INTO source_videos (
                id, project_id, original_filename, relative_path,
                file_size_bytes, sha256, status, container_format,
                duration_us, video_stream_index, video_codec, width, height, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SOURCE_F03",
                "PROJECT_F03",
                "原片.mp4",
                "source/SOURCE_F03/original.mp4",
                1024,
                "a" * 64,
                "ready",
                "mov,mp4,m4a,3gp,3g2,mj2",
                10_000_000,
                0,
                "h264",
                1920,
                1080,
                "2026-08-24T00:01:00+00:00",
            ),
        )
        connection.commit()

    return database_path


def _insert_minimal_ready_source(connection: sqlite3.Connection) -> None:
    """为 Constraint 测试建立最小 F01 Project + F02 ready Source。"""

    connection.execute(
        """
        INSERT INTO projects (
            id, name, target_language, target_region,
            workspace_path, project_format_version, status, created_at
        ) VALUES ('PROJECT_A', 'A', 'en', 'US', 'C:/a', 1, 'ready', '2026-08-24')
        """
    )
    connection.execute(
        """
        INSERT INTO source_videos (
            id, project_id, original_filename, relative_path,
            file_size_bytes, sha256, status, container_format,
            duration_us, video_stream_index, video_codec, width, height, created_at
        ) VALUES ('SOURCE_A', 'PROJECT_A', 'a.mp4', 'source/SOURCE_A/original.mp4',
            100, ?, 'ready', 'mp4', 1000000, 0, 'h264', 1280, 720, '2026-08-24')
        """,
        ("b" * 64,),
    )


def test_upgrade_0002_to_f03_head_is_additive_and_preserves_frozen_data(tmp_path: Path) -> None:
    """升级到当前 F03 head 后，F01 Project 和 F02 Source 数据必须原样保留。"""

    app_data_dir = tmp_path / "app-data"
    database_path = _create_f02_database(app_data_dir)

    init_database(app_data_dir)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_F03_HEAD,)
        assert connection.execute(
            "SELECT name FROM projects WHERE id='PROJECT_F03'"
        ).fetchone() == ("F03 Migration 测试",)
        assert connection.execute(
            "SELECT original_filename FROM source_videos WHERE id='SOURCE_F03'"
        ).fetchone() == ("原片.mp4",)
        columns = connection.execute(
            "PRAGMA table_info(source_preprocess)"
        ).fetchall()

    assert {column[1] for column in columns} == EXPECTED_PREPROCESS_COLUMNS


def test_upgrade_0002_to_f03_head_creates_one_safe_backup(tmp_path: Path) -> None:
    """已存在 F02 数据库升级到当前 F03 head 前只创建一次 SQLite 安全备份。"""

    app_data_dir = tmp_path / "app-data"
    database_path = _create_f02_database(app_data_dir)

    init_database(app_data_dir)

    backups = list((app_data_dir / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup_connection:
        assert backup_connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0002_create_source_videos",)
        assert backup_connection.execute(
            "SELECT id FROM source_videos WHERE id='SOURCE_F03'"
        ).fetchone() == ("SOURCE_F03",)
        assert backup_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_preprocess'"
        ).fetchone() is None

    with sqlite3.connect(database_path) as upgraded_connection:
        assert upgraded_connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_F03_HEAD,)


def test_processing_row_can_exist_before_preprocess_outputs_are_known(tmp_path: Path) -> None:
    """processing 恢复锚点允许先保存 Proxy/Thumbnail 目标路径，媒体 metadata 暂空。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        _insert_minimal_ready_source(connection)
        connection.execute(
            """
            INSERT INTO source_preprocess (
                source_video_id, project_id, status, profile_version,
                source_sha256_snapshot, proxy_relative_path,
                thumbnail_relative_path, created_at
            ) VALUES ('SOURCE_A', 'PROJECT_A', 'processing', 1, ?,
                'preprocess/SOURCE_A/proxy.mp4',
                'preprocess/SOURCE_A/thumbnail.jpg', '2026-08-24')
            """,
            ("b" * 64,),
        )
        row = connection.execute(
            "SELECT status, proxy_sha256, proxy_duration_us FROM source_preprocess"
        ).fetchone()

    assert row == ("processing", None, None)


def test_processing_with_audio_target_path_can_wait_for_audio_metadata(tmp_path: Path) -> None:
    """有音频 Source 在 processing 时可以先确定 audio.wav 路径，不能被 ready 约束提前拒绝。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        _insert_minimal_ready_source(connection)
        connection.execute(
            """
            INSERT INTO source_preprocess (
                source_video_id, project_id, status, profile_version,
                source_sha256_snapshot, proxy_relative_path,
                audio_relative_path, thumbnail_relative_path, created_at
            ) VALUES ('SOURCE_A', 'PROJECT_A', 'processing', 1, ?,
                'preprocess/SOURCE_A/proxy.mp4',
                'preprocess/SOURCE_A/audio.wav',
                'preprocess/SOURCE_A/thumbnail.jpg', '2026-08-24')
            """,
            ("b" * 64,),
        )
        row = connection.execute(
            "SELECT audio_relative_path, audio_sha256 FROM source_preprocess"
        ).fetchone()

    assert row == ("preprocess/SOURCE_A/audio.wav", None)


def test_ready_row_requires_proxy_thumbnail_and_mapping_metadata(tmp_path: Path) -> None:
    """缺少 Proxy/Thumbnail/Timeline Mapping 时不能冒充 ready。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        _insert_minimal_ready_source(connection)
        try:
            connection.execute(
                """
                INSERT INTO source_preprocess (
                    source_video_id, project_id, status, profile_version,
                    source_sha256_snapshot, proxy_relative_path,
                    thumbnail_relative_path, created_at
                ) VALUES ('SOURCE_A', 'PROJECT_A', 'ready', 1, ?,
                    'preprocess/SOURCE_A/proxy.mp4',
                    'preprocess/SOURCE_A/thumbnail.jpg', '2026-08-24')
                """,
                ("b" * 64,),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("ready Preprocess 必须具备 Proxy/Thumbnail/Mapping 核心元数据")


def test_ready_audio_path_requires_complete_analysis_audio_metadata(tmp_path: Path) -> None:
    """ready 时若声明 audio.wav，就必须同时具备 size/hash/duration/16k/mono/offset。"""

    database_path = init_database(tmp_path / "app-data")

    with sqlite3.connect(database_path) as connection:
        _insert_minimal_ready_source(connection)
        try:
            connection.execute(
                """
                INSERT INTO source_preprocess (
                    source_video_id, project_id, status, profile_version,
                    source_sha256_snapshot,
                    proxy_relative_path, proxy_file_size_bytes, proxy_sha256,
                    proxy_duration_us, proxy_video_time_base_num, proxy_video_time_base_den,
                    proxy_to_source_offset_us,
                    audio_relative_path,
                    thumbnail_relative_path, thumbnail_file_size_bytes, thumbnail_sha256,
                    thumbnail_source_time_us,
                    source_video_time_base_num, source_video_time_base_den,
                    created_at, completed_at
                ) VALUES (
                    'SOURCE_A', 'PROJECT_A', 'ready', 1, ?,
                    'preprocess/SOURCE_A/proxy.mp4', 100, ?, 1000000, 1, 90000, 0,
                    'preprocess/SOURCE_A/audio.wav',
                    'preprocess/SOURCE_A/thumbnail.jpg', 50, ?, 100000,
                    1, 90000, '2026-08-24', '2026-08-24'
                )
                """,
                ("b" * 64, "c" * 64, "d" * 64),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("ready Audio 不能只有路径而缺少完整分析音频 metadata")
