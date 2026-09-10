"""Add isolated storyboard working draft revisions.

Revision ID: 0018_source_storyboard_working_draft
Revises: 0017_p10_source_video_snapshot
Create Date: 2026-09-10

The working draft is intentionally not a formal ArtifactNode. It stores user edits
without mutating SOURCE_SHOT_FACTS and without pretending that TARGET_STORYBOARD
capability is available.
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_source_storyboard_working_draft"
down_revision = "0017_p10_source_video_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_storyboard_draft_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("overrides_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_snapshot_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "revision", name="uq_source_storyboard_draft_project_revision"),
    )
    op.create_index(
        "ix_source_storyboard_draft_revisions_project_id",
        "source_storyboard_draft_revisions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_source_storyboard_draft_revisions_source_snapshot_artifact_id",
        "source_storyboard_draft_revisions",
        ["source_snapshot_artifact_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_storyboard_draft_revisions_source_snapshot_artifact_id",
        table_name="source_storyboard_draft_revisions",
    )
    op.drop_index(
        "ix_source_storyboard_draft_revisions_project_id",
        table_name="source_storyboard_draft_revisions",
    )
    op.drop_table("source_storyboard_draft_revisions")
