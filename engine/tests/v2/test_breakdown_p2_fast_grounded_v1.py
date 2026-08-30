from pathlib import Path

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_fast_grounded_v1 as fast
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime


def shot(ordinal: int, start_us: int, end_us: int) -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id=f"ITEM_{ordinal}",
        original_shot_id=f"SHOT_{ordinal}",
        ordinal=ordinal,
        start_us=start_us,
        end_us=end_us,
        duration_us=end_us - start_us,
        reference_clip_path=f"unused-{ordinal}.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def semantic(*, summary: str, subjects: list[dict], props: list[dict]) -> dict:
    return {
        "scene": {
            "location_hint": "",
            "interior_exterior": "UNKNOWN",
            "time_of_day": "未知",
            "environment_description": "",
        },
        "shot": {
            "summary": summary,
            "visual_description": summary,
            "shot_type_hint": "特写",
            "camera_motion_hint": "UNKNOWN",
            "narrative_function_hint": "建立视觉信息",
            "composition_hint": "主体居中",
        },
        "subjects": subjects,
        "events": [],
        "props": props,
    }


def test_frame_sample_ratios_keep_short_shots_cheap() -> None:
    assert fast.frame_sample_ratios(800_000) == (0.50,)
    assert fast.frame_sample_ratios(2_000_000) == (0.25, 0.75)
    assert fast.frame_sample_ratios(5_000_000) == (0.15, 0.50, 0.85)


def test_scene_context_merge_never_imports_neighbor_people_or_props() -> None:
    grounded = semantic(
        summary="蓝色玫瑰插在玻璃花瓶中",
        subjects=[],
        props=[{"label": "蓝色玫瑰", "importance": "HIGH", "narrative_reason": "画面主体", "subject_labels": []}],
    )
    context = {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "客厅内摆有沙发和茶几",
        },
        # These keys deliberately simulate dangerous neighbor facts. The merge must ignore them.
        "subjects": [{"label": "subject_A", "appearance_summary": "年轻女性"}],
        "props": [{"label": "黑色塑料袋"}],
    }

    merged = fast._scene_context_merge(grounded, {"scene": context["scene"]})

    assert merged["scene"]["location_hint"] == "客厅"
    assert merged["scene"]["interior_exterior"] == "INT"
    assert merged["subjects"] == []
    assert [item["label"] for item in merged["props"]] == ["蓝色玫瑰"]
    assert merged["shot"]["visual_description"] == "蓝色玫瑰插在玻璃花瓶中"


def test_provider_uses_window_only_for_scene_and_exact_shot_for_visible_truth() -> None:
    shots = (
        shot(1, 0, 800_000),
        shot(2, 800_000, 3_640_000),
    )
    context = p2.P2RunContext(
        run_id="RUN_1",
        project_id="PROJECT_1",
        episode_id="EP_1",
        source_language="zh-CN",
        source_shot_revision_id="REV_1",
        audio_path=None,
        shots=shots,
    )

    def fake_runner(_config, _video, windows):
        window = windows[0]
        return (
            {
                "kind": "window_context",
                "window_id": window.window_id,
                "status": "READY",
                "semantic": {
                    "window_summary": "客厅内两人围绕蓝色玫瑰发生争执",
                    "scene_change_candidates": [],
                    "subject_continuity_hints": [{
                        "appearance_summary": "年轻女性，黑色长发",
                        "continuity_summary": "后续镜头为同一女性",
                        "shot_ordinals": [2],
                    }],
                    "prop_continuity_hints": [],
                    "shot_scene_hints": [
                        {
                            "revision_item_id": "ITEM_1",
                            "ordinal": 1,
                            "scene_continuity": "SAME",
                            "scene_basis": "CONTEXT",
                            "context_note": "由连续空间判断",
                            "scene": {
                                "location_hint": "客厅",
                                "interior_exterior": "INT",
                                "time_of_day": "白天",
                                "environment_description": "客厅",
                            },
                        },
                        {
                            "revision_item_id": "ITEM_2",
                            "ordinal": 2,
                            "scene_continuity": "SAME",
                            "scene_basis": "DIRECT",
                            "context_note": "人物位于客厅",
                            "scene": {
                                "location_hint": "客厅",
                                "interior_exterior": "INT",
                                "time_of_day": "白天",
                                "environment_description": "客厅",
                            },
                        },
                    ],
                },
            },
            {
                "kind": "shot_grounding",
                "revision_item_id": "ITEM_1",
                "status": "READY",
                "semantic": semantic(
                    summary="蓝色玫瑰插在玻璃花瓶中",
                    subjects=[],
                    props=[{"label": "蓝色玫瑰", "importance": "HIGH", "narrative_reason": "画面主体", "subject_labels": []}],
                ),
            },
            {
                "kind": "shot_grounding",
                "revision_item_id": "ITEM_2",
                "status": "READY",
                "semantic": semantic(
                    summary="年轻女性站在室内",
                    subjects=[{
                        "label": "subject_A",
                        "appearance_summary": "年轻女性，黑色长发",
                        "activity_summary": "站立",
                        "screen_position": "中央",
                        "visibility": "FULL",
                        "speaking_state": "UNKNOWN",
                    }],
                    props=[],
                ),
            },
        )

    provider = fast.Qwen3VLSemanticProvider(
        unified_inference_runner=fake_runner,
        episode_video_resolver=lambda _context: (Path("fake.mp4"), "test"),
    )
    result = provider.analyze(context)

    assert result.status == "READY"
    assert len(result.evidence) == 2
    first = result.evidence[0]
    assert first.payload["semantic"]["shot"]["summary"] == "蓝色玫瑰插在玻璃花瓶中"
    assert first.payload["semantic"]["scene"]["location_hint"] == "客厅"
    assert first.payload["semantic"]["subjects"] == []
    assert first.payload["semantic"]["props"][0]["label"] == "蓝色玫瑰"
    assert first.payload["exact_shot_grounding"]["visual_truth_policy"] == fast.VISUAL_TRUTH_POLICY
    assert result.metadata["model_load_policy"] == "one-run-one-vlm-process-one-model-load"


def test_stable_runtime_entry_uses_fast_grounded_provider() -> None:
    assert issubclass(runtime.Qwen3VLSemanticProvider, fast.Qwen3VLSemanticProvider)
    assert runtime.VLM_CONTEXTUAL_FAILURE_POLICY == "retired-from-production-fast-grounded-v1"
