from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

from engine.app.core import database as database_module
from engine.app.core.database import init_database


def test_init_database_is_safe_when_multiple_requests_start_together(tmp_path: Path) -> None:
    """多个 FastAPI worker thread 同时访问时只能串行执行首次 Alembic Migration。"""

    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(lambda _: init_database(tmp_path), range(16)))

    assert paths
    assert all(path == paths[0] for path in paths)
    assert paths[0].is_file()

    with sqlite3.connect(paths[0]) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert revision == ("0006_create_final_shots",)


def test_initialized_database_does_not_run_alembic_again_on_business_requests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """启动完成以后，缩略图/播放器等业务请求调用 init_database 时不得重复 upgrade。"""

    database_path = init_database(tmp_path)

    def unexpected_upgrade(*_args, **_kwargs) -> None:
        raise AssertionError("Alembic upgrade must not run again for an initialized database")

    monkeypatch.setattr(database_module.command, "upgrade", unexpected_upgrade)

    assert init_database(tmp_path) == database_path
    assert init_database(tmp_path) == database_path
