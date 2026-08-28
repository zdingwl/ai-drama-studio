from __future__ import annotations

from pathlib import Path

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime


def shot(ordinal: int, start_s: int, end_s: int) -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id=f"ITEM_{ordinal}",
        original_shot_id=f"SHOT_{ordinal}",
        ordinal=ordinal,
        start_us=start_s * 1_000_000,
        end_us=end_s * 1_000_000,
        duration_us=(end_s - start_s) * 1_000_000,
        reference_clip_path=f"unused-{ordinal}.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def context(shots: tuple[p2.P2ShotInput, ...]) -> p2.P2RunContext:
    return p2.P2RunContext(
        run_id="RUN_E2",
        project_id="PROJECT_E2",
        episode_id="EPISODE_E2",
        source_language="zh-CN",
        source_shot_revision_id="REV_E2",
        audio_path=None,
        shots=shots,
    )


def semantic(summary: str) -> dict:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "人物位于同一客厅空间。",
        },
        "shot": {
            "summary": summary,
            "visual_description": summary,
            "shot_type_hint": "中景",
            "camera_motion_hint": "静止",
            "narrative_function_hint": "推进人物互动",
            "composition_hint": "人物位于画面中央",
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
            "content": "人物站在桌边观察前方。",
            "subject_labels": ["subject_A"],
        }],
        "props": [{
            "label": "手机",
            "importance": "MEDIUM",
            "narrative_reason": "人物手边放着手机。",
            "subject_labels": ["subject_A"],
        }],
    }


def test_window_planner_is_shot_aligned_overlapping_and_covers_every_shot() -> None:
    shots = tuple(shot(index, (index - 1) * 5, index * 5) for index in range(1, 9))
    windows = e2._plan_windows(
        shots,
        target_duration_us=20_000_000,
        overlap_ratio=0.50,
    )

    assert [(item.start_us, item.end_us) for item in windows] == [
        (0, 20_000_000),
        (10_000_000, 30_000_000),
        (20_000_000, 40_000_000),
    ]
    assert set.intersection(
        {item.revision_item_id for item in windows[0].shots},
        {item.revision_item_id for item in windows[1].shots},
    ) == {"ITEM_3", "ITEM_4"}
    covered = {item.revision_item_id for window in windows for item in window.shots}
    assert covered == {item.revision_item_id for item in shots}


def test_provider_emits_exact_shot_vlm_output_and_selects_best_context_window(tmp_path: Path) -> None:
    shots = tuple(shot(index, (index - 1) * 5, index * 5) for index in range(1, 9))
    episode_video = tmp_path / "episode proxy.mp4"
    episode_video.write_bytes(b"video")
    calls = []

    def runner(config, video_path, windows):
        calls.append((config, video_path, tuple(windows)))
        rows = []
        for window in windows:
            rows.append({
                "window_id": window.window_id,
                "status": "READY",
                "semantic": {
                    "window_summary": f"{window.window_id} 连续窗口",
                    "scene_change_candidates": [],
                    "subject_continuity_hints": [],
                    "prop_continuity_hints": [],
                    "shots": [{
                        "revision_item_id": item.revision_item_id,
                        "ordinal": item.ordinal,
                        "scene_continuity": "SAME",
                        "scene_basis": "MIXED",
                        "context_note": f"由 {window.window_id} 提供上下文",
                        "semantic": semantic(f"{window.window_id} 镜头 {item.ordinal}"),
                    } for item in window.shots],
                },
            })
        return rows

    provider = e2.Qwen3VLSemanticProvider(
        model_name="fixture-qwen",
        window_duration_seconds=20,
        window_overlap_ratio=0.50,
        window_inference_runner=runner,
        episode_video_resolver=lambda _context: (episode_video, "fixture_proxy"),
    )
    result = provider.analyze(context(shots))

    assert result.status == "READY"
    assert len(calls) == 1
    assert len(result.evidence) == len(shots)
    assert all(item.source_type == "VLM_OUTPUT" for item in result.evidence)
    assert [(item.source_start_us, item.source_end_us) for item in result.evidence] == [
        (item.start_us, item.end_us) for item in shots
    ]
    assert result.metadata["episode_context_profile"] == e2.VLM_EPISODE_WINDOW_PROFILE
    assert result.metadata["window_count"] == 3
    assert result.metadata["episode_video_kind"] == "fixture_proxy"

    by_ordinal = {item.payload["shot_ordinal"]: item for item in result.evidence}
    # Shot 4 sits at the right edge of window-0001 but has surrounding context in window-0002.
    assert by_ordinal[4].text == "window-0002 镜头 4"
    assert by_ordinal[4].payload["episode_window"]["window_id"] == "window-0002"
    assert by_ordinal[4].payload["episode_window"]["scene_continuity"] == "SAME"
    assert "window-0001" in by_ordinal[4].payload["episode_window"]["supporting_window_ids"]

    p2.validate_provider_result(context(shots), result)


def test_e2_keeps_legacy_whitelist_and_drops_final_asset_ids(tmp_path: Path) -> None:
    shots = (shot(1, 0, 5),)
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"video")
    raw = semantic("人物在客厅站立")
    raw["character_id"] = "CHARACTER_FORBIDDEN"
    raw["scene_id"] = "SCENE_FORBIDDEN"
    raw["subjects"][0]["character_id"] = "CHARACTER_NESTED"
    raw["shot"]["raw_chain_of_thought"] = "must not persist"

    provider = e2.Qwen3VLSemanticProvider(
        window_duration_seconds=20,
        window_inference_runner=lambda _config, _video, windows: [{
            "window_id": windows[0].window_id,
            "status": "READY",
            "semantic": {
                "window_summary": "单镜头窗口",
                "shots": [{
                    "revision_item_id": shots[0].revision_item_id,
                    "scene_continuity": "UNCERTAIN",
                    "scene_basis": "DIRECT",
                    "semantic": raw,
                }],
            },
        }],
        episode_video_resolver=lambda _context: (video, "fixture_source"),
    )
    result = provider.analyze(context(shots))

    assert result.status == "READY"
    persisted = result.evidence[0].payload["semantic"]
    assert "character_id" not in str(persisted)
    assert "scene_id" not in str(persisted)
    assert "raw_chain_of_thought" not in str(persisted)
    p2.validate_provider_result(context(shots), result)


def test_missing_episode_video_fails_before_window_runner() -> None:
    shots = (shot(1, 0, 5),)
    called = False

    def runner(_config, _video, _windows):
        nonlocal called
        called = True
        raise AssertionError("runner must not execute")

    result = e2.Qwen3VLSemanticProvider(
        window_inference_runner=runner,
        episode_video_resolver=lambda _context: (None, "missing"),
    ).analyze(context(shots))

    assert result.status == "NOT_AVAILABLE"
    assert result.evidence == ()
    assert called is False


def test_stable_runtime_import_points_to_episode_window_provider() -> None:
    assert runtime.Qwen3VLSemanticProvider is e2.Qwen3VLSemanticProvider
    assert runtime.VLM_EPISODE_WINDOW_PROFILE == e2.VLM_EPISODE_WINDOW_PROFILE
