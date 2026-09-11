"""Supersede pending P13 candidates before asset-local visual identity v2.

Revision ID: 0023_p13_visual_scope_v2
Revises: 0022_p13_chinese_review_language
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_p13_visual_scope_v2"
down_revision = "0022_p13_chinese_review_language"
branch_labels = None
depends_on = None


_MIGRATION_REASON = (
    "P13 visual identity v2 contract upgrade: old pending candidate was generated "
    "before asset-local review scope correction"
)


def upgrade() -> None:
    # Retire only candidates that can still be accepted under the superseded scope.
    # Accepted/rejected/history and formal TARGET_ASSETS revisions remain untouched.
    op.execute(
        sa.text(
            "UPDATE replica_target_assets_candidates "
            "SET review_status = 'SUPERSEDED', review_reason = :reason "
            "WHERE review_status = 'NEEDS_REVIEW'"
        ).bindparams(reason=_MIGRATION_REASON)
    )


def downgrade() -> None:
    # Restore only rows retired by this exact migration.
    op.execute(
        sa.text(
            "UPDATE replica_target_assets_candidates "
            "SET review_status = 'NEEDS_REVIEW', review_reason = NULL "
            "WHERE review_status = 'SUPERSEDED' AND review_reason = :reason"
        ).bindparams(reason=_MIGRATION_REASON)
    )
