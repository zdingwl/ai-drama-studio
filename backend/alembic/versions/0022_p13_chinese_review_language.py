"""Supersede pre-v2 P13 candidates after Chinese review-language contract upgrade.

Revision ID: 0022_p13_chinese_review_language
Revises: 0021_p13_target_assets_preimplementation
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_p13_chinese_review_language"
down_revision = "0021_p13_target_assets_preimplementation"
branch_labels = None
depends_on = None


_MIGRATION_REASON = "P13 中文审核语言合同升级：旧待确认候选已由 v2 审核语言合同替代"


def upgrade() -> None:
    # Only pending human-review candidates are retired. Accepted/rejected/history and
    # formal TARGET_ASSETS revisions are intentionally untouched.
    op.execute(
        sa.text(
            "UPDATE replica_target_assets_candidates "
            "SET review_status = 'SUPERSEDED', review_reason = :reason "
            "WHERE review_status = 'NEEDS_REVIEW'"
        ).bindparams(reason=_MIGRATION_REASON)
    )


def downgrade() -> None:
    # Restore only rows marked by this exact migration; never revive unrelated
    # SUPERSEDED candidates.
    op.execute(
        sa.text(
            "UPDATE replica_target_assets_candidates "
            "SET review_status = 'NEEDS_REVIEW', review_reason = NULL "
            "WHERE review_status = 'SUPERSEDED' AND review_reason = :reason"
        ).bindparams(reason=_MIGRATION_REASON)
    )
