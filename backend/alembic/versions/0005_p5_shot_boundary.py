"""add P5 shot boundary sets and anchors

Revision ID: 0005_p5_shot_boundary
Revises: 0004_p4_task_provider_job
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_p5_shot_boundary"
down_revision: str | None = "0004_p4_task_provider_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shot_boundary_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("source_video_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("detector_profile_json", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_video_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "revision", name="uq_shot_boundary_set_episode_revision"),
        sa.UniqueConstraint("task_id", name="uq_shot_boundary_set_task"),
    )
    op.create_index("ix_shot_boundary_sets_project_id", "shot_boundary_sets", ["project_id"], unique=False)
    op.create_index("ix_shot_boundary_sets_episode_id", "shot_boundary_sets", ["episode_id"], unique=False)
    op.create_index(
        "ix_shot_boundary_sets_source_video_artifact_id",
        "shot_boundary_sets",
        ["source_video_artifact_id"],
        unique=False,
    )
    op.create_index("ix_shot_boundary_sets_task_id", "shot_boundary_sets", ["task_id"], unique=False)
    op.create_index("ix_shot_boundary_sets_input_fingerprint", "shot_boundary_sets", ["input_fingerprint"], unique=False)
    op.create_index("ix_shot_boundary_sets_is_current", "shot_boundary_sets", ["is_current"], unique=False)

    op.create_table(
        "shot_anchors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("shot_boundary_set_id", sa.String(length=36), nullable=False),
        sa.Column("shot_number", sa.Integer(), nullable=False),
        sa.Column("start_us", sa.BigInteger(), nullable=False),
        sa.Column("end_us", sa.BigInteger(), nullable=False),
        sa.Column("duration_us", sa.BigInteger(), nullable=False),
        sa.Column("thumbnail_relative_path", sa.String(length=768), nullable=False),
        sa.Column("reference_clip_relative_path", sa.String(length=768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shot_boundary_set_id"], ["shot_boundary_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shot_boundary_set_id", "shot_number", name="uq_shot_anchor_set_number"),
    )
    op.create_index("ix_shot_anchors_project_id", "shot_anchors", ["project_id"], unique=False)
    op.create_index("ix_shot_anchors_episode_id", "shot_anchors", ["episode_id"], unique=False)
    op.create_index("ix_shot_anchors_shot_boundary_set_id", "shot_anchors", ["shot_boundary_set_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shot_anchors_shot_boundary_set_id", table_name="shot_anchors")
    op.drop_index("ix_shot_anchors_episode_id", table_name="shot_anchors")
    op.drop_index("ix_shot_anchors_project_id", table_name="shot_anchors")
    op.drop_table("shot_anchors")

    op.drop_index("ix_shot_boundary_sets_is_current", table_name="shot_boundary_sets")
    op.drop_index("ix_shot_boundary_sets_input_fingerprint", table_name="shot_boundary_sets")
    op.drop_index("ix_shot_boundary_sets_task_id", table_name="shot_boundary_sets")
    op.drop_index("ix_shot_boundary_sets_source_video_artifact_id", table_name="shot_boundary_sets")
    op.drop_index("ix_shot_boundary_sets_episode_id", table_name="shot_boundary_sets")
    op.drop_index("ix_shot_boundary_sets_project_id", table_name="shot_boundary_sets")
    op.drop_table("shot_boundary_sets")
