from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import remake_policy_v1, studio_v2, target_localization_routes_v1


def _use_temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    return factory


def test_remake_policy_read_returns_virtual_defaults_without_insert(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    factory = _use_temp_db(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="只读策略测试",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )

    policy = remake_policy_v1.get_project_remake_policy(project["id"])

    assert policy["scene_policy"] == "AUTO"
    assert policy["character_policy"] == "LOCALIZE"
    assert policy["generation_engine"] == "MINIMAX_H3_LOCAL"
    with factory() as session:
        assert session.get(remake_policy_v1.ProjectRemakePolicy, project["id"]) is None


def test_explicit_remake_policy_update_still_persists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    factory = _use_temp_db(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="显式策略测试",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )

    updated = remake_policy_v1.update_project_remake_policy(
        project["id"],
        scene_policy="KEEP",
    )

    assert updated["scene_policy"] == "KEEP"
    with factory() as session:
        row = session.get(remake_policy_v1.ProjectRemakePolicy, project["id"])
        assert row is not None
        assert row.scene_policy == "KEEP"


def test_target_localization_get_only_reads_current_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(project_id: str):
        calls.append(project_id)
        return {"schema_version": "target-localization-v1", "project_id": project_id}

    monkeypatch.setattr(target_localization_routes_v1, "get_target_localization_v1", fake_get)

    result = target_localization_routes_v1.api_get_target_localization("PROJECT_READ_ONLY")

    assert result == {
        "schema_version": "target-localization-v1",
        "project_id": "PROJECT_READ_ONLY",
    }
    assert calls == ["PROJECT_READ_ONLY"]
