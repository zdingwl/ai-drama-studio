from __future__ import annotations

from engine.app import breakdown_p2_fusion_v1 as fusion
from engine.app import breakdown_p2_refinement_v1 as e3
from engine.app import breakdown_p2_sidecar_v1 as p2


def make_context() -> p2.P2RunContext:
    shots = tuple(
        p2.P2ShotInput(
            revision_item_id=f"ITEM_{ordinal}",
            original_shot_id=f"SHOT_{ordinal}",
            ordinal=ordinal,
            start_us=(ordinal - 1) * 2_000_000,
            end_us=ordinal * 2_000_000,
            duration_us=2_000_000,
            reference_clip_path=f"unused-{ordinal}.mp4",
            thumbnail_path=None,
            keyframes=(),
        )
        for ordinal in range(1, 4)
    )
    return p2.P2RunContext(
        run_id="RUN_E3",
        project_id="PROJECT_E3",
        episode_id="EPISODE_E3",
        source_language="zh-CN",
        source_shot_revision_id="REV_E3",
        audio_path=None,
        shots=shots,
    )


def semantic(summary: str) -> dict:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "人物位于客厅。",
        },
        "shot": {
            "summary": summary,
            "visual_description": summary,
            "shot_type_hint": "中景",
            "camera_motion_hint": "静止",
            "narrative_function_hint": "人物互动",
            "composition_hint": "人物居中",
        },
        "subjects": [{
            "label": "subject_A",
            "appearance_summary": "黑色短发，白色上衣",
            "activity_summary": "站在桌边",
            "screen_position": "中央",
            "visibility": "FULL",
            "speaking_state": "UNKNOWN",
        }],
        "events": [{
            "event_type": "ACTION",
            "start_ratio": 0.1,
            "end_ratio": 0.8,
            "content": "人物站在桌边。",
            "subject_labels": ["subject_A"],
        }],
        "props": [{
            "label": "手机",
            "importance": "MEDIUM",
            "narrative_reason": "手机放在桌边。",
            "subject_labels": ["subject_A"],
        }],
    }


def make_bundle() -> fusion.FusionInputBundle:
    context = make_context()
    vlm_evidence = tuple(
        p2.P2EvidenceRecord(
            source_type="VLM_OUTPUT",
            source_id=f"VLM_{shot.ordinal}",
            source_start_us=shot.start_us,
            source_end_us=shot.end_us,
            shot_revision_item_id=shot.revision_item_id,
            text=f"E2 镜头 {shot.ordinal}",
            language="zh-CN",
            payload={
                "semantic": semantic(f"E2 镜头 {shot.ordinal}"),
                "episode_window": {
                    "window_id": "window-0001" if shot.ordinal < 3 else "window-0002",
                    "supporting_window_ids": ["window-0002"] if shot.ordinal == 2 else [],
                    "scene_continuity": "SAME" if shot.ordinal > 1 else "UNCERTAIN",
                    "scene_basis": "MIXED",
                    "context_note": "由连续窗口确认仍在客厅。",
                },
            },
        )
        for shot in context.shots
    )
    asr = p2.P2ProviderResult(
        component="ASR", provider="fixture-asr", model="fixture", status="READY",
        evidence=(p2.P2EvidenceRecord(
            source_type="ASR_SEGMENT", source_id="ASR_1",
            source_start_us=1_500_000, source_end_us=4_500_000,
            text="你终于回来了。", language="zh-CN",
        ),),
    )
    ocr = p2.P2ProviderResult(
        component="OCR", provider="fixture-ocr", model="fixture", status="READY",
        evidence=(p2.P2EvidenceRecord(
            source_type="OCR_OBSERVATION", source_id="OCR_1",
            source_start_us=2_500_000, source_end_us=2_500_001,
            shot_revision_item_id="ITEM_2", text="未接来电", language="zh-CN",
            confidence=0.95, payload={"polygon_norm": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.2], [0.1, 0.2]]},
        ),),
    )
    vlm_result = p2.P2ProviderResult(
        component="VLM", provider="qwen3-vl", model="fixture-qwen", status="READY",
        evidence=vlm_evidence,
        metadata={
            "window_summaries": [
                {"window_id": "window-0001", "window_summary": "客厅内人物等待并查看手机。"},
                {"window_id": "window-0002", "window_summary": "同一客厅内人物继续对话。"},
            ]
        },
    )
    return fusion.FusionInputBundle(
        context=context,
        components={
            "ASR": fusion.LoadedComponent("ASR", "file:///asr", "a" * 64, asr),
            "OCR": fusion.LoadedComponent("OCR", "file:///ocr", "b" * 64, ocr),
            "VLM": fusion.LoadedComponent("VLM", "memory://e2", "c" * 64, vlm_result),
        },
        warnings=(),
    )


