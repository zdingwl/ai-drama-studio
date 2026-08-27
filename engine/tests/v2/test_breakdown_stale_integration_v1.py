from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import (
    breakdown_serializer_v1,
    breakdown_service_v1,
    shot_edit_routes_v2,
    shot_editor_v2,
    shot_revision_v2,
    studio_v2,
)
from engine.app.breakdown_models_v1 import BreakdownRun, SceneSegmentDraft, ShotSemanticDraft
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem


class FakePending:
    def commit_files(self) -> None:
        pass

    def cleanup(self) -> None:
        pass


def setup_episode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    monkeypatch.setattr(shot_editor_v2, "get_session", lambda: factory())
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(shot_editor_v2, "episode_dir", studio_v2.episode_dir)
    monkeypatch.setattr(shot_editor_v2, "_render_pending", lambda *args, **kwargs: FakePending())

    source = tmp_path / "source.mp4"
    source.write_bytes(b"episode-source")
    with factory() as session:
        project = studio_v2.Project(
            id="PROJECT_1",
            name="P1.6 STALE Integration",
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
        for ordinal, start_us, end_us in [
            (1, 0, 1_000_000),
            (2, 1_000_000, 2_000_000),
            (3, 2_000_000, 3_000_000),
        ]:
            reference = tmp_path / f"reference-{ordinal}.mp4"
            thumbnail = tmp_path / f"thumbnail-{ordinal}.jpg"
            reference.write_bytes(f"old-reference-{ordinal}".encode())
            thumbnail.write_bytes(f"old-thumbnail-{ordinal}".encode())
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}",
                episode_id=episode.id,
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(reference),
                thumbnail_path=str(thumbnail),
                keyframes_json="[]",
                short_description=f"shot {ordinal}",
                shot_type=None,
                camera_motion=None,
                status="READY",
            ))
        session.commit()
    return factory


def publish_simple_breakdown(factory: Any) -> tuple[BreakdownRun, list[ShotRevisionItem]]:
    run = breakdown_service_v1.create_breakdown_run("EPISODE_1", pipeline_profile="p1.6-test")
    with factory() as session:
        items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == run.source_shot_revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        assert items
        segment = SceneSegmentDraft(
            id=studio_v2.new_id("SCENESEG"),
            run_id=run.id,
            episode_id=run.episode_id,
            ordinal=1,
            source_start_us=items[0].start_us,
            source_end_us=items[-1].end_us,
            location_hint="test location",
            interior_exterior="INTERIOR",
            time_of_day="DAY",
            summary="P1.6 integration segment",
            confidence=1.0,
        )
        session.add(segment)
        session.flush()
        for item in items:
            session.add(ShotSemanticDraft(
                id=studio_v2.new_id("SHOTDRAFT"),
                run_id=run.id,
                scene_segment_id=segment.id,
                source_shot_revision_item_id=item.id,
                source_shot_id_snapshot=item.original_shot_id,
                shot_ordinal_snapshot=item.ordinal,
                source_start_us=item.start_us,
                source_end_us=item.end_us,
                summary=f"shot {item.ordinal}",
                confidence=1.0,
            ))
        session.commit()
    published = breakdown_service_v1.publish_breakdown_run(run.id)
    assert published.status == "READY"
    assert published.is_current is True
    return published, items


