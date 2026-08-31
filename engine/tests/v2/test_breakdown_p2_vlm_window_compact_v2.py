from pathlib import Path
import sys

from engine.app import breakdown_g1_fusion_replay_v1 as replay_v1
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v2 as instrumented


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_breakdown_vlm_window_compact_v2 as compact  # noqa: E402


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


def test_compact_prompt_removes_verbose_per_shot_prose_fields() -> None:
    window = {
        "shots": [
            {
                "ordinal": 1,
                "revision_item_id": "ITEM_1",
                "window_start_seconds": 0.0,
                "window_end_seconds": 1.0,
            },
            {
                "ordinal": 2,
                "revision_item_id": "ITEM_2",
                "window_start_seconds": 1.0,
                "window_end_seconds": 2.0,
            },
        ]
    }

    prompt = compact._compact_window_prompt("zh-CN", window)

    assert compact.WINDOW_CONTEXT_PROMPT_PROFILE == instrumented.WINDOW_PROMPT_PROFILE
    assert '"context_note"' not in prompt
    assert '"environment_description"' not in prompt
    assert '"continuity_summary"' not in prompt
    assert '"scene_change_candidates"' not in prompt
    assert '"shot_scene_hints"' in prompt
    assert '"subject_continuity_hints"' in prompt
    assert "shot_scene_hints 必须覆盖窗口内每个 Shot" in prompt


def test_compact_payload_normalizes_into_e6_scene_and_subject_inputs() -> None:
    shots = (
        shot(1, 0, 1_000_000),
        shot(2, 1_000_000, 2_000_000),
    )
    window = e2.EpisodeVLMWindow(
        ordinal=1,
        start_us=0,
        end_us=2_000_000,
        shots=shots,
    )
    raw = {
        "window_summary": "公寓走廊内两人连续出现",
        "subject_continuity_hints": [{
            "appearance_summary": "黑色长发白色露肩上衣",
            "shot_ordinals": [1, 2],
        }],
        "prop_continuity_hints": [{
            "label": "黑色塑料袋",
            "shot_ordinals": [1, 2],
        }],
        "shot_scene_hints": [
            {
                "revision_item_id": "ITEM_1",
                "ordinal": 1,
                "scene_continuity": "SAME",
                "scene_basis": "DIRECT",
                "scene": {
                    "location_hint": "公寓走廊",
                    "interior_exterior": "INT",
                    "time_of_day": "白天",
                },
            },
            {
                "revision_item_id": "ITEM_2",
                "ordinal": 2,
                "scene_continuity": "NEW_SCENE",
                "scene_basis": "DIRECT",
                "scene": {
                    "location_hint": "客厅",
                    "interior_exterior": "INT",
                    "time_of_day": "白天",
                },
            },
        ],
    }

    provider = instrumented.Qwen3VLSemanticProvider(
        unified_inference_runner=lambda *_args: (),
    )
    normalized = provider._normalize_window_summary(raw, window)

    assert normalized["subject_continuity_hints"][0]["shot_ordinals"] == [1, 2]
    assert normalized["subject_continuity_hints"][0]["continuity_summary"] is None
    assert normalized["prop_continuity_hints"][0]["label"] == "黑色塑料袋"
    assert normalized["shot_scene_hints"][0]["context_note"] is None
    assert normalized["shot_scene_hints"][0]["scene"]["environment_description"] is None
    assert replay_v1._direct_new_scene_ordinals([normalized]) == {2}
