from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import content_analysis_v2, shot_revision_v2, studio_v2  # noqa: F401


def setup_episode(monkeypatch, tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    with factory() as session:
        project = studio_v2.Project(
            id="PROJECT_1",
            name="Revision Test",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        )
        episode = studio_v2.Episode(
            id="EPISODE_1",
            project_id=project.id,
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="x" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=2_000_000,
        )
        session.add_all([project, episode])
        session.flush()
        for ordinal, start_us, end_us in [(1, 0, 1_000_000), (2, 1_000_000, 2_000_000)]:
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}",
                episode_id=episode.id,
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(tmp_path / f"r{ordinal}.mp4"),
                thumbnail_path=str(tmp_path / f"t{ordinal}.jpg"),
                keyframes_json="[]",
                status="READY",
            ))
        session.commit()
    return factory


def new_payloads(tmp_path: Path):
    return [
        {
            "ordinal": 1,
            "start_us": 0,
            "end_us": 800_000,
            "duration_us": 800_000,
            "reference_clip_path": str(tmp_path / "new1.mp4"),
            "thumbnail_path": str(tmp_path / "new1.jpg"),
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        },
        {
            "ordinal": 2,
            "start_us": 800_000,
            "end_us": 2_000_000,
            "duration_us": 1_200_000,
            "reference_clip_path": str(tmp_path / "new2.mp4"),
            "thumbnail_path": str(tmp_path / "new2.jpg"),
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        },
    ]


def test_auto_rerun_keeps_baseline_and_switches_current(monkeypatch, tmp_path: Path) -> None:
    setup_episode(monkeypatch, tmp_path)

    result = shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_payloads(tmp_path))
    assert result[0]["end_us"] == 800_000

    revisions = shot_revision_v2.list_shot_revisions("EPISODE_1")
    assert [(item["revision"], item["kind"], item["is_current"]) for item in revisions] == [
        (2, "AUTO", True),
        (1, "BASELINE", False),
    ]

    old = shot_revision_v2.get_shot_revision(revisions[1]["id"])
    assert old is not None
    assert [item["end_us"] for item in old["shots"]] == [1_000_000, 2_000_000]


def test_failed_database_switch_rolls_back_old_current(monkeypatch, tmp_path: Path) -> None:
    setup_episode(monkeypatch, tmp_path)
    baseline = shot_revision_v2.ensure_current_revision("EPISODE_1")
    assert baseline is not None and baseline["is_current"] is True

    invalid = new_payloads(tmp_path)
    invalid[1]["ordinal"] = 1
    with pytest.raises(Exception):
        shot_revision_v2.commit_auto_shot_revision("EPISODE_1", invalid)

    current = studio_v2.list_shots("EPISODE_1")
    assert [item["end_us"] for item in current] == [1_000_000, 2_000_000]
    revisions = shot_revision_v2.list_shot_revisions("EPISODE_1")
    assert len(revisions) == 1
    assert revisions[0]["revision"] == 1
    assert revisions[0]["is_current"] is True


def test_restore_creates_new_revision_without_rewriting_history(monkeypatch, tmp_path: Path) -> None:
    setup_episode(monkeypatch, tmp_path)
    shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_payloads(tmp_path))
    revisions = shot_revision_v2.list_shot_revisions("EPISODE_1")
    baseline_id = next(item["id"] for item in revisions if item["revision"] == 1)

    restored = shot_revision_v2.restore_shot_revision(baseline_id)
    assert [item["end_us"] for item in restored] == [1_000_000, 2_000_000]

    after = shot_revision_v2.list_shot_revisions("EPISODE_1")
    assert [(item["revision"], item["kind"], item["is_current"]) for item in after] == [
        (3, "RESTORE", True),
        (2, "AUTO", False),
        (1, "BASELINE", False),
    ]
    assert after[0]["source_revision_id"] == baseline_id
