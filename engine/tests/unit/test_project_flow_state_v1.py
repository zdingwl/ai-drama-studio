from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from engine.app import project_flow_state_v1 as flow
from engine.app.project_flow_state_read_v1 import normalize_project_flow_state_v1


def _stage(
    key: str,
    ordinal: int,
    *,
    validity: str = "CURRENT",
    readiness: str = "READY",
    consumable: bool = True,
    reason_code: str = "READY",
    reason: str = "ready",
    open_review_cases: int = 0,
) -> dict:
    return {
        "stage_key": key,
        "ordinal": ordinal,
        "label": key,
        "validity": validity,
        "readiness": readiness,
        "execution": "IDLE",
        "consumable": consumable,
        "reason_code": reason_code,
        "reason": reason,
        "current_input_fingerprint": None,
        "built_input_fingerprint": None,
        "metrics": {},
        "open_review_cases": open_review_cases,
        "active_command": None,
        "warnings": [],
        "last_success": None,
    }


def _payload(stages: list[dict]) -> dict:
    return {
        "schema_version": "project-flow-state-v1",
        "project_id": "PROJECT_1",
        "revision": "a" * 64,
        "generated_at": "2026-09-02T20:00:00+00:00",
        "overall_status": "BLOCKED_DEPENDENCY",
        "can_continue": False,
        "next_action": {
            "action_key": "OLD",
            "kind": "WAIT",
            "label": "old",
            "reason": "old",
            "enabled": False,
            "target_surface": "PROJECT",
            "command_key": None,
        },
        "active_command": None,
        "review_summary": {"open_count": 0, "blocking_count": 0, "by_type": {}},
        "runtime_summary": {"blocking_runtime_count": 0, "items": []},
        "episodes": [{
            "episode_id": "EP_1",
            "sort_order": 1,
            "title": "EP01",
            "preprocess_status": "READY",
            "shot_count": 10,
            "current_shot_revision_id": "SHOTREV_1",
            "current_breakdown_run_id": "RUN_1",
        }],
        "stages": stages,
    }


def test_target_audio_pending_is_actionable_not_dependency_block() -> None:
    stages = [
        _stage("project_setup", 1),
        _stage("source_split", 2),
        _stage("source_understanding", 3),
        _stage("source_assets", 4),
        _stage("source_snapshot", 5),
        _stage("target_design", 6),
        _stage(
            "target_dialogue",
            7,
            validity="CURRENT",
            readiness="BLOCKED_DEPENDENCY",
            consumable=False,
            reason_code="TARGET_AUDIO_PENDING",
            reason="目标文本已就绪，仍需显式生成目标语音",
        ),
        _stage("remake_timing", 8, validity="NOT_BUILT", readiness="BLOCKED_DEPENDENCY", consumable=False),
        _stage("h3_generation", 9, validity="NOT_BUILT", readiness="BLOCKED_DEPENDENCY", consumable=False),
        _stage("postproduction_output", 10, validity="NOT_BUILT", readiness="BLOCKED_DEPENDENCY", consumable=False),
    ]

    result = normalize_project_flow_state_v1(_payload(stages))
    target = next(item for item in result["stages"] if item["stage_key"] == "target_dialogue")

    assert target["validity"] == "NOT_BUILT"
    assert target["readiness"] == "READY"
    assert target["consumable"] is False
    assert result["overall_status"] == "READY_TO_CONTINUE"
    assert result["can_continue"] is True
    assert result["next_action"]["command_key"] == "PREPARE_REMAKE"
    assert result["next_action"]["enabled"] is True


