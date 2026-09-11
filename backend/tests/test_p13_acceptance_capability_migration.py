import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection


def _load_migration() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0024_p13_acceptance_capability.py"
    spec = importlib.util.spec_from_file_location("p13_acceptance_capability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(connection: Connection) -> tuple[dict[str, str | None], dict[str, int]]:
    projects = {
        row.id: row.current_plan_id
        for row in connection.execute(
            sa.text("SELECT id, current_plan_id FROM projects ORDER BY id")
        )
    }
    plans = {
        row.id: row.is_current
        for row in connection.execute(
            sa.text("SELECT id, is_current FROM project_execution_plans ORDER BY id")
        )
    }
    return projects, plans


def test_p13_acceptance_migration_invalidates_only_replica_cached_plans() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE projects ("
            "id VARCHAR(64) PRIMARY KEY, project_type VARCHAR(32) NOT NULL, current_plan_id VARCHAR(64) NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE project_execution_plans ("
            "id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL, is_current INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO projects (id, project_type, current_plan_id) VALUES "
            "('replica', 'REPLICA', 'plan-replica'),"
            "('redraw', 'REDRAW', 'plan-redraw')"
        )
        connection.exec_driver_sql(
            "INSERT INTO project_execution_plans (id, project_id, is_current) VALUES "
            "('plan-replica', 'replica', 1),"
            "('plan-redraw', 'redraw', 1)"
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        projects, plans = _state(connection)
        assert projects == {"redraw": "plan-redraw", "replica": None}
        assert plans == {"plan-redraw": 1, "plan-replica": 0}

        connection.execute(
            sa.text(
                "UPDATE projects SET current_plan_id = 'plan-replica' WHERE id = 'replica'"
            )
        )
        connection.execute(
            sa.text(
                "UPDATE project_execution_plans SET is_current = 1 WHERE id = 'plan-replica'"
            )
        )
        migration.downgrade()
        projects, plans = _state(connection)
        assert projects == {"redraw": "plan-redraw", "replica": None}
        assert plans == {"plan-redraw": 1, "plan-replica": 0}
