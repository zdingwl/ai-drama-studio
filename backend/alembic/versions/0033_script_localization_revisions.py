"""Add independent script-localization revisions; existing Replica tables stay unchanged.

Revision ID: 0033_script_localization_revisions
Revises: 0032_replica_asset_workspace
"""

from alembic import op
import sqlalchemy as sa

revision = "0033_script_localization_revisions"
down_revision = "0032_replica_asset_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "script_localization_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("artifact_id", name="uq_script_localization_revision_artifact"),
    )
    op.create_index("ix_script_localization_revisions_project_id", "script_localization_revisions", ["project_id"])
    op.create_index("ix_script_localization_revisions_artifact_id", "script_localization_revisions", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_script_localization_revisions_artifact_id", table_name="script_localization_revisions")
    op.drop_index("ix_script_localization_revisions_project_id", table_name="script_localization_revisions")
    op.drop_table("script_localization_revisions")
