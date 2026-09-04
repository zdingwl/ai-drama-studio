from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.review_issue_routes_v1 import _require_confirmed_speaker_person
from engine.app.review_issue_v1 import set_review_issue_status, upsert_review_issue
from engine.app.source_dialogue_speaker_override_v1 import (
    load_episode_source_dialogue_speaker_overrides_v1,
    source_dialogue_signature_v1,
    upsert_source_dialogue_speaker_override_v1,
)


def _seed(monkeypatch, tmp_path: Path) -> tuple[str, str]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    project = studio_v2.create_project(
        name="speaker review",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    episode_id = "EP_SPEAKER_1"
    with factory() as session:
        session.add(studio_v2.Episode(
            id=episode_id,
            project_id=project["id"],
            title="第一集",
            original_filename="ep1.mp4",
            source_path=str(tmp_path / "ep1.mp4"),
            source_sha256="0" * 64,
            sort_order=1,
            status="IMPORTED",
        ))
        session.commit()
    return project["id"], episode_id


def test_speaker_issue_cannot_be_closed_without_writing_source_truth(monkeypatch, tmp_path: Path) -> None:
    project_id, episode_id = _seed(monkeypatch, tmp_path)
    issue = upsert_review_issue(
        project_id=project_id,
        episode_id=episode_id,
        source_key="auto:source-speaker:DIALOGUE_1",
        issue_type="SPEAKER",
        severity="BLOCKING",
        reason="说话人仍不明确",
    )

    with pytest.raises(ValueError, match="必须通过对应编辑器修改真实业务数据"):
        set_review_issue_status(issue["id"], status="RESOLVED", resolution={"manual": True})
    with pytest.raises(ValueError, match="必须通过对应编辑器修改真实业务数据"):
        set_review_issue_status(issue["id"], status="IGNORED", resolution={"manual": True})


def test_speaker_person_must_be_bound_to_final_character() -> None:
    people = {
        "PERSON_PENDING": {
            "person_key": "PERSON_PENDING",
            "display_name": "待确认人物",
            "character": None,
        },
        "PERSON_CONFIRMED": {
            "person_key": "PERSON_CONFIRMED",
            "display_name": "已确认人物",
            "character": {"id": "CHAR_1", "name": "人物一"},
        },
    }

    with pytest.raises(ValueError, match="请先确认人物身份"):
        _require_confirmed_speaker_person(people, person_key="PERSON_PENDING")

    confirmed = _require_confirmed_speaker_person(people, person_key="PERSON_CONFIRMED")
    assert confirmed["character"]["id"] == "CHAR_1"

    with pytest.raises(ValueError, match="不属于这条对白所在场景"):
        _require_confirmed_speaker_person(people, person_key="PERSON_MISSING")


def test_manual_speaker_override_is_persisted_with_dialogue_signature(monkeypatch, tmp_path: Path) -> None:
    project_id, episode_id = _seed(monkeypatch, tmp_path)
    dialogue = {
        "dialogue_key": "EP_SPEAKER_1:SHOTREV_1:H1:D1",
        "start_us": 1_000_000,
        "end_us": 2_000_000,
        "source_text": "你怎么会在这里？",
        "speakers": [],
    }

    saved = upsert_source_dialogue_speaker_override_v1(
        project_id=project_id,
        episode_id=episode_id,
        dialogue=dialogue,
        person_key="EP_SPEAKER_1:RUN_1:S1:P2",
    )
    loaded = load_episode_source_dialogue_speaker_overrides_v1(episode_id)

    assert saved["dialogue_signature"] == source_dialogue_signature_v1(dialogue)
    assert loaded[dialogue["dialogue_key"]] == {
        "person_key": "EP_SPEAKER_1:RUN_1:S1:P2",
        "dialogue_signature": saved["dialogue_signature"],
    }
