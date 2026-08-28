from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_p2_fusion_episode_v2 as episode_fusion
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownEvidenceLink, TimelineEvent


def shot(ordinal: int) -> p2.P2ShotInput:
    start_us = (ordinal - 1) * 1_000_000
    end_us = ordinal * 1_000_000
    return p2.P2ShotInput(
        revision_item_id=f"REVITEM_{ordinal}",
        original_shot_id=f"SHOT_{ordinal}",
        ordinal=ordinal,
        start_us=start_us,
        end_us=end_us,
        duration_us=end_us - start_us,
        reference_clip_path=f"shot-{ordinal}.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def vlm_record(
    item: p2.P2ShotInput,
    *,
    location: str | None,
    interior_exterior: str = "INT",
    time_of_day: str = "白天",
) -> p2.P2EvidenceRecord:
    semantic = {
        "schema_version": "breakdown-p2-vlm-shot-semantics-v1",
        "scene": {
            "location_hint": location or "",
            "interior_exterior": interior_exterior,
            "time_of_day": time_of_day,
            "environment_description": "",
        },
        "shot": {"summary": f"镜头{item.ordinal}"},
        "subjects": [],
        "events": [],
        "props": [],
    }
    return p2.P2EvidenceRecord(
        source_type="VLM_OUTPUT",
        source_id=f"vlm-{item.ordinal}",
        source_start_us=item.start_us,
        source_end_us=item.end_us,
        shot_revision_item_id=item.revision_item_id,
        text=f"镜头{item.ordinal}",
        language="zh-CN",
        payload={"semantic": semantic},
    )


def test_scene_continuity_keeps_closeup_and_unknown_inside_current_scene() -> None:
    shots = tuple(shot(index) for index in range(1, 5))
    records = {
        shots[0].revision_item_id: vlm_record(shots[0], location="客厅"),
        shots[1].revision_item_id: vlm_record(shots[1], location=None, interior_exterior="UNKNOWN"),
        shots[2].revision_item_id: vlm_record(shots[2], location="室内"),
        shots[3].revision_item_id: vlm_record(shots[3], location="家中客厅"),
    }

    plans = episode_fusion._continuity_segment_plans(shots, records)

    assert len(plans) == 1
    assert [item.ordinal for item in plans[0].shots] == [1, 2, 3, 4]


def test_scene_continuity_cuts_only_on_strong_location_change() -> None:
    shots = tuple(shot(index) for index in range(1, 5))
    records = {
        shots[0].revision_item_id: vlm_record(shots[0], location="客厅"),
        shots[1].revision_item_id: vlm_record(shots[1], location=None, interior_exterior="UNKNOWN"),
        shots[2].revision_item_id: vlm_record(shots[2], location="医院走廊"),
        shots[3].revision_item_id: vlm_record(shots[3], location="医院走廊"),
    }

    plans = episode_fusion._continuity_segment_plans(shots, records)

    assert len(plans) == 2
    assert [item.ordinal for item in plans[0].shots] == [1, 2]
    assert [item.ordinal for item in plans[1].shots] == [3, 4]


def test_scene_compatible_specificity_does_not_split() -> None:
    shots = (shot(1), shot(2))
    records = {
        shots[0].revision_item_id: vlm_record(shots[0], location="病房"),
        shots[1].revision_item_id: vlm_record(shots[1], location="医院病房"),
    }

    details = episode_fusion._continuity_plan_details(shots, records)

    assert len(details) == 1
    assert details[0].anchor.location == "医院病房"


def _loaded(component: str, result: p2.P2ProviderResult) -> legacy.LoadedComponent:
    return legacy.LoadedComponent(
        component=component,
        artifact_uri=f"file:///tmp/{component.lower()}.json",
        fingerprint="a" * 64,
        result=result,
    )


