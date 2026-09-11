"""Add P13 Target Assets staging and typed revision storage.

Revision ID: 0021_p13_target_assets_preimplementation
Revises: 0020_p12_target_script_preimplementation
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_p13_target_assets_preimplementation"
down_revision = "0020_p12_target_script_preimplementation"
branch_labels = None
depends_on = None


_REPLICA_SKILL_ID = "project.replica"
_OLD_REPLICA_SKILL_VERSION = "1.2.0"
_NEW_REPLICA_SKILL_VERSION = "1.3.0"


def _invalidate_replica_plans() -> None:
    op.execute(
        sa.text(
            "UPDATE project_execution_plans SET is_current = 0 "
            "WHERE project_id IN ("
            "SELECT id FROM projects WHERE project_type = 'REPLICA' AND root_skill_id = :skill_id"
            ")"
        ).bindparams(skill_id=_REPLICA_SKILL_ID)
    )
    op.execute(
        sa.text(
            "UPDATE projects SET current_plan_id = NULL "
            "WHERE project_type = 'REPLICA' AND root_skill_id = :skill_id"
        ).bindparams(skill_id=_REPLICA_SKILL_ID)
    )


def upgrade() -> None:
    op.create_table(
        "replica_target_assets_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("base_target_assets_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("generation_sequence", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("review_reason", sa.String(length=800), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_bible_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_target_assets_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generated_by_task_id", name="uq_replica_target_assets_candidates_task_id"),
    )
    op.create_index("ix_replica_target_assets_candidates_project_id", "replica_target_assets_candidates", ["project_id"], unique=False)
    op.create_index("ix_replica_target_assets_candidates_target_bible_artifact_id", "replica_target_assets_candidates", ["target_bible_artifact_id"], unique=False)
    op.create_index("ix_replica_target_assets_candidates_base_target_assets_artifact_id", "replica_target_assets_candidates", ["base_target_assets_artifact_id"], unique=False)
    op.create_index("ix_replica_target_assets_candidates_generated_by_task_id", "replica_target_assets_candidates", ["generated_by_task_id"], unique=True)
    op.create_index("ix_replica_target_assets_candidates_input_fingerprint", "replica_target_assets_candidates", ["input_fingerprint"], unique=False)
    op.create_index("ix_replica_target_assets_candidates_review_status", "replica_target_assets_candidates", ["review_status"], unique=False)

    op.create_table(
        "replica_target_assets_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_bible_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["candidate_id"], ["replica_target_assets_candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", name="uq_replica_target_assets_revisions_artifact_id"),
    )
    op.create_index("ix_replica_target_assets_revisions_project_id", "replica_target_assets_revisions", ["project_id"], unique=False)
    op.create_index("ix_replica_target_assets_revisions_artifact_id", "replica_target_assets_revisions", ["artifact_id"], unique=False)
    op.create_index("ix_replica_target_assets_revisions_target_bible_artifact_id", "replica_target_assets_revisions", ["target_bible_artifact_id"], unique=False)
    op.create_index("ix_replica_target_assets_revisions_candidate_id", "replica_target_assets_revisions", ["candidate_id"], unique=False)
    op.create_index("ix_replica_target_assets_revisions_generated_by_task_id", "replica_target_assets_revisions", ["generated_by_task_id"], unique=False)

    # Root Skill 1.3.0 registers the P13 Professional Skill while preserving
    # target_assets requires=[TARGET_BIBLE]. TARGET_ASSETS remains PLANNED until P13 PASS.
    _invalidate_replica_plans()
    op.execute(
        sa.text(
            "UPDATE projects SET root_skill_version = :new_version, workflow_revision = workflow_revision + 1 "
            "WHERE project_type = 'REPLICA' AND root_skill_id = :skill_id "
            "AND root_skill_version = :old_version"
        ).bindparams(
            skill_id=_REPLICA_SKILL_ID,
            old_version=_OLD_REPLICA_SKILL_VERSION,
            new_version=_NEW_REPLICA_SKILL_VERSION,
        )
    )


def downgrade() -> None:
    _invalidate_replica_plans()
    op.execute(
        sa.text(
            "UPDATE projects SET root_skill_version = :old_version, workflow_revision = workflow_revision + 1 "
            "WHERE project_type = 'REPLICA' AND root_skill_id = :skill_id "
            "AND root_skill_version = :new_version"
        ).bindparams(
            skill_id=_REPLICA_SKILL_ID,
            old_version=_OLD_REPLICA_SKILL_VERSION,
            new_version=_NEW_REPLICA_SKILL_VERSION,
        )
    )

    op.drop_index("ix_replica_target_assets_revisions_generated_by_task_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_candidate_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_target_bible_artifact_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_artifact_id", table_name="replica_target_assets_revisions")
    op.drop_index("ix_replica_target_assets_revisions_project_id", table_name="replica_target_assets_revisions")
    op.drop_table("replica_target_assets_revisions")

    op.drop_index("ix_replica_target_assets_candidates_review_status", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_input_fingerprint", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_generated_by_task_id", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_base_target_assets_artifact_id", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_target_bible_artifact_id", table_name="replica_target_assets_candidates")
    op.drop_index("ix_replica_target_assets_candidates_project_id", table_name="replica_target_assets_candidates")
    op.drop_table("replica_target_assets_candidates")
