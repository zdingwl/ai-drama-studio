from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import project_management_v1, studio_v2


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(
        studio_v2,
        "SessionLocal",
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def test_project_management_create_update_and_soft_delete(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)

    project = project_management_v1.create_managed_project(
        name="美国版测试项目",
        source_language="zh",
        target_language="en",
        target_region="US",
        redraw_rules=["CHARACTER", "LANGUAGE"],
    )
    assert project["name"] == "美国版测试项目"
    assert project["source_language"] == "zh"
    assert project["target_language"] == "en"
    assert project["target_region"] == "US"
    assert project["redraw_rules"] == ["CHARACTER", "LANGUAGE"]

    listed = project_management_v1.list_managed_projects()
    assert [item["id"] for item in listed] == [project["id"]]

    updated = project_management_v1.update_managed_project(
        project["id"],
        name="英国版测试项目",
        source_language="zh",
        target_language="en",
        target_region="GB",
        redraw_rules=["SCENE", "LANGUAGE"],
    )
    assert updated["name"] == "英国版测试项目"
    assert updated["target_region"] == "GB"
    assert updated["redraw_rules"] == ["SCENE", "LANGUAGE"]

    project_management_v1.soft_delete_managed_project(project["id"])
    assert project_management_v1.list_managed_projects() == []
    with pytest.raises(LookupError):
        project_management_v1.get_managed_project(project["id"])

    # 删除只是项目管理层软删除，原项目和工作区数据仍然保留，避免误删生产资产。
    underlying = studio_v2.get_project(project["id"])
    assert underlying is not None
    assert underlying["name"] == "英国版测试项目"


def test_project_management_defaults_existing_project_rules(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    legacy = studio_v2.create_project(
        name="旧项目",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )

    managed = project_management_v1.get_managed_project(legacy["id"])
    assert managed["redraw_rules"] == ["CHARACTER", "SCENE", "LANGUAGE"]


def test_project_management_requires_at_least_one_redraw_rule(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="至少选择一项"):
        project_management_v1.create_managed_project(
            name="无规则项目",
            source_language="zh",
            target_language="en",
            target_region="US",
            redraw_rules=[],
        )
