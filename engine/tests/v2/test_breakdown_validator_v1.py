from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_service_v1, breakdown_validator_v1, shot_revision_v2, studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownEvidenceLink,
    BreakdownRun,
    DraftPropHint,
    DraftPropOccurrence,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
    TimelineEvent,
    TimelineEventSubject,
)
from engine.app.shot_revision_v2 import ShotRevisionItem


def setup_valid_draft(monkeypatch, tmp_path: Path):
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
            name="Breakdown Validator Test",
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

    run = breakdown_service_v1.create_breakdown_run("EPISODE_1", pipeline_profile="fixture-v1")
    with factory() as session:
        revision_items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == run.source_shot_revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        assert len(revision_items) == 2
        item1, item2 = revision_items

        segment1 = SceneSegmentDraft(
            id="SCENESEG_1",
            run_id=run.id,
            episode_id=run.episode_id,
            ordinal=1,
            source_start_us=item1.start_us,
            source_end_us=item1.end_us,
            location_hint="走廊",
            confidence=0.9,
        )
        segment2 = SceneSegmentDraft(
            id="SCENESEG_2",
            run_id=run.id,
            episode_id=run.episode_id,
            ordinal=2,
            source_start_us=item2.start_us,
            source_end_us=item2.end_us,
            location_hint="病房",
            confidence=0.8,
        )
        draft1 = ShotSemanticDraft(
            id="SHOTDRAFT_1",
            run_id=run.id,
            scene_segment_id=segment1.id,
            source_shot_revision_item_id=item1.id,
            source_shot_id_snapshot=item1.original_shot_id,
            shot_ordinal_snapshot=item1.ordinal,
            source_start_us=item1.start_us,
            source_end_us=item1.end_us,
            summary="人物A说话",
            confidence=0.95,
        )
        draft2 = ShotSemanticDraft(
            id="SHOTDRAFT_2",
            run_id=run.id,
            scene_segment_id=segment2.id,
            source_shot_revision_item_id=item2.id,
            source_shot_id_snapshot=item2.original_shot_id,
            shot_ordinal_snapshot=item2.ordinal,
            source_start_us=item2.start_us,
            source_end_us=item2.end_us,
            summary="切到病房",
            confidence=0.9,
        )
        local = LocalSubject(
            id="LOCALSUBJECT_1",
            run_id=run.id,
            scene_segment_id=segment1.id,
            ordinal=1,
            display_label="人物A",
            first_seen_us=100_000,
            last_seen_us=900_000,
            confidence=0.88,
        )
        presence = ShotLocalSubject(
            id="SHOTSUBJECT_1",
            run_id=run.id,
            shot_draft_id=draft1.id,
            local_subject_id=local.id,
            first_seen_us=100_000,
            last_seen_us=900_000,
            confidence=0.9,
        )
        event = TimelineEvent(
            id="EVENT_1",
            run_id=run.id,
            shot_draft_id=draft1.id,
            ordinal=1,
            event_type="DIALOGUE",
            source_start_us=200_000,
            source_end_us=400_000,
            shot_relative_start_us=200_000,
            shot_relative_end_us=400_000,
            content_text="你好",
            confidence=0.92,
            origin="RULE",
        )
        participant = TimelineEventSubject(
            id="EVENTSUBJECT_1",
            event_id=event.id,
            local_subject_id=local.id,
            role="SPEAKER",
            confidence=0.9,
        )
        prop = DraftPropHint(
            id="PROPHINT_1",
            run_id=run.id,
            scene_segment_id=segment1.id,
            ordinal=1,
            label_hint="手机",
            first_seen_us=300_000,
            last_seen_us=600_000,
            confidence=0.75,
        )
        occurrence = DraftPropOccurrence(
            id="PROPOCC_1",
            prop_hint_id=prop.id,
            shot_draft_id=draft1.id,
            source_start_us=300_000,
            source_end_us=600_000,
            confidence=0.8,
        )
        evidence = BreakdownEvidenceLink(
            id="EVIDENCE_1",
            run_id=run.id,
            owner_type="SHOT_DRAFT",
            owner_id=draft1.id,
            source_type="RULE",
            role="SUPPORT",
            confidence=0.7,
        )
        session.add_all([
            segment1,
            segment2,
            draft1,
            draft2,
            local,
            presence,
            event,
            participant,
            prop,
            occurrence,
            evidence,
        ])
        session.commit()

    return factory, run.id


