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
    # SQLite does not support ALTER TABLE ADD CONSTRAINT. Use batch mode so
    # Alembic can rebuild the table while preserving SQLite compatibility.
    with op.batch_alter_table("artifact_nodes") as batch_op:
        batch_op.add_column(
            sa.Column("episode_id", sa.String(36), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_artifact_nodes_episode_id",
            "episodes",
            ["episode_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_index("ix_artifact_nodes_episode_id", "artifact_nodes", ["episode_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_nodes_episode_id", table_name="artifact_nodes")
    with op.batch_alter_table("artifact_nodes") as batch_op:
        batch_op.drop_constraint(
            "fk_artifact_nodes_episode_id",
            type_="foreignkey",
        )
        batch_op.drop_column("episode_id")
