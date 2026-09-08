"""create project and artifact graph tables

Revision ID: 0001_project_skill_kernel
Revises:
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_project_skill_kernel"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("project_type", sa.String(length=32), nullable=False),
        sa.Column("source_language", sa.String(length=32), nullable=True),
        sa.Column("target_language", sa.String(length=32), nullable=False),
        sa.Column("target_region", sa.String(length=64), nullable=False),
        sa.Column("scene_strategy", sa.String(length=16), nullable=False),
        sa.Column("audio_policy", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("workflow_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_project_type", "projects", ["project_type"], unique=False)

    op.create_table(
        "artifact_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=48), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifact_nodes_project_id", "artifact_nodes", ["project_id"], unique=False)
    op.create_index("ix_artifact_nodes_artifact_type", "artifact_nodes", ["artifact_type"], unique=False)
    op.create_index("ix_artifact_nodes_is_current", "artifact_nodes", ["is_current"], unique=False)

    op.create_table(
        "artifact_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_node_id", sa.String(length=36), nullable=False),
        sa.Column("target_node_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_node_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifact_edges_project_id", "artifact_edges", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_artifact_edges_project_id", table_name="artifact_edges")
    op.drop_table("artifact_edges")
    op.drop_index("ix_artifact_nodes_is_current", table_name="artifact_nodes")
    op.drop_index("ix_artifact_nodes_artifact_type", table_name="artifact_nodes")
    op.drop_index("ix_artifact_nodes_project_id", table_name="artifact_nodes")
    op.drop_table("artifact_nodes")
    op.drop_index("ix_projects_project_type", table_name="projects")
    op.drop_table("projects")
