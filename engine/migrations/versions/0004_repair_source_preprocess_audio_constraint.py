"""F03：修复已经执行过旧版 0003 的 source_preprocess Audio CHECK。

背景：
- F03 早期 0003 把 Audio 设计成“全空或全完整”；
- 但正常 processing 阶段已经知道 ``audio.wav`` 目标路径，此时 size/hash/duration
  还未生成，因此旧 CHECK 会拒绝合法的 processing 记录；
- 后来虽然修正了 0003 文件，但用户已经执行过的 0003 数据库不会自动重跑 Migration。

本 0004 是兼容性修复：
- 只在数据库仍存在旧 ``ck_source_preprocess_audio_all_or_none`` 时重建表约束；
- 如果数据库已经具有正确 ``ck_source_preprocess_audio_ready_consistency``，则不重复重建；
- 不修改 F01 projects、F02 source_videos，也不修改任何 Workspace 媒体文件；
- 数据库升级前仍由 ``init_database()`` 的 SQLite Backup Gate 自动创建一致性备份。
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_repair_source_preprocess_audio_constraint"
down_revision = "0003_create_source_preprocess"
branch_labels = None
depends_on = None

OLD_CONSTRAINT = "ck_source_preprocess_audio_all_or_none"
NEW_CONSTRAINT = "ck_source_preprocess_audio_ready_consistency"
NEW_CONDITION = (
    "status != 'ready' OR ("
    "(audio_relative_path IS NULL AND "
    "audio_file_size_bytes IS NULL AND audio_sha256 IS NULL AND "
    "audio_duration_us IS NULL AND audio_sample_rate IS NULL AND "
    "audio_channels IS NULL AND audio_to_source_offset_us IS NULL) OR "
    "(audio_relative_path IS NOT NULL AND "
    "audio_file_size_bytes > 0 AND "
    "audio_sha256 IS NOT NULL AND length(audio_sha256) = 64 AND "
    "audio_duration_us > 0 AND audio_sample_rate = 16000 AND "
    "audio_channels = 1 AND audio_to_source_offset_us IS NOT NULL)"
    ")"
)


def upgrade() -> None:
    """把已部署旧 Audio CHECK 修成只在 ``ready`` 时要求完整元数据。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    checks = {
        constraint.get("name"): constraint
        for constraint in inspector.get_check_constraints("source_preprocess")
        if constraint.get("name")
    }

    has_old = OLD_CONSTRAINT in checks
    has_new = NEW_CONSTRAINT in checks

    # 全新数据库会先执行当前正确的 0003；此时 0004 只推进 revision，不做无意义表重建。
    if has_new and not has_old:
        return

    # SQLite 不能原地 ALTER CHECK；Alembic batch 会创建临时表、复制原数据、再原子替换。
    # 这里只调整 source_preprocess 的 CHECK，既有列、主键、唯一约束、外键和数据均保留。
    with op.batch_alter_table("source_preprocess", recreate="always") as batch_op:
        if has_old:
            batch_op.drop_constraint(OLD_CONSTRAINT, type_="check")
        if not has_new:
            batch_op.create_check_constraint(NEW_CONSTRAINT, NEW_CONDITION)


def downgrade() -> None:
    """兼容性修复不恢复已经确认错误的旧约束。

    当前仓库中的 canonical 0003 本身已经使用正确的新约束，因此从 0004 回退 revision 时
    保留新约束才与当前 0003 Schema 一致；不会重新制造 processing 无法落库的问题。
    """

    return
