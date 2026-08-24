"""F06：创建自动人物识别 Run / Candidate / Track Evidence 表。

F06 只读取已经 confirmed 的 F05 Final Shot，不修改 `final_shots`。
自动人物结果与后续 F07 Final Character 物理分离；本迁移不提前创建人物姓名、角色类型或人工修正字段。
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_create_character_detection"
down_revision = "0006_create_final_shots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 F06 三张自动 Evidence 表与当前 Run 唯一索引。"""

    op.create_table(
        "character_detection_runs",
        # 一次完整自动人物识别运行的稳定 ID；重跑会创建新 ID，历史 Run 不覆盖。
        sa.Column("id", sa.String(length=64), primary_key=True),
        # 所属 Project。
        sa.Column("project_id", sa.String(length=64), nullable=False),
        # F06 运行时冻结的 F05 Edit Set 身份与 revision，用于下游追溯/失效判断。
        sa.Column("source_edit_set_id", sa.String(length=64), nullable=False),
        sa.Column("source_edit_set_revision", sa.Integer(), nullable=False),
        # processing=正在运行；ready=完整验证通过；failed=失败但历史保留。
        sa.Column("status", sa.String(length=16), nullable=False),
        # 同一项目只允许一份 ready Run 被标为当前正式自动 Evidence。
        sa.Column("is_current", sa.Integer(), nullable=False, server_default="0"),
        # 算法与采样参数版本；用于未来阈值变化后识别结果来源。
        sa.Column("profile_version", sa.String(length=32), nullable=False),
        sa.Column("sampling_profile_json", sa.Text(), nullable=False),
        # YuNet/SFace 固定模型身份与真实权重 Hash。
        sa.Column("detector_model_id", sa.String(length=96), nullable=False),
        sa.Column("detector_model_sha256", sa.String(length=64), nullable=False),
        sa.Column("recognizer_model_id", sa.String(length=96), nullable=False),
        sa.Column("recognizer_model_sha256", sa.String(length=64), nullable=False),
        # 实际 OpenCV 运行版本和设备；F06 V1 为 CPU DNN。
        sa.Column("opencv_version", sa.String(length=32), nullable=False),
        sa.Column("runtime_device", sa.String(length=24), nullable=False),
        # 运行统计。processing 初始为 0，ready/failed 时写最终值。
        sa.Column("sampled_frame_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("face_observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("track_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        # UTC 时间与失败信息。processing 时 completed/error 必须为空。
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_character_detection_project"),
        sa.ForeignKeyConstraint(
            ["source_edit_set_id"],
            ["shot_edit_sets.id"],
            name="fk_character_detection_edit_set",
        ),
        sa.CheckConstraint("status IN ('processing', 'ready', 'failed')", name="ck_character_detection_status"),
        sa.CheckConstraint("is_current IN (0, 1)", name="ck_character_detection_current"),
        sa.CheckConstraint("source_edit_set_revision >= 1", name="ck_character_detection_revision"),
        sa.CheckConstraint("sampled_frame_count >= 0", name="ck_character_detection_sample_count"),
        sa.CheckConstraint("face_observation_count >= 0", name="ck_character_detection_face_count"),
        sa.CheckConstraint("track_count >= 0", name="ck_character_detection_track_count"),
        sa.CheckConstraint("candidate_count >= 0", name="ck_character_detection_candidate_count"),
        sa.CheckConstraint(
            "(status = 'processing' AND completed_at IS NULL AND error_code IS NULL) OR "
            "(status = 'ready' AND completed_at IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ck_character_detection_completion",
        ),
        sa.CheckConstraint("is_current = 0 OR status = 'ready'", name="ck_character_detection_current_ready"),
    )
    op.create_index(
        "ix_character_detection_project_created",
        "character_detection_runs",
        ["project_id", "created_at"],
        unique=False,
    )
    # SQLite partial unique index：历史 ready Run 可以保留，但每个项目当前正式 Run 最多一个。
    op.create_index(
        "uq_character_detection_current_project",
        "character_detection_runs",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
    )

    op.create_table(
        "character_candidates",
        # F06 自动聚类 Candidate ID。它不是 F07 Final Character ID。
        sa.Column("id", sa.String(length=72), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        # Run 内稳定显示顺序；ready 后不再修改。
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("track_count", sa.Integer(), nullable=False),
        sa.Column("shot_count", sa.Integer(), nullable=False),
        # Candidate 最早/最晚 Evidence sample 的 Source 时间。
        sa.Column("first_seen_us", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_us", sa.BigInteger(), nullable=False),
        # 自动 Cover 的 Evidence；JPEG 可从 source_time+bbox 重建，不存入数据库。
        sa.Column("cover_track_id", sa.String(length=64), nullable=False),
        sa.Column("cover_source_us", sa.BigInteger(), nullable=False),
        sa.Column("cover_bbox_json", sa.Text(), nullable=False),
        # SFace normalized float32 little-endian 聚类中心；禁止 pickle。
        sa.Column("centroid_embedding_blob", sa.LargeBinary(), nullable=False),
        # 单 Track Candidate 没有内部相似度，因此允许 NULL。
        sa.Column("cluster_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["character_detection_runs.id"], name="fk_character_candidate_run", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_character_candidate_project"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_character_candidate_ordinal"),
        sa.CheckConstraint("ordinal >= 1", name="ck_character_candidate_ordinal"),
        sa.CheckConstraint("track_count >= 1", name="ck_character_candidate_track_count"),
        sa.CheckConstraint("shot_count >= 1", name="ck_character_candidate_shot_count"),
        sa.CheckConstraint("last_seen_us >= first_seen_us", name="ck_character_candidate_range"),
        sa.CheckConstraint(
            "cluster_score IS NULL OR (cluster_score >= 0 AND cluster_score <= 1)",
            name="ck_character_candidate_score",
        ),
    )

    op.create_table(
        "character_tracks",
        # 一个 Final Shot 内的一段人物人脸 Evidence Track；Track 不跨 Shot。
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("final_shot_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=72), nullable=False),
        # 当前 Shot 内 1-based Track 顺序，仅用于稳定 UI/调试排序。
        sa.Column("track_ordinal_in_shot", sa.Integer(), nullable=False),
        # Track 真实 Evidence sample 的最早/最晚 Source 时间，不伪装成连续可见区间。
        sa.Column("start_us", sa.BigInteger(), nullable=False),
        sa.Column("end_us", sa.BigInteger(), nullable=False),
        # 自动选择的最佳人脸 Evidence，用于 Track/Candidate Cover 重建。
        sa.Column("representative_source_us", sa.BigInteger(), nullable=False),
        sa.Column("representative_bbox_json", sa.Text(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("mean_face_quality", sa.Float(), nullable=False),
        sa.Column("max_face_quality", sa.Float(), nullable=False),
        # SFace normalized float32 little-endian Track mean embedding；禁止 pickle。
        sa.Column("track_embedding_blob", sa.LargeBinary(), nullable=False),
        # 轻量 Evidence JSON：source_time/bbox/detection_score/quality；不保存 JPEG/base64/逐帧 embedding。
        sa.Column("samples_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["character_detection_runs.id"], name="fk_character_track_run", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["character_candidates.id"], name="fk_character_track_candidate", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_character_track_project"),
        sa.ForeignKeyConstraint(["final_shot_id"], ["final_shots.id"], name="fk_character_track_final_shot"),
        sa.UniqueConstraint(
            "run_id", "final_shot_id", "track_ordinal_in_shot", name="uq_character_track_ordinal_in_shot"
        ),
        sa.CheckConstraint("track_ordinal_in_shot >= 1", name="ck_character_track_ordinal"),
        sa.CheckConstraint("end_us >= start_us", name="ck_character_track_range"),
        sa.CheckConstraint(
            "representative_source_us >= start_us AND representative_source_us <= end_us",
            name="ck_character_track_representative_time",
        ),
        sa.CheckConstraint("sample_count >= 1", name="ck_character_track_sample_count"),
        sa.CheckConstraint("mean_face_quality >= 0 AND mean_face_quality <= 1", name="ck_character_track_mean_quality"),
        sa.CheckConstraint("max_face_quality >= 0 AND max_face_quality <= 1", name="ck_character_track_max_quality"),
        sa.CheckConstraint("max_face_quality >= mean_face_quality", name="ck_character_track_quality_order"),
    )
    op.create_index("ix_character_track_candidate", "character_tracks", ["candidate_id", "start_us"], unique=False)
    op.create_index("ix_character_track_shot", "character_tracks", ["final_shot_id", "start_us"], unique=False)


def downgrade() -> None:
    """只删除 F06 自动人物 Evidence；F05 Final Shot 与更早冻结数据保持不变。"""

    op.drop_index("ix_character_track_shot", table_name="character_tracks")
    op.drop_index("ix_character_track_candidate", table_name="character_tracks")
    op.drop_table("character_tracks")
    op.drop_table("character_candidates")
    op.drop_index("uq_character_detection_current_project", table_name="character_detection_runs")
    op.drop_index("ix_character_detection_project_created", table_name="character_detection_runs")
    op.drop_table("character_detection_runs")