def new_auto_payloads(tmp_path: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for ordinal, start_us, end_us in [
        (1, 0, 1_400_000),
        (2, 1_400_000, 3_000_000),
    ]:
        reference = tmp_path / f"auto-reference-{ordinal}.mp4"
        thumbnail = tmp_path / f"auto-thumbnail-{ordinal}.jpg"
        reference.write_bytes(f"auto-reference-{ordinal}".encode())
        thumbnail.write_bytes(f"auto-thumbnail-{ordinal}".encode())
        payloads.append({
            "ordinal": ordinal,
            "start_us": start_us,
            "end_us": end_us,
            "duration_us": end_us - start_us,
            "reference_clip_path": str(reference),
            "thumbnail_path": str(thumbnail),
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        })
    return payloads


def assert_run_stale_and_history_readable(
    factory: Any,
    run_id: str,
    old_revision_id: str,
    old_item_id: str,
    expected_bytes: bytes,
) -> dict[str, Any]:
    with factory() as session:
        run = session.get(BreakdownRun, run_id)
        old_revision = session.get(ShotRevision, old_revision_id)
        old_item = session.get(ShotRevisionItem, old_item_id)
        current_revision = session.scalar(select(ShotRevision).where(
            ShotRevision.episode_id == "EPISODE_1",
            ShotRevision.is_current.is_(True),
        ))
        assert run is not None and run.status == "STALE" and run.is_current is False
        assert old_revision is not None and old_revision.is_current is False
        assert current_revision is not None and current_revision.id != old_revision_id
        assert old_item is not None
        assert Path(old_item.reference_clip_path).read_bytes() == expected_bytes

    historical = breakdown_serializer_v1.get_breakdown_run(run_id)
    assert historical is not None
    assert historical["run"]["status"] == "STALE"
    assert historical["run"]["source_shot_revision_id"] == old_revision_id
    historical_shot = historical["scene_segments"][0]["shots"][0]
    assert historical_shot["source_shot_revision_item"]["id"] == old_item_id
    return historical


@pytest.mark.parametrize("operation", ["adjust", "split", "merge"])
def test_manual_shot_mutations_automatically_stale_current_breakdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run, items = publish_simple_breakdown(factory)
    old_revision_id = run.source_shot_revision_id
    old_item_id = items[0].id

    if operation == "adjust":
        shot_editor_v2.adjust_boundary(shot_id="SHOT_2", side="start", source_time_us=1_200_000)
    elif operation == "split":
        shot_editor_v2.split_shot(shot_id="SHOT_2", source_time_us=1_500_000)
    else:
        shot_editor_v2.merge_with_next(shot_id="SHOT_1")

    historical = assert_run_stale_and_history_readable(
        factory,
        run.id,
        old_revision_id,
        old_item_id,
        b"old-reference-1",
    )
    assert historical["scene_segments"][0]["shots"][0]["source_shot_id_snapshot"] == "SHOT_1"
    assert breakdown_serializer_v1.get_current_breakdown("EPISODE_1") is None


def test_record_manual_revision_also_stales_old_breakdown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run, items = publish_simple_breakdown(factory)

    revision = shot_revision_v2.record_manual_revision("EPISODE_1", note="direct manual revision")
    assert revision["kind"] == "MANUAL" and revision["is_current"] is True

    assert_run_stale_and_history_readable(
        factory,
        run.id,
        run.source_shot_revision_id,
        items[0].id,
        b"old-reference-1",
    )


def test_auto_rerun_automatically_stales_breakdown_and_old_reference_api_stays_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run, items = publish_simple_breakdown(factory)
    old_shot_ids = {item.original_shot_id for item in items}

    new_shots = shot_revision_v2.commit_auto_shot_revision(
        "EPISODE_1",
        new_auto_payloads(tmp_path),
        note="P1.6 auto rerun",
    )
    assert old_shot_ids.isdisjoint({shot["id"] for shot in new_shots})

    historical = assert_run_stale_and_history_readable(
        factory,
        run.id,
        run.source_shot_revision_id,
        items[0].id,
        b"old-reference-1",
    )
    old_reference_url = historical["scene_segments"][0]["shots"][0]["source_shot_revision_item"]["reference_url"]

    app = FastAPI()
    app.include_router(shot_edit_routes_v2.router)
    response = TestClient(app).get(old_reference_url)
    assert response.status_code == 200
    assert response.content == b"old-reference-1"


def test_restore_creates_new_current_revision_and_stales_breakdown_from_pre_restore_current(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    first_run, _ = publish_simple_breakdown(factory)
    baseline_id = first_run.source_shot_revision_id

    shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_auto_payloads(tmp_path), note="prepare restore")
    with factory() as session:
        first = session.get(BreakdownRun, first_run.id)
        assert first is not None and first.status == "STALE"

    second_run, second_items = publish_simple_breakdown(factory)
    pre_restore_revision_id = second_run.source_shot_revision_id
    assert pre_restore_revision_id != baseline_id

    restored = shot_revision_v2.restore_shot_revision(baseline_id)
    assert [shot["end_us"] for shot in restored] == [1_000_000, 2_000_000, 3_000_000]

    assert_run_stale_and_history_readable(
        factory,
        second_run.id,
        pre_restore_revision_id,
        second_items[0].id,
        b"auto-reference-1",
    )
    revisions = shot_revision_v2.list_shot_revisions("EPISODE_1")
    assert revisions[0]["kind"] == "RESTORE"
    assert revisions[0]["source_revision_id"] == baseline_id


def test_processing_run_is_staled_when_shot_revision_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run = breakdown_service_v1.create_breakdown_run("EPISODE_1", pipeline_profile="processing-race")

    shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_auto_payloads(tmp_path))

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None
        assert row.status == "STALE"
        assert row.is_current is False
        assert row.completed_at is not None


def test_shot_revision_and_breakdown_stale_roll_back_together_on_transaction_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run, _ = publish_simple_breakdown(factory)
    before_revision_id = run.source_shot_revision_id
    before_shots = studio_v2.list_shots("EPISODE_1")

    original = shot_revision_v2._mark_breakdown_runs_stale

    def fail_after_stale(session: Any, episode_id: str, current_revision_id: str) -> list[str]:
        changed = original(session, episode_id, current_revision_id)
        assert changed == [run.id]
        raise RuntimeError("force rollback after stale mutation")

    monkeypatch.setattr(shot_revision_v2, "_mark_breakdown_runs_stale", fail_after_stale)
    with pytest.raises(RuntimeError, match="force rollback"):
        shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_auto_payloads(tmp_path))

    with factory() as session:
        current_revision = session.scalar(select(ShotRevision).where(
            ShotRevision.episode_id == "EPISODE_1",
            ShotRevision.is_current.is_(True),
        ))
        row = session.get(BreakdownRun, run.id)
        assert current_revision is not None and current_revision.id == before_revision_id
        assert row is not None and row.status == "READY" and row.is_current is True

    after_shots = studio_v2.list_shots("EPISODE_1")
    assert [(shot["id"], shot["start_us"], shot["end_us"]) for shot in after_shots] == [
        (shot["id"], shot["start_us"], shot["end_us"]) for shot in before_shots
    ]
