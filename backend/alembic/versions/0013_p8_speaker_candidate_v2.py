"""Invalidate P8 v1 SOURCE_SHOT_FACTS after adding provisional speaker candidates.

Revision ID: 0013_p8_speaker_candidate_v2
Revises: 0012_p6_canonical_evidence_v2
Create Date: 2026-09-09

P8 schema 1.1 adds a provisional Source-Bible character candidate to each canonical dialogue
binding. Existing P8 v1 artifacts do not contain that field and must not remain CURRENT after the
contract changes. History is preserved. P5/P6/P7 remain untouched; the recovery path is an explicit
P8 rerun on the already-CURRENT upstream source chain.
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_p8_speaker_candidate_v2"
down_revision = "0012_p6_canonical_evidence_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    artifact_nodes = sa.table(
        "artifact_nodes",
        sa.column("project_id", sa.String()),
        sa.column("artifact_type", sa.String()),
        sa.column("validity", sa.String()),
        sa.column("is_current", sa.Boolean()),
    )
    projects = sa.table(
        "projects",
        sa.column("id", sa.String()),
        sa.column("current_plan_id", sa.String()),
    )
    plans = sa.table(
        "project_execution_plans",
        sa.column("project_id", sa.String()),
        sa.column("is_current", sa.Boolean()),
    )

    affected_project_ids = sa.select(artifact_nodes.c.project_id).where(
        artifact_nodes.c.artifact_type == "SOURCE_SHOT_FACTS",
        artifact_nodes.c.is_current.is_(True),
    )

    op.execute(
        plans.update()
        .where(plans.c.project_id.in_(affected_project_ids))
        .where(plans.c.is_current.is_(True))
        .values(is_current=False)
    )
    op.execute(projects.update().where(projects.c.id.in_(affected_project_ids)).values(current_plan_id=None))
    op.execute(
        artifact_nodes.update()
        .where(artifact_nodes.c.artifact_type == "SOURCE_SHOT_FACTS")
        .where(artifact_nodes.c.is_current.is_(True))
        .values(validity="STALE", is_current=False)
    )


def downgrade() -> None:
    # Intentionally irreversible: v1 artifacts cannot regain CURRENT status because they lack the
    # speaker-candidate field required by the v2 contract.
    pass
