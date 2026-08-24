"""F03：创建 Source Video 预处理派生资产表。

业务目的：
- 为 F02 冻结 Source Video 保存统一的分析 Proxy、WAV、Thumbnail；
- 保存 Source ↔ Proxy / Audio 的明确时间映射，供 F04+ 使用；
- processing 阶段允许尚未生成的媒体元数据为空；
- ready 阶段由数据库 CHECK 强制核心派生资产完整；
- 本 Migration 只做 Additive Change，不修改 F01/F02 已冻结表字段语义。
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_create_source_preprocess"
down_revision = "0002_create_source_videos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 F03 唯一业务表 ``source_preprocess``。"""

    op.create_table(
        "source_preprocess",
        sa.Column(
            "source_video_id",
            sa.String(),
            nullable=False,
            comment="F02 Source Video ID，同时作为 F03 预处理资产集唯一主键。",
        ),
        sa.Column(
            "project_id",
            sa.String(),
            nullable=False,
            comment="所属 F01 Project ID，便于项目级读取。",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="processing",
            comment="F03 状态；只允许 processing 或 ready。",
        ),
        sa.Column(
            "profile_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="固定预处理参数版本；F03 V1 固定为 1。",
        ),
        sa.Column(
            "source_sha256_snapshot",
            sa.String(length=64),
            nullable=False,
            comment="F03 开始前重新核验得到的 Source SHA-256 快照。",
        ),
        sa.Column(
            "proxy_relative_path",
            sa.Text(),
            nullable=False,
            comment="相对 Project Workspace 的 proxy.mp4 正式路径。",
        ),
        sa.Column(
            "proxy_file_size_bytes",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy 完成后的真实文件大小；processing 阶段未知可空。",
        ),
        sa.Column(
            "proxy_sha256",
            sa.String(length=64),
            nullable=True,
            comment="Proxy 文件 SHA-256；ready 时必填。",
        ),
        sa.Column(
            "proxy_duration_us",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy Source-domain 权威时长，整数微秒。",
        ),
        sa.Column(
            "proxy_video_time_base_num",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy 主视频流 time_base 分子。",
        ),
        sa.Column(
            "proxy_video_time_base_den",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy 主视频流 time_base 分母。",
        ),
        sa.Column(
            "proxy_fps_num",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy avg_frame_rate 分子；VFR/未知时允许为空。",
        ),
        sa.Column(
            "proxy_fps_den",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy avg_frame_rate 分母；VFR/未知时允许为空。",
        ),
        sa.Column(
            "proxy_to_source_offset_us",
            sa.BigInteger(),
            nullable=True,
            comment="Proxy→Source 线性 offset：source_us = proxy_us + offset。",
        ),
        sa.Column(
            "audio_relative_path",
            sa.Text(),
            nullable=True,
            comment="分析 audio.wav 相对路径；Source 无音频时为空。",
        ),
        sa.Column(
            "audio_file_size_bytes",
            sa.BigInteger(),
            nullable=True,
            comment="分析 WAV 文件大小；无音频时为空。",
        ),
        sa.Column(
            "audio_sha256",
            sa.String(length=64),
            nullable=True,
            comment="分析 WAV SHA-256；无音频时为空。",
        ),
        sa.Column(
            "audio_duration_us",
            sa.BigInteger(),
            nullable=True,
            comment="分析 WAV 时长，整数微秒。",
        ),
        sa.Column(
            "audio_sample_rate",
            sa.Integer(),
            nullable=True,
            comment="分析 WAV 采样率；F03 V1 有音频时固定为 16000。",
        ),
        sa.Column(
            "audio_channels",
            sa.Integer(),
            nullable=True,
            comment="分析 WAV 声道数；F03 V1 有音频时固定为 1。",
        ),
        sa.Column(
            "audio_to_source_offset_us",
            sa.BigInteger(),
            nullable=True,
            comment="Audio→Source 线性 offset：source_us = audio_us + offset。",
        ),
        sa.Column(
            "thumbnail_relative_path",
            sa.Text(),
            nullable=False,
            comment="thumbnail.jpg 相对 Workspace 的正式路径。",
        ),
        sa.Column(
            "thumbnail_file_size_bytes",
            sa.BigInteger(),
            nullable=True,
            comment="Thumbnail 文件大小；ready 时必填。",
        ),
        sa.Column(
            "thumbnail_sha256",
            sa.String(length=64),
            nullable=True,
            comment="Thumbnail SHA-256；ready 时必填。",
        ),
        sa.Column(
            "thumbnail_source_time_us",
            sa.BigInteger(),
            nullable=True,
            comment="Thumbnail 对应 Source Timeline 时间，整数微秒。",
        ),
        sa.Column(
            "source_video_time_base_num",
            sa.BigInteger(),
            nullable=True,
            comment="F03 运行时读取的 Source 主视频流 time_base 分子快照。",
        ),
        sa.Column(
            "source_video_time_base_den",
            sa.BigInteger(),
            nullable=True,
            comment="F03 运行时读取的 Source 主视频流 time_base 分母快照。",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="预处理记录创建时间，业务层统一写 UTC。",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="全部预处理派生资产校验并发布完成的 UTC 时间。",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'ready')",
            name="ck_source_preprocess_status",
        ),
        sa.CheckConstraint(
            "profile_version >= 1",
            name="ck_source_preprocess_profile_version",
        ),
        sa.CheckConstraint(
            "length(source_sha256_snapshot) = 64",
            name="ck_source_preprocess_source_hash",
        ),
        sa.CheckConstraint(
            "status != 'ready' OR ("
            "proxy_file_size_bytes > 0 AND "
            "proxy_sha256 IS NOT NULL AND length(proxy_sha256) = 64 AND "
            "proxy_duration_us > 0 AND "
            "proxy_video_time_base_num IS NOT NULL AND proxy_video_time_base_num != 0 AND "
            "proxy_video_time_base_den > 0 AND "
            "proxy_to_source_offset_us IS NOT NULL AND "
            "thumbnail_file_size_bytes > 0 AND "
            "thumbnail_sha256 IS NOT NULL AND length(thumbnail_sha256) = 64 AND "
            "thumbnail_source_time_us IS NOT NULL AND "
            "source_video_time_base_num IS NOT NULL AND source_video_time_base_num != 0 AND "
            "source_video_time_base_den > 0 AND "
            "completed_at IS NOT NULL"
            ")",
            name="ck_source_preprocess_ready_core",
        ),
        sa.CheckConstraint(
            "(audio_relative_path IS NULL AND "
            "audio_file_size_bytes IS NULL AND audio_sha256 IS NULL AND "
            "audio_duration_us IS NULL AND audio_sample_rate IS NULL AND "
            "audio_channels IS NULL AND audio_to_source_offset_us IS NULL) OR "
            "(audio_relative_path IS NOT NULL AND "
            "audio_file_size_bytes > 0 AND "
            "audio_sha256 IS NOT NULL AND length(audio_sha256) = 64 AND "
            "audio_duration_us > 0 AND audio_sample_rate = 16000 AND "
            "audio_channels = 1 AND audio_to_source_offset_us IS NOT NULL)",
            name="ck_source_preprocess_audio_all_or_none",
        ),
        sa.ForeignKeyConstraint(
            ["source_video_id"],
            ["source_videos.id"],
            name="fk_source_preprocess_source_video",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_source_preprocess_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "source_video_id",
            name="pk_source_preprocess",
        ),
        sa.UniqueConstraint(
            "project_id",
            name="uq_source_preprocess_project_id",
        ),
        sa.UniqueConstraint(
            "proxy_relative_path",
            name="uq_source_preprocess_proxy_path",
        ),
        sa.UniqueConstraint(
            "thumbnail_relative_path",
            name="uq_source_preprocess_thumbnail_path",
        ),
    )


def downgrade() -> None:
    """仅用于开发期 Schema 回退；不会删除 F02 Source 原片。"""

    op.drop_table("source_preprocess")
