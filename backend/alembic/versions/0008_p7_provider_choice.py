"""P7 project source understanding provider choice.

Revision ID: 0008_p7_provider_choice
Revises: 0007_p7_source_bible
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_p7_provider_choice"
down_revision = "0007_p7_source_bible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "source_understanding_provider",
            sa.String(length=40),
            nullable=False,
            server_default="DOUBAO_SEED_2_1_PRO_API",
        ),
    )
    op.alter_column("projects", "source_understanding_provider", server_default=None)


def downgrade() -> None:
    op.drop_column("projects", "source_understanding_provider")
