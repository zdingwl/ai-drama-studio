import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0023_p13_visual_identity_scope_v2.py"
    spec = importlib.util.spec_from_file_location("p13_visual_identity_scope_v2", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p13_visual_identity_scope_migration_only_supersedes_pending_candidates() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE replica_target_assets_candidates ("
            "id VARCHAR(64) PRIMARY KEY, review_status VARCHAR(32) NOT NULL, review_reason TEXT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO replica_target_assets_candidates (id, review_status, review_reason) VALUES "
            "('pending', 'NEEDS_REVIEW', NULL),"
            "('accepted', 'ACCEPTED', 'accepted before migration'),"
            "('rejected', 'REJECTED', 'rejected before migration'),"
            "('superseded', 'SUPERSEDED', 'older reason')"
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        rows = {
            row.id: (row.review_status, row.review_reason)
            for row in connection.execute(
                sa.text(
                    "SELECT id, review_status, review_reason "
                    "FROM replica_target_assets_candidates ORDER BY id"
                )
            )
        }
        assert rows["pending"] == ("SUPERSEDED", migration._MIGRATION_REASON)
        assert rows["accepted"] == ("ACCEPTED", "accepted before migration")
        assert rows["rejected"] == ("REJECTED", "rejected before migration")
        assert rows["superseded"] == ("SUPERSEDED", "older reason")

        migration.downgrade()
        rows = {
            row.id: (row.review_status, row.review_reason)
            for row in connection.execute(
                sa.text(
                    "SELECT id, review_status, review_reason "
                    "FROM replica_target_assets_candidates ORDER BY id"
                )
            )
        }
        assert rows["pending"] == ("NEEDS_REVIEW", None)
        assert rows["accepted"] == ("ACCEPTED", "accepted before migration")
        assert rows["rejected"] == ("REJECTED", "rejected before migration")
        assert rows["superseded"] == ("SUPERSEDED", "older reason")
