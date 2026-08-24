"""F04：创建本地 TransNetV2 自动拉片 Detection Run 与 Shot Candidate 表。

F04 只保存自动检测证据，不创建 Final Shot。所有正式时间使用 integer microseconds；
候选同时保存 Proxy 与 Source Timeline，Source 时间来自 F03 已冻结 mapping。

本迁移只新增 F04 表，可以整体 downgrade；不会修改 F01–F03 已冻结字段。
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
        # 一次自动拉片运行的稳定业务 ID；ready 后用于关联全部自动 Candidate。
        sa.Column("id", sa.String(length=64), primary_key=True),
        # 该 Detection Run 所属 F01 项目；V1 每个项目只保留一份 ready 自动证据。
        sa.Column("project_id", sa.String(length=64), nullable=False),
        # 本次结果基于哪一个 F02 Source；与 F03 快照一起用于 stale 检查。
        sa.Column("source_video_id", sa.String(length=64), nullable=False),
        # processing 表示模型正在执行；ready 表示候选与运行元数据已经同事务完整提交。
        sa.Column("status", sa.String(length=16), nullable=False),
        # 固定算法身份；V1 为 transnetv2_pytorch，不允许 UI 随意改成其它检测器。
        sa.Column("detector_name", sa.String(length=64), nullable=False),
        # 固定算法 Profile 版本；以后阈值/归一化规则变化必须升版，而不是静默改变历史语义。
        sa.Column("detector_profile_version", sa.Integer(), nullable=False),
        # 单帧 transition sigmoid score 的固定判断阈值；V1 = 0.5。
        sa.Column("detector_threshold", sa.Float(), nullable=False),
        # 相邻自动 Cut 小于该窗口时确定性去抖；单位 integer microseconds。
        sa.Column("min_boundary_gap_us", sa.BigInteger(), nullable=False),
        # Python 分发包版本，用于将来复现本次模型实现。
        sa.Column("detector_package_version", sa.String(length=32), nullable=False),
        # 实际执行时的 PyTorch 版本；processing 尚未完成推理时允许为空。
        sa.Column("torch_version", sa.String(length=64), nullable=True),
        # 实际计算设备，例如 cuda:0 / cpu；只在推理成功后落值。
        sa.Column("detector_device", sa.String(length=128), nullable=True),
        # 实际读取逐帧 PTS 的 FFprobe 版本；时间证据可追溯所需。
        sa.Column("ffprobe_version", sa.String(length=256), nullable=True),
        # F03 Profile 快照；F03 变化后旧 F04 不允许假装仍然有效。
        sa.Column("preprocess_profile_version", sa.Integer(), nullable=False),
        # F03 Proxy 内容身份快照；运行前/commit 前均重新计算 SHA-256。
        sa.Column("proxy_sha256_snapshot", sa.String(length=64), nullable=False),
        # F03 已冻结的 Proxy→Source 映射快照；下游权威时间属于 Source Domain。
        sa.Column("proxy_to_source_offset_us", sa.BigInteger(), nullable=False),
        # 以下检测区间与统计只有 ready 后才具有完整业务含义。
        sa.Column("proxy_start_us", sa.BigInteger(), nullable=True),
        sa.Column("proxy_end_us", sa.BigInteger(), nullable=True),
        sa.Column("source_start_us", sa.BigInteger(), nullable=True),
        sa.Column("source_end_us", sa.BigInteger(), nullable=True),
        # 成功与 FFprobe PTS 一一对齐的模型 prediction 数量。
        sa.Column("analyzed_frame_count", sa.Integer(), nullable=True),
        # 归一化并去抖后的自动 Cut 数；理论上 shot_count = detected_cut_count + 1。
        sa.Column("detected_cut_count", sa.Integer(), nullable=True),
        # 自动 Shot Candidate 数；即使没有任何 Cut，也必须至少有一个覆盖整段视频的 Candidate。
        sa.Column("shot_count", sa.Integer(), nullable=True),
        # UTC 创建/完成时间；completed_at 为空表示尚未 ready。
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
        # Candidate 只是 F04 Auto Evidence，不是 F05 人工确认后的 Final Shot ID。
        sa.Column("id", sa.String(length=64), primary_key=True),
        # 所属 Detection Run；run 删除时 Candidate 一并删除，避免孤儿自动证据。
        sa.Column("detection_id", sa.String(length=64), nullable=False),
        # 冗余项目归属用于业务查询与后续 Feature 关联；必须与 Detection Run 项目一致。
        sa.Column("project_id", sa.String(length=64), nullable=False),
        # 1-based 镜头顺序；跨行连续性由 F04 业务层在 commit 前统一验证。
        sa.Column("ordinal", sa.Integer(), nullable=False),
        # 自动检测得到的 Proxy Timeline 半开区间 [start, end)。
        sa.Column("detected_proxy_start_us", sa.BigInteger(), nullable=False),
        sa.Column("detected_proxy_end_us", sa.BigInteger(), nullable=False),
        # 同一自动边界映射后的 Source Domain 半开区间；后续 Feature 以此作为权威自动时间证据。
        sa.Column("detected_start_us", sa.BigInteger(), nullable=False),
        sa.Column("detected_end_us", sa.BigInteger(), nullable=False),
        # Source 区间时长；必须严格等于 detected_end_us - detected_start_us。
        sa.Column("duration_us", sa.BigInteger(), nullable=False),
        # cut=模型自动边界；video_end=最后一个 Candidate 由视频终点自然收口。
        sa.Column("end_boundary_kind", sa.String(length=16), nullable=False),
        # TransNetV2 transition sigmoid score，范围 0..1；仅 cut 有值，不能解释成“准确率”。
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
            "end_boundary_score IS NULL OR (end_boundary_score >= 0 AND end_boundary_score <= 1)",
            name="ck_shot_candidate_boundary_score_range",
        ),
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
