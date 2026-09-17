"""Add staged replica visual asset workspace.

Revision ID: 0032_replica_asset_workspace
Revises: 0031_artifact_episode_scope
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_replica_asset_workspace"
down_revision = "0031_artifact_episode_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replica_asset_workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_storyboard_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", name="uq_replica_asset_workspace_project"),
    )
    op.create_index("ix_replica_asset_workspaces_project_id", "replica_asset_workspaces", ["project_id"])
    op.create_index("ix_replica_asset_workspaces_target_storyboard_artifact_id", "replica_asset_workspaces", ["target_storyboard_artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_replica_asset_workspaces_target_storyboard_artifact_id", table_name="replica_asset_workspaces")
    op.drop_index("ix_replica_asset_workspaces_project_id", table_name="replica_asset_workspaces")
    op.drop_table("replica_asset_workspaces")
