"""F04：创建本地 TransNetV2 自动拉片 Detection Run 与 Shot Candidate 表。

F04 只保存自动检测证据，不创建 Final Shot。所有正式时间使用 integer microseconds；
候选同时保存 Proxy 与 Source Timeline，Source 时间来自 F03 已冻结 mapping。
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_create_shot_detection"
down_revision = "0004_repair_source_preprocess_audio_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 F04 两张表；不修改 F01–F03 已冻结表结构。"""

    op.create_table(
        "shot_detection_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_video_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detector_name", sa.String(length=64), nullable=False),
        sa.Column("detector_profile_version", sa.Integer(), nullable=False),
        sa.Column("detector_threshold", sa.Float(), nullable=False),
        sa.Column("min_boundary_gap_us", sa.BigInteger(), nullable=False),
        sa.Column("detector_package_version", sa.String(length=32), nullable=False),
        sa.Column("torch_version", sa.String(length=64), nullable=True),
        sa.Column("detector_device", sa.String(length=128), nullable=True),
        sa.Column("ffprobe_version", sa.String(length=256), nullable=True),
        sa.Column("preprocess_profile_version", sa.Integer(), nullable=False),
        sa.Column("proxy_sha256_snapshot", sa.String(length=64), nullable=False),
        sa.Column("proxy_to_source_offset_us", sa.BigInteger(), nullable=False),
        sa.Column("proxy_start_us", sa.BigInteger(), nullable=True),
        sa.Column("proxy_end_us", sa.BigInteger(), nullable=True),
        sa.Column("source_start_us", sa.BigInteger(), nullable=True),
        sa.Column("source_end_us", sa.BigInteger(), nullable=True),
        sa.Column("analyzed_frame_count", sa.Integer(), nullable=True),
        sa.Column("detected_cut_count", sa.Integer(), nullable=True),
        sa.Column("shot_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_shot_detection_project"),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name="fk_shot_detection_source"),
        sa.UniqueConstraint("project_id", name="uq_shot_detection_project"),
        sa.CheckConstraint("status IN ('processing', 'ready')", name="ck_shot_detection_status"),
        sa.CheckConstraint("detector_profile_version >= 1", name="ck_shot_detection_profile"),
        sa.CheckConstraint("detector_threshold > 0 AND detector_threshold < 1", name="ck_shot_detection_threshold"),
        sa.CheckConstraint("min_boundary_gap_us >= 0", name="ck_shot_detection_gap"),
        sa.CheckConstraint(
            "status != 'ready' OR ("
            "torch_version IS NOT NULL AND detector_device IS NOT NULL AND ffprobe_version IS NOT NULL AND "
            "proxy_start_us IS NOT NULL AND proxy_end_us > proxy_start_us AND "
            "source_start_us IS NOT NULL AND source_end_us > source_start_us AND "
            "analyzed_frame_count > 0 AND detected_cut_count >= 0 AND shot_count >= 1 AND "
            "shot_count = detected_cut_count + 1 AND completed_at IS NOT NULL"
            ")",
            name="ck_shot_detection_ready_complete",
        ),
    )

    op.create_table(
        "shot_candidates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("detection_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("detected_proxy_start_us", sa.BigInteger(), nullable=False),
        sa.Column("detected_proxy_end_us", sa.BigInteger(), nullable=False),
        sa.Column("detected_start_us", sa.BigInteger(), nullable=False),
        sa.Column("detected_end_us", sa.BigInteger(), nullable=False),
        sa.Column("duration_us", sa.BigInteger(), nullable=False),
        sa.Column("end_boundary_kind", sa.String(length=16), nullable=False),
        sa.Column("end_boundary_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["detection_id"],
            ["shot_detection_runs.id"],
            name="fk_shot_candidate_detection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_shot_candidate_project"),
        sa.UniqueConstraint("detection_id", "ordinal", name="uq_shot_candidate_ordinal"),
        sa.CheckConstraint("ordinal >= 1", name="ck_shot_candidate_ordinal"),
        sa.CheckConstraint("detected_proxy_end_us > detected_proxy_start_us", name="ck_shot_candidate_proxy_range"),
        sa.CheckConstraint("detected_end_us > detected_start_us", name="ck_shot_candidate_source_range"),
        sa.CheckConstraint("duration_us = detected_end_us - detected_start_us", name="ck_shot_candidate_duration"),
        sa.CheckConstraint("end_boundary_kind IN ('cut', 'video_end')", name="ck_shot_candidate_boundary_kind"),
        sa.CheckConstraint(
            "(end_boundary_kind = 'cut' AND end_boundary_score IS NOT NULL) OR "
            "(end_boundary_kind = 'video_end' AND end_boundary_score IS NULL)",
            name="ck_shot_candidate_boundary_score",
        ),
    )


def downgrade() -> None:
    """只回退 F04 新表；F01–F03 数据保持不变。"""

    op.drop_table("shot_candidates")
    op.drop_table("shot_detection_runs")