def error_codes(result: breakdown_validator_v1.BreakdownValidationResult) -> set[str]:
    return {item.code for item in result.errors}


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


def test_valid_draft_passes_and_publish_uses_validator_counts(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)

    result = breakdown_validator_v1.validate_breakdown_run(run_id)
    assert result.passed is True
    assert result.errors == ()
    assert result.counts == {
        "scene_segment": 2,
        "shot": 2,
        "local_subject": 1,
        "shot_local_subject": 1,
        "timeline_event": 1,
        "timeline_event_subject": 1,
        "prop_hint": 1,
        "prop_occurrence": 1,
        "evidence_link": 1,
    }

    published = breakdown_service_v1.publish_breakdown_run(run_id)
    assert published.status == "READY"
    assert published.is_current is True
    assert json.loads(published.counts_json)["shot"] == 2

    with factory() as session:
        row = session.get(BreakdownRun, run_id)
        assert row is not None and row.is_current is True


def test_missing_revision_item_draft_is_hard_failure_and_publish_marks_failed(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)
    with factory() as session:
        draft = session.get(ShotSemanticDraft, "SHOTDRAFT_2")
        assert draft is not None
        session.delete(draft)
        session.commit()

    result = breakdown_validator_v1.validate_breakdown_run(run_id)
    assert "SHOT_DRAFT_CARDINALITY" in error_codes(result)
    assert result.passed is False

    with pytest.raises(breakdown_service_v1.BreakdownValidationGateError, match="SHOT_DRAFT_CARDINALITY"):
        breakdown_service_v1.publish_breakdown_run(run_id)

    with factory() as session:
        run = session.get(BreakdownRun, run_id)
        assert run is not None and run.status == "FAILED" and run.is_current is False


def test_snapshot_and_scene_coverage_must_match_revision_items(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)
    with factory() as session:
        draft = session.get(ShotSemanticDraft, "SHOTDRAFT_1")
        assert draft is not None
        draft.source_end_us = 900_000
        session.commit()

    codes = error_codes(breakdown_validator_v1.validate_breakdown_run(run_id))
    assert "SHOT_DRAFT_SNAPSHOT_MISMATCH" in codes
    assert "SEGMENT_TIME_COVERAGE_MISMATCH" in codes


def test_subject_event_and_prop_cannot_cross_scene_segment(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)
    with factory() as session:
        session.add(ShotLocalSubject(
            id="SHOTSUBJECT_CROSS",
            run_id=run_id,
            shot_draft_id="SHOTDRAFT_2",
            local_subject_id="LOCALSUBJECT_1",
            first_seen_us=1_100_000,
            last_seen_us=1_300_000,
            confidence=0.7,
        ))
        event = TimelineEvent(
            id="EVENT_2",
            run_id=run_id,
            shot_draft_id="SHOTDRAFT_2",
            ordinal=1,
            event_type="ACTION",
            source_start_us=1_200_000,
            source_end_us=1_400_000,
            shot_relative_start_us=200_000,
            shot_relative_end_us=400_000,
            content_text="人物A进入",
            confidence=0.8,
            origin="RULE",
        )
        session.add(event)
        session.add(TimelineEventSubject(
            id="EVENTSUBJECT_CROSS",
            event_id=event.id,
            local_subject_id="LOCALSUBJECT_1",
            role="ACTOR",
            confidence=0.8,
        ))
        session.add(DraftPropOccurrence(
            id="PROPOCC_CROSS",
            prop_hint_id="PROPHINT_1",
            shot_draft_id="SHOTDRAFT_2",
            source_start_us=1_200_000,
            source_end_us=1_400_000,
            confidence=0.8,
        ))
        session.commit()

    codes = error_codes(breakdown_validator_v1.validate_breakdown_run(run_id))
    assert "SHOT_SUBJECT_CROSS_SEGMENT" in codes
    assert "EVENT_SUBJECT_CROSS_SEGMENT" in codes
    assert "PROP_OCCURRENCE_CROSS_SEGMENT" in codes


