"""Invalidate persisted REPLICA plans after P13 capability acceptance.

Revision ID: 0024_p13_acceptance_capability
Revises: 0023_p13_visual_scope_v2
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_p13_acceptance_capability"
down_revision = "0023_p13_visual_scope_v2"
branch_labels = None
depends_on = None


def _invalidate_replica_plans() -> None:
    # Capability availability participates in step readiness at compile time but is
    # intentionally not persisted in the project fingerprint. Invalidate cached
    # REPLICA plans so the next explicit compile reflects TARGET_ASSETS=AVAILABLE.
    op.execute(
        sa.text(
            "UPDATE project_execution_plans SET is_current = 0 "
            "WHERE project_id IN (SELECT id FROM projects WHERE project_type = 'REPLICA')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE projects SET current_plan_id = NULL "
            "WHERE project_type = 'REPLICA'"
        )
    )


def upgrade() -> None:
    _invalidate_replica_plans()


def downgrade() -> None:
    # A code rollback makes TARGET_ASSETS planned again, so cached plans compiled
    # under the accepted capability state must also be discarded.
    _invalidate_replica_plans()
