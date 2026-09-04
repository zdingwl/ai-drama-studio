from __future__ import annotations

from copy import deepcopy

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.breakdown_manual_override_v1 import (
    apply_manual_overrides_v1,
    persist_shot_manual_edit_v1,
)
from engine.app.breakdown_shot_rerun_v1 import (
    SHOT_RERUN_PROFILE,
    SHOT_RERUN_SCHEMA_VERSION,
    apply_shot_rerun_overrides_v1,
    build_shot_rerun_overlay_v1,
    persist_shot_rerun_artifact_v1,
)


def _draft(
    *,
    run_id: str = "RUN_1",
    revision_id: str = "REV_1",
    current: bool = True,
) -> dict[str, object]:
    return {
        "run": {
            "id": run_id,
            "project_id": "PROJECT_1",
            "episode_id": "EPISODE_1",
            "source_shot_revision_id": revision_id,
            "status": "READY",
            "is_current": current,
        }
    }


def _timeline(
    *,
    run_id: str = "RUN_1",
    revision_id: str = "REV_1",
) -> dict[str, object]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": run_id,
        "source_shot_revision_id": revision_id,
        "episode_id": "EPISODE_1",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 1,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 1_000_000,
                "end_us": 3_000_000,
                "duration_us": 2_000_000,
                "title": "走廊",
                "scene_info": {
                    "location": "走廊",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": "住宅走廊",
                },
                "people": [
                    {
                        "ref": "P1",
                        "display_name": "人物1",
                        "appearance": "黑色短发",
                    }
                ],
                "story_summary": "人物在走廊说话。",
                "shots": [
                    {
                        "ordinal": 1,
                        "start_us": 1_000_000,
                        "end_us": 3_000_000,
                        "duration_us": 2_000_000,
                        "thumbnail_url": None,
                        "reference_url": None,
                        "summary": "人物说话。",
                        "narrative_function": "对白镜头",
                        "visual_description": "人物站在走廊。",
                        "people": ["P1"],
                        "performance": [{"text": "说话", "people": ["P1"]}],
                        "dialogue": [
                            {
                                "dialogue_group_id": "DG_ORIGINAL",
                                "start_us": 1_200_000,
                                "end_us": 2_400_000,
                                "text": "原始对白",
                                "source_language": "zh",
                                "speakers": ["P1"],
                            }
                        ],
                        "props": [],
                        "cinematography": {
                            "shot_type": "中景",
                            "composition": "居中",
                            "camera_motion": "固定",
                        },
                        "on_screen_text": [],
                    }
                ],
            }
        ],
    }


def _target() -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id="ITEM_1",
        original_shot_id="SHOT_1",
        ordinal=1,
        start_us=1_000_000,
        end_us=3_000_000,
        duration_us=2_000_000,
        reference_clip_path="shot.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def _asr() -> p2.P2ProviderResult:
    segment = p2.P2EvidenceRecord(
        source_type="ASR_SEGMENT",
        source_id="SEG_1",
        source_start_us=1_180_000,
        source_end_us=2_420_000,
        text="重新识别对白",
        language="zh",
        payload={"segment_index": 0, "word_count": 2},
    )
    word1 = p2.P2EvidenceRecord(
        source_type="ASR_WORD",
        source_id="WORD_1",
        source_start_us=1_200_000,
        source_end_us=1_800_000,
        text="重新识别",
        language="zh",
        payload={"segment_id": "SEG_1", "raw_word": "重新识别"},
    )
    word2 = p2.P2EvidenceRecord(
        source_type="ASR_WORD",
        source_id="WORD_2",
        source_start_us=1_800_000,
        source_end_us=2_400_000,
        text="对白",
        language="zh",
        payload={"segment_id": "SEG_1", "raw_word": "对白"},
    )
    return p2.P2ProviderResult(
        component="ASR",
        provider="fake-asr",
        model="fake",
        status="READY",
        evidence=(segment, word1, word2),
    )


def _ocr() -> p2.P2ProviderResult:
    evidence = (
        p2.P2EvidenceRecord(
            source_type="OCR_OBSERVATION",
            source_id="OCR_1",
            source_start_us=1_500_000,
            source_end_us=1_500_001,
            shot_revision_item_id="ITEM_1",
            text="门牌 302",
            language="zh",
            confidence=0.9,
            payload={"bbox_px": [10, 10, 100, 40], "image_width": 640, "image_height": 360},
        ),
        p2.P2EvidenceRecord(
            source_type="OCR_OBSERVATION",
            source_id="OCR_2",
            source_start_us=2_000_000,
            source_end_us=2_000_001,
            shot_revision_item_id="ITEM_1",
            text="门牌 302",
            language="zh",
            confidence=0.92,
            payload={"bbox_px": [10, 10, 100, 40], "image_width": 640, "image_height": 360},
        ),
    )
    return p2.P2ProviderResult(
        component="OCR",
        provider="fake-ocr",
        model="fake",
        status="READY",
        evidence=evidence,
        metadata={"sample_interval_us": 500_000},
    )


