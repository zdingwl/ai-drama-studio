from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import character_gallery_routes_v10 as routes
from engine.app import studio_v2
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun


def _session_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _track(track_id: str, shot_id: str, sample_count: int, *, recovered: bool = False) -> CharacterTrack:
    recovery = None
    if recovered:
        recovery = {
            "source": "V10_1_SHOT_FRAGMENT_AGGREGATION",
            "target_candidate_id": "CHAR_CANDIDATE_A",
            "shot_id": shot_id,
            "score": 0.88,
        }
    return CharacterTrack(
        id=track_id,
        run_id="RUN_A",
        candidate_id="CHAR_CANDIDATE_A",
        shot_id=shot_id,
        start_us=0,
        end_us=500_000,
        representative_source_us=250_000,
        bbox_json="[10,20,100,200]",
        sample_count=sample_count,
        face_visible=False,
        mean_face_score=None,
        body_evidence_score=0.85,
        evidence_json=json.dumps({"identity_recovery": recovery}),
    )


def test_gallery_api_exposes_all_track_evidence_shots_not_only_gallery_subset(monkeypatch, tmp_path: Path) -> None:
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(routes, "get_session", lambda: SessionLocal())

    gallery_root = tmp_path / "analysis" / "RUN_A" / "characters" / "character_001"
    gallery_root.mkdir(parents=True)
    cover_path = gallery_root / "gallery_001.jpg"
    manifest_path = gallery_root / "gallery.json"
    manifest_path.write_text(json.dumps({
        "identity_status": "RESOLVED",
        "policy": "test gallery subset",
        "images": [{
            "path": str(cover_path),
            "shot_id": "SHOT_1",
            "shot_ordinal": 1,
            "source_time_us": 100_000,
            "instance_id": "SHOT_1:100000:P01",
            "instance_class": "CLEAN",
            "quality": 0.95,
            "reliability": 1.0,
            "seed_eligible": True,
            "face_visible": False,
            "feature_channels": ["person_reid"],
        }],
    }), encoding="utf-8")

    with SessionLocal() as session:
        session.add(studio_v2.Project(
            id="PROJECT_A",
            name="Gallery Evidence Test",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EP_1",
            project_id="PROJECT_A",
            title="第一集",
            original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"),
            source_sha256="a" * 64,
            sort_order=1,
            status="READY",
        ))
        for ordinal in range(1, 4):
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}",
                episode_id="EP_1",
                ordinal=ordinal,
                start_us=(ordinal - 1) * 1_000_000,
                end_us=ordinal * 1_000_000,
                duration_us=1_000_000,
                reference_clip_path=str(tmp_path / f"shot_{ordinal}.mp4"),
                status="READY",
            ))
        session.add(ContentAnalysisRun(
            id="RUN_A",
            project_id="PROJECT_A",
            status="READY",
            is_current=True,
            profile_version="f05-assets-v10.1-person-evidence-model-classification",
            component_status_json="{}",
            counts_json="{}",
        ))
        session.add(CharacterCandidate(
            id="CHAR_CANDIDATE_A",
            run_id="RUN_A",
            project_id="PROJECT_A",
            ordinal=1,
            auto_label="人物 001",
            track_count=4,
            shot_count=3,
            confidence=0.93,
            cover_path=str(cover_path),
            evidence_json=json.dumps({"identity_status": "RESOLVED"}),
        ))
        session.add_all([
            _track("TRACK_1A", "SHOT_1", 3),
            _track("TRACK_1B", "SHOT_1", 2),
            _track("TRACK_2", "SHOT_2", 4, recovered=True),
            _track("TRACK_3", "SHOT_3", 1),
        ])
        session.commit()

    payload = routes.get_character_gallery("CHAR_CANDIDATE_A")

    assert payload["gallery_image_count"] == 1
    assert payload["evidence_shot_count"] == 3
    assert [item["shot_ordinal"] for item in payload["evidence_shots"]] == [1, 2, 3]
    assert payload["evidence_shots"][0]["track_count"] == 2
    assert payload["evidence_shots"][0]["sample_count"] == 5
    assert payload["evidence_shots"][1]["recovered_track_count"] == 1
    assert payload["evidence_shots"][1]["recovery_sources"] == ["V10_1_SHOT_FRAGMENT_AGGREGATION"]

    # The visual response is exhaustive by Shot even though the bounded Gallery itself
    # selected only SHOT_1. SHOT_2/3 receive persisted Track representative crop URLs.
    assert payload["image_count"] == 3
    by_shot = {item["shot_id"]: item for item in payload["images"]}
    assert by_shot["SHOT_1"]["source_kind"] == "gallery"
    assert by_shot["SHOT_2"]["source_kind"] == "track_representative"
    assert by_shot["SHOT_3"]["source_kind"] == "track_representative"
    assert by_shot["SHOT_2"]["url"].endswith("/evidence-shot/SHOT_2")
