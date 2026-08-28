from __future__ import annotations

from pathlib import Path

from engine.app.asset_semantics_p4_v1 import (
    _bbox_norm,
    _normalize_guided_result,
    build_guided_prompt,
)
from engine.app.breakdown_asset_guidance_v1 import (
    PropSearchGuide,
    SceneSearchGuide,
    ShotAssetGuidance,
)


def _guidance() -> ShotAssetGuidance:
    return ShotAssetGuidance(
        shot_id="SHOT_CURRENT_1",
        episode_id="EP_1",
        shot_revision_id="SHOTREV_CURRENT",
        shot_revision_item_id="SHOTREVITEM_1",
        breakdown_run_id="BREAKDOWN_RUN_1",
        scene=SceneSearchGuide(
            breakdown_run_id="BREAKDOWN_RUN_1",
            scene_segment_id="SCENESEG_1",
            location_hint="走廊",
            interior_exterior="INTERIOR",
            time_of_day="DAY",
            summary="两人在走廊交谈",
            environment_description="狭长走廊，两侧有房门",
        ),
        props=(
            PropSearchGuide(
                breakdown_run_id="BREAKDOWN_RUN_1",
                prop_hint_id="PROP_HINT_SECRET_ID",
                occurrence_id="PROP_OCC_SECRET_ID",
                label_hint="黑色塑料袋",
                normalized_hint="黑色塑料袋",
                importance="SUPPORTING",
                narrative_reason="人物手中持续拿着该物体",
                source_start_us=1_000_000,
                source_end_us=2_000_000,
                screen_position_hint="RIGHT",
                interaction_summary="人物B右手提着黑色塑料袋",
                confidence=None,
            ),
        ),
    )


def test_prompt_treats_breakdown_as_hypothesis_not_truth() -> None:
    prompt, target_map = build_guided_prompt(_guidance())

    assert "只是搜索提示/假设，可能正确、可能错误" in prompt
    assert "必须以当前图片中真正可见的内容为准" in prompt
    assert "看不见就 observed=false" in prompt
    assert "黑色塑料袋" in prompt
    assert "target_key" in prompt
    assert "PROP_HINT_SECRET_ID" not in prompt
    assert "PROP_OCC_SECRET_ID" not in prompt
    assert target_map["P1"].prop_hint_id == "PROP_HINT_SECRET_ID"


def test_guided_result_maps_local_target_key_back_to_provenance() -> None:
    result = _normalize_guided_result({
        "scene": {
            "label": "走廊",
            "indoor_outdoor": "内",
            "time_of_day": "日",
            "confidence": 0.91,
            "draft_match": "MATCH",
            "reason": "可见狭长通道与两侧房门",
        },
        "guided_props": [{
            "target_key": "P1",
            "observed": True,
            "confidence": 0.88,
            "reason": "人物右手提着黑色袋子",
            "bbox_norm": [0.65, 0.42, 0.92, 0.96],
        }],
        "discovered_props": [],
    }, _guidance())

    prop = result["guided_props"][0]
    assert prop["name"] == "黑色塑料袋"
    assert prop["observed"] is True
    assert prop["prop_hint_id"] == "PROP_HINT_SECRET_ID"
    assert prop["occurrence_id"] == "PROP_OCC_SECRET_ID"
    assert prop["bbox_norm"] == [0.65, 0.42, 0.92, 0.96]


def test_guided_result_keeps_rejected_draft_target_as_not_observed() -> None:
    result = _normalize_guided_result({
        "scene": {"label": "走廊", "draft_match": "MATCH"},
        "guided_props": [{
            "target_key": "P1",
            "observed": False,
            "confidence": 0.99,
            "reason": "当前帧没有看到该物体",
            "bbox_norm": [0.1, 0.1, 0.9, 0.9],
        }],
    }, _guidance())

    prop = result["guided_props"][0]
    assert prop["observed"] is False
    assert prop["confidence"] == 0.0
    assert prop["bbox_norm"] is None


def test_bbox_normalization_rejects_invalid_or_zero_area_boxes() -> None:
    assert _bbox_norm([-0.1, 0.1, 0.5, 0.5]) is None
    assert _bbox_norm([0.2, 0.2, 0.2, 0.7]) is None
    assert _bbox_norm([0.9, 0.8, 0.2, 0.1]) == [0.2, 0.1, 0.9, 0.8]


def test_asset_route_uses_p4_semantics_entrypoint() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "engine" / "app" / "asset_routes_v3.py").read_text(encoding="utf-8")

    assert "from engine.app.asset_semantics_p4_v1 import enrich_asset_run, semantic_model_status" in source
    assert "Draft 引导场景 / 道具验证" in source
