"""complete P2 versioned skill, artifact and execution plan kernel

Revision ID: 0002_p2_versioned_kernel
Revises: 0001_project_skill_kernel
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_p2_versioned_kernel"
down_revision: str | None = "0001_project_skill_kernel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SKILL_BY_PROJECT_TYPE = {
    "REPLICA": "project.replica",
    "REDRAW": "project.redraw",
    "TRANSLATION": "project.translation",
    "NOVEL_TO_DRAMA": "project.novel_to_drama",
    "SCRIPT_TO_DRAMA": "project.script_to_drama",
    "SCRIPT_LOCALIZATION": "project.script_localization",
}


def upgrade() -> None:
    op.add_column("projects", sa.Column("visual_style", sa.String(length=80), nullable=True))
    op.add_column("projects", sa.Column("root_skill_id", sa.String(length=96), nullable=True))
    op.add_column("projects", sa.Column("root_skill_version", sa.String(length=32), nullable=True))
    op.add_column("projects", sa.Column("current_plan_id", sa.String(length=36), nullable=True))

    for project_type, skill_id in _SKILL_BY_PROJECT_TYPE.items():
        op.execute(
            sa.text(
                "UPDATE projects SET root_skill_id = :skill_id, root_skill_version = '1.0.0' "
                "WHERE project_type = :project_type"
            ).bindparams(skill_id=skill_id, project_type=project_type)
        )

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("root_skill_id", existing_type=sa.String(length=96), nullable=False)
        batch_op.alter_column("root_skill_version", existing_type=sa.String(length=32), nullable=False)

    op.add_column("artifact_nodes", sa.Column("namespace", sa.String(length=16), nullable=True))
    op.add_column("artifact_nodes", sa.Column("input_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("artifact_nodes", sa.Column("skill_id", sa.String(length=96), nullable=True))
    op.add_column("artifact_nodes", sa.Column("skill_version", sa.String(length=32), nullable=True))
    op.add_column("artifact_nodes", sa.Column("validity", sa.String(length=16), nullable=True))

    op.execute(
        sa.text(
            "UPDATE artifact_nodes SET "
            "namespace = CASE "
            "WHEN artifact_type IN ('SOURCE_VIDEO','SOURCE_TEXT','SHOT_ANCHORS','SOURCE_DIALOGUE','SOURCE_BIBLE',"
            "'STORY_SKELETON','RHYTHM_SKELETON','SOURCE_SHOT_FACTS','SOURCE_CHARACTERS','SOURCE_SCENES',"
            "'SOURCE_PROPS','SOURCE_VIDEO_SNAPSHOT','SOURCE_TEXT_SNAPSHOT') THEN 'SOURCE' "
            "WHEN artifact_type IN ('ADAPTATION_PLAN','TARGET_BIBLE','TARGET_SCRIPT','TARGET_ASSETS') THEN 'TARGET' "
            "ELSE 'PRODUCTION' END, "
            "input_fingerprint = 'legacy-unfingerprinted', "
            "skill_id = 'legacy', skill_version = '0', validity = 'STALE', is_current = 0"
        )
    )

    with op.batch_alter_table("artifact_nodes") as batch_op:
        batch_op.alter_column("namespace", existing_type=sa.String(length=16), nullable=False)
        batch_op.alter_column("input_fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("skill_id", existing_type=sa.String(length=96), nullable=False)
        batch_op.alter_column("skill_version", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("validity", existing_type=sa.String(length=16), nullable=False)

    op.create_index("ix_artifact_nodes_namespace", "artifact_nodes", ["namespace"], unique=False)
    op.create_index("ix_artifact_nodes_input_fingerprint", "artifact_nodes", ["input_fingerprint"], unique=False)
    op.create_index("ix_artifact_nodes_validity", "artifact_nodes", ["validity"], unique=False)

    op.create_table(
        "project_execution_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("root_skill_id", sa.String(length=96), nullable=False),
        sa.Column("root_skill_version", sa.String(length=32), nullable=False),
        sa.Column("workflow_revision", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "revision", name="uq_project_execution_plan_revision"),
    )
    op.create_index("ix_project_execution_plans_project_id", "project_execution_plans", ["project_id"], unique=False)
    op.create_index("ix_project_execution_plans_input_fingerprint", "project_execution_plans", ["input_fingerprint"], unique=False)
    op.create_index("ix_project_execution_plans_is_current", "project_execution_plans", ["is_current"], unique=False)

    op.create_table(
        "project_execution_plan_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=96), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=800), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("requires_json", sa.JSON(), nullable=False),
        sa.Column("produces_json", sa.JSON(), nullable=False),
        sa.Column("missing_artifacts_json", sa.JSON(), nullable=False),
        sa.Column("unavailable_capabilities_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["project_execution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "position", name="uq_project_execution_plan_step_position"),
    )
    op.create_index("ix_project_execution_plan_steps_plan_id", "project_execution_plan_steps", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_execution_plan_steps_plan_id", table_name="project_execution_plan_steps")
    op.drop_table("project_execution_plan_steps")
    op.drop_index("ix_project_execution_plans_is_current", table_name="project_execution_plans")
    op.drop_index("ix_project_execution_plans_input_fingerprint", table_name="project_execution_plans")
    op.drop_index("ix_project_execution_plans_project_id", table_name="project_execution_plans")
    op.drop_table("project_execution_plans")

    op.drop_index("ix_artifact_nodes_validity", table_name="artifact_nodes")
    op.drop_index("ix_artifact_nodes_input_fingerprint", table_name="artifact_nodes")
    op.drop_index("ix_artifact_nodes_namespace", table_name="artifact_nodes")
    with op.batch_alter_table("artifact_nodes") as batch_op:
        batch_op.drop_column("validity")
        batch_op.drop_column("skill_version")
        batch_op.drop_column("skill_id")
        batch_op.drop_column("input_fingerprint")
        batch_op.drop_column("namespace")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("current_plan_id")
        batch_op.drop_column("root_skill_version")
        batch_op.drop_column("root_skill_id")
        batch_op.drop_column("visual_style")
