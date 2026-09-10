"""Add formal P9 source resolution revisions.

Revision ID: 0016_p9_source_resolution
Revises: 0015_p6_ocr_subtitle_v4
Create Date: 2026-09-10

P9 stores typed, versioned Source Character/Speaker/Scene/Prop resolution payloads behind
ArtifactNode revisions. This migration does not create SOURCE_VIDEO_SNAPSHOT and does not change
P9 capability availability.
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_p9_source_resolution"
down_revision = "0015_p6_ocr_subtitle_v4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_resolution_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("resolution_kind", sa.String(length=24), nullable=False),
        sa.Column("source_video_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_shot_facts_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("shot_anchors_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_dialogue_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"]),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["shot_anchors_artifact_id"], ["artifact_nodes.id"]),
        sa.ForeignKeyConstraint(["source_bible_artifact_id"], ["artifact_nodes.id"]),
        sa.ForeignKeyConstraint(["source_dialogue_artifact_id"], ["artifact_nodes.id"]),
        sa.ForeignKeyConstraint(["source_shot_facts_artifact_id"], ["artifact_nodes.id"]),
        sa.ForeignKeyConstraint(["source_video_artifact_id"], ["artifact_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id"),
    )
    op.create_index("ix_source_resolution_revisions_project_id", "source_resolution_revisions", ["project_id"])
    op.create_index("ix_source_resolution_revisions_artifact_id", "source_resolution_revisions", ["artifact_id"], unique=True)
    op.create_index("ix_source_resolution_revisions_resolution_kind", "source_resolution_revisions", ["resolution_kind"])
    op.create_index("ix_source_resolution_revisions_source_video_artifact_id", "source_resolution_revisions", ["source_video_artifact_id"])
    op.create_index("ix_source_resolution_revisions_source_bible_artifact_id", "source_resolution_revisions", ["source_bible_artifact_id"])
    op.create_index("ix_source_resolution_revisions_source_shot_facts_artifact_id", "source_resolution_revisions", ["source_shot_facts_artifact_id"])
    op.create_index("ix_source_resolution_revisions_shot_anchors_artifact_id", "source_resolution_revisions", ["shot_anchors_artifact_id"])
    op.create_index("ix_source_resolution_revisions_source_dialogue_artifact_id", "source_resolution_revisions", ["source_dialogue_artifact_id"])
    op.create_index("ix_source_resolution_revisions_generated_by_task_id", "source_resolution_revisions", ["generated_by_task_id"])


def downgrade() -> None:
    op.drop_index("ix_source_resolution_revisions_generated_by_task_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_source_dialogue_artifact_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_shot_anchors_artifact_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_source_shot_facts_artifact_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_source_bible_artifact_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_source_video_artifact_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_resolution_kind", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_artifact_id", table_name="source_resolution_revisions")
    op.drop_index("ix_source_resolution_revisions_project_id", table_name="source_resolution_revisions")
    op.drop_table("source_resolution_revisions")
