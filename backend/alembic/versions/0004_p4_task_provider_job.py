"""add P4 task and provider job execution tables

Revision ID: 0004_p4_task_provider_job
Revises: 0003_p3_source_assets
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_p4_task_provider_job"
down_revision: str | None = "0003_p3_source_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("task_name", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("business_key", sa.String(length=64), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_artifact_ids_json", sa.JSON(), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("plan_step_key", sa.String(length=96), nullable=True),
        sa.Column("episode_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["project_execution_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "business_key", name="uq_task_project_business_key"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_task_project_idempotency_key"),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"], unique=False)
    op.create_index("ix_tasks_task_type", "tasks", ["task_type"], unique=False)
    op.create_index("ix_tasks_business_key", "tasks", ["business_key"], unique=False)
    op.create_index("ix_tasks_input_fingerprint", "tasks", ["input_fingerprint"], unique=False)
    op.create_index("ix_tasks_plan_id", "tasks", ["plan_id"], unique=False)
    op.create_index("ix_tasks_episode_id", "tasks", ["episode_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_cancel_requested", "tasks", ["cancel_requested"], unique=False)
    op.create_index("ix_tasks_worker_id", "tasks", ["worker_id"], unique=False)
    op.create_index("ix_tasks_heartbeat_at", "tasks", ["heartbeat_at"], unique=False)

    op.create_table(
        "provider_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=96), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("capability", sa.String(length=96), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("local_job_id", sa.String(length=128), nullable=False),
        sa.Column("remote_job_id", sa.String(length=256), nullable=True),
        sa.Column("safe_error", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("local_job_id"),
    )
    op.create_index("ix_provider_jobs_project_id", "provider_jobs", ["project_id"], unique=False)
    op.create_index("ix_provider_jobs_task_id", "provider_jobs", ["task_id"], unique=False)
    op.create_index("ix_provider_jobs_episode_id", "provider_jobs", ["episode_id"], unique=False)
    op.create_index("ix_provider_jobs_artifact_id", "provider_jobs", ["artifact_id"], unique=False)
    op.create_index("ix_provider_jobs_provider", "provider_jobs", ["provider"], unique=False)
    op.create_index("ix_provider_jobs_capability", "provider_jobs", ["capability"], unique=False)
    op.create_index("ix_provider_jobs_payload_fingerprint", "provider_jobs", ["payload_fingerprint"], unique=False)
    op.create_index("ix_provider_jobs_status", "provider_jobs", ["status"], unique=False)
    op.create_index("ix_provider_jobs_remote_job_id", "provider_jobs", ["remote_job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_provider_jobs_remote_job_id", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_status", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_payload_fingerprint", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_capability", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_provider", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_artifact_id", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_episode_id", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_task_id", table_name="provider_jobs")
    op.drop_index("ix_provider_jobs_project_id", table_name="provider_jobs")
    op.drop_table("provider_jobs")

    op.drop_index("ix_tasks_heartbeat_at", table_name="tasks")
    op.drop_index("ix_tasks_worker_id", table_name="tasks")
    op.drop_index("ix_tasks_cancel_requested", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_episode_id", table_name="tasks")
    op.drop_index("ix_tasks_plan_id", table_name="tasks")
    op.drop_index("ix_tasks_input_fingerprint", table_name="tasks")
    op.drop_index("ix_tasks_business_key", table_name="tasks")
    op.drop_index("ix_tasks_task_type", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_table("tasks")
