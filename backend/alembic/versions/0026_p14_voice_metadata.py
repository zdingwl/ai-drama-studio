"""Add editable IndexTTS voice metadata.

Revision ID: 0026_p14_voice_metadata
Revises: 0025_p14_target_audio_timing
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_p14_voice_metadata"
down_revision = "0025_p14_target_audio_timing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "indextts_voice_metadata",
        sa.Column("voice_key", sa.String(length=160), primary_key=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("gender", sa.String(length=24), nullable=False),
        sa.Column("age_range", sa.String(length=32), nullable=False),
        sa.Column("style_tags_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("indextts_voice_metadata")
