"""F03 0004 兼容迁移：修复用户已经执行过的旧版 0003 Audio CHECK。"""

from pathlib import Path
import sqlite3

from alembic import command

from engine.app.core.database import _build_alembic_config, init_database


OLD_REVISION = "0003_create_source_preprocess"
NEW_REVISION = "0004_repair_source_preprocess_audio_constraint"


def _create_deployed_old_0003_database(app_data_dir: Path) -> Path:
    """模拟真实用户场景：数据库 revision 已是 0003，但表仍带早期错误 Audio CHECK。"""

    app_data_dir.mkdir(parents=True, exist_ok=True)
    database_path = app_data_dir / "app.db"

    # 先通过正式 Migration 建立冻结的 F01/F02 表，再手工构造“历史上已经部署”的旧 F03 表。
    command.upgrade(_build_alembic_config(database_path), "0002_create_source_videos")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE source_preprocess (
                source_video_id VARCHAR NOT NULL,
                project_id VARCHAR NOT NULL,
                status VARCHAR(16) DEFAULT 'processing' NOT NULL,
                profile_version INTEGER DEFAULT '1' NOT NULL,
                source_sha256_snapshot VARCHAR(64) NOT NULL,
                proxy_relative_path TEXT NOT NULL,
                proxy_file_size_bytes BIGINT,
                proxy_sha256 VARCHAR(64),
                proxy_duration_us BIGINT,
                proxy_video_time_base_num BIGINT,
                proxy_video_time_base_den BIGINT,
                proxy_fps_num BIGINT,
                proxy_fps_den BIGINT,
                proxy_to_source_offset_us BIGINT,
                audio_relative_path TEXT,
                audio_file_size_bytes BIGINT,
                audio_sha256 VARCHAR(64),
                audio_duration_us BIGINT,
                audio_sample_rate INTEGER,
                audio_channels INTEGER,
                audio_to_source_offset_us BIGINT,
                thumbnail_relative_path TEXT NOT NULL,
                thumbnail_file_size_bytes BIGINT,
                thumbnail_sha256 VARCHAR(64),
                thumbnail_source_time_us BIGINT,
                source_video_time_base_num BIGINT,
                source_video_time_base_den BIGINT,
                created_at DATETIME NOT NULL,
                completed_at DATETIME,
                CONSTRAINT pk_source_preprocess PRIMARY KEY (source_video_id),
                CONSTRAINT uq_source_preprocess_project_id UNIQUE (project_id),
                CONSTRAINT uq_source_preprocess_proxy_path UNIQUE (proxy_relative_path),
                CONSTRAINT uq_source_preprocess_thumbnail_path UNIQUE (thumbnail_relative_path),
                CONSTRAINT ck_source_preprocess_status CHECK (status IN ('processing', 'ready')),
                CONSTRAINT ck_source_preprocess_profile_version CHECK (profile_version >= 1),
                CONSTRAINT ck_source_preprocess_source_hash CHECK (length(source_sha256_snapshot) = 64),
                CONSTRAINT ck_source_preprocess_ready_core CHECK (
                    status != 'ready' OR (
                        proxy_file_size_bytes > 0 AND
                        proxy_sha256 IS NOT NULL AND length(proxy_sha256) = 64 AND
                        proxy_duration_us > 0 AND
                        proxy_video_time_base_num IS NOT NULL AND proxy_video_time_base_num != 0 AND
                        proxy_video_time_base_den > 0 AND
                        proxy_to_source_offset_us IS NOT NULL AND
                        thumbnail_file_size_bytes > 0 AND
                        thumbnail_sha256 IS NOT NULL AND length(thumbnail_sha256) = 64 AND
                        thumbnail_source_time_us IS NOT NULL AND
                        source_video_time_base_num IS NOT NULL AND source_video_time_base_num != 0 AND
                        source_video_time_base_den > 0 AND
                        completed_at IS NOT NULL
                    )
                ),
                CONSTRAINT ck_source_preprocess_audio_all_or_none CHECK (
                    (audio_relative_path IS NULL AND
                     audio_file_size_bytes IS NULL AND audio_sha256 IS NULL AND
                     audio_duration_us IS NULL AND audio_sample_rate IS NULL AND
                     audio_channels IS NULL AND audio_to_source_offset_us IS NULL)
                    OR
                    (audio_relative_path IS NOT NULL AND
                     audio_file_size_bytes > 0 AND
                     audio_sha256 IS NOT NULL AND length(audio_sha256) = 64 AND
                     audio_duration_us > 0 AND audio_sample_rate = 16000 AND
                     audio_channels = 1 AND audio_to_source_offset_us IS NOT NULL)
                ),
                CONSTRAINT fk_source_preprocess_source_video
                    FOREIGN KEY(source_video_id) REFERENCES source_videos (id) ON DELETE RESTRICT,
                CONSTRAINT fk_source_preprocess_project
                    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
            )
            """
        )
        connection.execute("UPDATE alembic_version SET version_num = ?", (OLD_REVISION,))
        connection.commit()

    return database_path


def test_0004_repairs_deployed_old_0003_and_preserves_backup(tmp_path: Path) -> None:
    """旧 0003 自动备份后升级 0004，并允许有音频任务先建立 processing 恢复锚点。"""

    app_data = tmp_path / "app-data"
    database_path = _create_deployed_old_0003_database(app_data)

    # 先证明历史旧约束确实会拒绝 F03 当前合法的 processing 记录。
    with sqlite3.connect(database_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO source_preprocess (
                    source_video_id, project_id, status, profile_version,
                    source_sha256_snapshot, proxy_relative_path,
                    audio_relative_path, thumbnail_relative_path, created_at
                ) VALUES (
                    'SOURCE_OLD', 'PROJECT_OLD', 'processing', 1,
                    ?, 'preprocess/SOURCE_OLD/proxy.mp4',
                    'preprocess/SOURCE_OLD/audio.wav',
                    'preprocess/SOURCE_OLD/thumbnail.jpg', '2026-08-24'
                )
                """,
                ("a" * 64,),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("历史旧 Audio CHECK 应该拒绝 processing + audio target path")

    init_database(app_data)

    backups = list((app_data / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone() == (OLD_REVISION,)
        old_sql = backup.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_preprocess'"
        ).fetchone()[0]
        assert "ck_source_preprocess_audio_all_or_none" in old_sql

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (NEW_REVISION,)
        repaired_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_preprocess'"
        ).fetchone()[0]
        assert "ck_source_preprocess_audio_all_or_none" not in repaired_sql
        assert "ck_source_preprocess_audio_ready_consistency" in repaired_sql

        # 0004 后，有音频 Source 可以先保存 audio.wav 目标路径，其余元数据等生成完成后再补。
        connection.execute(
            """
            INSERT INTO source_preprocess (
                source_video_id, project_id, status, profile_version,
                source_sha256_snapshot, proxy_relative_path,
                audio_relative_path, thumbnail_relative_path, created_at
            ) VALUES (
                'SOURCE_NEW', 'PROJECT_NEW', 'processing', 1,
                ?, 'preprocess/SOURCE_NEW/proxy.mp4',
                'preprocess/SOURCE_NEW/audio.wav',
                'preprocess/SOURCE_NEW/thumbnail.jpg', '2026-08-24'
            )
            """,
            ("b" * 64,),
        )
        connection.rollback()


def test_0004_is_noop_for_current_correct_0003_schema(tmp_path: Path) -> None:
    """全新数据库执行当前 0003 后再到 0004，不应重复破坏正确表结构。"""

    app_data = tmp_path / "app-data"
    database_path = app_data / "app.db"
    app_data.mkdir(parents=True)

    command.upgrade(_build_alembic_config(database_path), OLD_REVISION)
    with sqlite3.connect(database_path) as before:
        sql_before = before.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_preprocess'"
        ).fetchone()[0]
        assert "ck_source_preprocess_audio_ready_consistency" in sql_before

    init_database(app_data)

    with sqlite3.connect(database_path) as after:
        assert after.execute("SELECT version_num FROM alembic_version").fetchone() == (NEW_REVISION,)
        sql_after = after.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_preprocess'"
        ).fetchone()[0]
        assert "ck_source_preprocess_audio_ready_consistency" in sql_after
