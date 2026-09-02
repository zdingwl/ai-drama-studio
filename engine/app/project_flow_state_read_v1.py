"""Public read facade for ProjectFlowState V1.

The first ProjectFlowState composer intentionally keeps existing target-dialogue text and
TTS facts separate.  Workflow V2, however, defines Validity for the *stage output consumed
by the next stage*.  Therefore target text without current TTS audio is not yet a complete
stage output: it is NOT_BUILT (actionable), not a BLOCKED_DEPENDENCY.

Keep this normalization side-effect free.  It exists as a small compatibility layer while
ProjectFlowState replaces the older page-specific state models.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from engine.app.project_flow_state_contract_v1 import ProjectFlowStateV1
from engine.app.project_flow_state_v1 import get_project_flow_state_v1


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
    return normalize_project_flow_state_v1(get_project_flow_state_v1(project_id))


__all__ = ["get_project_flow_state_read_v1", "normalize_project_flow_state_v1"]
