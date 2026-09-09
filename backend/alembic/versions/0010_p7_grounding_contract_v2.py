"""Invalidate P7 outputs generated under grounding contract v1.

Revision ID: 0010_p7_grounding_contract_v2
Revises: 0009_p7_grounded_professional_skill
Create Date: 2026-09-09

`grounded-source-truth-v1` still allowed populated fact-like claims to carry UNKNOWN grounding.
`grounded-source-truth-v2` forbids that escape hatch and changes SOURCE_BIBLE schema/prompt semantics.
Existing P7 SOURCE_BIBLE outputs and their direct Story/Rhythm descendants must therefore become
STALE on deployment. P6 Source Evidence is intentionally untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_p7_grounding_contract_v2"
down_revision = "0009_p7_grounded_professional_skill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    artifact_nodes = sa.table(
        "artifact_nodes",
        sa.column("id", sa.String()),
        sa.column("artifact_type", sa.String()),
        sa.column("validity", sa.String()),
        sa.column("is_current", sa.Boolean()),
    )
    artifact_edges = sa.table(
        "artifact_edges",
        sa.column("source_node_id", sa.String()),
        sa.column("target_node_id", sa.String()),
    )

    source_bible_ids = sa.select(artifact_nodes.c.id).where(
        artifact_nodes.c.artifact_type == "SOURCE_BIBLE"
    )
    p7_descendant_ids = sa.select(artifact_edges.c.target_node_id).where(
        artifact_edges.c.source_node_id.in_(source_bible_ids)
    )

    op.execute(
        artifact_nodes.update()
        .where(
            sa.or_(
                artifact_nodes.c.id.in_(source_bible_ids),
                artifact_nodes.c.id.in_(p7_descendant_ids),
            )
        )
        .where(artifact_nodes.c.is_current.is_(True))
        .values(validity="STALE", is_current=False)
    )


def downgrade() -> None:
    # Intentionally irreversible. A SOURCE_BIBLE rejected by the stricter v2 Source Truth
    # contract must never silently become CURRENT again after a schema downgrade.
    pass
