"""F02：创建 Source Video 原片资产表。

业务目的：
- 一个 F01 Project 在 F02 V1 中最多保存一份 Source Video；
- 导入开始时先建立 ``importing`` 记录，使异常退出后可以恢复；
- 文件流式写入和 FFprobe 完成后，再补齐媒体元数据并切换为 ``ready``；
- Source Video 是后续 F03–F35 的只读源证据，不允许被后续流程覆盖。

为什么部分媒体字段允许 NULL：
``importing`` 记录是在真正读取完整文件、计算 SHA-256、执行 FFprobe 之前创建的，
因此此时还不知道文件大小、时长、编码、宽高等数据。只有 ``ready`` 状态才要求这些
字段全部有效，数据库通过 ``ck_source_videos_ready_metadata`` 做最终兜底。

本 Migration 是 Additive Change，不修改 F01 已冻结的 ``projects`` 字段语义。
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_create_source_videos"
down_revision = "0001_create_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 F02 唯一业务表 ``source_videos``。"""

    op.create_table(
        "source_videos",
        sa.Column(
            "id",
            sa.String(),
            nullable=False,
            comment="稳定 Source Video ID，格式 SOURCE_<UUID4_HEX>。",
        ),
        sa.Column(
            "project_id",
            sa.String(),
            nullable=False,
            comment="所属 F01 Project ID；F02 V1 一个项目最多一份 Source Video。",
        ),
        sa.Column(
            "original_filename",
            sa.Text(),
            nullable=False,
            comment="用户选择视频时的原始文件名，只用于展示和追溯，不参与内部路径生成。",
        ),
        sa.Column(
            "relative_path",
            sa.Text(),
            nullable=False,
            comment="相对 Project Workspace 的正式原片路径，例如 source/SOURCE_xxx/original.mp4。",
        ),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            nullable=True,
            comment="完整导入后的真实文件字节数；importing 阶段未知可空。",
        ),
        sa.Column(
            "sha256",
            sa.String(length=64),
            nullable=True,
            comment="完整原片内容 SHA-256 小写十六进制；importing 阶段未知可空。",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="importing",
            comment="导入状态；F02 只允许 importing 或 ready。",
        ),
        sa.Column(
            "container_format",
            sa.Text(),
            nullable=True,
            comment="FFprobe format_name；importing 阶段未知可空。",
        ),
        sa.Column(
            "duration_us",
            sa.BigInteger(),
            nullable=True,
            comment="Source Timeline 权威时长，整数微秒；ready 时必须大于 0。",
        ),
        sa.Column(
            "source_start_time_us",
            sa.BigInteger(),
            nullable=True,
            comment="FFprobe start_time 转换后的 Source 起始时间，整数微秒；未知可空。",
        ),
        sa.Column(
            "video_stream_index",
            sa.Integer(),
            nullable=True,
            comment="F02 选中的主视频流 index；ready 时必须存在。",
        ),
        sa.Column(
            "video_codec",
            sa.String(length=64),
            nullable=True,
            comment="主视频流 codec_name；ready 时必须存在。",
        ),
        sa.Column(
            "width",
            sa.Integer(),
            nullable=True,
            comment="主视频流编码宽度；ready 时必须大于 0。",
        ),
        sa.Column(
            "height",
            sa.Integer(),
            nullable=True,
            comment="主视频流编码高度；ready 时必须大于 0。",
        ),
        sa.Column(
            "fps_num",
            sa.BigInteger(),
            nullable=True,
            comment="主视频流 avg_frame_rate 分子；无法可靠取得时可空。",
        ),
        sa.Column(
            "fps_den",
            sa.BigInteger(),
            nullable=True,
            comment="主视频流 avg_frame_rate 分母；无法可靠取得时可空。",
        ),
        sa.Column(
            "audio_stream_index",
            sa.Integer(),
            nullable=True,
            comment="主音频流 index；无音频视频允许为空。",
        ),
        sa.Column(
            "audio_codec",
            sa.String(length=64),
            nullable=True,
            comment="主音频流 codec_name；无音频视频允许为空。",
        ),
        sa.Column(
            "audio_sample_rate",
            sa.Integer(),
            nullable=True,
            comment="主音频流采样率；无音频视频允许为空。",
        ),
        sa.Column(
            "audio_channels",
            sa.Integer(),
            nullable=True,
            comment="主音频流声道数；无音频视频允许为空。",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Source 导入记录创建时间，业务层统一写 UTC。",
        ),
        sa.CheckConstraint(
            "status IN ('importing', 'ready')",
            name="ck_source_videos_status",
        ),
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0",
            name="ck_source_videos_file_size",
        ),
        sa.CheckConstraint(
            "status != 'ready' OR ("
            "file_size_bytes > 0 AND "
            "sha256 IS NOT NULL AND length(sha256) = 64 AND "
            "container_format IS NOT NULL AND "
            "duration_us > 0 AND "
            "video_stream_index IS NOT NULL AND "
            "video_codec IS NOT NULL AND "
            "width > 0 AND height > 0"
            ")",
            name="ck_source_videos_ready_metadata",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_source_videos_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_videos"),
        sa.UniqueConstraint("project_id", name="uq_source_videos_project_id"),
        sa.UniqueConstraint("relative_path", name="uq_source_videos_relative_path"),
    )


def downgrade() -> None:
    """仅用于开发期 Schema 回退；不会作为用户层面的“删除原片”功能。"""

    op.drop_table("source_videos")
