from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_g1_fusion_replay_completed_v1 as completed
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem


def _fixture_factory():
    engine = create_engine("sqlite:///:memory:")
    studio_v2.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_run(factory, *, status: str) -> None:
    with factory() as session:
        session.add(studio_v2.Project(
            id="PROJECT_REPLAY",
            name="Replay",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EPISODE_REPLAY",
            project_id="PROJECT_REPLAY",
            title="E1",
            original_filename="e1.mp4",
            source_path="e1.mp4",
            source_sha256="a" * 64,
            sort_order=1,
        ))
        session.add(ShotRevision(
            id="REVISION_REPLAY",
            episode_id="EPISODE_REPLAY",
            revision=1,
            kind="AUTO",
            is_current=False,
        ))
        session.add(ShotRevisionItem(
            id="ITEM_REPLAY_1",
            revision_id="REVISION_REPLAY",
            original_shot_id="SHOT_REPLAY_1",
            ordinal=1,
            start_us=0,
            end_us=1_000_000,
            duration_us=1_000_000,
            reference_clip_path="shot-1.mp4",
            thumbnail_path=None,
            keyframes_json="[]",
            short_description=None,
            shot_type=None,
            camera_motion=None,
            shot_status="READY",
        ))
        session.add(BreakdownRun(
            id="RUN_REPLAY",
            project_id="PROJECT_REPLAY",
            episode_id="EPISODE_REPLAY",
            source_shot_revision_id="REVISION_REPLAY",
            status=status,
            is_current=status in {"READY", "READY_WITH_WARNINGS"},
            component_status_json=json.dumps({
                "ASR": {"status": "READY"},
                "OCR": {"status": "READY"},
                "VLM": {"status": "READY"},
            }),
        ))
        session.commit()


def _loaded(component: str) -> legacy.LoadedComponent:
    result = p2.P2ProviderResult(
        component=component,
        provider=f"fixture-{component.lower()}",
        model="fixture",
        status="READY",
    )
    return legacy.LoadedComponent(
        component=component,
        artifact_uri=f"file:///unused/{component.lower()}.json",
        fingerprint="b" * 64,
        result=result,
    )


@pytest.mark.parametrize("status", ["READY", "READY_WITH_WARNINGS", "STALE"])
def test_completed_replay_loader_accepts_ready_like_historical_runs(monkeypatch, status: str) -> None:
    factory = _fixture_factory()
    _seed_run(factory, status=status)
    monkeypatch.setattr(completed.studio_v2, "get_session", lambda: factory())
    monkeypatch.setattr(
        completed.legacy,
        "_load_one_component",
        lambda _context, _entry, component: _loaded(component),
    )

    bundle = completed.load_completed_fusion_inputs("RUN_REPLAY")

    assert bundle.context.run_id == "RUN_REPLAY"
    assert bundle.context.source_shot_revision_id == "REVISION_REPLAY"
    assert [shot.ordinal for shot in bundle.context.shots] == [1]
    assert bundle.components["VLM"].result.status == "READY"


@pytest.mark.parametrize("status", ["PROCESSING", "FAILED"])
def test_completed_replay_loader_rejects_non_completed_runs(monkeypatch, status: str) -> None:
    factory = _fixture_factory()
    _seed_run(factory, status=status)
    monkeypatch.setattr(completed.studio_v2, "get_session", lambda: factory())

    with pytest.raises(legacy.BreakdownP2FusionError, match="只读重放"):
        completed.load_completed_fusion_inputs("RUN_REPLAY")