def test_review_block_always_routes_to_review_center() -> None:
    stages = [
        _stage("project_setup", 1),
        _stage("source_split", 2),
        _stage("source_understanding", 3),
        _stage(
            "source_assets",
            4,
            validity="CURRENT",
            readiness="BLOCKED_REVIEW",
            consumable=False,
            reason_code="ASSET_REVIEW_REQUIRED",
            reason="还有人物身份需要确认",
            open_review_cases=3,
        ),
    ]
    payload = _payload(stages)
    payload["review_summary"] = {
        "open_count": 3,
        "blocking_count": 3,
        "by_type": {"CHARACTER_IDENTITY": 3},
    }

    result = normalize_project_flow_state_v1(payload)

    assert result["overall_status"] == "BLOCKED_REVIEW"
    assert result["can_continue"] is True
    assert result["next_action"]["kind"] == "NAVIGATE"
    assert result["next_action"]["target_surface"] == "REVIEW"
    assert result["next_action"]["command_key"] is None


def test_same_business_facts_keep_same_revision_and_stale_history_is_not_current(monkeypatch) -> None:
    project = SimpleNamespace(
        id="PROJECT_1",
        name="Demo",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )

    class FakeSession:
        def get(self, model, key):
            return project if key == "PROJECT_1" else None

    @contextmanager
    def fake_session():
        yield FakeSession()

    monkeypatch.setattr(flow, "get_session", fake_session)
    monkeypatch.setattr(flow, "list_project_tasks", lambda project_id, limit=100: [])
    monkeypatch.setattr(flow, "list_review_issues", lambda project_id, status="OPEN": [])
    # These rows intentionally represent superseded history. They may make the stage STALE,
    # but must never be surfaced as the current business-item count.
    monkeypatch.setattr(flow, "_persisted_counts", lambda project_id: {
        "asset_revisions": 0,
        "target_characters": 2,
        "scene_mappings": 1,
        "target_dialogues": 76,
        "remake_timelines": 1,
        "generation_segments": 30,
        "generation_selections": 12,
        "episode_outputs": 1,
    })
    monkeypatch.setattr(flow, "list_episode_records", lambda project_id: [])
    monkeypatch.setattr(flow, "get_asset_workspace", lambda project_id, auto_bootstrap=False: {
        "status": "EMPTY",
        "stale": False,
        "revision": None,
        "characters": [],
        "scenes": [],
        "props": [],
    })
    monkeypatch.setattr(flow, "load_project_source_drama_snapshot_v1", lambda project_id: (_ for _ in ()).throw(RuntimeError("not built")))
    monkeypatch.setattr(flow, "get_target_localization_v1", lambda project_id: (_ for _ in ()).throw(RuntimeError("not built")))
    monkeypatch.setattr(flow, "get_target_dialogue_v1", lambda project_id: (_ for _ in ()).throw(RuntimeError("not built")))
    monkeypatch.setattr(flow, "get_remake_timeline_v1", lambda project_id: (_ for _ in ()).throw(RuntimeError("not built")))

    first_now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    second_now = first_now + timedelta(minutes=5)
    monkeypatch.setattr(flow, "utcnow", lambda: first_now)
    first = flow.get_project_flow_state_v1("PROJECT_1")
    monkeypatch.setattr(flow, "utcnow", lambda: second_now)
    second = flow.get_project_flow_state_v1("PROJECT_1")

    assert first["generated_at"] != second["generated_at"]
    assert first["revision"] == second["revision"]
    assert first["overall_status"] == "READY_TO_CONTINUE"
    assert first["next_action"]["action_key"] == "IMPORT_EPISODES"

    by_stage = {item["stage_key"]: item for item in first["stages"]}
    assert by_stage["target_design"]["validity"] == "STALE"
    assert by_stage["target_design"]["metrics"]["target_character_count"] == 0
    assert by_stage["target_design"]["metrics"]["scene_mapping_count"] == 0
    assert by_stage["target_dialogue"]["validity"] == "STALE"
    assert by_stage["target_dialogue"]["metrics"]["dialogue_count"] == 0
    assert by_stage["target_dialogue"]["metrics"]["audio_ready_count"] == 0
    assert by_stage["remake_timing"]["metrics"]["generation_segment_count"] == 0
