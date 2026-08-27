from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_p2_sidecar_v1 as p2, breakdown_service_v1, shot_revision_v2, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem


def setup_episode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """建立带 audio/reference/keyframes 的最小正式 V2 Episode。"""

    home = tmp_path / "工作 空间"
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(home))
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'p2 sidecar.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "原视频 ep01.mp4"
    audio = tmp_path / "源音频 ep01.wav"
    source.write_bytes(b"video")
    audio.write_bytes(b"audio")
    with factory() as session:
        project = studio_v2.Project(
            id="PROJECT_P2",
            name="P2 Sidecar Test",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        )
        episode = studio_v2.Episode(
            id="EPISODE_P2",
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
        session.add(studio_v2.Preprocess(
            id="PREPROCESS_P2",
            episode_id=episode.id,
            status="READY",
            proxy_path=str(tmp_path / "proxy.mp4"),
            audio_path=str(audio),
        ))
        for ordinal, start_us, end_us in [(1, 0, 1_000_000), (2, 1_000_000, 2_000_000)]:
            reference = tmp_path / f"参考 镜头 {ordinal}.mp4"
            thumbnail = tmp_path / f"缩略图 {ordinal}.jpg"
            reference.write_bytes(f"reference-{ordinal}".encode())
            thumbnail.write_bytes(f"thumb-{ordinal}".encode())
            session.add(studio_v2.Shot(
                id=f"SHOT_P2_{ordinal}",
                episode_id=episode.id,
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(reference),
                thumbnail_path=str(thumbnail),
                keyframes_json=json.dumps([
                    {"source_us": start_us + 100_000, "path": str(thumbnail)},
                ], ensure_ascii=False),
                status="READY",
            ))
        session.commit()
    return factory


def create_run() -> BreakdownRun:
    return breakdown_service_v1.create_breakdown_run(
        "EPISODE_P2",
        pipeline_profile="breakdown-p2-sidecar-v1",
        component_status={"ASR": "PENDING", "OCR": "PENDING", "VLM": "PENDING"},
    )


def test_p2_context_is_frozen_to_breakdown_run_shot_revision(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run = create_run()

    context = p2.load_p2_run_context(run.id)

    assert context.run_id == run.id
    assert context.project_id == "PROJECT_P2"
    assert context.episode_id == "EPISODE_P2"
    assert context.source_language == "zh-CN"
    assert context.audio_path == str(tmp_path / "源音频 ep01.wav")
    assert [shot.original_shot_id for shot in context.shots] == ["SHOT_P2_1", "SHOT_P2_2"]
    assert [shot.ordinal for shot in context.shots] == [1, 2]
    assert context.shots[0].keyframes[0]["source_us"] == 100_000

    with factory() as session:
        revision = session.get(ShotRevision, context.source_shot_revision_id)
        items = session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == context.source_shot_revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all()
        assert revision is not None and revision.is_current is True
        assert [shot.revision_item_id for shot in context.shots] == [item.id for item in items]


class FakeAsrProvider:
    component = "ASR"

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        shot = context.shots[0]
        return p2.P2ProviderResult(
            component="ASR",
            provider="fixture-asr",
            model="fixture-word-timing-v1",
            status="READY",
            metadata={"device": "cpu", "word_timestamps": True},
            evidence=(
                p2.P2EvidenceRecord(
                    source_type="ASR_SEGMENT",
                    source_id="asr-segment-1",
                    source_start_us=100_000,
                    source_end_us=600_000,
                    shot_revision_item_id=shot.revision_item_id,
                    text="你好",
                    language="zh",
                    confidence=0.93,
                    payload={"speaker_label": "SPEAKER_00"},
                ),
                p2.P2EvidenceRecord(
                    source_type="ASR_WORD",
                    source_id="asr-word-1",
                    source_start_us=120_000,
                    source_end_us=220_000,
                    shot_revision_item_id=shot.revision_item_id,
                    text="你",
                    language="zh",
                    confidence=0.97,
                    payload={"segment_id": "asr-segment-1"},
                ),
            ),
        )


def test_local_provider_persists_idempotent_raw_evidence_and_run_provenance(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run = create_run()
    provider = FakeAsrProvider()

    first = p2.run_local_provider(run.id, provider)
    second = p2.run_local_provider(run.id, provider)

    assert first.path == second.path
    assert first.fingerprint == second.fingerprint
    assert first.evidence_count == 2
    artifact_path = Path(first.path)
    assert artifact_path.is_file()
    assert "工作 空间" in first.path
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == p2.P2_SIDECAR_SCHEMA_VERSION
    assert payload["source_shot_revision_id"] == run.source_shot_revision_id
    assert payload["provider"] == "fixture-asr"
    assert payload["evidence"][0]["source_type"] == "ASR_SEGMENT"
    assert payload["evidence"][1]["source_type"] == "ASR_WORD"

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "PROCESSING"
        statuses = json.loads(row.component_status_json)
        providers = json.loads(row.provider_metadata_json)
        assert statuses["ASR"]["status"] == "READY"
        assert statuses["ASR"]["artifact_uri"] == first.uri
        assert statuses["ASR"]["evidence_count"] == 2
        assert providers["p2_sidecar"]["ASR"]["metadata"]["word_timestamps"] is True
        # P2.1 只能保存匿名 Evidence，不得顺手物化 Final Asset。
        assert session.scalars(select(studio_v2.Character)).all() == []
        assert session.scalars(select(studio_v2.Scene)).all() == []
        assert session.scalars(select(studio_v2.Prop)).all() == []


def test_anonymous_sidecar_rejects_final_asset_id_leakage(monkeypatch, tmp_path: Path) -> None:
    setup_episode(monkeypatch, tmp_path)
    run = create_run()
    context = p2.load_p2_run_context(run.id)
    result = p2.P2ProviderResult(
        component="VLM",
        provider="fixture-vlm",
        model="fixture-vlm-v1",
        status="READY",
        metadata={"character_id": "CHARACTER_SHOULD_NEVER_BE_HERE"},
        evidence=(
            p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id="vlm-1",
                shot_revision_item_id=context.shots[0].revision_item_id,
                text="人物A在门口说话",
                confidence=0.8,
            ),
        ),
    )

    with pytest.raises(p2.BreakdownP2SidecarError, match="禁止字段 metadata.character_id"):
        p2.persist_provider_result(context, result)

    root = p2.p2_evidence_root(context)
    assert not (root / "vlm").exists()


def test_stale_breakdown_run_cannot_continue_p2_sidecar(monkeypatch, tmp_path: Path) -> None:
    factory = setup_episode(monkeypatch, tmp_path)
    run = create_run()
    old_revision_id = run.source_shot_revision_id

    new_payloads = [
        {
            "ordinal": 1,
            "start_us": 0,
            "end_us": 800_000,
            "duration_us": 800_000,
            "reference_clip_path": str(tmp_path / "new-1.mp4"),
            "thumbnail_path": None,
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
            "reference_clip_path": str(tmp_path / "new-2.mp4"),
            "thumbnail_path": None,
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        },
    ]
    shot_revision_v2.commit_auto_shot_revision("EPISODE_P2", new_payloads)

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        current = session.scalar(
            select(ShotRevision).where(
                ShotRevision.episode_id == "EPISODE_P2",
                ShotRevision.is_current.is_(True),
            )
        )
        assert row is not None and row.status == "STALE"
        assert row.source_shot_revision_id == old_revision_id
        assert current is not None and current.id != old_revision_id

    with pytest.raises(p2.BreakdownP2SidecarError, match="当前状态为 STALE"):
        p2.run_local_provider(run.id, FakeAsrProvider())


def test_shot_bound_evidence_must_stay_inside_its_revision_item(monkeypatch, tmp_path: Path) -> None:
    setup_episode(monkeypatch, tmp_path)
    run = create_run()
    context = p2.load_p2_run_context(run.id)
    result = p2.P2ProviderResult(
        component="OCR",
        provider="fixture-ocr",
        model="fixture-ocr-v1",
        status="READY",
        evidence=(
            p2.P2EvidenceRecord(
                source_type="OCR_OBSERVATION",
                source_id="ocr-1",
                source_start_us=900_000,
                source_end_us=1_100_000,
                shot_revision_item_id=context.shots[0].revision_item_id,
                text="医院",
                confidence=0.91,
                payload={"polygon": [[1, 1], [20, 1], [20, 10], [1, 10]]},
            ),
        ),
    )

    with pytest.raises(p2.BreakdownP2SidecarError, match="时间越出该 Shot"):
        p2.persist_provider_result(context, result)
