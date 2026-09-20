"""Script-to-drama-only independent script shelf.

Revision ID: 0035_drama_script_shelf
Revises: 0034_script_to_drama_revisions
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_drama_script_shelf"
down_revision = "0034_script_to_drama_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drama_shelf_scripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("latest_revision", sa.Integer(), nullable=False),
        sa.Column("active_document_id", sa.String(36), sa.ForeignKey("source_documents.id", ondelete="SET NULL")),
        sa.Column("active_revision", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_drama_shelf_scripts_project_id", "drama_shelf_scripts", ["project_id"])
    op.create_table(
        "drama_shelf_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("script_id", sa.String(36), sa.ForeignKey("drama_shelf_scripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("source_asset_id", sa.String(36), sa.ForeignKey("source_assets.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("script_id", "revision", name="uq_drama_shelf_script_revision"),
    )
    op.create_index("ix_drama_shelf_revisions_script_id", "drama_shelf_revisions", ["script_id"])
    op.create_index("ix_drama_shelf_revisions_source_asset_id", "drama_shelf_revisions", ["source_asset_id"])
    # Old script documents are adopted on first shelf read so their immutable
    # source files can be read through the configured storage root, not Alembic.


def downgrade() -> None:
    op.drop_index("ix_drama_shelf_revisions_source_asset_id", table_name="drama_shelf_revisions")
    op.drop_index("ix_drama_shelf_revisions_script_id", table_name="drama_shelf_revisions")
    op.drop_table("drama_shelf_revisions")
    op.drop_index("ix_drama_shelf_scripts_project_id", table_name="drama_shelf_scripts")
    op.drop_table("drama_shelf_scripts")
