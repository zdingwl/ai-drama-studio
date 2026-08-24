"""F05：创建人工镜头修正 Edit Set 与 Final Shot 表。

F04 `shot_candidates` 继续保存不可覆盖的 Auto Evidence；F05 只在新表中保存人工最终边界。
Final Shot 是后续人物、对白、Scene、生成和 QC 统一关联的生产级 Shot 身份。

本迁移只新增 F05 表，不改写 0001–0005 历史结构。
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_create_final_shots"
down_revision = "0005_create_shot_detection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 F05 Edit Set 与 Final Shot；不修改 F04 自动检测表。"""

    op.create_table(
        "shot_edit_sets",
        # 一套人工镜头修正工作的稳定 ID；V1 每个项目只允许存在一套。
        sa.Column("id", sa.String(length=64), primary_key=True),
        # 所属 Project；UNIQUE 保证同一项目不会出现两套互相冲突的 Final Shot 时间轴。
        sa.Column("project_id", sa.String(length=64), nullable=False),
        # F05 初始化时所基于的 F04 Detection Run。该外键故意不级联删除，避免 F04 重跑悄悄破坏 Final Shot。
        sa.Column("source_detection_id", sa.String(length=64), nullable=False),
        # editing=允许修改；confirmed=人工确认后锁定，后续 Feature 可以稳定读取。
        sa.Column("status", sa.String(length=16), nullable=False),
        # 每次边界调整、拆分、合并或确认都会递增，用于前端/后续调试判断是否发生编辑。
        sa.Column("revision", sa.Integer(), nullable=False),
        # Final Shot 时间轴必须完整覆盖的 Source Domain 区间，来自 F04 ready Detection snapshot。
        sa.Column("source_start_us", sa.BigInteger(), nullable=False),
        sa.Column("source_end_us", sa.BigInteger(), nullable=False),
        # UTC 时间。confirmed_at 只在人工确认后有值。
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_shot_edit_set_project"),
        sa.ForeignKeyConstraint(
            ["source_detection_id"],
            ["shot_detection_runs.id"],
            name="fk_shot_edit_set_detection",
        ),
        sa.UniqueConstraint("project_id", name="uq_shot_edit_set_project"),
        sa.CheckConstraint("status IN ('editing', 'confirmed')", name="ck_shot_edit_set_status"),
        sa.CheckConstraint("revision >= 1", name="ck_shot_edit_set_revision"),
        sa.CheckConstraint("source_end_us > source_start_us", name="ck_shot_edit_set_source_range"),
        sa.CheckConstraint(
            "(status = 'editing' AND confirmed_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL)",
            name="ck_shot_edit_set_confirmed_at",
        ),
    )

    op.create_table(
        "final_shots",
        # 后续所有 Production Feature 使用的稳定 Shot ID；边界调整不会改变该 ID。
        sa.Column("id", sa.String(length=64), primary_key=True),
        # 所属 F05 Edit Set；Edit Set 删除时 Final Shot 一并删除。
        sa.Column("edit_set_id", sa.String(length=64), nullable=False),
        # 冗余项目归属，方便后续按 Project 查询，并防止跨项目关联混乱。
        sa.Column("project_id", sa.String(length=64), nullable=False),
        # 1-based 当前镜头顺序。拆分/合并后由业务层重新维护连续 ordinal。
        sa.Column("ordinal", sa.Integer(), nullable=False),
        # 人工工作区最终使用的 Source Domain 半开区间 [final_start_us, final_end_us)。
        sa.Column("final_start_us", sa.BigInteger(), nullable=False),
        sa.Column("final_end_us", sa.BigInteger(), nullable=False),
        # 必须严格等于 final_end_us - final_start_us，避免下游读取到不一致派生值。
        sa.Column("duration_us", sa.BigInteger(), nullable=False),
        # auto=尚未发生人工结构改变；manual=该 Shot 经过边界调整、拆分或合并。
        sa.Column("origin_kind", sa.String(length=16), nullable=False),
        # JSON 字符串，保存本 Shot 可追溯到哪些 F04 Candidate ID。拆分继承、合并取并集。
        sa.Column("origin_candidate_ids_json", sa.Text(), nullable=False),
        # UTC 创建/最后修改时间。
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["edit_set_id"],
            ["shot_edit_sets.id"],
            name="fk_final_shot_edit_set",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_final_shot_project"),
        sa.UniqueConstraint("edit_set_id", "ordinal", name="uq_final_shot_ordinal"),
        sa.CheckConstraint("ordinal >= 1", name="ck_final_shot_ordinal"),
        sa.CheckConstraint("final_end_us > final_start_us", name="ck_final_shot_range"),
        sa.CheckConstraint("duration_us = final_end_us - final_start_us", name="ck_final_shot_duration"),
        sa.CheckConstraint("origin_kind IN ('auto', 'manual')", name="ck_final_shot_origin_kind"),
        sa.CheckConstraint("length(origin_candidate_ids_json) >= 2", name="ck_final_shot_origin_json"),
    )


def downgrade() -> None:
    """只回退 F05 新表；F04 自动证据和更早数据保持不变。"""

    op.drop_table("final_shots")
    op.drop_table("shot_edit_sets")
