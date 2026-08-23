"""AI Drama Studio 的 Alembic Migration 运行环境。

F01 只通过这里执行版本化数据库变更，不在业务函数中手写 CREATE TABLE。
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = None


def run_migrations_offline() -> None:
    """离线执行 Migration；主要保留 Alembic 标准能力。"""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """连接 init_database() 指定的 app.db 并执行 Migration。"""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
