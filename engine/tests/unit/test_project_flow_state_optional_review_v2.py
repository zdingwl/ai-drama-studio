from __future__ import annotations

from engine.app import project_flow_state_read_v1 as read
from engine.app.source_drama_snapshot_auto_v2 import load_project_source_drama_snapshot_auto_v2


def _stage(
    key: str,
    ordinal: int,
    *,
    validity: str = "CURRENT",
    readiness: str = "READY",
    consumable: bool = True,
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
        "reason_code": "READY" if readiness == "READY" else "LEGACY_REVIEW_GATE",
        "reason": "ready" if readiness == "READY" else "旧人工审核门禁",
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
        "generated_at": "2026-09-07T12:00:00+00:00",
        "overall_status": "BLOCKED_REVIEW",
        "can_continue": False,
        "next_action": {
            "action_key": "OPEN_REVIEW_CENTER",
            "kind": "NAVIGATE",
            "label": "处理待确认",
            "reason": "旧人工审核门禁",
            "enabled": True,
            "target_surface": "REVIEW",
            "command_key": None,
        },
        "active_command": None,
        "review_summary": {
            "open_count": 4,
            "blocking_count": 4,
            "by_type": {"SPEAKER": 2, "SOURCE_DIALOGUE": 2},
        },
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


def test_current_review_gate_becomes_optional_correction_and_flow_continues() -> None:
    stages = [
        _stage("project_setup", 1),
        _stage("source_split", 2),
        _stage("source_understanding", 3),
        _stage("source_assets", 4),
        _stage(
            "source_snapshot",
            5,
            readiness="BLOCKED_REVIEW",
            consumable=False,
            open_review_cases=4,
        ),
        _stage("target_design", 6, validity="NOT_BUILT", readiness="BLOCKED_DEPENDENCY", consumable=False),
    ]

    relaxed = read.relax_optional_review_gates_v2(_payload(stages))
    result = read.normalize_project_flow_state_v1(relaxed)
    snapshot = next(item for item in result["stages"] if item["stage_key"] == "source_snapshot")

    assert snapshot["validity"] == "CURRENT"
    assert snapshot["readiness"] == "READY"
    assert snapshot["consumable"] is True
    assert snapshot["open_review_cases"] == 4
    assert snapshot["reason_code"] == "READY_WITH_OPTIONAL_CORRECTIONS"
    assert result["review_summary"]["open_count"] == 4
    assert result["review_summary"]["blocking_count"] == 0
    assert result["overall_status"] == "BLOCKED_DEPENDENCY"
    assert result["next_action"]["target_surface"] == "PROJECT"


def test_dependency_runtime_or_stale_gate_is_never_relaxed_as_review() -> None:
    stages = [
        _stage("project_setup", 1),
        _stage(
            "source_snapshot",
            5,
            validity="STALE",
            readiness="BLOCKED_REVIEW",
            consumable=False,
            open_review_cases=2,
        ),
        _stage("target_design", 6, validity="NOT_BUILT", readiness="BLOCKED_DEPENDENCY", consumable=False),
    ]

    relaxed = read.relax_optional_review_gates_v2(_payload(stages))
    snapshot = next(item for item in relaxed["stages"] if item["stage_key"] == "source_snapshot")

    assert snapshot["validity"] == "STALE"
    assert snapshot["readiness"] == "BLOCKED_REVIEW"
    assert snapshot["consumable"] is False


def test_read_facade_rebinds_legacy_composer_to_auto_snapshot_loader(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_compose(project_id: str) -> dict:
        observed["project_id"] = project_id
        observed["loader"] = read._composer.load_project_source_drama_snapshot_v1
        return _payload([
            _stage("project_setup", 1),
            _stage("source_split", 2, validity="NOT_BUILT", readiness="READY", consumable=False),
        ])

    monkeypatch.setattr(read._composer, "get_project_flow_state_v1", fake_compose)
    result = read.get_project_flow_state_read_v1("PROJECT_1")

    assert observed["project_id"] == "PROJECT_1"
    assert observed["loader"] is load_project_source_drama_snapshot_auto_v2
    assert result["next_action"]["action_key"] == "PREPARE_REMAKE"
