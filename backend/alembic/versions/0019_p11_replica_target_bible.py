"""Add P11 Replica Target Bible typed revision storage.

Revision ID: 0019_p11_replica_target_bible
Revises: 0018_source_storyboard_working_draft
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_p11_replica_target_bible"
down_revision = "0018_source_storyboard_working_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replica_target_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_snapshot_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", name="uq_replica_target_revisions_artifact_id"),
    )
    op.create_index("ix_replica_target_revisions_project_id", "replica_target_revisions", ["project_id"], unique=False)
    op.create_index("ix_replica_target_revisions_artifact_id", "replica_target_revisions", ["artifact_id"], unique=False)
    op.create_index("ix_replica_target_revisions_artifact_kind", "replica_target_revisions", ["artifact_kind"], unique=False)
    op.create_index(
        "ix_replica_target_revisions_source_snapshot_artifact_id",
        "replica_target_revisions",
        ["source_snapshot_artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_replica_target_revisions_generated_by_task_id",
        "replica_target_revisions",
        ["generated_by_task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_replica_target_revisions_generated_by_task_id", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_source_snapshot_artifact_id", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_artifact_kind", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_artifact_id", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_project_id", table_name="replica_target_revisions")
    op.drop_table("replica_target_revisions")
