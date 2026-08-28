from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_p2_fusion_v1 as fusion, breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, shot_revision_v2, studio_v2
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
)


class FixedProvider:
    def __init__(self, component: str, builder):
        self.component = component
        self._builder = builder

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        return self._builder(context)


def setup_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, shot_count: int = 2):
    home = tmp_path / "P2 Fusion 工作 空间"
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(home))
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'p2 fusion.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "原视频.mp4"
    audio = tmp_path / "源音频.wav"
    source.write_bytes(b"video")
    audio.write_bytes(b"audio")
    with factory() as session:
        session.add(studio_v2.Project(
            id="PROJECT_P2_FUSION",
            name="P2 Fusion",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        duration_us = shot_count * 1_000_000
        session.add(studio_v2.Episode(
            id="EPISODE_P2_FUSION",
            project_id="PROJECT_P2_FUSION",
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="f" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=duration_us,
        ))
        session.flush()
        session.add(studio_v2.Preprocess(
            id="PREPROCESS_P2_FUSION",
            episode_id="EPISODE_P2_FUSION",
            status="READY",
            proxy_path=str(tmp_path / "proxy.mp4"),
            audio_path=str(audio),
        ))
        for ordinal in range(1, shot_count + 1):
            start_us = (ordinal - 1) * 1_000_000
            end_us = ordinal * 1_000_000
            clip = tmp_path / f"Fusion 参考 镜头 {ordinal}.mp4"
            clip.write_bytes(b"clip")
            session.add(studio_v2.Shot(
                id=f"SHOT_P2_FUSION_{ordinal}",
                episode_id="EPISODE_P2_FUSION",
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(clip),
                thumbnail_path=None,
                keyframes_json="[]",
                status="READY",
            ))
        session.commit()

    run = breakdown_service_v1.create_breakdown_run(
        "EPISODE_P2_FUSION",
        pipeline_profile="breakdown-p2-fusion-v1",
        component_status={"ASR": "PENDING", "OCR": "PENDING", "VLM": "PENDING"},
    )
    return factory, run


def vlm_semantic(*, summary: str, subjects=None, props=None, location: str = "住宅楼走廊"):
    return {
        "schema_version": "breakdown-p2-vlm-shot-semantics-v1",
        "scene": {
            "location_hint": location,
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "狭长的住宅楼走廊。",
        },
        "shot": {
            "summary": summary,
            "visual_description": summary,
            "shot_type_hint": "中景",
            "camera_motion_hint": "固定",
            "narrative_function_hint": "冲突建立",
            "composition_hint": "双人或单人构图",
        },
        "subjects": subjects or [],
        "events": [
            {
                "event_type": "ACTION",
                "start_ratio": 0.1,
                "end_ratio": 0.8,
                "content": summary,
                "subject_labels": [item["label"] for item in (subjects or [])],
            }
        ],
        "props": props or [],
    }


def ready_vlm_provider(*, two_identical_people_same_shot: bool = False):
    def build(context: p2.P2RunContext) -> p2.P2ProviderResult:
        evidence = []
        for shot in context.shots:
            if two_identical_people_same_shot:
                subjects = [
                    {
                        "label": "subject_A",
                        "appearance_summary": "年轻女性，黑色上衣",
                        "activity_summary": "站在左侧",
                        "screen_position": "左侧",
                        "visibility": "FULL",
                        "speaking_state": "UNKNOWN",
                    },
                    {
                        "label": "subject_B",
                        "appearance_summary": "年轻女性，黑色上衣",
                        "activity_summary": "站在右侧",
                        "screen_position": "右侧",
                        "visibility": "FULL",
                        "speaking_state": "UNKNOWN",
                    },
                ]
            else:
                subjects = [
                    {
                        "label": "subject_A",
                        "appearance_summary": "年轻女性，黑色上衣",
                        "activity_summary": "抬手拦住另一人",
                        "screen_position": "左侧",
                        "visibility": "FULL",
                        "speaking_state": "LIKELY_SPEAKING",
                    }
                ]
            props = [
                {
                    "label": "黑色塑料袋",
                    "importance": "HIGH",
                    "narrative_reason": "人物手中持续拿着并参与当前动作",
                    "subject_labels": [subjects[0]["label"]],
                }
            ]
            semantic = vlm_semantic(
                summary=f"镜头{shot.ordinal}：人物在走廊发生动作",
                subjects=subjects,
                props=props,
            )
            evidence.append(p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id=f"vlm-{shot.ordinal}",
                source_start_us=shot.start_us,
                source_end_us=shot.end_us,
                shot_revision_item_id=shot.revision_item_id,
                text=semantic["shot"]["summary"],
                language=context.source_language,
                confidence=None,
                payload={"shot_ordinal": shot.ordinal, "semantic": semantic},
            ))
        return p2.P2ProviderResult(
            component="VLM",
            provider="fixture-vlm",
            model="fixture-vlm-v1",
            status="READY",
            evidence=tuple(evidence),
            metadata={"semantic_schema": "breakdown-p2-vlm-shot-semantics-v1"},
        )
    return FixedProvider("VLM", build)


def ready_asr_provider():
    def build(context: p2.P2RunContext) -> p2.P2ProviderResult:
        return p2.P2ProviderResult(
            component="ASR",
            provider="fixture-asr",
            model="fixture-asr-v1",
            status="READY",
            evidence=(
                p2.P2EvidenceRecord(
                    source_type="ASR_SEGMENT",
                    source_id="asr-segment-cross",
                    source_start_us=800_000,
                    source_end_us=1_200_000,
                    shot_revision_item_id=None,
                    text="跨镜",
                    language="zh",
                    confidence=None,
                    payload={"segment_index": 0},
                ),
                p2.P2EvidenceRecord(
                    source_type="ASR_WORD",
                    source_id="asr-word-1",
                    source_start_us=820_000,
                    source_end_us=940_000,
                    shot_revision_item_id=None,
                    text="跨",
                    language="zh",
                    confidence=0.97,
                    payload={"segment_id": "asr-segment-cross", "raw_word": "跨"},
                ),
                p2.P2EvidenceRecord(
                    source_type="ASR_WORD",
                    source_id="asr-word-2",
                    source_start_us=1_040_000,
                    source_end_us=1_180_000,
                    shot_revision_item_id=None,
                    text="镜",
                    language="zh",
                    confidence=0.93,
                    payload={"segment_id": "asr-segment-cross", "raw_word": "镜"},
                ),
            ),
            metadata={"word_timestamps": True},
        )
    return FixedProvider("ASR", build)


def ready_ocr_provider():
    def build(context: p2.P2RunContext) -> p2.P2ProviderResult:
        shot = context.shots[0]
        common_payload = {
            "image_width": 200,
            "image_height": 100,
            "bbox_px": [10.0, 10.0, 150.0, 40.0],
            "polygon_px": [[10, 10], [150, 10], [150, 40], [10, 40]],
            "polygon_norm": [[0.05, 0.1], [0.75, 0.1], [0.75, 0.4], [0.05, 0.4]],
        }
        return p2.P2ProviderResult(
            component="OCR",
            provider="fixture-ocr",
            model="fixture-ocr-v1",
            status="READY",
            evidence=(
                p2.P2EvidenceRecord(
                    source_type="OCR_OBSERVATION",
                    source_id="ocr-1",
                    source_start_us=100_000,
                    source_end_us=100_001,
                    shot_revision_item_id=shot.revision_item_id,
                    text="医院",
                    language=context.source_language,
                    confidence=0.96,
                    payload={**common_payload, "frame_sample_index": 0},
                ),
                p2.P2EvidenceRecord(
                    source_type="OCR_OBSERVATION",
                    source_id="ocr-2",
                    source_start_us=600_000,
                    source_end_us=600_001,
                    shot_revision_item_id=shot.revision_item_id,
                    text="医院",
                    language=context.source_language,
                    confidence=0.94,
                    payload={**common_payload, "frame_sample_index": 1},
                ),
            ),
            metadata={"sample_interval_us": 500_000},
        )
    return FixedProvider("OCR", build)


def empty_provider(component: str, status: str = "NO_EVIDENCE"):
    return FixedProvider(component, lambda _context: p2.P2ProviderResult(
        component=component,
        provider=f"fixture-{component.lower()}",
        model=f"fixture-{component.lower()}-v1",
        status=status,
        evidence=(),
        metadata={},
    ))


def persist_all(run_id: str, *, asr=None, ocr=None, vlm=None):
    artifacts = {}
    for provider in (
        asr or ready_asr_provider(),
        ocr or ready_ocr_provider(),
        vlm or ready_vlm_provider(),
    ):
        artifacts[provider.component] = p2.run_local_provider(run_id, provider)
    return artifacts


def test_fusion_builds_complete_p1_draft_splits_asr_and_stitches_ocr(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_run(monkeypatch, tmp_path)
    persist_all(run.id)

    published = fusion.fuse_breakdown_run(run.id)

    assert published.status == "READY"
    assert published.is_current is True
    with factory() as session:
        segments = session.scalars(select(SceneSegmentDraft).where(SceneSegmentDraft.run_id == run.id)).all()
        drafts = session.scalars(select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)).all()
        subjects = session.scalars(select(LocalSubject).where(LocalSubject.run_id == run.id)).all()
        presences = session.scalars(select(ShotLocalSubject).where(ShotLocalSubject.run_id == run.id)).all()
        events = session.scalars(select(TimelineEvent).where(TimelineEvent.run_id == run.id)).all()
        props = session.scalars(select(DraftPropHint).where(DraftPropHint.run_id == run.id)).all()
        occurrences = session.scalars(select(DraftPropOccurrence)).all()
        links = session.scalars(select(BreakdownEvidenceLink).where(BreakdownEvidenceLink.run_id == run.id)).all()

        assert len(segments) == 1
        assert len(drafts) == 2
        assert len(subjects) == 1
        assert len(presences) == 2
        assert len(props) == 1
        assert len(occurrences) == 2

        dialogue = sorted((item for item in events if item.event_type == "DIALOGUE"), key=lambda item: item.source_start_us)
        assert [(item.content_text, item.source_start_us, item.source_end_us) for item in dialogue] == [
            ("跨", 820_000, 940_000),
            ("镜", 1_040_000, 1_180_000),
        ]
        assert all(json.loads(item.metadata_json)["text_policy"] == "word-timestamp-split" for item in dialogue)

        ocr_events = [item for item in events if item.event_type == "OCR"]
        assert len(ocr_events) == 1
        assert ocr_events[0].content_text == "医院"
        assert ocr_events[0].source_start_us == 100_000
        assert ocr_events[0].source_end_us == 1_000_000
        assert json.loads(ocr_events[0].metadata_json)["observation_count"] == 2

        assert any(link.source_id == "asr-word-1" for link in links)
        assert any(link.source_id == "ocr-2" for link in links)
        assert any(link.source_id == "vlm-1" for link in links)
        assert session.scalars(select(studio_v2.Character)).all() == []
        assert session.scalars(select(studio_v2.Scene)).all() == []
        assert session.scalars(select(studio_v2.Prop)).all() == []

        row = session.get(BreakdownRun, run.id)
        assert row is not None
        status = json.loads(row.component_status_json)["FUSION"]
        assert status["status"] == "READY"
        assert status["profile"] == fusion.FUSION_PROFILE
        assert json.loads(row.counts_json)["shot"] == 2


def test_no_evidence_asr_ocr_publish_ready_with_warnings_but_keep_full_shot_coverage(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_run(monkeypatch, tmp_path)
    persist_all(
        run.id,
        asr=empty_provider("ASR", "NO_EVIDENCE"),
        ocr=empty_provider("OCR", "NO_EVIDENCE"),
    )

    published = fusion.fuse_breakdown_run(run.id)

    assert published.status == "READY_WITH_WARNINGS"
    with factory() as session:
        drafts = session.scalars(select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)).all()
        assert len(drafts) == 2
        warning_payload = json.loads(session.get(BreakdownRun, run.id).warning_json)
        pipeline = warning_payload["pipeline"]
        codes = {item["code"] for item in pipeline}
        assert "ASR_DEGRADED_NO_EVIDENCE" in codes
        assert "OCR_DEGRADED_NO_EVIDENCE" in codes


def test_tampered_sidecar_fingerprint_fails_before_any_draft_write(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_run(monkeypatch, tmp_path)
    artifacts = persist_all(run.id)
    ocr_path = Path(artifacts["OCR"].path)
    ocr_path.write_text(ocr_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(fusion.BreakdownP2FusionError, match="fingerprint"):
        fusion.fuse_breakdown_run(run.id)

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "FAILED" and row.is_current is False
        assert session.scalars(select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)).all() == []


def test_failed_vlm_component_blocks_fusion_and_marks_processing_run_failed(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_run(monkeypatch, tmp_path)
    persist_all(
        run.id,
        vlm=empty_provider("VLM", "FAILED"),
    )

    with pytest.raises(fusion.BreakdownP2FusionError, match="VLM Provider 已失败"):
        fusion.fuse_breakdown_run(run.id)

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "FAILED"
        assert session.scalars(select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)).all() == []


def test_same_shot_identical_appearance_subjects_remain_distinct(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_run(monkeypatch, tmp_path, shot_count=1)
    persist_all(
        run.id,
        asr=empty_provider("ASR"),
        ocr=empty_provider("OCR"),
        vlm=ready_vlm_provider(two_identical_people_same_shot=True),
    )

    published = fusion.fuse_breakdown_run(run.id)
    assert published.status == "READY_WITH_WARNINGS"

    with factory() as session:
        subjects = session.scalars(select(LocalSubject).where(LocalSubject.run_id == run.id)).all()
        presences = session.scalars(select(ShotLocalSubject).where(ShotLocalSubject.run_id == run.id)).all()
        assert len(subjects) == 2
        assert len(presences) == 2
        assert {item.display_label for item in subjects} == {"人物A", "人物B"}


def test_stale_run_cannot_fuse_old_sidecars(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_run(monkeypatch, tmp_path)
    persist_all(run.id)

    new_payloads = []
    for ordinal, start_us, end_us in [(1, 0, 800_000), (2, 800_000, 2_000_000)]:
        clip = tmp_path / f"新 Revision {ordinal}.mp4"
        clip.write_bytes(b"new")
        new_payloads.append({
            "ordinal": ordinal,
            "start_us": start_us,
            "end_us": end_us,
            "duration_us": end_us - start_us,
            "reference_clip_path": str(clip),
            "thumbnail_path": None,
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        })
    shot_revision_v2.commit_auto_shot_revision("EPISODE_P2_FUSION", new_payloads)

    with pytest.raises(p2.BreakdownP2SidecarError, match="当前状态为 STALE"):
        fusion.fuse_breakdown_run(run.id)

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "STALE"
        assert session.scalars(select(ShotSemanticDraft).where(ShotSemanticDraft.run_id == run.id)).all() == []
