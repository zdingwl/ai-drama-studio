from __future__ import annotations

from engine.app import breakdown_p2_fusion_episode_v4 as e4
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_continuity_v1 as continuity
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


def subject(label: str, appearance: str) -> dict:
    return {
        "label": label,
        "appearance_summary": appearance,
        "activity_summary": "",
        "screen_position": "中央",
        "visibility": "FULL",
        "speaking_state": "UNKNOWN",
    }


def semantic(subjects: list[dict]) -> dict:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "客厅",
        },
        "shot": {
            "summary": "人物在客厅",
            "visual_description": "人物在客厅",
            "shot_type_hint": "中景",
            "camera_motion_hint": "静止",
            "narrative_function_hint": "对话",
            "composition_hint": "双人构图",
        },
        "subjects": subjects,
        "events": [],
        "props": [],
    }


def test_production_vlm_wrapper_preserves_window_subject_and_prop_hints() -> None:
    shots = (shot(1, 0, 3), shot(2, 3, 6))
    window = e2.EpisodeVLMWindow(
        ordinal=1,
        start_us=0,
        end_us=6_000_000,
        shots=shots,
    )
    provider = continuity.Qwen3VLSemanticProvider(
        window_inference_runner=lambda _config, _video, _windows: (),
        episode_video_resolver=lambda _context: (None, "unused"),
    )
    normalized = provider._normalize_window_summary({
        "window_summary": "同一客厅内男女持续对话",
        "scene_change_candidates": [],
        "subject_continuity_hints": [{
            "appearance_summary": "年轻女性，黑色长发，白色上衣",
            "continuity_summary": "两镜为同一女性",
            "shot_ordinals": [1, 2, 999],
            "members": [
                {"ordinal": 1, "label": "subject_A"},
                {"revision_item_id": "ITEM_2", "label": "subject_B"},
            ],
        }],
        "prop_continuity_hints": [{
            "label": "手机",
            "continuity_summary": "同一手机",
            "shot_ordinals": [1, 2],
        }],
    }, window)

    assert normalized["subject_continuity_hints"] == [{
        "appearance_summary": "年轻女性，黑色长发，白色上衣",
        "continuity_summary": "两镜为同一女性",
        "shot_ordinals": [1, 2],
        "members": [
            {"revision_item_id": "ITEM_1", "ordinal": 1, "label": "subject_A"},
            {"revision_item_id": "ITEM_2", "ordinal": 2, "label": "subject_B"},
        ],
    }]
    assert normalized["prop_continuity_hints"][0]["shot_ordinals"] == [1, 2]
    assert issubclass(continuity.Qwen3VLSemanticProvider, runtime.Qwen3VLSemanticProvider)


def test_e4_continuity_hint_merges_same_people_even_when_labels_swap_and_actions_change() -> None:
    shots = [shot(1, 0, 2), shot(2, 2, 4), shot(3, 4, 6)]
    semantics = [
        semantic([
            subject("subject_A", "年轻女性，黑色长发，白色上衣，表情惊讶"),
            subject("subject_B", "年轻男性，黑色短发，黑色西装，站立"),
        ]),
        semantic([
            subject("subject_A", "年轻女性，黑色长发，白色上衣，双臂交叉，表情愤怒"),
            subject("subject_B", "年轻男性，黑色短发，黑色西装，低头看手机"),
        ]),
        # Shot-local labels swap here: A is now male and B is female.
        semantic([
            subject("subject_A", "年轻男性，黑色短发，黑色西装，正在说话"),
            subject("subject_B", "年轻女性，黑色长发，白色上衣，转头看向对方"),
        ]),
    ]
    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=semantics)
    window_summaries = [{
        "window_id": "window-0001",
        "subject_continuity_hints": [
            {
                "appearance_summary": "年轻女性，黑色长发，白色上衣",
                "continuity_summary": "三镜为同一女性",
                "shot_ordinals": [1, 2, 3],
                "members": [],
            },
            {
                "appearance_summary": "年轻男性，黑色短发，黑色西装",
                "continuity_summary": "三镜为同一男性",
                "shot_ordinals": [1, 2, 3],
                "members": [],
            },
        ],
    }]

    keys, members, stats = e4._build_subject_cluster_keys([plan], window_summaries)

    female_key = keys[("ITEM_1", "subject_A")]
    male_key = keys[("ITEM_1", "subject_B")]
    assert female_key == keys[("ITEM_2", "subject_A")]
    assert female_key == keys[("ITEM_3", "subject_B")]
    assert male_key == keys[("ITEM_2", "subject_B")]
    assert male_key == keys[("ITEM_3", "subject_A")]
    assert female_key != male_key
    assert len(members[female_key]) == 3
    assert len(members[male_key]) == 3
    assert stats.observation_count == 6
    assert stats.cluster_count == 2
    assert stats.explicit_union_count >= 4


def test_e4_hard_same_shot_cannot_link_blocks_bad_continuity_hint_transitively() -> None:
    shots = [shot(1, 0, 2), shot(2, 2, 4)]
    semantics = [
        semantic([
            subject("subject_A", "年轻女性，黑色长发，白色上衣"),
            subject("subject_B", "年轻女性，黑色长发，白色上衣"),
        ]),
        semantic([
            subject("subject_A", "年轻女性，黑色长发，白色上衣"),
        ]),
    ]
    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=semantics)
    # Deliberately malformed model hint tries to place both women from Shot 1 in one identity chain.
    window_summaries = [{
        "window_id": "window-0001",
        "subject_continuity_hints": [{
            "appearance_summary": "年轻女性，黑色长发，白色上衣",
            "continuity_summary": "错误连续性提示",
            "shot_ordinals": [1, 2],
            "members": [
                {"revision_item_id": "ITEM_1", "ordinal": 1, "label": "subject_A"},
                {"revision_item_id": "ITEM_2", "ordinal": 2, "label": "subject_A"},
                {"revision_item_id": "ITEM_1", "ordinal": 1, "label": "subject_B"},
            ],
        }],
    }]

    keys, _members, stats = e4._build_subject_cluster_keys([plan], window_summaries)

    assert keys[("ITEM_1", "subject_A")] != keys[("ITEM_1", "subject_B")]
    assert stats.rejected_cannot_link_count >= 1


def test_e4_stable_appearance_fallback_ignores_expression_and_pose_words() -> None:
    shots = [shot(1, 0, 2), shot(2, 2, 4)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic([subject("subject_A", "年轻女性，黑色长发，白色上衣，表情惊讶")]),
            semantic([subject("subject_B", "年轻女性，黑色长发，白色上衣，双臂交叉，表情愤怒")]),
        ],
    )

    keys, _members, stats = e4._build_subject_cluster_keys([plan], [])

    assert keys[("ITEM_1", "subject_A")] == keys[("ITEM_2", "subject_B")]
    assert stats.fallback_union_count == 1
