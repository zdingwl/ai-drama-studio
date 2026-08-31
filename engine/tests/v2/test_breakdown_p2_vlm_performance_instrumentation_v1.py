from pathlib import Path

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v2 as instrumented
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime


def shot() -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id="ITEM_1",
        original_shot_id="SHOT_1",
        ordinal=1,
        start_us=0,
        end_us=800_000,
        duration_us=800_000,
        reference_clip_path="unused.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def semantic() -> dict:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "客厅",
        },
        "shot": {
            "summary": "蓝色玫瑰插在玻璃花瓶中",
            "visual_description": "蓝色玫瑰插在玻璃花瓶中",
            "shot_type_hint": "特写",
            "camera_motion_hint": "UNKNOWN",
            "narrative_function_hint": "建立道具",
            "composition_hint": "主体居中",
        },
        "subjects": [],
        "events": [],
        "props": [{
            "label": "蓝色玫瑰",
            "importance": "HIGH",
            "narrative_reason": "画面主体",
            "subject_labels": [],
        }],
    }


def test_instrumented_provider_persists_host_and_model_runner_timings() -> None:
    item = shot()
    context = p2.P2RunContext(
        run_id="RUN_TIMING",
        project_id="PROJECT_1",
        episode_id="EP_1",
        source_language="zh-CN",
        source_shot_revision_id="REV_1",
        audio_path=None,
        shots=(item,),
    )

    def fake_runner(_config, _video, windows):
        window = windows[0]
        return (
            {
                "kind": "window_context",
                "window_id": window.window_id,
                "status": "READY",
                "semantic": {
                    "window_summary": "客厅里的蓝色玫瑰",
                    "scene_change_candidates": [],
                    "subject_continuity_hints": [],
                    "prop_continuity_hints": [],
                    "shot_scene_hints": [{
                        "revision_item_id": "ITEM_1",
                        "ordinal": 1,
                        "scene_continuity": "SAME",
                        "scene_basis": "DIRECT",
                        "context_note": "同一客厅",
                        "scene": {
                            "location_hint": "客厅",
                            "interior_exterior": "INT",
                            "time_of_day": "白天",
                            "environment_description": "客厅",
                        },
                    }],
                },
            },
            {
                "kind": "shot_grounding",
                "revision_item_id": "ITEM_1",
                "status": "READY",
                "semantic": semantic(),
            },
            {
                "kind": "host_preparation_timing",
                "status": "READY",
                "timing": {
                    "profile": instrumented.PERFORMANCE_PROFILE,
                    "window_materialization_total_seconds": 1.25,
                    "grounding_frame_materialization_total_seconds": 0.75,
                    "subprocess_wall_seconds": 8.5,
                    "grounding_frame_count": 1,
                },
            },
            {
                "kind": "runtime_timing",
                "status": "READY",
                "timing": {
                    "profile": instrumented.PERFORMANCE_PROFILE,
                    "model_load_seconds": 2.0,
                    "window_context_total_seconds": 3.0,
                    "window_timings": [{
                        "window_id": window.window_id,
                        "shot_count": 1,
                        "elapsed_seconds": 3.0,
                        "status": "READY",
                    }],
                    "exact_shot_total_seconds": 3.25,
                    "grounding_batch_count": 1,
                    "grounding_frame_count": 1,
                    "grounding_batch_timings": [{
                        "batch_ordinal": 1,
                        "shot_count": 1,
                        "frame_count": 1,
                        "first_shot_ordinal": 1,
                        "last_shot_ordinal": 1,
                        "elapsed_seconds": 3.25,
                        "status": "READY",
                    }],
                    "runner_total_seconds": 8.25,
                },
            },
        )

    provider = instrumented.Qwen3VLSemanticProvider(
        unified_inference_runner=fake_runner,
        episode_video_resolver=lambda _context: (Path("fake.mp4"), "test"),
    )
    result = provider.analyze(context)

    assert result.status == "READY"
    performance = result.metadata["performance"]
    assert performance["profile"] == instrumented.PERFORMANCE_PROFILE
    assert performance["provider_runner_wall_seconds"] is not None
    assert performance["host"]["window_materialization_total_seconds"] == 1.25
    assert performance["host"]["grounding_frame_materialization_total_seconds"] == 0.75
    assert performance["model_runner"]["model_load_seconds"] == 2.0
    assert performance["model_runner"]["window_context_total_seconds"] == 3.0
    assert performance["model_runner"]["exact_shot_total_seconds"] == 3.25
    assert performance["model_runner"]["grounding_batch_timings"][0]["frame_count"] == 1
    assert result.evidence[0].payload["semantic"]["subjects"] == []


def test_stable_runtime_routes_through_instrumented_provider() -> None:
    assert issubclass(runtime.Qwen3VLSemanticProvider, instrumented.Qwen3VLSemanticProvider)
    assert runtime.VLM_PERFORMANCE_PROFILE == instrumented.PERFORMANCE_PROFILE
