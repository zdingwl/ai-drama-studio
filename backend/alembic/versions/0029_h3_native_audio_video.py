"""Allow H3 native audio-video storyboard candidates.

Revision ID: 0029_h3_native_audio_video
Revises: 0028_source_script_first
Create Date: 2026-09-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_h3_native_audio_video"
down_revision = "0028_source_script_first"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("replica_storyboard_candidates") as batch_op:
        batch_op.alter_column("target_audio_artifact_id", existing_type=sa.String(36), nullable=True)
        batch_op.alter_column("timing_plan_artifact_id", existing_type=sa.String(36), nullable=True)
    for table_name in ("replica_post_candidates", "replica_final_output_revisions"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("target_audio_artifact_id", existing_type=sa.String(36), nullable=True)
            batch_op.alter_column("timing_plan_artifact_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    for table_name in ("replica_final_output_revisions", "replica_post_candidates"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("timing_plan_artifact_id", existing_type=sa.String(36), nullable=False)
            batch_op.alter_column("target_audio_artifact_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("replica_storyboard_candidates") as batch_op:
        batch_op.alter_column("timing_plan_artifact_id", existing_type=sa.String(36), nullable=False)
        batch_op.alter_column("target_audio_artifact_id", existing_type=sa.String(36), nullable=False)
