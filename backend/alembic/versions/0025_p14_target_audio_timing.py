"""Add P14 target audio and dialogue timing storage and bump REPLICA root contract.

Revision ID: 0025_p14_target_audio_timing
Revises: 0024_p13_acceptance_capability
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_p14_target_audio_timing"
down_revision = "0024_p13_acceptance_capability"
branch_labels = None
depends_on = None


def _invalidate_replica_plans() -> None:
    op.execute(sa.text("UPDATE project_execution_plans SET is_current = 0 WHERE project_id IN (SELECT id FROM projects WHERE project_type = 'REPLICA')"))
    op.execute(sa.text("UPDATE projects SET current_plan_id = NULL WHERE project_type = 'REPLICA'"))


def _candidate_table(name: str, second_artifact_column: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_script_artifact_id", sa.String(length=36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(second_artifact_column, sa.String(length=36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generation_sequence", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("review_reason", sa.String(length=800), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("generated_by_task_id", name=f"uq_{name}_task"),
    )
    for column in ("project_id", "target_script_artifact_id", second_artifact_column, "generated_by_task_id", "input_fingerprint", "review_status"):
        op.create_index(f"ix_{name}_{column}", name, [column])


def _revision_table(name: str, second_artifact_column: str, candidate_table: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_script_artifact_id", sa.String(length=36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(second_artifact_column, sa.String(length=36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey(f"{candidate_table}.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "target_script_artifact_id", second_artifact_column, "candidate_id", "generated_by_task_id"):
        op.create_index(f"ix_{name}_{column}", name, [column])


def upgrade() -> None:
    _candidate_table("replica_target_audio_candidates", "target_bible_artifact_id")
    _revision_table("replica_target_audio_revisions", "target_bible_artifact_id", "replica_target_audio_candidates")
    _candidate_table("replica_timing_plan_candidates", "target_audio_artifact_id")
    _revision_table("replica_timing_plan_revisions", "target_audio_artifact_id", "replica_timing_plan_candidates")
    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.4.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    _invalidate_replica_plans()


def downgrade() -> None:
    _invalidate_replica_plans()
    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.3.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    op.drop_table("replica_timing_plan_revisions")
    op.drop_table("replica_timing_plan_candidates")
    op.drop_table("replica_target_audio_revisions")
    op.drop_table("replica_target_audio_candidates")
