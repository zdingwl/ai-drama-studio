"""add P3 source asset, episode and source document tables

Revision ID: 0003_p3_source_assets
Revises: 0002_p2_versioned_kernel
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_p3_source_assets"
down_revision: str | None = "0002_p2_versioned_kernel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("asset_kind", sa.String(length=16), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.String(length=512), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "asset_kind", "sha256", name="uq_source_asset_project_kind_sha256"),
        sa.UniqueConstraint("relative_path"),
    )
    op.create_index("ix_source_assets_project_id", "source_assets", ["project_id"], unique=False)
    op.create_index("ix_source_assets_asset_kind", "source_assets", ["asset_kind"], unique=False)
    op.create_index("ix_source_assets_sha256", "source_assets", ["sha256"], unique=False)

    op.create_table(
        "episodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), nullable=False),
        sa.Column("episode_order", sa.Integer(), nullable=False),
        sa.Column("duration_us", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("codec_name", sa.String(length=64), nullable=False),
        sa.Column("avg_frame_rate", sa.String(length=32), nullable=False),
        sa.Column("has_audio", sa.Boolean(), nullable=False),
        sa.Column("probe_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["source_assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_asset_id", name="uq_episode_source_asset"),
    )
    op.create_index("ix_episodes_project_id", "episodes", ["project_id"], unique=False)
    op.create_index("ix_episodes_source_asset_id", "episodes", ["source_asset_id"], unique=False)
    op.create_index("ix_episodes_episode_order", "episodes", ["episode_order"], unique=False)

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document_format", sa.String(length=16), nullable=False),
        sa.Column("encoding", sa.String(length=32), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["source_assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "revision", name="uq_source_document_project_revision"),
    )
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"], unique=False)
    op.create_index("ix_source_documents_source_asset_id", "source_documents", ["source_asset_id"], unique=False)
    op.create_index("ix_source_documents_is_current", "source_documents", ["is_current"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_source_documents_is_current", table_name="source_documents")
    op.drop_index("ix_source_documents_source_asset_id", table_name="source_documents")
    op.drop_index("ix_source_documents_project_id", table_name="source_documents")
    op.drop_table("source_documents")
    op.drop_index("ix_episodes_episode_order", table_name="episodes")
    op.drop_index("ix_episodes_source_asset_id", table_name="episodes")
    op.drop_index("ix_episodes_project_id", table_name="episodes")
    op.drop_table("episodes")
    op.drop_index("ix_source_assets_sha256", table_name="source_assets")
    op.drop_index("ix_source_assets_asset_kind", table_name="source_assets")
    op.drop_index("ix_source_assets_project_id", table_name="source_assets")
    op.drop_table("source_assets")
