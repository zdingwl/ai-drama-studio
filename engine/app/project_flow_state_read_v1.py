"""Public read facade for ProjectFlowState V1.

The first ProjectFlowState composer intentionally keeps existing target-dialogue text and
TTS facts separate. Workflow V2 defines Validity for the *stage output consumed by the next
stage*. Therefore target text without current TTS audio is not yet a complete stage output:
it is NOT_BUILT (actionable), not a BLOCKED_DEPENDENCY.

The current product rule is also fully automatic by default: an OPEN ReviewIssue is an
optional correction signal, not a consumability gate. The legacy composer still records
review counts and a few historical BLOCKED_REVIEW states, so this read facade removes only
those review-only gates while preserving technical/runtime/staleness/QC gates.

Keep this normalization side-effect free with respect to persisted business data. No model,
Task, ReviewIssue or artifact is created from GET/read paths.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from engine.app import project_flow_state_v1 as _composer
from engine.app.project_flow_state_contract_v1 import ProjectFlowStateV1
from engine.app.source_drama_snapshot_auto_v2 import load_project_source_drama_snapshot_auto_v2


def _overall_status(first: Mapping[str, Any] | None, active_command: Mapping[str, Any] | None) -> str:
    if active_command is not None:
        return "PROCESSING"
    if first is None:
        return "COMPLETE"
    if first.get("execution") in {"FAILED", "INTERRUPTED"}:
        return "FAILED"
    readiness = str(first.get("readiness") or "")
    if readiness == "BLOCKED_REVIEW":
        return "BLOCKED_REVIEW"
    if readiness == "WAITING_RUNTIME":
        return "WAITING_RUNTIME"
    if readiness == "BLOCKED_DEPENDENCY":
        return "BLOCKED_DEPENDENCY"
    return "READY_TO_CONTINUE"


def _next_action(
    first: Mapping[str, Any] | None,
    *,
    active_command: Mapping[str, Any] | None,
    episode_count: int,
) -> dict[str, Any]:
    if active_command is not None:
        return {
            "action_key": "WAIT_ACTIVE_COMMAND",
            "kind": "WAIT",
            "label": "等待当前任务完成",
            "reason": str(active_command.get("message") or active_command.get("title") or "当前后台任务正在执行"),
            "enabled": False,
            "target_surface": "PROJECT",
            "command_key": None,
        }
    if first is None:
        return {
            "action_key": "COMPLETE",
            "kind": "NONE",
            "label": "全部流程已完成",
            "reason": "所有阶段当前版本均可消费",
            "enabled": False,
            "target_surface": "OUTPUT",
            "command_key": None,
        }

    stage_key = str(first.get("stage_key") or "")
    readiness = str(first.get("readiness") or "")
    execution = str(first.get("execution") or "")
    reason = str(first.get("reason") or "当前阶段尚未完成")
    if readiness == "BLOCKED_REVIEW":
        # Compatibility only. The current public read path relaxes review-only gates before
        # reaching this function, but historical callers of normalize_project_flow_state_v1
        # may still provide an old BLOCKED_REVIEW payload.
        return {
            "action_key": "OPEN_REVIEW_CENTER",
            "kind": "NAVIGATE",
            "label": f"处理 {int(first.get('open_review_cases') or 0)} 项待确认",
            "reason": reason,
            "enabled": True,
            "target_surface": "REVIEW",
            "command_key": None,
        }
    if readiness == "WAITING_RUNTIME":
        return {
            "action_key": "WAIT_RUNTIME",
            "kind": "WAIT",
            "label": "恢复本地运行环境后重试",
            "reason": reason,
            "enabled": False,
            "target_surface": "OUTPUT" if stage_key in {"h3_generation", "postproduction_output"} else "PROJECT",
            "command_key": None,
        }
    if stage_key == "source_split" and episode_count == 0:
        return {
            "action_key": "IMPORT_EPISODES",
            "kind": "NAVIGATE",
            "label": "导入原短剧视频",
            "reason": reason,
            "enabled": True,
            "target_surface": "PROJECT",
            "command_key": None,
        }

    command_key = (
        "H3_GENERATE_READY"
        if stage_key == "h3_generation"
        else "POSTPRODUCTION"
        if stage_key == "postproduction_output"
        else "PREPARE_REMAKE"
    )
    label = {
        "PREPARE_REMAKE": "验证并继续自动准备",
        "H3_GENERATE_READY": "生成可用 H3 镜头",
        "POSTPRODUCTION": "执行后期并生成成片",
    }[command_key]
    retry = execution in {"FAILED", "INTERRUPTED"}
    return {
        "action_key": f"RETRY_{command_key}" if retry else command_key,
        "kind": "RETRY" if retry else "COMMAND",
        "label": label,
        "reason": reason,
        "enabled": readiness == "READY",
        "target_surface": "OUTPUT" if stage_key in {"h3_generation", "postproduction_output"} else "PROJECT",
        "command_key": command_key,
    }


def _optional_correction_message(count: int) -> str:
    return f"当前结果可继续；另有 {count} 项可选纠错，不影响自动流程。"


def relax_optional_review_gates_v2(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only legacy human-review gates from one composed flow-state snapshot.

    A stage is relaxed only when the legacy composer says the data itself is CURRENT and the
    sole readiness state is BLOCKED_REVIEW. Missing/stale artifacts, runtime failures,
    dependencies, H3 machine-QC/selection and postproduction output requirements are left
    untouched.
    """

    state = deepcopy(dict(payload))
    stages = [deepcopy(dict(item)) for item in state.get("stages") or [] if isinstance(item, Mapping)]
    for stage in stages:
        if stage.get("validity") != "CURRENT" or stage.get("readiness") != "BLOCKED_REVIEW":
            continue
        count = max(0, int(stage.get("open_review_cases") or 0))
        stage["readiness"] = "READY"
        stage["consumable"] = True
        stage["reason_code"] = "READY_WITH_OPTIONAL_CORRECTIONS" if count else "READY"
        stage["reason"] = _optional_correction_message(count) if count else "当前版本可继续自动流程。"
        warnings = [str(item) for item in stage.get("warnings") or [] if str(item).strip()]
        if count:
            message = _optional_correction_message(count)
            if message not in warnings:
                warnings.append(message)
        stage["warnings"] = warnings
    state["stages"] = stages

    review_summary = state.get("review_summary")
    if isinstance(review_summary, Mapping):
        summary = deepcopy(dict(review_summary))
        # OPEN items remain visible as optional corrections. They no longer count as flow
        # blockers; true blockers are represented by stage dependency/runtime/QC state.
        summary["blocking_count"] = 0
        state["review_summary"] = summary
    return state


