"""Invalidate Source Understanding outputs built on P6 canonical dialogue v1.

Revision ID: 0012_p6_canonical_evidence_v2
Revises: 0011_p8_source_shot_facts
Create Date: 2026-09-09

P6 v1 could aggressively merge adjacent ASR segments into long canonical utterances even when
speaker/turn continuity was not established. P6 v2 changes the canonical dialogue policy and ASR
quality profile. Existing per-Episode SourceEvidenceSet rows and every CURRENT formal artifact that
consumes the old canonical text must therefore become non-current/STALE on deployment.

History is intentionally preserved. The correct recovery path is an explicit real P6 rerun, followed
by P7 and P8 reruns. SOURCE_VIDEO and SHOT_ANCHORS are untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_p6_canonical_evidence_v2"
down_revision = "0011_p8_source_shot_facts"
branch_labels = None
depends_on = None


_INVALIDATED_ARTIFACT_TYPES = (
    "SOURCE_DIALOGUE",
    "SOURCE_BIBLE",
    "STORY_SKELETON",
    "RHYTHM_SKELETON",
    "SOURCE_SHOT_FACTS",
)


def upgrade() -> None:
    evidence_sets = sa.table(
        "source_evidence_sets",
        sa.column("is_current", sa.Boolean()),
    )
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
        artifact_nodes.c.artifact_type.in_(_INVALIDATED_ARTIFACT_TYPES),
        artifact_nodes.c.is_current.is_(True),
    )

    # Artifact invalidation and execution-plan invalidation are one contract: a plan derived from a
    # superseded P6/P7/P8 source chain must not stay CURRENT after deployment.
    op.execute(
        plans.update()
        .where(plans.c.project_id.in_(affected_project_ids))
        .where(plans.c.is_current.is_(True))
        .values(is_current=False)
    )
    op.execute(
        projects.update()
        .where(projects.c.id.in_(affected_project_ids))
        .values(current_plan_id=None)
    )
    op.execute(
        evidence_sets.update()
        .where(evidence_sets.c.is_current.is_(True))
        .values(is_current=False)
    )
    op.execute(
        artifact_nodes.update()
        .where(artifact_nodes.c.artifact_type.in_(_INVALIDATED_ARTIFACT_TYPES))
        .where(artifact_nodes.c.is_current.is_(True))
        .values(validity="STALE", is_current=False)
    )


def downgrade() -> None:
    # Intentionally irreversible. Outputs built on the superseded canonical Evidence policy must
    # never silently become CURRENT again after a schema downgrade.
    pass
