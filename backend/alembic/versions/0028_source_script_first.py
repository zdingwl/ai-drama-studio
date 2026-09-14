"""Add formal script-first SOURCE_SCRIPT storage.

Revision ID: 0028_source_script_first
Revises: 0027_p15_p16_p17_replica_production
Create Date: 2026-09-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_source_script_first"
down_revision = "0027_p15_p16_p17_replica_production"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_script_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("source_video_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_dialogue_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_bible_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "source_video_artifact_id", "source_dialogue_artifact_id", "source_bible_artifact_id", "generated_by_task_id"):
        op.create_index(f"ix_source_script_revisions_{column}", "source_script_revisions", [column])
    with op.batch_alter_table("replica_target_revisions") as batch_op:
        batch_op.alter_column("source_snapshot_artifact_id", existing_type=sa.String(36), nullable=True)
        batch_op.add_column(sa.Column("source_script_artifact_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key("fk_replica_target_revisions_source_script_artifact_id", "artifact_nodes", ["source_script_artifact_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_index("ix_replica_target_revisions_source_script_artifact_id", ["source_script_artifact_id"])
    with op.batch_alter_table("replica_target_script_revisions") as batch_op:
        batch_op.alter_column("source_snapshot_artifact_id", existing_type=sa.String(36), nullable=True)
        batch_op.add_column(sa.Column("source_script_artifact_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key("fk_replica_target_script_revisions_source_script_artifact_id", "artifact_nodes", ["source_script_artifact_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_index("ix_replica_target_script_revisions_source_script_artifact_id", ["source_script_artifact_id"])
    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.6.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    op.execute(sa.text("UPDATE project_execution_plans SET is_current = 0"))
    op.execute(sa.text("UPDATE projects SET current_plan_id = NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    target_count = bind.execute(sa.text("SELECT COUNT(*) FROM replica_target_revisions WHERE source_script_artifact_id IS NOT NULL")).scalar_one()
    script_count = bind.execute(sa.text("SELECT COUNT(*) FROM replica_target_script_revisions WHERE source_script_artifact_id IS NOT NULL")).scalar_one()
    if target_count or script_count:
        raise RuntimeError("Cannot downgrade 0028 while Script-first Target revisions exist")
    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.5.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    with op.batch_alter_table("replica_target_script_revisions") as batch_op:
        batch_op.drop_index("ix_replica_target_script_revisions_source_script_artifact_id")
        batch_op.drop_constraint("fk_replica_target_script_revisions_source_script_artifact_id", type_="foreignkey")
        batch_op.drop_column("source_script_artifact_id")
        batch_op.alter_column("source_snapshot_artifact_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("replica_target_revisions") as batch_op:
        batch_op.drop_index("ix_replica_target_revisions_source_script_artifact_id")
        batch_op.drop_constraint("fk_replica_target_revisions_source_script_artifact_id", type_="foreignkey")
        batch_op.drop_column("source_script_artifact_id")
        batch_op.alter_column("source_snapshot_artifact_id", existing_type=sa.String(36), nullable=False)
    for column in reversed(("project_id", "artifact_id", "source_video_artifact_id", "source_dialogue_artifact_id", "source_bible_artifact_id", "generated_by_task_id")):
        op.drop_index(f"ix_source_script_revisions_{column}", table_name="source_script_revisions")
    op.drop_table("source_script_revisions")
    op.execute(sa.text("UPDATE project_execution_plans SET is_current = 0"))
    op.execute(sa.text("UPDATE projects SET current_plan_id = NULL"))