def test_build_items_include_neighbor_scene_window_asr_and_ocr_context() -> None:
    bundle = make_bundle()
    items = e3.build_refinement_items(bundle)

    assert len(items) == 3
    middle = items[1]
    assert middle["previous_shot"]["revision_item_id"] == "ITEM_1"
    assert middle["current_shot"]["revision_item_id"] == "ITEM_2"
    assert middle["next_shot"]["revision_item_id"] == "ITEM_3"
    assert middle["scene_context"]["location_hint"] == "客厅"
    assert {item["window_id"] for item in middle["window_context"]} == {"window-0001", "window-0002"}
    assert middle["asr_context"][0]["text"] == "你终于回来了。"
    assert middle["ocr_context"][0]["text"] == "未接来电"


def test_refiner_whitelists_output_preserves_subject_labels_and_e2_semantic() -> None:
    bundle = make_bundle()

    def runner(_config, items):
        rows = []
        for item in items:
            candidate = semantic(f"精修镜头 {item['ordinal']}")
            candidate["character_id"] = "CHARACTER_FORBIDDEN"
            candidate["subjects"].append({
                "label": "subject_X",
                "appearance_summary": "不允许新增的人",
                "visibility": "FULL",
                "speaking_state": "UNKNOWN",
            })
            rows.append({
                "revision_item_id": item["revision_item_id"],
                "status": "READY",
                "refinement_note": "结合连续窗口、相邻镜头和对白上下文。",
                "semantic": candidate,
            })
        return rows

    result = e3.ContextualShotRefiner(inference_runner=runner).refine(bundle)

    assert result.status == "READY"
    assert len(result.evidence) == 3
    middle = result.evidence[1]
    assert middle.text == "精修镜头 2"
    assert middle.payload["e2_semantic"]["shot"]["summary"] == "E2 镜头 2"
    assert [item["label"] for item in middle.payload["semantic"]["subjects"]] == ["subject_A"]
    assert "character_id" not in str(middle.payload["semantic"])
    assert middle.payload["contextual_refinement"]["asr_source_ids"] == ["ASR_1"]
    p2.validate_provider_result(
        bundle.context,
        p2.P2ProviderResult(
            component="VLM", provider=result.provider, model=result.model,
            status="READY", evidence=result.evidence, metadata=result.metadata,
        ),
    )


def test_partial_refinement_failure_falls_back_per_shot_with_warning() -> None:
    bundle = make_bundle()

    def runner(_config, items):
        return [
            {
                "revision_item_id": item["revision_item_id"],
                "status": "FAILED" if item["ordinal"] == 2 else "READY",
                "semantic": semantic(f"精修镜头 {item['ordinal']}") if item["ordinal"] != 2 else None,
            }
            for item in items
        ]

    result = e3.ContextualShotRefiner(inference_runner=runner).refine(bundle)

    assert result.status == "READY_WITH_WARNINGS"
    by_ordinal = {item.payload["shot_ordinal"]: item for item in result.evidence}
    assert by_ordinal[2].payload["semantic"]["shot"]["summary"] == "E2 镜头 2"
    assert by_ordinal[2].payload["contextual_refinement"]["status"] == "FALLBACK_E2"
    assert result.metadata["fallback_shot_count"] == 1


def test_provider_adapter_keeps_e2_source_ids_and_marks_e3_metadata(monkeypatch) -> None:
    bundle = make_bundle()
    e2_result = bundle.components["VLM"].result
    monkeypatch.setattr(e3, "_load_context_bundle", lambda _context, _result: bundle)

    refiner = e3.ContextualShotRefiner(
        inference_runner=lambda _config, items: [
            {
                "revision_item_id": item["revision_item_id"],
                "status": "READY",
                "semantic": semantic(f"最终镜头 {item['ordinal']}"),
            }
            for item in items
        ]
    )
    final = e3.refine_e2_provider_result(bundle.context, e2_result, refiner=refiner)

    assert final.status == "READY"
    assert [item.source_id for item in final.evidence] == ["VLM_1", "VLM_2", "VLM_3"]
    assert final.metadata["contextual_refinement_profile"] == e3.REFINEMENT_PROFILE
    assert final.metadata["e2_semantic_preservation"] == "VLM_OUTPUT.payload.e2_semantic"
    assert final.evidence[0].payload["semantic"]["shot"]["summary"] == "最终镜头 1"
    assert final.evidence[0].payload["e2_semantic"]["shot"]["summary"] == "E2 镜头 1"
