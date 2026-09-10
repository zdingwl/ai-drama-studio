"""Add formal P10 source video snapshot revisions.

Revision ID: 0017_p10_source_video_snapshot
Revises: 0016_p9_source_resolution
Create Date: 2026-09-10

P10 freezes already accepted CURRENT Source Facts into a typed SOURCE_VIDEO_SNAPSHOT.
It does not invoke providers and does not change SOURCE_SNAPSHOT capability availability.
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_p10_source_video_snapshot"
down_revision = "0016_p9_source_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_video_snapshot_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_video_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("shot_anchors_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_dialogue_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("story_skeleton_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("rhythm_skeleton_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_shot_facts_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_characters_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_speakers_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_scenes_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_props_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rhythm_skeleton_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shot_anchors_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_bible_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_characters_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_dialogue_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_props_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_scenes_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_shot_facts_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_speakers_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_video_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["story_skeleton_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id"),
    )
    for column in (
        "project_id",
        "artifact_id",
        "source_video_artifact_id",
        "shot_anchors_artifact_id",
        "source_dialogue_artifact_id",
        "source_bible_artifact_id",
        "story_skeleton_artifact_id",
        "rhythm_skeleton_artifact_id",
        "source_shot_facts_artifact_id",
        "source_characters_artifact_id",
        "source_speakers_artifact_id",
        "source_scenes_artifact_id",
        "source_props_artifact_id",
        "generated_by_task_id",
    ):
        op.create_index(
            f"ix_source_video_snapshot_revisions_{column}",
            "source_video_snapshot_revisions",
            [column],
            unique=column == "artifact_id",
        )


def downgrade() -> None:
    for column in reversed(
        (
            "project_id",
            "artifact_id",
            "source_video_artifact_id",
            "shot_anchors_artifact_id",
            "source_dialogue_artifact_id",
            "source_bible_artifact_id",
            "story_skeleton_artifact_id",
            "rhythm_skeleton_artifact_id",
            "source_shot_facts_artifact_id",
            "source_characters_artifact_id",
            "source_speakers_artifact_id",
            "source_scenes_artifact_id",
            "source_props_artifact_id",
            "generated_by_task_id",
        )
    ):
        op.drop_index(f"ix_source_video_snapshot_revisions_{column}", table_name="source_video_snapshot_revisions")
    op.drop_table("source_video_snapshot_revisions")