def test_event_prop_time_and_confidence_ranges_are_enforced(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)
    with factory() as session:
        event = session.get(TimelineEvent, "EVENT_1")
        occurrence = session.get(DraftPropOccurrence, "PROPOCC_1")
        prop = session.get(DraftPropHint, "PROPHINT_1")
        assert event is not None and occurrence is not None and prop is not None
        event.source_end_us = 1_100_000
        occurrence.source_end_us = 1_100_000
        prop.confidence = 1.2
        session.commit()

    codes = error_codes(breakdown_validator_v1.validate_breakdown_run(run_id))
    assert "EVENT_RANGE_OUTSIDE_SHOT" in codes
    assert "EVENT_RELATIVE_TIME_MISMATCH" in codes
    assert "PROP_OCCURRENCE_RANGE_OUTSIDE_SHOT" in codes
    assert "CONFIDENCE_OUT_OF_RANGE" in codes


def test_cross_run_subject_event_prop_and_evidence_links_are_rejected(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)
    foreign_run = breakdown_service_v1.create_breakdown_run("EPISODE_1")
    with factory() as session:
        segment = SceneSegmentDraft(
            id="SCENESEG_FOREIGN",
            run_id=foreign_run.id,
            episode_id="EPISODE_1",
            ordinal=1,
            source_start_us=0,
            source_end_us=1_000_000,
            confidence=0.8,
        )
        local = LocalSubject(
            id="LOCALSUBJECT_FOREIGN",
            run_id=foreign_run.id,
            scene_segment_id=segment.id,
            ordinal=1,
            display_label="人物A",
            first_seen_us=100_000,
            last_seen_us=500_000,
            confidence=0.8,
        )
        prop = DraftPropHint(
            id="PROPHINT_FOREIGN",
            run_id=foreign_run.id,
            scene_segment_id=segment.id,
            ordinal=1,
            label_hint="合同",
            first_seen_us=100_000,
            last_seen_us=500_000,
            confidence=0.8,
        )
        session.add_all([segment, local, prop])
        session.flush()
        session.add(ShotLocalSubject(
            id="SHOTSUBJECT_FOREIGN",
            run_id=run_id,
            shot_draft_id="SHOTDRAFT_1",
            local_subject_id=local.id,
            first_seen_us=100_000,
            last_seen_us=300_000,
            confidence=0.8,
        ))
        session.add(TimelineEventSubject(
            id="EVENTSUBJECT_FOREIGN",
            event_id="EVENT_1",
            local_subject_id=local.id,
            role="LISTENER",
            confidence=0.8,
        ))
        session.add(DraftPropOccurrence(
            id="PROPOCC_FOREIGN",
            prop_hint_id=prop.id,
            shot_draft_id="SHOTDRAFT_1",
            source_start_us=100_000,
            source_end_us=300_000,
            confidence=0.8,
        ))
        session.add(BreakdownEvidenceLink(
            id="EVIDENCE_FOREIGN",
            run_id=run_id,
            owner_type="LOCAL_SUBJECT",
            owner_id=local.id,
            source_type="RULE",
            role="CONTEXT",
            confidence=0.8,
        ))
        session.commit()

    codes = error_codes(breakdown_validator_v1.validate_breakdown_run(run_id))
    assert "SHOT_SUBJECT_CROSS_RUN" in codes
    assert "EVENT_SUBJECT_CROSS_RUN" in codes
    assert "PROP_OCCURRENCE_CROSS_RUN" in codes
    assert "EVIDENCE_OWNER_CROSS_RUN" in codes


def test_stale_historical_run_remains_structurally_valid_after_source_revision_change(monkeypatch, tmp_path: Path) -> None:
    factory, run_id = setup_valid_draft(monkeypatch, tmp_path)
    breakdown_service_v1.publish_breakdown_run(run_id)

    shot_revision_v2.commit_auto_shot_revision("EPISODE_1", new_payloads(tmp_path))
    result = breakdown_validator_v1.validate_breakdown_run(run_id)

    with factory() as session:
        run = session.get(BreakdownRun, run_id)
        assert run is not None
        assert run.status == "STALE"
        assert run.is_current is False

    assert result.passed is True
    assert "CURRENT_RUN_SOURCE_STALE" not in error_codes(result)
