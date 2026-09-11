"""P13 target assets candidate and typed revision storage.

Revision ID: 0021_p13_target_assets
Revises: 0020_p12_target_script_preimplementation
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_p13_target_assets"
down_revision = "0020_p12_target_script_preimplementation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replica_target_assets_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_revision", sa.Integer(), nullable=False),
        sa.Column("target_bible_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=False),
        sa.Column("published_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("approval_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_bible_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_artifact_id"], ["artifact_nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generated_by_task_id"),
        sa.UniqueConstraint("published_artifact_id"),
    )
    op.create_index("ix_replica_target_assets_candidates_project_id", "replica_target_assets_candidates", ["project_id"])
    op.create_index("ix_replica_target_assets_candidates_target_bible_artifact_id", "replica_target_assets_candidates", ["target_bible_artifact_id"])
    op.create_index("ix_replica_target_assets_candidates_input_fingerprint", "replica_target_assets_candidates", ["input_fingerprint"])
    op.create_index("ix_replica_target_assets_candidates_status", "replica_target_assets_candidates", ["status"])
    op.create_index("ix_replica_target_assets_candidates_generated_by_task_id", "replica_target_assets_candidates", ["generated_by_task_id"])
    op.create_index("ix_replica_target_assets_candidates_published_artifact_id", "replica_target_assets_candidates", ["published_artifact_id"])

    op.create_table(
        "replica_target_assets_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_revision", sa.Integer(), nullable=False),
        sa.Column("target_bible_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=False),
        sa.Column("approved_from_candidate_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_bible_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_from_candidate_id"], ["replica_target_assets_candidates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id"),
        sa.UniqueConstraint("approved_from_candidate_id"),
    )
    op.create_index("ix_replica_target_assets_revisions_project_id", "replica_target_assets_revisions", ["project_id"])
    op.create_index("ix_replica_target_assets_revisions_artifact_id", "replica_target_assets_revisions", ["artifact_id"])
    op.create_index("ix_replica_target_assets_revisions_target_bible_artifact_id", "replica_target_assets_revisions", ["target_bible_artifact_id"])
    op.create_index("ix_replica_target_assets_revisions_generated_by_task_id", "replica_target_assets_revisions", ["generated_by_task_id"])
    op.create_index("ix_replica_target_assets_revisions_approved_from_candidate_id", "replica_target_assets_revisions", ["approved_from_candidate_id"])
    op.create_index("ix_replica_target_assets_revisions_input_fingerprint", "replica_target_assets_revisions", ["input_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_replica_target_assets_revisions_input_fingerprint", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_approved_from_candidate_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_generated_by_task_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_target_bible_artifact_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_artifact_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_project_id", table_name="replica_target_assets_revisions")
    op.drop_table("replica_target_assets_revisions")

    op.drop_index("ix_replica_target_assets_candidates_published_artifact_id", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_generated_by_task_id", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_status", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_input_fingerprint", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_target_bible_artifact_id", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_project_id", table_name="replica_target_assets_candidates")
    op.drop_table("replica_target_assets_candidates")
