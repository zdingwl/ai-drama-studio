from __future__ import annotations

from pathlib import Path
import sys

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import run_breakdown_refinement_qwen3 as runner


def context() -> p2.P2RunContext:
    shot = p2.P2ShotInput(
        revision_item_id="ITEM_1",
        original_shot_id="SHOT_1",
        ordinal=1,
        start_us=0,
        end_us=2_000_000,
        duration_us=2_000_000,
        reference_clip_path="unused.mp4",
        thumbnail_path=None,
        keyframes=(),
    )
    return p2.P2RunContext(
        run_id="RUN_E3_FAILSOFT",
        project_id="PROJECT_E3_FAILSOFT",
        episode_id="EPISODE_E3_FAILSOFT",
        source_language="zh-CN",
        source_shot_revision_id="REV_E3_FAILSOFT",
        audio_path=None,
        shots=(shot,),
    )


def semantic() -> dict:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "人物位于客厅。",
        },
        "shot": {
            "summary": "人物在客厅站立。",
            "visual_description": "人物位于画面中央。",
            "shot_type_hint": "中景",
            "camera_motion_hint": "静止",
            "narrative_function_hint": "推进人物互动",
            "composition_hint": "人物居中",
        },
        "subjects": [],
        "events": [],
        "props": [],
    }


def e2_result() -> p2.P2ProviderResult:
    return p2.P2ProviderResult(
        component="VLM",
        provider="qwen3-vl",
        model="fixture-qwen",
        status="READY",
        evidence=(p2.P2EvidenceRecord(
            source_type="VLM_OUTPUT",
            source_id="VLM_1",
            source_start_us=0,
            source_end_us=2_000_000,
            shot_revision_item_id="ITEM_1",
            text="人物在客厅站立。",
            language="zh-CN",
            payload={
                "shot_ordinal": 1,
                "semantic": semantic(),
                "episode_window": {
                    "window_id": "window-0001",
                    "scene_continuity": "SAME",
                    "scene_basis": "MIXED",
                },
            },
        ),),
        metadata={"profile": "breakdown-p2-vlm-episode-window-e2-v1"},
    )


def test_whole_e3_failure_falls_back_to_ready_e2_semantics() -> None:
    ctx = context()
    raw = e2_result()
    failed = p2.P2ProviderResult(
        component="VLM",
        provider="qwen3-vl",
        model="fixture-qwen",
        status="FAILED",
        evidence=(),
        metadata={
            "contextual_refinement_metadata": {
                "error_type": "CalledProcessError",
            }
        },
        warnings=("P2-E3 contextual refinement inference failed",),
    )

    result = runtime._fallback_to_e2(ctx, raw, failed_result=failed)

    assert result.status == "READY"
    assert result.evidence[0].payload["semantic"] == semantic()
    assert result.evidence[0].payload["e2_semantic"] == semantic()
    assert result.evidence[0].payload["contextual_refinement"]["status"] == "FALLBACK_E2"
    assert result.metadata["contextual_refinement_status"] == "FALLBACK_E2"
    assert result.metadata["contextual_refinement_failure_policy"] == runtime.VLM_CONTEXTUAL_FAILURE_POLICY
    assert any("using validated E2 semantics" in item for item in result.warnings)
    p2.validate_provider_result(ctx, result)


def test_e3_runner_serializes_runtime_setup_failure_per_shot() -> None:
    items = (
        {"revision_item_id": "ITEM_1"},
        {"revision_item_id": "ITEM_2"},
    )

    rows = runner._failure_records(items, RuntimeError("cuda load failed"), stage="runtime_setup")

    assert [row["revision_item_id"] for row in rows] == ["ITEM_1", "ITEM_2"]
    assert all(row["status"] == "FAILED" for row in rows)
    assert all(row["failure_stage"] == "runtime_setup" for row in rows)
    assert all("cuda load failed" in row["error_detail"] for row in rows)
    assert all("保留 E2 结果" in row["refinement_note"] for row in rows)
