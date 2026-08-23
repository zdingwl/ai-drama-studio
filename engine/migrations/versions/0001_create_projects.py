"""F01：创建 projects 项目基础信息表。

这张表只保存“创建项目”所需的项目级基础数据。
禁止在本 Migration 中提前加入视频、Shot、人物、对白等后续 Feature 数据。
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_create_projects"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 F01 唯一的业务表 projects。"""

    op.create_table(
        "projects",
        sa.Column(
            "id",
            sa.String(),
            nullable=False,
            comment="项目唯一业务 ID。创建后永久不变，不使用项目名称生成。",
        ),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
            comment="用户看到的项目名称；允许不同项目使用相同名称。",
        ),
        sa.Column(
            "source_language",
            sa.String(length=32),
            nullable=True,
            comment="原片语言代码；为空表示当前尚未确认。",
        ),
        sa.Column(
            "target_language",
            sa.String(length=32),
            nullable=False,
            comment="重制后的目标语言代码，例如 en。",
        ),
        sa.Column(
            "target_region",
            sa.String(length=32),
            nullable=False,
            comment="本土化目标地区代码，例如 US。",
        ),
        sa.Column(
            "workspace_path",
            sa.Text(),
            nullable=False,
            comment="该项目 Workspace 的绝对路径，用于重新打开项目。",
        ),
        sa.Column(
            "project_format_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="项目目录和 project.json 的格式版本；F01 固定为 1。",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="creating",
            comment="项目创建状态；F01 只允许 creating 或 ready。",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="项目创建时间，业务层统一写入 UTC 时间。",
        ),
        sa.Column(
            "last_opened_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次成功打开项目 Workspace 的时间。",
        ),
        sa.CheckConstraint(
            "status IN ('creating', 'ready')",
            name="ck_projects_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint(
            "workspace_path",
            name="uq_projects_workspace_path",
        ),
    )


def downgrade() -> None:
    """回退 F01 初始表；这不是用户层面的“删除项目”功能。"""

    op.drop_table("projects")
