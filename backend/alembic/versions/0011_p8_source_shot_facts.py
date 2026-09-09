"""Add P8 SOURCE_SHOT_FACTS revision storage.

Revision ID: 0011_p8_source_shot_facts
Revises: 0010_p7_grounding_contract_v2
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_p8_source_shot_facts"
down_revision = "0010_p7_grounding_contract_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_shot_facts_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("source_video_artifact_id", sa.String(), nullable=False),
        sa.Column("source_bible_artifact_id", sa.String(), nullable=False),
        sa.Column("shot_anchors_artifact_id", sa.String(), nullable=False),
        sa.Column("source_dialogue_artifact_id", sa.String(), nullable=False),
        sa.Column("generated_by_task_id", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(["source_video_artifact_id"], ["artifact_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id"),
    )
    op.create_index(op.f("ix_source_shot_facts_revisions_artifact_id"), "source_shot_facts_revisions", ["artifact_id"], unique=True)
    op.create_index(op.f("ix_source_shot_facts_revisions_generated_by_task_id"), "source_shot_facts_revisions", ["generated_by_task_id"], unique=False)
    op.create_index(op.f("ix_source_shot_facts_revisions_project_id"), "source_shot_facts_revisions", ["project_id"], unique=False)
    op.create_index(op.f("ix_source_shot_facts_revisions_shot_anchors_artifact_id"), "source_shot_facts_revisions", ["shot_anchors_artifact_id"], unique=False)
    op.create_index(op.f("ix_source_shot_facts_revisions_source_bible_artifact_id"), "source_shot_facts_revisions", ["source_bible_artifact_id"], unique=False)
    op.create_index(op.f("ix_source_shot_facts_revisions_source_dialogue_artifact_id"), "source_shot_facts_revisions", ["source_dialogue_artifact_id"], unique=False)
    op.create_index(op.f("ix_source_shot_facts_revisions_source_video_artifact_id"), "source_shot_facts_revisions", ["source_video_artifact_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_source_shot_facts_revisions_source_video_artifact_id"), table_name="source_shot_facts_revisions")
    op.drop_index(op.f("ix_source_shot_facts_revisions_source_dialogue_artifact_id"), table_name="source_shot_facts_revisions")
    op.drop_index(op.f("ix_source_shot_facts_revisions_source_bible_artifact_id"), table_name="source_shot_facts_revisions")
    op.drop_index(op.f("ix_source_shot_facts_revisions_shot_anchors_artifact_id"), table_name="source_shot_facts_revisions")
    op.drop_index(op.f("ix_source_shot_facts_revisions_project_id"), table_name="source_shot_facts_revisions")
    op.drop_index(op.f("ix_source_shot_facts_revisions_generated_by_task_id"), table_name="source_shot_facts_revisions")
    op.drop_index(op.f("ix_source_shot_facts_revisions_artifact_id"), table_name="source_shot_facts_revisions")
    op.drop_table("source_shot_facts_revisions")
