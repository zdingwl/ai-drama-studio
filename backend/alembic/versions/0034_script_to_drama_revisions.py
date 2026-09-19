"""Independent script-to-drama preproduction revisions.

Revision ID: 0034_script_to_drama_revisions
Revises: 0033_script_localization_revisions
"""

from alembic import op
import sqlalchemy as sa

revision = "0034_script_to_drama_revisions"
down_revision = "0033_script_localization_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "script_to_drama_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("artifact_id", name="uq_script_to_drama_revision_artifact"),
    )
    op.create_index("ix_script_to_drama_revisions_project_id", "script_to_drama_revisions", ["project_id"])
    op.create_index("ix_script_to_drama_revisions_artifact_id", "script_to_drama_revisions", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_script_to_drama_revisions_artifact_id", table_name="script_to_drama_revisions")
    op.drop_index("ix_script_to_drama_revisions_project_id", table_name="script_to_drama_revisions")
    op.drop_table("script_to_drama_revisions")
