"""F01 创建项目所需的数据库初始化入口。

当前文件只负责把应用级 SQLite 数据库初始化到 F01 所需的 schema。
F01 只允许出现 projects 一张业务表，不提前创建后续 Feature 的表。
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from engine.app.core.paths import get_app_data_path

DATABASE_FILENAME = "app.db"
MIGRATION_HEAD = "head"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def init_database(app_data_path: Path | None = None) -> Path:
    """初始化 AI Drama Studio 的应用级 SQLite 数据库。

    业务作用：
    - 确保应用数据目录存在；
    - 在目录中使用固定文件名 ``app.db``；
    - 通过 Alembic 升级到当前 schema，F01 首次会创建 ``projects`` 表；
    - 重复调用是安全的，已在最新版本时不会重复建表。

    为什么使用 Alembic 而不是 ``Base.metadata.create_all()``：
    数据库从第一版就必须有可追踪的升级历史。开发期和以后正式升级统一走
    Migration，避免同一个数据库存在两套建表逻辑。

    安全边界：
    - 只允许初始化应用级 ``app.db``；
    - 不创建 Project Workspace；
    - 不插入任何项目业务数据；
    - 不创建 Episode、Shot、Character 等后续 Feature 的表。

    Args:
        app_data_path: 可选的应用数据目录。测试时传入临时目录；正式运行留空，
            由 ``get_app_data_path()`` 按 F01 规则解析。

    Returns:
        Path: 初始化完成后的 ``app.db`` 绝对路径。

    Raises:
        OSError: 应用数据目录无法创建或数据库文件无法写入。
        alembic.util.exc.CommandError: Migration 配置或执行失败。
    """

    data_dir = (app_data_path or get_app_data_path()).expanduser().resolve(strict=False)
    data_dir.mkdir(parents=True, exist_ok=True)

    database_path = data_dir / DATABASE_FILENAME

    # 不使用独立 alembic.ini 的原因：F01 当前只需要一个本地 app.db。
    # 由此函数把实际数据库路径传给 Alembic，可保证测试使用 tmp_path，
    # 正式运行使用 get_app_data_path()，避免 Migration 写错数据库。
    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic_config.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{database_path.as_posix()}",
    )

    command.upgrade(alembic_config, MIGRATION_HEAD)
    return database_path
