from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import shot_editor_v2, shot_revision_v2, studio_v2


class FakePending:
    def commit_files(self) -> None:
        pass

    def cleanup(self) -> None:
        pass


def setup_timeline(monkeypatch, tmp_path: Path) -> tuple[str, list[str], sessionmaker]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(shot_editor_v2, "get_session", lambda: session_factory())
    monkeypatch.setattr(studio_v2, "SessionLocal", session_factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(shot_editor_v2, "episode_dir", studio_v2.episode_dir)
    monkeypatch.setattr(shot_editor_v2, "_render_pending", lambda *args, **kwargs: FakePending())

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")

    with session_factory() as session:
        project = studio_v2.Project(
            id="PROJECT_1",
            name="Shot Edit Test",
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
            duration_us=3_000_000,
        )
        session.add_all([project, episode])
        session.flush()
        shot_ids: list[str] = []
        for ordinal, start_us, end_us in [
            (1, 0, 1_000_000),
            (2, 1_000_000, 2_000_000),
            (3, 2_000_000, 3_000_000),
        ]:
            shot_id = f"SHOT_{ordinal}"
            shot_ids.append(shot_id)
            session.add(studio_v2.Shot(
                id=shot_id,
                episode_id=episode.id,
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(tmp_path / f"shot_{ordinal}.mp4"),
                thumbnail_path=str(tmp_path / f"shot_{ordinal}.jpg"),
                keyframes_json="[]",
                status="READY",
            ))
        session.commit()
    return "EPISODE_1", shot_ids, session_factory


def assert_continuous(shots: list[dict]) -> None:
    assert [shot["ordinal"] for shot in shots] == list(range(1, len(shots) + 1))
    assert shots[0]["start_us"] == 0
    assert shots[-1]["end_us"] == 3_000_000
    for left, right in zip(shots, shots[1:]):
        assert left["end_us"] == right["start_us"]
        assert left["duration_us"] == left["end_us"] - left["start_us"]
    assert shots[-1]["duration_us"] == shots[-1]["end_us"] - shots[-1]["start_us"]


def assert_manual_revision_created(episode_id: str) -> None:
    revisions = shot_revision_v2.list_shot_revisions(episode_id)
    assert len(revisions) == 2
    assert revisions[0]["revision"] == 2
    assert revisions[0]["kind"] == "MANUAL"
    assert revisions[0]["is_current"] is True
    assert revisions[1]["revision"] == 1
    assert revisions[1]["kind"] == "BASELINE"
    assert revisions[1]["is_current"] is False


def test_adjust_boundary_updates_both_adjacent_shots_and_versions(monkeypatch, tmp_path: Path) -> None:
    episode_id, shot_ids, _ = setup_timeline(monkeypatch, tmp_path)
    shots = shot_editor_v2.adjust_boundary(shot_id=shot_ids[1], side="start", source_time_us=1_200_000)
    assert shots[0]["end_us"] == 1_200_000
    assert shots[1]["start_us"] == 1_200_000
    assert_continuous(shots)
    assert_manual_revision_created(episode_id)


def test_split_keeps_left_id_and_creates_continuous_ordinals(monkeypatch, tmp_path: Path) -> None:
    episode_id, shot_ids, _ = setup_timeline(monkeypatch, tmp_path)
    shots = shot_editor_v2.split_shot(shot_id=shot_ids[1], source_time_us=1_500_000)
    assert len(shots) == 4
    assert shots[1]["id"] == shot_ids[1]
    assert shots[1]["end_us"] == 1_500_000
    assert shots[2]["start_us"] == 1_500_000
    assert_continuous(shots)
    assert_manual_revision_created(episode_id)


def test_merge_with_next_removes_one_boundary_and_keeps_timeline_continuous(monkeypatch, tmp_path: Path) -> None:
    episode_id, shot_ids, _ = setup_timeline(monkeypatch, tmp_path)
    shots = shot_editor_v2.merge_with_next(shot_id=shot_ids[0])
    assert len(shots) == 2
    assert shots[0]["id"] == shot_ids[0]
    assert shots[0]["end_us"] == 2_000_000
    assert_continuous(shots)
    assert_manual_revision_created(episode_id)
