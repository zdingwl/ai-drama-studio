from engine.app import breakdown_p2_vlm_continuity_v1 as continuity
from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v3 as production
from scripts import run_breakdown_vlm_exact_shot_compact_v3 as compact


def test_production_vlm_routes_to_accepted_exact_shot_compact_v3() -> None:
    provider = continuity.Qwen3VLSemanticProvider()
    config = provider._runtime_config("zh-CN")

    assert issubclass(continuity.Qwen3VLSemanticProvider, production.Qwen3VLSemanticProvider)
    assert continuity.VLM_WINDOW_PROMPT_PROFILE == (
        "breakdown-p2-vlm-window-context-segment-index-zh-v4"
    )
    assert continuity.VLM_EXACT_SHOT_PROMPT_PROFILE == (
        "breakdown-p2-vlm-exact-shot-detector-recheck-zh-v5"
    )
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py"


def test_production_exact_shot_limits_remain_unchanged() -> None:
    provider = continuity.Qwen3VLSemanticProvider()

    assert provider.grounding_batch_size == 5
    assert provider.exact_shot_max_pixels == 524288
    assert provider.grounding_max_new_tokens == 4096


def test_detector_candidates_drive_anonymous_shot_local_supplement() -> None:
    shot = {
        "revision_item_id": "ITEM_3",
        "ordinal": 3,
        "frames": [
            {"path": "unused-1.jpg", "person_detections": [
                {"box": [0.0, .05, .38, .9], "score": .88},
                {"box": [.48, .12, .28, .7], "score": .91},
            ]},
            {"path": "unused-2.jpg", "person_detections": [
                {"box": [0.0, .04, .39, .91], "score": .86},
                {"box": [.5, .13, .27, .69], "score": .90},
            ]},
        ],
    }
    semantic = {
        "shot": {"summary": "灰白短发老人站在门口", "visual_description": "灰白短发老人站在门口"},
        "subjects": [{
            "label": "subject_A",
            "appearance_summary": "灰白短发，花衬衫",
            "activity_summary": "站立",
            "screen_position": "中央",
            "visibility": "FULL",
            "frame_boxes": [
                {"frame": 1, "box": [.46, .1, .32, .73]},
                {"frame": 2, "box": [.48, .11, .31, .72]},
            ],
        }],
    }

    candidates = compact._presence_candidates(shot, semantic)
    assert [item["ref"] for item in candidates] == ["F1-C1", "F2-C1"]

    merged, count = compact._merge_presence_recheck(semantic, {
        "missing_people": [{
            "refs": ["F1-C1", "F2-C1"],
            "appearance": "黑色长发，白色露肩上衣",
            "activity": "背对镜头站立",
            "position": "前景",
            "visibility": "BACK_VIEW",
            "name": "不得采信的身份字段",
        }],
    }, candidates)

    assert count == 1
    assert [item["label"] for item in merged["subjects"]] == ["subject_A", "subject_B"]
    added = merged["subjects"][1]
    assert added["visibility"] == "BACK_VIEW"
    assert added["frame_boxes"] == [
        {"frame": 1, "box": [0.0, .05, .38, .9]},
        {"frame": 2, "box": [0.0, .04, .39, .91]},
    ]
    assert "name" not in added and "character_id" not in added
    assert "黑色长发" in merged["shot"]["summary"]


def test_detector_recheck_does_not_run_on_ambiguous_equal_count_without_locations() -> None:
    candidates = compact._presence_candidates({
        "frames": [{"person_detections": [{"box": [.1, .1, .5, .8], "score": .8}]}]
    }, {
        "subjects": [{"label": "subject_A", "frame_boxes": []}],
    })
    assert candidates == []


def test_focused_result_must_add_people_without_exceeding_detector_ceiling() -> None:
    first = {"subjects": [{"label": "subject_A"}]}
    shot = {"frames": [{"person_detections": [{}, {}]}]}
    focused = {"subjects": [{"label": "subject_A"}, {"label": "subject_B"}]}

    accepted = compact._focused_semantic_if_safe(first, focused, shot)
    assert accepted == (focused, 1)
    assert compact._focused_semantic_if_safe(first, first, shot) is None
    assert compact._focused_semantic_if_safe(
        first, {"subjects": [{}, {}, {}]}, shot
    ) is None