def source_bundle() -> legacy.FusionInputBundle:
    shots = (shot(1), shot(2))
    context = p2.P2RunContext(
        run_id="RUN_E1",
        project_id="PROJECT_E1",
        episode_id="EPISODE_E1",
        source_language="zh-CN",
        source_shot_revision_id="REVISION_E1",
        audio_path=None,
        shots=shots,
    )
    asr = p2.P2ProviderResult(
        component="ASR",
        provider="fixture-asr",
        model="fixture-asr",
        status="READY",
        evidence=(
            p2.P2EvidenceRecord(
                source_type="ASR_SEGMENT",
                source_id="asr-segment-cross",
                source_start_us=800_000,
                source_end_us=1_200_000,
                text="你怎么现在才回来？",
                language="zh",
                payload={"segment_index": 0},
            ),
            p2.P2EvidenceRecord(
                source_type="ASR_WORD",
                source_id="asr-word-left",
                source_start_us=820_000,
                source_end_us=940_000,
                text="你怎么",
                language="zh",
                confidence=0.96,
                payload={"segment_id": "asr-segment-cross", "raw_word": "你怎么"},
            ),
            p2.P2EvidenceRecord(
                source_type="ASR_WORD",
                source_id="asr-word-right",
                source_start_us=1_040_000,
                source_end_us=1_180_000,
                text="才回来",
                language="zh",
                confidence=0.94,
                payload={"segment_id": "asr-segment-cross", "raw_word": "才回来"},
            ),
        ),
        metadata={"word_timestamps": True},
    )
    empty_ocr = p2.P2ProviderResult(
        component="OCR",
        provider="fixture-ocr",
        model="fixture-ocr",
        status="NO_EVIDENCE",
    )
    empty_vlm = p2.P2ProviderResult(
        component="VLM",
        provider="fixture-vlm",
        model="fixture-vlm",
        status="READY",
    )
    return legacy.FusionInputBundle(
        context=context,
        components={
            "ASR": _loaded("ASR", asr),
            "OCR": _loaded("OCR", empty_ocr),
            "VLM": _loaded("VLM", empty_vlm),
        },
        warnings=(),
    )


def test_projection_bundle_preserves_raw_asr_but_hides_words_from_first_write_pass() -> None:
    bundle = source_bundle()

    projected = episode_fusion._episode_projection_bundle(bundle)

    assert len(bundle.components["ASR"].result.evidence) == 3
    assert [item.source_type for item in projected.components["ASR"].result.evidence] == ["ASR_SEGMENT"]
    assert projected.components["ASR"].result.metadata["fusion_consumption_policy"] == episode_fusion.ASR_DIALOGUE_POLICY


def test_dialogue_rewrite_keeps_full_sentence_across_two_shot_projections() -> None:
    engine = create_engine("sqlite:///:memory:")
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    bundle = source_bundle()

    with factory() as session:
        session.add_all([
            TimelineEvent(
                id="EVENT_LEFT",
                run_id="RUN_E1",
                shot_draft_id="DRAFT_LEFT",
                ordinal=1,
                event_type="DIALOGUE",
                source_start_us=800_000,
                source_end_us=1_000_000,
                shot_relative_start_us=800_000,
                shot_relative_end_us=1_000_000,
                content_text="旧的左半句",
                language="zh",
                origin="ASR",
                metadata_json=json.dumps({"asr_segment_id": "asr-segment-cross"}),
            ),
            TimelineEvent(
                id="EVENT_RIGHT",
                run_id="RUN_E1",
                shot_draft_id="DRAFT_RIGHT",
                ordinal=1,
                event_type="DIALOGUE",
                source_start_us=1_000_000,
                source_end_us=1_200_000,
                shot_relative_start_us=0,
                shot_relative_end_us=200_000,
                content_text="旧的右半句",
                language="zh",
                origin="ASR",
                metadata_json=json.dumps({"asr_segment_id": "asr-segment-cross"}),
            ),
        ])
        session.commit()

        episode_fusion._rewrite_dialogue_events(
            session,
            run_id="RUN_E1",
            source_bundle=bundle,
        )
        session.flush()

        events = list(session.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.run_id == "RUN_E1", TimelineEvent.event_type == "DIALOGUE")
            .order_by(TimelineEvent.source_start_us)
        ).all())
        assert [item.content_text for item in events] == [
            "你怎么现在才回来？",
            "你怎么现在才回来？",
        ]

        left_meta = json.loads(events[0].metadata_json)
        right_meta = json.loads(events[1].metadata_json)
        assert left_meta["dialogue_group_id"] == right_meta["dialogue_group_id"] == "asr-segment-cross"
        assert left_meta["continues_from_previous_shot"] is False
        assert left_meta["continues_to_next_shot"] is True
        assert right_meta["continues_from_previous_shot"] is True
        assert right_meta["continues_to_next_shot"] is False
        assert left_meta["dialogue_source_start_us"] == 800_000
        assert right_meta["dialogue_source_end_us"] == 1_200_000

        links = list(session.scalars(
            select(BreakdownEvidenceLink)
            .where(BreakdownEvidenceLink.run_id == "RUN_E1")
        ).all())
        assert {(item.owner_id, item.source_id) for item in links} == {
            ("EVENT_LEFT", "asr-word-left"),
            ("EVENT_RIGHT", "asr-word-right"),
        }
