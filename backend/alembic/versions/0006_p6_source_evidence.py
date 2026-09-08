"""add P6 canonical source evidence

Revision ID: 0006_p6_source_evidence
Revises: 0005_p5_shot_boundary
Create Date: 2026-09-08
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0006_p6_source_evidence"
down_revision: str | None = "0005_p5_shot_boundary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns: op.create_index(f"ix_{table}_{column}", table, [column], unique=False)


def upgrade() -> None:
    op.create_table("source_evidence_sets",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("episode_id",sa.String(36),nullable=False),sa.Column("source_video_artifact_id",sa.String(36),nullable=False),sa.Column("task_id",sa.String(36),nullable=False),sa.Column("revision",sa.Integer(),nullable=False),sa.Column("input_fingerprint",sa.String(64),nullable=False),sa.Column("asr_profile_json",sa.JSON(),nullable=False),sa.Column("ocr_profile_json",sa.JSON(),nullable=False),sa.Column("sampling_hints_json",sa.JSON(),nullable=False),sa.Column("is_current",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["episode_id"],["episodes.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_video_artifact_id"],["artifact_nodes.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["task_id"],["tasks.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("episode_id","revision",name="uq_source_evidence_set_episode_revision"),sa.UniqueConstraint("task_id",name="uq_source_evidence_set_task"))
    _indexes("source_evidence_sets",("project_id","episode_id","source_video_artifact_id","task_id","input_fingerprint","is_current"))
    op.create_table("asr_evidence_segments",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("episode_id",sa.String(36),nullable=False),sa.Column("source_evidence_set_id",sa.String(36),nullable=False),sa.Column("segment_number",sa.Integer(),nullable=False),sa.Column("start_us",sa.BigInteger(),nullable=False),sa.Column("end_us",sa.BigInteger(),nullable=False),sa.Column("text",sa.Text(),nullable=False),sa.Column("language",sa.String(32),nullable=True),sa.Column("confidence",sa.Float(),nullable=True),sa.Column("provenance_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["episode_id"],["episodes.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_evidence_set_id"],["source_evidence_sets.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("source_evidence_set_id","segment_number",name="uq_asr_evidence_set_segment"))
    _indexes("asr_evidence_segments",("project_id","episode_id","source_evidence_set_id"))
    op.create_table("ocr_evidence_observations",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("episode_id",sa.String(36),nullable=False),sa.Column("source_evidence_set_id",sa.String(36),nullable=False),sa.Column("observation_number",sa.Integer(),nullable=False),sa.Column("timestamp_us",sa.BigInteger(),nullable=False),sa.Column("text",sa.Text(),nullable=False),sa.Column("confidence",sa.Float(),nullable=True),sa.Column("bbox_json",sa.JSON(),nullable=False),sa.Column("sample_source",sa.String(32),nullable=False),sa.Column("provenance_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["episode_id"],["episodes.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_evidence_set_id"],["source_evidence_sets.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("source_evidence_set_id","observation_number",name="uq_ocr_evidence_set_observation"))
    _indexes("ocr_evidence_observations",("project_id","episode_id","source_evidence_set_id"))
    op.create_table("source_dialogue_utterances",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("episode_id",sa.String(36),nullable=False),sa.Column("source_evidence_set_id",sa.String(36),nullable=False),sa.Column("utterance_number",sa.Integer(),nullable=False),sa.Column("start_us",sa.BigInteger(),nullable=False),sa.Column("end_us",sa.BigInteger(),nullable=False),sa.Column("text",sa.Text(),nullable=False),sa.Column("language",sa.String(32),nullable=True),sa.Column("source_segment_ids_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["episode_id"],["episodes.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_evidence_set_id"],["source_evidence_sets.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("source_evidence_set_id","utterance_number",name="uq_source_dialogue_set_utterance"))
    _indexes("source_dialogue_utterances",("project_id","episode_id","source_evidence_set_id"))
    op.create_table("source_visual_text_spans",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("episode_id",sa.String(36),nullable=False),sa.Column("source_evidence_set_id",sa.String(36),nullable=False),sa.Column("span_number",sa.Integer(),nullable=False),sa.Column("start_us",sa.BigInteger(),nullable=False),sa.Column("end_us",sa.BigInteger(),nullable=False),sa.Column("text",sa.Text(),nullable=False),sa.Column("confidence",sa.Float(),nullable=True),sa.Column("bbox_json",sa.JSON(),nullable=False),sa.Column("source_observation_ids_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["episode_id"],["episodes.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_evidence_set_id"],["source_evidence_sets.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("source_evidence_set_id","span_number",name="uq_source_visual_text_set_span"))
    _indexes("source_visual_text_spans",("project_id","episode_id","source_evidence_set_id"))
    op.create_table("shot_dialogue_projections",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("episode_id",sa.String(36),nullable=False),sa.Column("source_evidence_set_id",sa.String(36),nullable=False),sa.Column("source_dialogue_utterance_id",sa.String(36),nullable=False),sa.Column("shot_anchor_id",sa.String(36),nullable=False),sa.Column("shot_number",sa.Integer(),nullable=False),sa.Column("overlap_start_us",sa.BigInteger(),nullable=False),sa.Column("overlap_end_us",sa.BigInteger(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["episode_id"],["episodes.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_evidence_set_id"],["source_evidence_sets.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_dialogue_utterance_id"],["source_dialogue_utterances.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["shot_anchor_id"],["shot_anchors.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("source_dialogue_utterance_id","shot_anchor_id",name="uq_dialogue_projection_utterance_shot"))
    _indexes("shot_dialogue_projections",("project_id","episode_id","source_evidence_set_id","source_dialogue_utterance_id","shot_anchor_id"))


def downgrade() -> None:
    for table, columns in (("shot_dialogue_projections",("shot_anchor_id","source_dialogue_utterance_id","source_evidence_set_id","episode_id","project_id")),("source_visual_text_spans",("source_evidence_set_id","episode_id","project_id")),("source_dialogue_utterances",("source_evidence_set_id","episode_id","project_id")),("ocr_evidence_observations",("source_evidence_set_id","episode_id","project_id")),("asr_evidence_segments",("source_evidence_set_id","episode_id","project_id")),("source_evidence_sets",("is_current","input_fingerprint","task_id","source_video_artifact_id","episode_id","project_id"))):
        for column in columns: op.drop_index(f"ix_{table}_{column}",table_name=table)
        op.drop_table(table)
