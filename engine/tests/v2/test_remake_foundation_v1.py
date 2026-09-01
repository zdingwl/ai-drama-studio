from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import remake_policy_v1, review_issue_v1, studio_v2


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", session_factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def seed_project(monkeypatch, tmp_path: Path) -> str:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="Remake V1",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    return project["id"]


def test_project_remake_policy_defaults_and_updates(monkeypatch, tmp_path: Path) -> None:
    project_id = seed_project(monkeypatch, tmp_path)

    policy = remake_policy_v1.get_project_remake_policy(project_id)
    assert policy is not None
    assert policy["scene_policy"] == "AUTO"
    assert policy["character_policy"] == "LOCALIZE"
    assert policy["generation_engine"] == "MINIMAX_H3_LOCAL"

    updated = remake_policy_v1.update_project_remake_policy(
        project_id,
        scene_policy="keep",
    )
    assert updated["scene_policy"] == "KEEP"
    assert updated["character_policy"] == "LOCALIZE"


def test_review_issue_is_upserted_and_resolved(monkeypatch, tmp_path: Path) -> None:
    project_id = seed_project(monkeypatch, tmp_path)

    first = review_issue_v1.upsert_review_issue(
        project_id=project_id,
        source_key="auto:shot:SHOT_1",
        issue_type="SHOT_BOUNDARY",
        reason="边界可信度较低",
        ai_suggestion={"confidence": 0.51},
    )
    assert first["status"] == "OPEN"

    second = review_issue_v1.upsert_review_issue(
        project_id=project_id,
        source_key="auto:shot:SHOT_1",
        issue_type="SHOT_BOUNDARY",
        reason="镜头过短",
        severity="BLOCKING",
    )
    assert second["id"] == first["id"]
    assert second["severity"] == "BLOCKING"
    assert second["reason"] == "镜头过短"

    open_items = review_issue_v1.list_review_issues(project_id)
    assert [item["id"] for item in open_items] == [first["id"]]

    resolved = review_issue_v1.set_review_issue_status(
        first["id"],
        status="RESOLVED",
        resolution={"manual": True},
    )
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_at"] is not None
    assert review_issue_v1.list_review_issues(project_id) == []
