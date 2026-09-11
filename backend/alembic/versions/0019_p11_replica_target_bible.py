"""Add P11 Replica Target Bible typed revision storage and migrate Replica root skill binding.

Revision ID: 0019_p11_replica_target_bible
Revises: 0018_source_storyboard_working_draft
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_p11_replica_target_bible"
down_revision = "0018_source_storyboard_working_draft"
branch_labels = None
depends_on = None


_REPLICA_SKILL_ID = "project.replica"
_OLD_REPLICA_SKILL_VERSION = "1.0.0"
_NEW_REPLICA_SKILL_VERSION = "1.1.0"


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
        "replica_target_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_snapshot_artifact_id"], ["artifact_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", name="uq_replica_target_revisions_artifact_id"),
    )
    op.create_index("ix_replica_target_revisions_project_id", "replica_target_revisions", ["project_id"], unique=False)
    op.create_index("ix_replica_target_revisions_artifact_id", "replica_target_revisions", ["artifact_id"], unique=False)
    op.create_index("ix_replica_target_revisions_artifact_kind", "replica_target_revisions", ["artifact_kind"], unique=False)
    op.create_index(
        "ix_replica_target_revisions_source_snapshot_artifact_id",
        "replica_target_revisions",
        ["source_snapshot_artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_replica_target_revisions_generated_by_task_id",
        "replica_target_revisions",
        ["generated_by_task_id"],
        unique=False,
    )

    # The P11 admission splits the old target_localize step into target_bible and
    # target_script. That is a Root Skill contract change, so persisted REPLICA
    # projects must move to the new binding and any plan compiled under 1.0.0 must
    # be discarded. Source/Target artifacts are intentionally untouched here.
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
    # A downgrade restores the old Root Skill binding, but still invalidates plans
    # because any plan compiled while 1.1.0 was installed cannot be interpreted as
    # a valid 1.0.0 plan. workflow_revision remains monotonic by design.
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

    op.drop_index("ix_replica_target_revisions_generated_by_task_id", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_source_snapshot_artifact_id", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_artifact_kind", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_artifact_id", table_name="replica_target_revisions")
    op.drop_index("ix_replica_target_revisions_project_id", table_name="replica_target_revisions")
    op.drop_table("replica_target_revisions")