def _vlm() -> p2.P2ProviderResult:
    semantic = {
        "scene": {
            "location_hint": "走廊",
            "interior_exterior": "INT",
            "time_of_day": "day",
            "environment_description": "住宅走廊",
        },
        "shot": {
            "summary": "人物停下脚步并开口说话。",
            "visual_description": "人物在明亮走廊中停下并看向画外。",
            "narrative_function_hint": "回应对方",
            "shot_type_hint": "近景",
            "composition_hint": "人物偏右构图",
            "camera_motion_hint": "固定",
        },
        "subjects": [
            {
                "label": "subject_A",
                "appearance_summary": "黑色短发人物",
                "activity_summary": "停下脚步并说话",
            }
        ],
        "events": [
            {
                "event_type": "ACTION",
                "content": "人物停下脚步并看向画外",
                "subject_labels": ["subject_A"],
            }
        ],
        "props": [
            {
                "label": "手机",
                "importance": "MEDIUM",
                "narrative_reason": "人物手中拿着手机",
                "subject_labels": ["subject_A"],
            }
        ],
    }
    return p2.P2ProviderResult(
        component="VLM",
        provider="fake-vlm",
        model="fake",
        status="READY",
        evidence=(
            p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id="VLM_1",
                source_start_us=1_000_000,
                source_end_us=3_000_000,
                shot_revision_item_id="ITEM_1",
                text="人物停下脚步并开口说话。",
                language="zh",
                payload={"semantic": semantic},
            ),
        ),
    )


def test_scoped_fusion_updates_target_facts_without_rewriting_people() -> None:
    overlay, warnings = build_shot_rerun_overlay_v1(
        target=_target(),
        base_timeline=_timeline(),
        asr_result=_asr(),
        ocr_result=_ocr(),
        vlm_result=_vlm(),
        rerun_id="SHOTRERUN_1",
    )

    assert overlay["summary"] == "人物停下脚步并开口说话。"
    assert overlay["visual_description"] == "人物在明亮走廊中停下并看向画外。"
    assert overlay["narrative_function"] == "回应对方"
    assert overlay["cinematography"] == {
        "shot_type": "近景",
        "composition": "人物偏右构图",
        "camera_motion": "固定",
    }
    assert overlay["performance"] == [{"text": "人物停下脚步并看向画外", "people": ["P1"]}, {"text": "停下脚步并说话", "people": ["P1"]}]
    assert overlay["props"] == [{"label": "手机", "interaction": "人物手中拿着手机"}]
    assert overlay["dialogue"] == [
        {
            "dialogue_group_id": "DG_ORIGINAL",
            "start_us": 1_200_000,
            "end_us": 2_400_000,
            "text": "重新识别对白",
            "source_language": "zh",
            "speakers": ["P1"],
        }
    ]
    assert overlay["on_screen_text"] == [
        {"start_us": 1_500_000, "end_us": 2_500_000, "text": "门牌 302"}
    ]
    assert "people" not in overlay
    assert warnings == []


def test_rerun_artifact_applies_only_to_exact_run_and_revision(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    draft = _draft()
    base = _timeline()
    artifact = {
        "schema_version": SHOT_RERUN_SCHEMA_VERSION,
        "profile": SHOT_RERUN_PROFILE,
        "rerun_id": "SHOTRERUN_1",
        "project_id": "PROJECT_1",
        "episode_id": "EPISODE_1",
        "source_breakdown_run_id": "RUN_1",
        "source_shot_revision_id": "REV_1",
        "shot_ordinal": 1,
        "source_revision_item_id": "ITEM_1",
        "source_start_us": 1_000_000,
        "source_end_us": 3_000_000,
        "context_shot_ordinals": [1],
        "audio_scope_start_us": 200_000,
        "audio_scope_end_us": 3_800_000,
        "created_at": "2026-09-04T00:00:00+00:00",
        "providers": {},
        "overlay": {"summary": "只属于 RUN_1 / REV_1 的单镜结果"},
        "user_warnings": [],
        "artifact_fingerprint": "",
    }
    persist_shot_rerun_artifact_v1(draft, artifact)

    projected = apply_shot_rerun_overrides_v1(draft, base)
    assert projected["scenes"][0]["shots"][0]["summary"] == "只属于 RUN_1 / REV_1 的单镜结果"

    new_run = apply_shot_rerun_overrides_v1(
        _draft(run_id="RUN_2"),
        _timeline(run_id="RUN_2"),
    )
    assert new_run["scenes"][0]["shots"][0]["summary"] == "人物说话。"

    new_revision = apply_shot_rerun_overrides_v1(
        _draft(revision_id="REV_2"),
        _timeline(revision_id="REV_2"),
    )
    assert new_revision["scenes"][0]["shots"][0]["summary"] == "人物说话。"


def test_manual_dialogue_stays_above_rerun_when_slot_and_time_are_stable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    draft = _draft()
    source = _timeline()
    persist_shot_manual_edit_v1(
        draft,
        source,
        shot_ordinal=1,
        edits={"dialogues": [{"index": 0, "text": "用户最终校正对白"}]},
    )

    effective = deepcopy(source)
    effective["scenes"][0]["shots"][0]["dialogue"][0]["text"] = "单镜 AI 新对白"
    projected = apply_manual_overrides_v1(
        draft,
        effective,
        source_timeline_payload=source,
    )
    assert projected["scenes"][0]["shots"][0]["dialogue"][0]["text"] == "用户最终校正对白"


def test_manual_dialogue_fails_closed_if_rerun_changes_dialogue_timing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    draft = _draft()
    source = _timeline()
    persist_shot_manual_edit_v1(
        draft,
        source,
        shot_ordinal=1,
        edits={"dialogues": [{"index": 0, "text": "用户旧校正对白"}]},
    )

    effective = deepcopy(source)
    dialogue = effective["scenes"][0]["shots"][0]["dialogue"][0]
    dialogue["start_us"] = 1_300_000
    dialogue["text"] = "结构已经变化的 AI 对白"
    projected = apply_manual_overrides_v1(
        draft,
        effective,
        source_timeline_payload=source,
    )
    assert projected["scenes"][0]["shots"][0]["dialogue"][0]["text"] == "结构已经变化的 AI 对白"
