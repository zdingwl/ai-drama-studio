"""Add P12 Target Script typed revision storage and tighten Replica root inputs.

Revision ID: 0020_p12_target_script_preimplementation
Revises: 0019_p11_replica_target_bible
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_p12_target_script_preimplementation"
down_revision = "0019_p11_replica_target_bible"
branch_labels = None
depends_on = None


_REPLICA_SKILL_ID = "project.replica"
_OLD_REPLICA_SKILL_VERSION = "1.1.0"
_NEW_REPLICA_SKILL_VERSION = "1.2.0"


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
        "replica_target_script_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("adaptation_plan_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("target_bible_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_snapshot_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["adaptation_plan_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_bible_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", name="uq_replica_target_script_revisions_artifact_id"),
    )
    op.create_index("ix_replica_target_script_revisions_project_id", "replica_target_script_revisions", ["project_id"], unique=False)
    op.create_index("ix_replica_target_script_revisions_artifact_id", "replica_target_script_revisions", ["artifact_id"], unique=False)
    op.create_index("ix_replica_target_script_revisions_source_snapshot_artifact_id", "replica_target_script_revisions", ["source_snapshot_artifact_id"], unique=False)
    op.create_index("ix_replica_target_script_revisions_adaptation_plan_artifact_id", "replica_target_script_revisions", ["adaptation_plan_artifact_id"], unique=False)
    op.create_index("ix_replica_target_script_revisions_target_bible_artifact_id", "replica_target_script_revisions", ["target_bible_artifact_id"], unique=False)
    op.create_index("ix_replica_target_script_revisions_generated_by_task_id", "replica_target_script_revisions", ["generated_by_task_id"], unique=False)

    # P11 has passed real acceptance and P12 is now formally admitted for validation.
    # Root Skill 1.2.0 records the exact three P12 hard inputs. TARGET_SCRIPT itself
    # remains PLANNED until P12 completes its own real manual acceptance.
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

    op.drop_index("ix_replica_target_script_revisions_generated_by_task_id", table_name="replica_target_script_revisions")
    op.drop_index("ix_replica_target_script_revisions_target_bible_artifact_id", table_name="replica_target_script_revisions")
    op.drop_index("ix_replica_target_script_revisions_adaptation_plan_artifact_id", table_name="replica_target_script_revisions")
    op.drop_index("ix_replica_target_script_revisions_source_snapshot_artifact_id", table_name="replica_target_script_revisions")
    op.drop_index("ix_replica_target_script_revisions_artifact_id", table_name="replica_target_script_revisions")
    op.drop_index("ix_replica_target_script_revisions_project_id", table_name="replica_target_script_revisions")
    op.drop_table("replica_target_script_revisions")