def normalize_project_flow_state_v1(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize current composer output to the public Workflow V2 semantics."""

    state = deepcopy(dict(payload))
    stages = [deepcopy(dict(item)) for item in state.get("stages") or [] if isinstance(item, Mapping)]
    for stage in stages:
        if stage.get("stage_key") == "target_dialogue" and stage.get("reason_code") == "TARGET_AUDIO_PENDING":
            stage["validity"] = "NOT_BUILT"
            stage["readiness"] = "READY"
            stage["consumable"] = False
    state["stages"] = stages

    first = next((item for item in stages if not bool(item.get("consumable"))), None)
    active_command = state.get("active_command") if isinstance(state.get("active_command"), Mapping) else None
    episode_count = len(state.get("episodes") or [])
    state["overall_status"] = _overall_status(first, active_command)
    state["next_action"] = _next_action(first, active_command=active_command, episode_count=episode_count)
    state["can_continue"] = bool((state.get("next_action") or {}).get("enabled"))
    return ProjectFlowStateV1.model_validate(state).model_dump(mode="json")


def get_project_flow_state_read_v1(project_id: str) -> dict[str, Any]:
    # The legacy composer owns a module-local binding to the old Snapshot loader. Rebind it
    # once to the Auto V2 loader before composition so ProjectFlowState consumes the same
    # SourceDramaSnapshot semantics as the formal product routes. Assigning the same callable
    # is deterministic and does not mutate persisted data or invoke inference.
    _composer.load_project_source_drama_snapshot_v1 = load_project_source_drama_snapshot_auto_v2
    composed = _composer.get_project_flow_state_v1(project_id)
    return normalize_project_flow_state_v1(relax_optional_review_gates_v2(composed))


__all__ = [
    "get_project_flow_state_read_v1",
    "normalize_project_flow_state_v1",
    "relax_optional_review_gates_v2",
]
