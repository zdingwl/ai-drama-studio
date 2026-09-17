"""Add optional episode scope to artifact nodes.

Revision ID: 0031_artifact_episode_scope
Revises: 0030_replica_five_step_pipeline
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_artifact_episode_scope"
down_revision = "0030_replica_five_step_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifact_nodes",
        sa.Column("episode_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_artifact_nodes_episode_id",
        "artifact_nodes",
        "episodes",
        ["episode_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_artifact_nodes_episode_id", "artifact_nodes", ["episode_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_nodes_episode_id", table_name="artifact_nodes")
    op.drop_constraint("fk_artifact_nodes_episode_id", "artifact_nodes", type_="foreignkey")
    op.drop_column("artifact_nodes", "episode_id")
