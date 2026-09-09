"""Invalidate legacy P7 outputs after Professional Skill grounding upgrade.

Revision ID: 0009_p7_grounded_professional_skill
Revises: 0008_p7_provider_choice
Create Date: 2026-09-09

The grounded source-truth contract changes the semantic generation rules for SOURCE_BIBLE.
Existing P7 outputs were generated before source-video-understanding@1.0.0 / grounded-source-truth-v1
and must not remain CURRENT after deployment. P6 Source Evidence is intentionally untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_p7_grounded_professional_skill"
down_revision = "0008_p7_provider_choice"
branch_labels = None
depends_on = None


_P7_DERIVED_TYPES = (
    "SOURCE_BIBLE",
    "STORY_SKELETON",
    "RHYTHM_SKELETON",
)


def upgrade() -> None:
    artifact_nodes = sa.table(
        "artifact_nodes",
        sa.column("artifact_type", sa.String()),
        sa.column("validity", sa.String()),
        sa.column("is_current", sa.Boolean()),
    )
    op.execute(
        artifact_nodes.update()
        .where(artifact_nodes.c.artifact_type.in_(_P7_DERIVED_TYPES))
        .where(artifact_nodes.c.is_current.is_(True))
        .values(validity="STALE", is_current=False)
    )


def downgrade() -> None:
    # Intentionally irreversible: a SOURCE_BIBLE generated under the old ungrounded contract
    # cannot safely become CURRENT again merely because the schema migration is downgraded.
    pass
