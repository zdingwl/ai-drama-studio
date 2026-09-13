"""Add Replica storyboard, generation selection and final-output production storage.

Revision ID: 0027_p15_p16_p17_replica_production
Revises: 0026_p14_voice_metadata
Create Date: 2026-09-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_p15_p16_p17_replica_production"
down_revision = "0026_p14_voice_metadata"
branch_labels = None
depends_on = None


def _index(table: str, column: str) -> None:
    op.create_index(f"ix_{table}_{column}", table, [column])


def _invalidate_replica_plans() -> None:
    op.execute(sa.text("UPDATE project_execution_plans SET is_current = 0 WHERE project_id IN (SELECT id FROM projects WHERE project_type = 'REPLICA')"))
    op.execute(sa.text("UPDATE projects SET current_plan_id = NULL WHERE project_type = 'REPLICA'"))


def upgrade() -> None:
    op.create_table(
        "replica_storyboard_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_snapshot_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_bible_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_script_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_assets_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_audio_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("timing_plan_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("generation_sequence", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("bundle_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("review_reason", sa.String(800), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "source_snapshot_artifact_id", "target_bible_artifact_id", "target_script_artifact_id", "target_assets_artifact_id", "target_audio_artifact_id", "timing_plan_artifact_id", "generated_by_task_id", "input_fingerprint", "review_status"):
        _index("replica_storyboard_candidates", column)

    op.create_table(
        "replica_target_storyboard_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("replica_storyboard_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "candidate_id", "generated_by_task_id"):
        _index("replica_target_storyboard_revisions", column)

    op.create_table(
        "replica_generation_segments_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_storyboard_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("replica_storyboard_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "target_storyboard_artifact_id", "candidate_id", "generated_by_task_id"):
        _index("replica_generation_segments_revisions", column)

    op.create_table(
        "replica_generation_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_storyboard_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generation_segments_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_assets_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generation_segment_id", sa.String(180), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider_job_id", sa.String(36), sa.ForeignKey("provider_jobs.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("prompt_fingerprint", sa.String(64), nullable=False),
        sa.Column("remote_job_id", sa.String(256), nullable=True),
        sa.Column("storage_filename", sa.String(320), nullable=False),
        sa.Column("media_url", sa.String(1000), nullable=False),
        sa.Column("media_sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("actual_duration_us", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("codec_name", sa.String(120), nullable=False),
        sa.Column("technical_qc_status", sa.String(32), nullable=False),
        sa.Column("technical_qc_issues_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("generation_segments_artifact_id", "generation_segment_id", "attempt_number", name="uq_replica_generation_attempt_segment_attempt"),
    )
    for column in ("project_id", "target_storyboard_artifact_id", "generation_segments_artifact_id", "target_assets_artifact_id", "generated_by_task_id", "generation_segment_id", "provider_job_id", "remote_job_id", "technical_qc_status"):
        _index("replica_generation_attempts", column)

    op.create_table(
        "replica_generation_selection_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_storyboard_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generation_segments_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_assets_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
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
    )
    for column in ("project_id", "target_storyboard_artifact_id", "generation_segments_artifact_id", "target_assets_artifact_id", "generated_by_task_id", "input_fingerprint", "review_status"):
        _index("replica_generation_selection_candidates", column)

    op.create_table(
        "replica_generated_video_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("selection_candidate_id", sa.String(36), sa.ForeignKey("replica_generation_selection_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "selection_candidate_id", "generated_by_task_id"):
        _index("replica_generated_video_revisions", column)

    op.create_table(
        "replica_generation_selection_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("generated_video_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("selection_candidate_id", sa.String(36), sa.ForeignKey("replica_generation_selection_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "generated_video_artifact_id", "selection_candidate_id", "generated_by_task_id"):
        _index("replica_generation_selection_revisions", column)

    op.create_table(
        "replica_post_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_selection_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_audio_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_script_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("timing_plan_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
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
    )
    for column in ("project_id", "generation_selection_artifact_id", "target_audio_artifact_id", "target_script_artifact_id", "timing_plan_artifact_id", "generated_by_task_id", "input_fingerprint", "review_status"):
        _index("replica_post_candidates", column)

    op.create_table(
        "replica_final_output_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("generation_selection_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_audio_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_script_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("timing_plan_artifact_id", sa.String(36), sa.ForeignKey("artifact_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("replica_post_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_by_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("project_id", "artifact_id", "generation_selection_artifact_id", "target_audio_artifact_id", "target_script_artifact_id", "timing_plan_artifact_id", "candidate_id", "generated_by_task_id"):
        _index("replica_final_output_revisions", column)

    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.5.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    _invalidate_replica_plans()


def downgrade() -> None:
    _invalidate_replica_plans()
    op.execute(sa.text("UPDATE projects SET root_skill_version = '1.4.0' WHERE project_type = 'REPLICA' AND root_skill_id = 'project.replica'"))
    op.drop_table("replica_final_output_revisions")
    op.drop_table("replica_post_candidates")
    op.drop_table("replica_generation_selection_revisions")
    op.drop_table("replica_generated_video_revisions")
    op.drop_table("replica_generation_selection_candidates")
    op.drop_table("replica_generation_attempts")
    op.drop_table("replica_generation_segments_revisions")
    op.drop_table("replica_target_storyboard_revisions")
    op.drop_table("replica_storyboard_candidates")
