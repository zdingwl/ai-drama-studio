"""AI Drama Studio 应用级 SQLite 初始化与 Migration 安全入口。

F01 建立了固定 ``app.db`` 和 Alembic 初始化方式；F02 首次需要把已经存在的
F01 数据库从 0001 升级到 0002，因此本文件在不改变 F01 对外 Contract 的前提下，
增加“有真实 pending migration 时先做 SQLite 安全备份”的保护。

公开入口仍只有 ``init_database()``。下面的私有 helper 只是把配置、版本判断和备份
细节拆开，避免业务层或 Controller 自己处理数据库升级。

并发规则：FastAPI 的同步 endpoint 会在线程池中执行。Alembic ``EnvironmentContext``
内部使用进程级代理对象，不允许多个线程同时执行 ``command.upgrade()``。因此数据库
Migration 必须由本模块串行执行，并且同一进程中每个数据库只初始化一次；业务请求
后续只复用已经完成 Migration 的 ``app.db``。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from engine.app.core.paths import get_app_data_path

DATABASE_FILENAME = "app.db"
MIGRATION_HEAD = "head"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
BACKUPS_DIRNAME = "backups"

# Alembic EnvironmentContext 不是线程安全的。F05 页面可能同时读取播放器、缩略图和关键帧，
# 这些同步 FastAPI endpoint 会进入不同 worker thread。如果每个业务函数都重新执行 upgrade，
# 会出现 alembic.runtime.environment._remove_proxy() 的 KeyError: 'config'。
_DATABASE_INIT_LOCK = threading.RLock()
_INITIALIZED_DATABASE_PATHS: set[Path] = set()


def _build_alembic_config(database_path: Path) -> Config:
    """为指定 ``app.db`` 构造 Alembic 配置。

    这是内部适配函数，不执行业务 Migration，也不创建 Project/Source 数据。
    测试传入临时数据库、正式运行传入本机 app.db 时都复用同一套 Migration 目录。
    """

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{database_path.as_posix()}",
    )
    return config


def _read_database_revision(database_path: Path, config: Config) -> tuple[str | None, str]:
    """读取数据库当前 revision 和代码 Migration head。

    业务作用：只回答“现有数据库是否真的需要升级”。只有 current != head 时，
    ``init_database()`` 才会触发升级前备份，避免每次启动都产生无意义备份文件。
    """

    script = ScriptDirectory.from_config(config)
    head_revision = script.get_current_head()
    if head_revision is None:
        raise RuntimeError("Alembic 没有可用的 Migration head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

    return current_revision, head_revision


def _backup_database_before_upgrade(
    database_path: Path,
    app_data_dir: Path,
    current_revision: str | None,
) -> Path:
    """在 Schema Upgrade 前使用 SQLite backup API 创建一致性备份。

    为什么不能直接 ``shutil.copy(app.db)``：
    SQLite 未来可能启用 WAL，普通文件复制可能遗漏尚未 checkpoint 的事务；SQLite
    自带的 ``Connection.backup()`` 能获得一致性数据库快照，更适合作为 Migration 前备份。

    本函数只复制应用数据库，不修改源数据库，不包含 Project Workspace 媒体文件。
    """

    backups_dir = app_data_dir / BACKUPS_DIRNAME
    backups_dir.mkdir(parents=True, exist_ok=True)

    revision_label = current_revision or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backups_dir / f"app_{timestamp}_{revision_label}.db"

    with sqlite3.connect(database_path) as source_connection:
        with sqlite3.connect(backup_path) as backup_connection:
            source_connection.backup(backup_connection)

    return backup_path


def init_database(app_data_path: Path | None = None) -> Path:
    """初始化或安全升级 AI Drama Studio 的应用级 ``app.db``。

    业务作用：
    1. 确保应用数据目录存在；
    2. 固定使用 ``app.db``；
    3. 新数据库直接通过 Alembic 升级到当前 head；
    4. 已存在数据库如果 revision 落后于代码 head，先使用 SQLite backup API 保存快照；
    5. 备份成功后才执行 Alembic upgrade；
    6. 同一 Python 进程中，同一个数据库完成 Migration 后直接复用，不在每个 HTTP 请求中
       重复运行 Alembic；并发首次访问由线程锁串行化。

    F01 兼容性：
    - 返回值仍然是 ``app.db`` Path；
    - F01 的数据库位置、projects 字段和创建/打开项目语义完全不变；
    - 已经在最新 revision 时不会重复备份，也不会重复建表。

    F02 为什么需要升级前备份：
    F02 新增 ``0002_create_source_videos``，这是第一次升级用户已经实际使用过的 F01
    数据库。如果 Migration 失败，必须保留升级前可恢复快照，不能让用户只剩半升级状态。

    并发安全：
    - FastAPI 启动 lifespan 会首先调用本函数；正常请求随后命中进程内缓存；
    - 如果多个线程同时首次调用，只有第一个线程执行 revision 检查/备份/upgrade；
    - Migration 成功以后才写入缓存，失败不会把数据库错误标记为“已初始化”；
    - 开发时代码 reload 会启动新 Python 进程，因此新 Migration 仍会在新进程启动时检查。

    安全边界：
    - 只处理应用级 ``app.db`` 和 ``backups/``；
    - 不创建或修改 Project Workspace；
    - 不插入 Project / Source Video 业务数据；
    - Migration 失败时不删除升级前备份。

    Args:
        app_data_path: 可选应用数据目录。测试传临时目录；正式运行留空，由
            ``get_app_data_path()`` 按 F01 冻结规则解析。

    Returns:
        Path: 初始化/升级完成后的 ``app.db`` 绝对路径。

    Raises:
        OSError: 应用数据目录或备份目录无法创建、数据库无法访问。
        RuntimeError: Migration head 无法确定。
        alembic.util.exc.CommandError: Alembic 配置或 Migration 执行失败。
    """

    data_dir = (app_data_path or get_app_data_path()).expanduser().resolve(strict=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = (data_dir / DATABASE_FILENAME).resolve(strict=False)

    # 即使绝大多数请求都已初始化，也必须让“检查缓存 + 首次初始化”保持一个原子区间。
    # RLock 开销远小于 SQLite/Alembic；后续请求只进入几条 Python 指令就立即返回。
    with _DATABASE_INIT_LOCK:
        if database_path in _INITIALIZED_DATABASE_PATHS:
            return database_path

        database_existed = database_path.is_file() and database_path.stat().st_size > 0
        alembic_config = _build_alembic_config(database_path)

        if database_existed:
            current_revision, head_revision = _read_database_revision(database_path, alembic_config)
            if current_revision != head_revision:
                _backup_database_before_upgrade(
                    database_path=database_path,
                    app_data_dir=data_dir,
                    current_revision=current_revision,
                )

        command.upgrade(alembic_config, MIGRATION_HEAD)
        _INITIALIZED_DATABASE_PATHS.add(database_path)
        return database_path
