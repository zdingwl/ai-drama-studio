"""Invalidate Source Understanding outputs built before P6 canonical microduplicate guard v3.

Revision ID: 0014_p6_microduplicate_guard_v3
Revises: 0013_p8_speaker_candidate_v2
Create Date: 2026-09-10

P6 v3 keeps raw ASR evidence intact but changes canonical admission: physically implausible members of
near-adjacent exact-text duplicate micro-segment pairs remain raw-only and no longer materialize as
SourceDialogueUtterance rows. Existing CURRENT Source Evidence and every formal artifact that consumes
its canonical utterance set must therefore become non-current/STALE on deployment.

History is preserved. SOURCE_VIDEO and SHOT_ANCHORS are intentionally untouched. Recovery is an
explicit P6 rerun followed by P7 and P8 reruns so provenance never crosses canonical revisions.
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_p6_microduplicate_guard_v3"
down_revision = "0013_p8_speaker_candidate_v2"
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
        sa.column("project_id", sa.String()),
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
    # Intentionally irreversible. Artifacts built on the superseded canonical admission policy must
    # never silently regain CURRENT status after a schema downgrade.
    pass
