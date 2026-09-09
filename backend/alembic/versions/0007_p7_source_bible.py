"""add P7 SOURCE_BIBLE revisions

Revision ID: 0007_p7_source_bible
Revises: 0006_p6_source_evidence
Create Date: 2026-09-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_p7_source_bible"
down_revision: str | None = "0006_p6_source_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_bible_revisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("source_video_artifact_id", sa.String(36), nullable=False),
        sa.Column("source_dialogue_artifact_id", sa.String(36), nullable=False),
        sa.Column("shot_anchors_artifact_id", sa.String(36), nullable=True),
        sa.Column("generated_by_task_id", sa.String(36), nullable=True),
        sa.Column("edit_parent_artifact_id", sa.String(36), nullable=True),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edit_parent_artifact_id"], ["artifact_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shot_anchors_artifact_id"], ["artifact_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_dialogue_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_video_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id"),
    )
    for column in (
        "project_id",
        "artifact_id",
        "source_video_artifact_id",
        "source_dialogue_artifact_id",
        "shot_anchors_artifact_id",
        "generated_by_task_id",
        "edit_parent_artifact_id",
    ):
        op.create_index(f"ix_source_bible_revisions_{column}", "source_bible_revisions", [column], unique=False)


def downgrade() -> None:
    for column in (
        "edit_parent_artifact_id",
        "generated_by_task_id",
        "shot_anchors_artifact_id",
        "source_dialogue_artifact_id",
        "source_video_artifact_id",
        "artifact_id",
        "project_id",
    ):
        op.drop_index(f"ix_source_bible_revisions_{column}", table_name="source_bible_revisions")
    op.drop_table("source_bible_revisions")
