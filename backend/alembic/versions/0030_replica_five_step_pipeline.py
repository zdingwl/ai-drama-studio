"""Add Replica five-step localized storyboard, asset images and H3 prompt revisions.

Revision ID: 0030_replica_five_step_pipeline
Revises: 0029_h3_native_audio_video
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_replica_five_step_pipeline"
down_revision = "0029_h3_native_audio_video"
branch_labels = None
depends_on = None


def _candidate_columns(upstream_name: str):
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(upstream_name, sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("generation_sequence", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("review_reason", sa.String(800), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("replica_localized_storyboard_candidates", *_candidate_columns("source_snapshot_artifact_id"))
    op.create_index("ix_replica_localized_storyboard_candidates_project_id", "replica_localized_storyboard_candidates", ["project_id"])
    op.create_index("ix_replica_localized_storyboard_candidates_source_snapshot_artifact_id", "replica_localized_storyboard_candidates", ["source_snapshot_artifact_id"])
    op.create_index("ix_replica_localized_storyboard_candidates_review_status", "replica_localized_storyboard_candidates", ["review_status"])
    op.create_index("ix_replica_localized_storyboard_candidates_input_fingerprint", "replica_localized_storyboard_candidates", ["input_fingerprint"])

    op.create_table(
        "replica_localized_storyboard_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("source_snapshot_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("replica_localized_storyboard_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_replica_localized_storyboard_revisions_project_id", "replica_localized_storyboard_revisions", ["project_id"])
    op.create_index("ix_replica_localized_storyboard_revisions_artifact_id", "replica_localized_storyboard_revisions", ["artifact_id"], unique=True)

    op.create_table("replica_asset_image_candidates", *_candidate_columns("target_storyboard_artifact_id"))
    op.create_index("ix_replica_asset_image_candidates_project_id", "replica_asset_image_candidates", ["project_id"])
    op.create_index("ix_replica_asset_image_candidates_target_storyboard_artifact_id", "replica_asset_image_candidates", ["target_storyboard_artifact_id"])
    op.create_index("ix_replica_asset_image_candidates_review_status", "replica_asset_image_candidates", ["review_status"])
    op.create_index("ix_replica_asset_image_candidates_input_fingerprint", "replica_asset_image_candidates", ["input_fingerprint"])

    op.create_table(
        "replica_asset_image_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_storyboard_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("replica_asset_image_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_replica_asset_image_revisions_project_id", "replica_asset_image_revisions", ["project_id"])
    op.create_index("ix_replica_asset_image_revisions_artifact_id", "replica_asset_image_revisions", ["artifact_id"], unique=True)

    op.create_table(
        "replica_h3_prompt_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_storyboard_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_assets_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_replica_h3_prompt_revisions_project_id", "replica_h3_prompt_revisions", ["project_id"])
    op.create_index("ix_replica_h3_prompt_revisions_artifact_id", "replica_h3_prompt_revisions", ["artifact_id"], unique=True)

    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.7.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    op.execute(sa.text("UPDATE project_execution_plans SET is_current = 0"))
    op.execute(sa.text("UPDATE projects SET current_plan_id = NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "replica_h3_prompt_revisions",
        "replica_asset_image_revisions",
        "replica_asset_image_candidates",
        "replica_localized_storyboard_revisions",
        "replica_localized_storyboard_candidates",
    ):
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError("Cannot downgrade 0030 after five-step Replica v2 data has been created; export/remove those revisions explicitly first.")
    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.6.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    op.drop_table("replica_h3_prompt_revisions")
    op.drop_table("replica_asset_image_revisions")
    op.drop_table("replica_asset_image_candidates")
    op.drop_table("replica_localized_storyboard_revisions")
    op.drop_table("replica_localized_storyboard_candidates")
