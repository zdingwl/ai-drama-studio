"""Workflow V2 unified, read-only ProjectFlowState.

This module is a validator/read-model only.  It must never create Tasks, materialize missing
business rows, sync/close ReviewIssue, run generation, or mutate stale data.  It composes the
current persisted truth into one snapshot consumed by Project / Review Center / Output.

Persisted row counts are history/existence signals only. They may distinguish STALE from
NOT_BUILT, but must never be presented as the count of the current consumable version.
"""
from __future__ import annotations

from collections import Counter
from datetime import timezone
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import select

from engine.app.asset_workspace_v3 import AssetRevision, get_asset_workspace
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.episode_output_v1 import EpisodeOutput, compile_episode_outputs_v1
from engine.app.generation_segment_v1 import GenerationSegment, GenerationSegmentError, get_generation_segments_v1
from engine.app.generation_selection_v1 import GenerationSelection, list_generation_selections_v1
from engine.app.latentsync_provider_v1 import get_lip_sync_provider_v1
from engine.app.local_qwen_text_v1 import local_qwen_text_runtime_status
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.postproduction_v1 import get_postproduction_plan_v1
from engine.app.project_flow_state_contract_v1 import ProjectFlowStateV1
from engine.app.qwen3_tts_runtime_v1 import runtime_status as qwen3_tts_runtime_status
from engine.app.remake_timeline_v1 import RemakeTimeline, RemakeTimelineError, get_remake_timeline_v1
from engine.app.review_issue_v1 import list_review_issues
from engine.app.shot_revision_read_v2 import list_shot_revisions_read_only_v2
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError, load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Project, get_episode, get_session, list_episode_records, utcnow
from engine.app.target_dialogue_v1 import TargetDialogue, TargetDialogueError, get_target_dialogue_v1
from engine.app.target_localization_v1 import (
    SceneLocalizationMapping,
    TargetCharacter,
    TargetLocalizationError,
    get_target_localization_v1,
)
from engine.app.task_progress_v2 import ACTIVE_TASK_STATUSES, list_project_tasks


SCHEMA_VERSION = "project-flow-state-v1"

_STAGE_META = [
    ("project_setup", 1, "项目与本土化规则"),
    ("source_split", 2, "原视频与镜头"),
    ("source_understanding", 3, "原片剧情与镜头理解"),
    ("source_assets", 4, "原片人物 / 场景 / 道具"),
    ("source_snapshot", 5, "原片正式事实快照"),
    ("target_design", 6, "目标人物与场景"),
    ("target_dialogue", 7, "目标对白与声音"),
    ("remake_timing", 8, "目标时间轴与生成分段"),
    ("h3_generation", 9, "MiniMax H3 生成与选版"),
    ("postproduction_output", 10, "后期与最终成片"),
]

_ISSUE_STAGE = {
    "SHOT_BOUNDARY": "source_split",
    "CHARACTER_IDENTITY": "source_assets",
    "ASSET_BINDING": "source_assets",
    "PERSON_PRESENCE": "source_assets",
    "SPEAKER": "source_snapshot",
    "TARGET_CHARACTER": "target_design",
    "SCENE_LOCALIZATION": "target_design",
    "LOCALIZATION": "target_dialogue",
    "DIALOGUE_TIMING": "remake_timing",
    "H3_QC": "h3_generation",
    "LIP_SYNC_QC": "postproduction_output",
}

_DIRECT_TASK_STAGE = {
    "EPISODE_PREPROCESS": "source_split",
    "BATCH_PREPROCESS": "source_split",
    "EPISODE_SHOTS": "source_split",
    "BATCH_SHOTS": "source_split",
    "EPISODE_BREAKDOWN_P2": "source_understanding",
    "BATCH_BREAKDOWN_P2": "source_understanding",
    "ASSET_EXTRACTION": "source_assets",
    "ASSET_EXTRACTION_V3": "source_assets",
    "H3_GENERATE_READY_V1": "h3_generation",
    "H3_QC_RETRY_V1": "h3_generation",
    "POSTPRODUCTION_V1": "postproduction_output",
}

_PREPARE_STAGES = {
    "source_split",
    "source_understanding",
    "source_assets",
    "source_snapshot",
    "target_design",
    "target_dialogue",
    "remake_timing",
}
_OUTPUT_STAGES = {"target_design", "target_dialogue", "remake_timing", "h3_generation", "postproduction_output"}


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current_count(bundle: Mapping[str, Any] | None, key: str) -> int:
    """Return a count only from a validated current read-model bundle.

    Raw persisted table rows can include superseded revisions. A missing current bundle is
    therefore always zero current items, even when historical rows still exist.
    """

    if bundle is None:
        return 0
    try:
        return max(0, int(bundle.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _execution(status: str | None, error_message: str | None = None) -> str:
    normalized = str(status or "").upper()
    if normalized == "QUEUED":
        return "QUEUED"
    if normalized == "PROCESSING":
        return "PROCESSING"
    if normalized in {"READY", "READY_WITH_WARNINGS"}:
        return "SUCCEEDED"
    if normalized == "FAILED" and error_message == "TASK_INTERRUPTED_BY_PROCESS_RESTART":
        return "INTERRUPTED"
    if normalized in {"FAILED", "CANCELLED"}:
        return "FAILED"
    return "IDLE"


def _composite_stage(task: Mapping[str, Any]) -> str | None:
    stage = str(task.get("stage_key") or "").lower()
    if not stage:
        return None
    if any(token in stage for token in ("preprocess", "proxy", "shot", "reference")) and "snapshot" not in stage:
        return "source_split"
    if "breakdown" in stage:
        return "source_understanding"
    if "asset" in stage or "review_sync" in stage:
        return "source_assets"
    if "source_snapshot" in stage:
        return "source_snapshot"
    if "target_localization" in stage:
        return "target_design"
    if "target_dialogue" in stage or stage == "tts":
        return "target_dialogue"
    if "timing" in stage or "remake_timeline" in stage or "generation_segments" in stage:
        return "remake_timing"
    if "h3" in stage:
        return "h3_generation"
    if "postproduction" in stage or "lip_sync" in stage or "episode_output" in stage:
        return "postproduction_output"
    return None


def _task_applies(task: Mapping[str, Any], stage_key: str) -> bool:
    task_type = str(task.get("task_type") or "")
    direct = _DIRECT_TASK_STAGE.get(task_type)
    if direct is not None:
        return direct == stage_key
    terminal_success = str(task.get("status") or "") in {"READY", "READY_WITH_WARNINGS"}
    if task_type == "AUTO_REMAKE_PREP_V1":
        return stage_key in _PREPARE_STAGES if terminal_success else _composite_stage(task) == stage_key
    if task_type == "AUTO_OUTPUT_V1":
        return stage_key in _OUTPUT_STAGES if terminal_success else _composite_stage(task) == stage_key
    return False


def _command_payload(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(task.get("id") or ""),
        "task_type": str(task.get("task_type") or ""),
        "execution": _execution(str(task.get("status") or ""), str(task.get("error_message") or "") or None),
        "title": str(task.get("title") or task.get("task_type") or "后台任务"),
        "stage_key": task.get("stage_key"),
        "stage_label": task.get("stage_label"),
        "progress_mode": task.get("progress_mode"),
        "progress_percent": task.get("progress_percent"),
        "message": task.get("message"),
        "updated_at": task.get("updated_at"),
    }


def _stage_task_state(stage_key: str, tasks: list[Mapping[str, Any]]) -> tuple[str, dict[str, Any] | None, str | None]:
    relevant = [task for task in tasks if _task_applies(task, stage_key)]
    if not relevant:
        return "IDLE", None, None
    active = next((task for task in relevant if task.get("status") in ACTIVE_TASK_STATUSES), None)
    chosen = active or relevant[0]
    execution = _execution(str(chosen.get("status") or ""), str(chosen.get("error_message") or "") or None)
    command = _command_payload(chosen) if active is not None else None
    last_success = next(
        (str(task.get("completed_at")) for task in relevant if task.get("status") in {"READY", "READY_WITH_WARNINGS"} and task.get("completed_at")),
        None,
    )
    return execution, command, last_success


def _stage(
    *,
    stage_key: str,
    validity: str,
    readiness: str,
    reason_code: str,
    reason: str,
    tasks: list[Mapping[str, Any]],
    current_input_fingerprint: str | None = None,
    built_input_fingerprint: str | None = None,
    metrics: Mapping[str, Any] | None = None,
    open_review_cases: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    ordinal, label = next((ordinal, label) for key, ordinal, label in _STAGE_META if key == stage_key)
    execution, active_command, last_success = _stage_task_state(stage_key, tasks)
    return {
        "stage_key": stage_key,
        "ordinal": ordinal,
        "label": label,
        "validity": validity,
        "readiness": readiness,
        "execution": execution,
        "consumable": validity == "CURRENT" and readiness == "READY",
        "reason_code": reason_code,
        "reason": reason,
        "current_input_fingerprint": current_input_fingerprint,
        "built_input_fingerprint": built_input_fingerprint,
        "metrics": dict(metrics or {}),
        "open_review_cases": int(open_review_cases),
        "active_command": active_command,
        "warnings": list(dict.fromkeys(warnings or [])),
        "last_success": last_success,
    }


def _issue_summary(project_id: str) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    issues = list_review_issues(project_id, status="OPEN")
    by_type = Counter(str(item.get("issue_type") or "UNKNOWN") for item in issues)
    by_stage: Counter[str] = Counter()
    for item in issues:
        issue_type = str(item.get("issue_type") or "UNKNOWN")
        by_stage[_ISSUE_STAGE.get(issue_type, "source_snapshot")] += 1
    return issues, dict(by_type), dict(by_stage)


def _persisted_counts(project_id: str) -> dict[str, int]:
    with get_session() as session:
        return {
            "asset_revisions": len(list(session.scalars(select(AssetRevision).where(AssetRevision.project_id == project_id)).all())),
            "target_characters": len(list(session.scalars(select(TargetCharacter).where(TargetCharacter.project_id == project_id)).all())),
            "scene_mappings": len(list(session.scalars(select(SceneLocalizationMapping).where(SceneLocalizationMapping.project_id == project_id)).all())),
            "target_dialogues": len(list(session.scalars(select(TargetDialogue).where(TargetDialogue.project_id == project_id)).all())),
            "remake_timelines": len(list(session.scalars(select(RemakeTimeline).where(RemakeTimeline.project_id == project_id)).all())),
            "generation_segments": len(list(session.scalars(select(GenerationSegment).where(GenerationSegment.project_id == project_id)).all())),
            "generation_selections": len(list(session.scalars(select(GenerationSelection).where(GenerationSelection.project_id == project_id)).all())),
            "episode_outputs": len(list(session.scalars(select(EpisodeOutput).where(EpisodeOutput.project_id == project_id)).all())),
        }


def _runtime_item(key: str, label: str, *, ready: bool | None, reason_code: str | None, detail: str | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "checked": ready is not None,
        "ready": ready,
        "reason_code": reason_code,
        "detail": detail,
    }


def _qwen_runtime() -> dict[str, Any]:
    try:
        status = local_qwen_text_runtime_status()
        ready = bool(status.get("ready"))
        detail = str(status.get("provider") or "") or None
        return _runtime_item("qwen_text", "Qwen3-VL 文本规划", ready=ready, reason_code=None if ready else "MODEL_OFFLINE", detail=detail)
    except Exception as exc:
        return _runtime_item("qwen_text", "Qwen3-VL 文本规划", ready=False, reason_code="MODEL_OFFLINE", detail=str(exc))


def _tts_runtime() -> dict[str, Any]:
    try:
        status = qwen3_tts_runtime_status()
        ready = bool(status.get("ready"))
        detail = str(status.get("base_url") or "") or None
        return _runtime_item("qwen3_tts", "Qwen3-TTS", ready=ready, reason_code=None if ready else "TTS_OFFLINE", detail=detail)
    except Exception as exc:
        return _runtime_item("qwen3_tts", "Qwen3-TTS", ready=False, reason_code="TTS_OFFLINE", detail=str(exc))


def _h3_runtime(plan: Mapping[str, Any]) -> dict[str, Any]:
    required = {"FL2VA"}
    if any(
        isinstance(segment, Mapping) and segment.get("status") == "READY" and segment.get("generation_mode") == "REF2VA"
        for episode in plan.get("episodes") or []
        if isinstance(episode, Mapping)
        for segment in episode.get("segments") or []
    ):
        required.add("REF2VA")
    try:
        status = get_video_generation_provider_v1("MINIMAX_H3_LOCAL").status()
        missing: list[str] = []
        if "FL2VA" in required and not bool((status.get("fl2va") or {}).get("ready")):
            missing.append("FL2VA")
        if "REF2VA" in required and not bool((status.get("ref2va") or {}).get("ready")):
            missing.append("REF2VA")
        ready = not missing
        return _runtime_item(
            "minimax_h3",
            "MiniMax H3",
            ready=ready,
            reason_code=None if ready else "H3_OFFLINE",
            detail=None if ready else " / ".join(missing),
        )
    except Exception as exc:
        return _runtime_item("minimax_h3", "MiniMax H3", ready=False, reason_code="H3_OFFLINE", detail=str(exc))


def _lip_sync_runtime() -> dict[str, Any]:
    try:
        status = get_lip_sync_provider_v1().status()
        ready = bool(status.get("ready"))
        return _runtime_item("latentsync", "LatentSync", ready=ready, reason_code=None if ready else "LIPSYNC_OFFLINE")
    except Exception as exc:
        return _runtime_item("latentsync", "LatentSync", ready=False, reason_code="LIPSYNC_OFFLINE", detail=str(exc))


def _first_active_command(tasks: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    active = next((task for task in tasks if task.get("status") in ACTIVE_TASK_STATUSES), None)
    return _command_payload(active) if active is not None else None


def _next_action(first: Mapping[str, Any] | None, *, active_command: Mapping[str, Any] | None, episode_count: int) -> dict[str, Any]:
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

    stage_key = str(first["stage_key"])
    readiness = str(first["readiness"])
    execution = str(first["execution"])
    reason = str(first["reason"])
    if readiness == "BLOCKED_REVIEW":
        return {
            "action_key": "OPEN_REVIEW_CENTER",
            "kind": "NAVIGATE",
            "label": f"处理 {first.get('open_review_cases', 0)} 项待确认",
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
            "target_surface": "PROJECT" if stage_key not in {"h3_generation", "postproduction_output"} else "OUTPUT",
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
    return {
        "action_key": f"RETRY_{command_key}" if execution in {"FAILED", "INTERRUPTED"} else command_key,
        "kind": "RETRY" if execution in {"FAILED", "INTERRUPTED"} else "COMMAND",
        "label": label,
        "reason": reason,
        "enabled": readiness == "READY",
        "target_surface": "OUTPUT" if stage_key in {"h3_generation", "postproduction_output"} else "PROJECT",
        "command_key": command_key,
    }


def get_project_flow_state_v1(project_id: str) -> dict[str, Any]:
    """Compose one side-effect-free Workflow V2 state snapshot for a Project."""

    with get_session() as session:
        project_row = session.get(Project, project_id)
        if project_row is None:
            raise LookupError("项目不存在")
        project = {
            "id": project_row.id,
            "name": project_row.name,
            "source_language": project_row.source_language,
            "target_language": project_row.target_language,
            "target_region": project_row.target_region,
        }

    tasks = [dict(item) for item in list_project_tasks(project_id, limit=100)]
    open_issues, issues_by_type, issues_by_stage = _issue_summary(project_id)
    persisted = _persisted_counts(project_id)
    active_command = _first_active_command(tasks)
    runtime_items: list[dict[str, Any]] = []

    episode_states: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    breakdown_rows: list[dict[str, Any]] = []
    for episode in list_episode_records(project_id):
        episode_payload = get_episode(episode.id) or {}
        revisions = list_shot_revisions_read_only_v2(episode.id)
        current_revision = next((item for item in revisions if item.get("is_current")), None)
        breakdown = get_current_breakdown(episode.id)
        run_meta = (breakdown.get("run") or {}) if isinstance(breakdown, Mapping) else {}
        current_breakdown_id = str(run_meta.get("id") or "") or None
        shot_count = int(episode_payload.get("shot_count") or 0)
        split_rows.append({
            "episode_id": episode.id,
            "shot_count": shot_count,
            "current_revision_id": current_revision.get("id") if current_revision else None,
            "current_revision_number": current_revision.get("revision") if current_revision else None,
        })
        if current_breakdown_id:
            breakdown_rows.append({
                "episode_id": episode.id,
                "run_id": current_breakdown_id,
                "source_shot_revision_id": run_meta.get("source_shot_revision_id"),
            })
        episode_states.append({
            "episode_id": episode.id,
            "sort_order": int(episode.sort_order),
            "title": episode.title,
            "preprocess_status": episode_payload.get("preprocess_status"),
            "shot_count": shot_count,
            "current_shot_revision_id": current_revision.get("id") if current_revision else None,
            "current_breakdown_run_id": current_breakdown_id,
        })

    episode_count = len(episode_states)
    project_fp = _digest(project)
    split_fp = _digest(split_rows) if split_rows else None
    breakdown_fp = _digest(breakdown_rows) if breakdown_rows else None

    stages: list[dict[str, Any]] = []
    stages.append(_stage(
        stage_key="project_setup",
        validity="CURRENT",
        readiness="READY",
        reason_code="PROJECT_READY",
        reason="项目名称、原语言、目标语言和目标地区已建立",
        tasks=tasks,
        current_input_fingerprint=project_fp,
        built_input_fingerprint=project_fp,
        metrics={
            "source_language": project["source_language"],
            "target_language": project["target_language"],
            "target_region": project["target_region"],
        },
    ))

    split_review_count = int(issues_by_stage.get("source_split", 0))
    all_have_shots = episode_count > 0 and all(item["shot_count"] > 0 for item in split_rows)
    all_have_current_revision = all_have_shots and all(item["current_revision_id"] for item in split_rows)
    if episode_count == 0:
        split_validity, split_readiness = "NOT_BUILT", "READY"
        split_code, split_reason = "NO_EPISODES", "项目还没有导入原短剧视频"
    elif not all_have_shots:
        split_validity, split_readiness = "NOT_BUILT", "READY"
        split_code, split_reason = "SHOTS_NOT_BUILT", "部分剧集还没有形成当前 Shot / Reference Clip"
    elif not all_have_current_revision:
        split_validity, split_readiness = "STALE", "READY"
        split_code, split_reason = "SHOT_REVISION_MISSING", "已有 Shot，但部分旧项目尚未形成 Current ShotRevision，需要显式准备后再继续"
    elif split_review_count:
        split_validity, split_readiness = "CURRENT", "BLOCKED_REVIEW"
        split_code, split_reason = "SHOT_REVIEW_REQUIRED", f"有 {split_review_count} 个镜头边界问题需要确认"
    else:
        split_validity, split_readiness = "CURRENT", "READY"
        split_code, split_reason = "SHOTS_CURRENT", "全部剧集已有当前 Shot 和 Reference Clip"
    stages.append(_stage(
        stage_key="source_split",
        validity=split_validity,
        readiness=split_readiness,
        reason_code=split_code,
        reason=split_reason,
        tasks=tasks,
        current_input_fingerprint=project_fp,
        built_input_fingerprint=split_fp,
        metrics={"episode_count": episode_count, "shot_count": sum(item["shot_count"] for item in split_rows)},
        open_review_cases=split_review_count,
    ))

    split_consumable = stages[-1]["consumable"]
    understanding_review_count = int(issues_by_stage.get("source_understanding", 0))
    if not split_consumable:
        understanding_validity = "CURRENT" if len(breakdown_rows) == episode_count and episode_count > 0 else "NOT_BUILT"
        understanding_readiness = "BLOCKED_DEPENDENCY"
        understanding_code, understanding_reason = "WAITING_CURRENT_SHOTS", "原片理解被当前 Shot / 镜头确认状态阻塞"
    elif len(breakdown_rows) != episode_count:
        understanding_validity, understanding_readiness = "NOT_BUILT", "READY"
        understanding_code, understanding_reason = "BREAKDOWN_NOT_BUILT", "部分剧集还没有当前结构化原片理解结果"
    elif understanding_review_count:
        understanding_validity, understanding_readiness = "CURRENT", "BLOCKED_REVIEW"
        understanding_code, understanding_reason = "BREAKDOWN_REVIEW_REQUIRED", f"原片理解有 {understanding_review_count} 项需要确认"
    else:
        understanding_validity, understanding_readiness = "CURRENT", "READY"
        understanding_code, understanding_reason = "BREAKDOWN_CURRENT", "全部剧集的当前结构化原片理解已就绪"
    stages.append(_stage(
        stage_key="source_understanding",
        validity=understanding_validity,
        readiness=understanding_readiness,
        reason_code=understanding_code,
        reason=understanding_reason,
        tasks=tasks,
        current_input_fingerprint=split_fp,
        built_input_fingerprint=breakdown_fp,
        metrics={"episode_count": episode_count, "current_breakdown_count": len(breakdown_rows)},
        open_review_cases=understanding_review_count,
    ))

    asset_review_count = int(issues_by_stage.get("source_assets", 0))
    try:
        workspace = get_asset_workspace(project_id, auto_bootstrap=False)
    except Exception:
        workspace = {"status": "EMPTY", "stale": False, "revision": None, "characters": [], "scenes": [], "props": []}
    asset_revision = workspace.get("revision") if isinstance(workspace.get("revision"), Mapping) else None
    asset_fp = _digest({
        "revision_id": asset_revision.get("id") if asset_revision else None,
        "source_run_id": asset_revision.get("source_run_id") if asset_revision else None,
    }) if asset_revision else None
    if not stages[-1]["consumable"]:
        asset_validity = "STALE" if workspace.get("stale") and asset_revision else "CURRENT" if asset_revision else "NOT_BUILT"
        asset_readiness = "BLOCKED_DEPENDENCY"
        asset_code, asset_reason = "WAITING_SOURCE_UNDERSTANDING", "人物 / 场景 / 道具正式资产被原片理解状态阻塞"
    elif workspace.get("stale"):
        asset_validity, asset_readiness = "STALE", "READY"
        asset_code, asset_reason = "ASSET_REVISION_STALE", "已有资产版本基于旧的原片/AI Evidence，需要显式重新计算或采用新 Evidence"
    elif not asset_revision:
        asset_validity, asset_readiness = "NOT_BUILT", "READY"
        asset_code, asset_reason = "ASSET_REVISION_NOT_BUILT", "尚未形成当前 Final Character / Scene / Prop 资产版本"
    elif asset_review_count:
        asset_validity, asset_readiness = "CURRENT", "BLOCKED_REVIEW"
        asset_code, asset_reason = "ASSET_REVIEW_REQUIRED", f"人物 / 场景 / 道具还有 {asset_review_count} 项需要确认"
    else:
        asset_validity, asset_readiness = "CURRENT", "READY"
        asset_code, asset_reason = "ASSET_REVISION_CURRENT", "当前 Final Character / Scene / Prop 与 Shot Binding 已就绪"
    stages.append(_stage(
        stage_key="source_assets",
        validity=asset_validity,
        readiness=asset_readiness,
        reason_code=asset_code,
        reason=asset_reason,
        tasks=tasks,
        current_input_fingerprint=breakdown_fp,
        built_input_fingerprint=asset_fp,
        metrics={
            "character_count": len(workspace.get("characters") or []),
            "scene_count": len(workspace.get("scenes") or []),
            "prop_count": len(workspace.get("props") or []),
            "revision_count": persisted["asset_revisions"],
        },
        open_review_cases=asset_review_count,
    ))

    source_snapshot: dict[str, Any] | None = None
    source_snapshot_error: Exception | None = None
    try:
        source_snapshot = load_project_source_drama_snapshot_v1(project_id)
    except Exception as exc:
        source_snapshot_error = exc
    source_review_count = int(issues_by_stage.get("source_snapshot", 0))
    if not stages[-1]["consumable"]:
        snapshot_validity = "CURRENT" if source_snapshot is not None else "NOT_BUILT"
        snapshot_readiness = "BLOCKED_DEPENDENCY"
        snapshot_code, snapshot_reason = "WAITING_SOURCE_ASSETS", "SourceDramaSnapshot 被源人物 / 场景 / 道具确认状态阻塞"
    elif source_snapshot is None:
        snapshot_validity, snapshot_readiness = "NOT_BUILT", "READY"
        snapshot_code = "SOURCE_SNAPSHOT_UNAVAILABLE"
        snapshot_reason = str(source_snapshot_error or "当前 SourceDramaSnapshot 尚不可用")
    elif source_review_count:
        snapshot_validity, snapshot_readiness = "CURRENT", "BLOCKED_REVIEW"
        snapshot_code, snapshot_reason = "SOURCE_FACT_REVIEW_REQUIRED", f"原片正式事实还有 {source_review_count} 项需要确认"
    else:
        snapshot_validity, snapshot_readiness = "CURRENT", "READY"
        snapshot_code, snapshot_reason = "SOURCE_SNAPSHOT_CURRENT", "SourceDramaSnapshot 已成为当前下游唯一原片事实"
    source_fp = str(source_snapshot.get("source_fingerprint") or "") if source_snapshot else None
    stages.append(_stage(
        stage_key="source_snapshot",
        validity=snapshot_validity,
        readiness=snapshot_readiness,
        reason_code=snapshot_code,
        reason=snapshot_reason,
        tasks=tasks,
        current_input_fingerprint=asset_fp,
        built_input_fingerprint=source_fp,
        metrics={
            "episode_count": int(source_snapshot.get("episode_count") or 0) if source_snapshot else 0,
            "scene_count": int(source_snapshot.get("scene_count") or 0) if source_snapshot else 0,
            "shot_count": int(source_snapshot.get("shot_count") or 0) if source_snapshot else 0,
            "source_dialogue_count": int(source_snapshot.get("source_dialogue_count") or 0) if source_snapshot else 0,
            "resolved_character_count": int(source_snapshot.get("resolved_character_count") or 0) if source_snapshot else 0,
        },
        open_review_cases=source_review_count,
        warnings=list(source_snapshot.get("warnings") or []) if source_snapshot else [],
    ))

    target_bundle: dict[str, Any] | None = None
    target_error: Exception | None = None
    try:
        target_bundle = get_target_localization_v1(project_id)
    except Exception as exc:
        target_error = exc
    target_review_count = int(issues_by_stage.get("target_design", 0))
    target_rows_exist = persisted["target_characters"] > 0 or persisted["scene_mappings"] > 0
    if not stages[-1]["consumable"]:
        target_validity = "CURRENT" if target_bundle is not None else "STALE" if target_rows_exist else "NOT_BUILT"
        target_readiness = "BLOCKED_DEPENDENCY"
        target_code, target_reason = "WAITING_SOURCE_SNAPSHOT", "目标人物 / 场景被原片正式事实或上游待确认项阻塞"
    elif target_bundle is None:
        target_validity = "STALE" if target_rows_exist else "NOT_BUILT"
        runtime = _qwen_runtime(); runtime_items.append(runtime)
        if runtime["ready"] is False:
            target_readiness = "WAITING_RUNTIME"
            target_code, target_reason = "MODEL_OFFLINE", "目标人物 / 场景需要重新生成，但 Qwen3-VL 文本规划 Runtime 当前不可用"
        else:
            target_readiness = "READY"
            target_code = "TARGET_DESIGN_STALE" if target_rows_exist else "TARGET_DESIGN_NOT_BUILT"
            target_reason = str(target_error or "目标人物 / 场景方案尚未生成")
    elif target_review_count or int(target_bundle.get("review_count") or 0) > 0:
        target_validity, target_readiness = "CURRENT", "BLOCKED_REVIEW"
        count = max(target_review_count, int(target_bundle.get("review_count") or 0))
        target_code, target_reason = "TARGET_DESIGN_REVIEW_REQUIRED", f"目标人物 / 场景有 {count} 项需要确认"
    else:
        target_validity, target_readiness = "CURRENT", "READY"
        target_code, target_reason = "TARGET_DESIGN_CURRENT", "目标人物和场景 KEEP / LOCALIZE 方案已就绪"
    target_fp = _digest({
        "source_fingerprint": target_bundle.get("source_fingerprint") if target_bundle else None,
        "target_characters": target_bundle.get("target_characters") if target_bundle else [],
        "scene_mappings": target_bundle.get("scene_mappings") if target_bundle else [],
    }) if target_bundle else None
    stages.append(_stage(
        stage_key="target_design",
        validity=target_validity,
        readiness=target_readiness,
        reason_code=target_code,
        reason=target_reason,
        tasks=tasks,
        current_input_fingerprint=source_fp,
        built_input_fingerprint=target_fp,
        metrics={
            "target_character_count": _current_count(target_bundle, "target_character_count"),
            "scene_mapping_count": _current_count(target_bundle, "scene_mapping_count"),
        },
        open_review_cases=max(target_review_count, int(target_bundle.get("review_count") or 0) if target_bundle else 0),
    ))

    dialogue_bundle: dict[str, Any] | None = None
    dialogue_error: Exception | None = None
    try:
        dialogue_bundle = get_target_dialogue_v1(project_id)
    except Exception as exc:
        dialogue_error = exc
    dialogue_review_count = int(issues_by_stage.get("target_dialogue", 0))
    dialogue_rows_exist = persisted["target_dialogues"] > 0
    if not stages[-1]["consumable"]:
        dialogue_validity = "CURRENT" if dialogue_bundle is not None else "STALE" if dialogue_rows_exist else "NOT_BUILT"
        dialogue_readiness = "BLOCKED_DEPENDENCY"
        dialogue_code, dialogue_reason = "WAITING_TARGET_DESIGN", "目标对白和声音被目标人物 / 场景状态阻塞"
    elif dialogue_bundle is None:
        dialogue_validity = "STALE" if dialogue_rows_exist else "NOT_BUILT"
        runtime = _qwen_runtime(); runtime_items.append(runtime)
        if runtime["ready"] is False:
            dialogue_readiness = "WAITING_RUNTIME"
            dialogue_code, dialogue_reason = "MODEL_OFFLINE", "目标对白需要生成或重算，但 Qwen3-VL 文本规划 Runtime 当前不可用"
        else:
            dialogue_readiness = "READY"
            dialogue_code = "TARGET_DIALOGUE_STALE" if dialogue_rows_exist else "TARGET_DIALOGUE_NOT_BUILT"
            dialogue_reason = str(dialogue_error or "目标对白尚未生成")
    elif dialogue_review_count or int(dialogue_bundle.get("review_count") or 0) > 0:
        dialogue_validity, dialogue_readiness = "CURRENT", "BLOCKED_REVIEW"
        count = max(dialogue_review_count, int(dialogue_bundle.get("review_count") or 0))
        dialogue_code, dialogue_reason = "TARGET_DIALOGUE_REVIEW_REQUIRED", f"目标对白有 {count} 项需要确认"
    else:
        dialogue_count = _current_count(dialogue_bundle, "dialogue_count")
        audio_ready_count = _current_count(dialogue_bundle, "audio_ready_count")
        if audio_ready_count < dialogue_count:
            runtime = _tts_runtime(); runtime_items.append(runtime)
            dialogue_validity = "CURRENT"
            if runtime["ready"] is False:
                dialogue_readiness = "WAITING_RUNTIME"
                dialogue_code, dialogue_reason = "TTS_OFFLINE", f"目标文本已就绪，但 Qwen3-TTS 当前不可用（{audio_ready_count}/{dialogue_count} 条音频 READY）"
            else:
                dialogue_readiness = "BLOCKED_DEPENDENCY"
                dialogue_code, dialogue_reason = "TARGET_AUDIO_PENDING", f"目标文本已就绪，仍需显式生成目标语音（{audio_ready_count}/{dialogue_count}）"
        else:
            dialogue_validity, dialogue_readiness = "CURRENT", "READY"
            dialogue_code, dialogue_reason = "TARGET_DIALOGUE_AUDIO_CURRENT", "目标对白、角色声音和真实 TTS 时长已就绪"
    dialogue_fp = _digest({
        "source_fingerprint": dialogue_bundle.get("source_fingerprint") if dialogue_bundle else None,
        "dialogues": dialogue_bundle.get("dialogues") if dialogue_bundle else [],
        "voices": dialogue_bundle.get("voice_profiles") if dialogue_bundle else [],
    }) if dialogue_bundle else None
    stages.append(_stage(
        stage_key="target_dialogue",
        validity=dialogue_validity,
        readiness=dialogue_readiness,
        reason_code=dialogue_code,
        reason=dialogue_reason,
        tasks=tasks,
        current_input_fingerprint=target_fp,
        built_input_fingerprint=dialogue_fp,
        metrics={
            "dialogue_count": _current_count(dialogue_bundle, "dialogue_count"),
            "audio_ready_count": _current_count(dialogue_bundle, "audio_ready_count"),
            "voice_profile_count": _current_count(dialogue_bundle, "voice_profile_count"),
        },
        open_review_cases=max(dialogue_review_count, int(dialogue_bundle.get("review_count") or 0) if dialogue_bundle else 0),
    ))

    timeline: dict[str, Any] | None = None
    timeline_error: Exception | None = None
    try:
        timeline = get_remake_timeline_v1(project_id)
    except Exception as exc:
        timeline_error = exc
    timing_review_count = int(issues_by_stage.get("remake_timing", 0))
    timeline_rows_exist = persisted["remake_timelines"] > 0
    generation_plan: dict[str, Any] | None = None
    generation_error: Exception | None = None
    if stages[-1]["consumable"]:
        try:
            generation_plan = get_generation_segments_v1(project_id)
        except Exception as exc:
            generation_error = exc
    if not stages[-1]["consumable"]:
        timing_validity = "CURRENT" if timeline is not None else "STALE" if timeline_rows_exist else "NOT_BUILT"
        timing_readiness = "BLOCKED_DEPENDENCY"
        timing_code, timing_reason = "WAITING_TARGET_DIALOGUE", "目标时间轴被目标对白 / TTS 状态阻塞"
    elif timeline is None:
        timing_validity = "STALE" if timeline_rows_exist else "NOT_BUILT"
        timing_readiness = "READY"
        timing_code = "REMAKE_TIMELINE_STALE" if timeline_rows_exist else "REMAKE_TIMELINE_NOT_BUILT"
        timing_reason = str(timeline_error or "RemakeTimeline 尚未生成")
    elif timing_review_count or int(timeline.get("review_count") or 0) > 0:
        timing_validity, timing_readiness = "CURRENT", "BLOCKED_REVIEW"
        count = max(timing_review_count, int(timeline.get("review_count") or 0))
        timing_code, timing_reason = "DIALOGUE_TIMING_REVIEW_REQUIRED", f"有 {count} 个极端镜头时长需要人工确认"
    elif int(timeline.get("waiting_audio_count") or 0) > 0:
        timing_validity, timing_readiness = "CURRENT", "BLOCKED_DEPENDENCY"
        timing_code, timing_reason = "TIMELINE_WAITING_AUDIO", "RemakeTimeline 仍在等待真实目标语音时长"
    elif generation_plan is None:
        timing_validity = "STALE" if persisted["generation_segments"] > 0 else "NOT_BUILT"
        timing_readiness = "READY"
        timing_code = "GENERATION_SEGMENTS_STALE" if persisted["generation_segments"] > 0 else "GENERATION_SEGMENTS_NOT_BUILT"
        timing_reason = str(generation_error or "GenerationSegment 尚未编译")
    elif int(generation_plan.get("review_count") or 0) > 0:
        timing_validity, timing_readiness = "CURRENT", "BLOCKED_REVIEW"
        timing_code, timing_reason = "GENERATION_SEGMENT_REVIEW_REQUIRED", f"有 {generation_plan.get('review_count')} 个 GenerationSegment 需要确认"
    elif int(generation_plan.get("waiting_audio_count") or 0) > 0:
        timing_validity, timing_readiness = "CURRENT", "BLOCKED_DEPENDENCY"
        timing_code, timing_reason = "GENERATION_SEGMENT_WAITING_AUDIO", "GenerationSegment 仍在等待真实目标语音"
    else:
        timing_validity, timing_readiness = "CURRENT", "READY"
        timing_code, timing_reason = "GENERATION_SEGMENTS_CURRENT", "RemakeTimeline 与 H3 GenerationSegment 已按当前真实 TTS 时长编译完成"
    timing_fp = _digest({
        "timeline_source": timeline.get("source_fingerprint") if timeline else None,
        "dialogue": timeline.get("target_dialogue_fingerprint") if timeline else None,
        "segments": [
            {
                "id": segment.get("id"),
                "input_fingerprint": segment.get("input_fingerprint"),
                "status": segment.get("status"),
            }
            for episode in (generation_plan or {}).get("episodes") or []
            if isinstance(episode, Mapping)
            for segment in episode.get("segments") or []
            if isinstance(segment, Mapping)
        ],
    }) if timeline or generation_plan else None
    segment_count = _current_count(generation_plan, "segment_count")
    stages.append(_stage(
        stage_key="remake_timing",
        validity=timing_validity,
        readiness=timing_readiness,
        reason_code=timing_code,
        reason=timing_reason,
        tasks=tasks,
        current_input_fingerprint=dialogue_fp,
        built_input_fingerprint=timing_fp,
        metrics={
            "timeline_episode_count": _current_count(timeline, "episode_count"),
            "generation_segment_count": segment_count,
            "waiting_audio_count": _current_count(generation_plan or timeline, "waiting_audio_count"),
        },
        open_review_cases=max(timing_review_count, int((generation_plan or timeline or {}).get("review_count") or 0)),
    ))

    h3_review_count = int(issues_by_stage.get("h3_generation", 0))
    current_selections: list[dict[str, Any]] = []
    ready_segments: list[Mapping[str, Any]] = []
    if generation_plan is not None:
        ready_segments = [
            segment
            for episode in generation_plan.get("episodes") or []
            if isinstance(episode, Mapping)
            for segment in episode.get("segments") or []
            if isinstance(segment, Mapping) and segment.get("status") == "READY"
        ]
        try:
            current_selections = list_generation_selections_v1(project_id)
        except Exception:
            current_selections = []
    selected_ids = {str(item.get("generation_segment_id") or "") for item in current_selections}
    ready_ids = {str(item.get("id") or "") for item in ready_segments}
    selected_ready_count = len(selected_ids & ready_ids)
    if not stages[-1]["consumable"]:
        h3_validity = "CURRENT" if ready_ids and selected_ready_count == len(ready_ids) else "STALE" if persisted["generation_selections"] else "NOT_BUILT"
        h3_readiness = "BLOCKED_DEPENDENCY"
        h3_code, h3_reason = "WAITING_GENERATION_SEGMENTS", "H3 被目标时间轴 / GenerationSegment 状态阻塞"
    elif h3_review_count:
        h3_validity = "CURRENT" if ready_ids and selected_ready_count == len(ready_ids) else "NOT_BUILT"
        h3_readiness = "BLOCKED_REVIEW"
        h3_code, h3_reason = "H3_QC_REVIEW_REQUIRED", f"H3 质检仍有 {h3_review_count} 项需要人工确认"
    elif ready_ids and selected_ready_count == len(ready_ids):
        h3_validity, h3_readiness = "CURRENT", "READY"
        h3_code, h3_reason = "H3_SELECTIONS_CURRENT", "每个当前 GenerationSegment 都已有可用 GenerationSelection"
    else:
        h3_validity = "STALE" if persisted["generation_selections"] > selected_ready_count else "NOT_BUILT"
        runtime = _h3_runtime(generation_plan or {}); runtime_items.append(runtime)
        if runtime["ready"] is False:
            h3_readiness = "WAITING_RUNTIME"
            h3_code, h3_reason = "H3_OFFLINE", f"仍有 {max(0, len(ready_ids) - selected_ready_count)} 个 GenerationSegment 没有当前选版，MiniMax H3 Runtime 未就绪"
        else:
            h3_readiness = "READY"
            h3_code = "H3_SELECTION_STALE" if h3_validity == "STALE" else "H3_NOT_BUILT"
            h3_reason = f"仍有 {max(0, len(ready_ids) - selected_ready_count)} 个 GenerationSegment 需要显式 H3 生成 / QC / Selection"
    h3_fp = _digest(sorted(
        (str(item.get("generation_segment_id") or ""), str(item.get("segment_input_fingerprint") or ""), str(item.get("selected_attempt_id") or ""))
        for item in current_selections
    )) if current_selections else None
    stages.append(_stage(
        stage_key="h3_generation",
        validity=h3_validity,
        readiness=h3_readiness,
        reason_code=h3_code,
        reason=h3_reason,
        tasks=tasks,
        current_input_fingerprint=timing_fp,
        built_input_fingerprint=h3_fp,
        metrics={
            "generation_segment_count": len(ready_ids),
            "selected_segment_count": selected_ready_count,
            "persisted_selection_count": persisted["generation_selections"],
        },
        open_review_cases=h3_review_count,
    ))

    post_review_count = int(issues_by_stage.get("postproduction_output", 0))
    post_plan: dict[str, Any] | None = None
    output_plan: dict[str, Any] | None = None
    if stages[-1]["consumable"]:
        try:
            post_plan = get_postproduction_plan_v1(project_id)
            output_plan = compile_episode_outputs_v1(project_id, persist=False)
        except Exception:
            post_plan = None
            output_plan = None
    output_episodes = [item for item in (output_plan or {}).get("episodes") or [] if isinstance(item, Mapping)]
    completed_episodes = [item for item in output_episodes if item.get("status") == "SUCCEEDED"]
    if not stages[-1]["consumable"]:
        output_validity = "STALE" if persisted["episode_outputs"] else "NOT_BUILT"
        output_readiness = "BLOCKED_DEPENDENCY"
        output_code, output_reason = "WAITING_H3_SELECTION", "后期与最终成片被当前 H3 GenerationSelection 阻塞"
    elif post_review_count or int((post_plan or {}).get("review_count") or 0) > 0:
        output_validity = "STALE" if persisted["episode_outputs"] else "NOT_BUILT"
        output_readiness = "BLOCKED_REVIEW"
        count = max(post_review_count, int((post_plan or {}).get("review_count") or 0))
        output_code, output_reason = "LIP_SYNC_REVIEW_REQUIRED", f"后期还有 {count} 项口型 / 多脸定位需要确认"
    elif episode_count > 0 and len(completed_episodes) == episode_count:
        output_validity, output_readiness = "CURRENT", "READY"
        output_code, output_reason = "EPISODE_OUTPUT_CURRENT", "全部 Episode 都已有当前成功成片和字幕"
    else:
        output_validity = "STALE" if persisted["episode_outputs"] > len(completed_episodes) else "NOT_BUILT"
        ready_post = [
            segment
            for episode in (post_plan or {}).get("episodes") or []
            if isinstance(episode, Mapping)
            for segment in episode.get("segments") or []
            if isinstance(segment, Mapping) and segment.get("status") == "READY"
        ]
        needs_lip_sync = any(
            item.get("lip_sync_mode") in {"LATENTSYNC_FULL_SEGMENT", "LATENTSYNC_TARGET_FACE_ROI"}
            for item in ready_post
        )
        if needs_lip_sync:
            runtime = _lip_sync_runtime(); runtime_items.append(runtime)
        else:
            runtime = None
        if runtime is not None and runtime["ready"] is False:
            output_readiness = "WAITING_RUNTIME"
            output_code, output_reason = "LIPSYNC_OFFLINE", "当前后期计划包含可见对白口型，但 LatentSync Runtime 未就绪"
        else:
            output_readiness = "READY"
            output_code = "EPISODE_OUTPUT_STALE" if output_validity == "STALE" else "POSTPRODUCTION_NOT_BUILT"
            output_reason = f"当前已有 {len(completed_episodes)}/{episode_count} 集成功成片，需要显式执行后期 / 整集拼接"
    output_fp = _digest([
        (item.get("episode_id"), item.get("input_fingerprint"), item.get("status"), item.get("output_path"))
        for item in output_episodes
    ]) if output_episodes else None
    stages.append(_stage(
        stage_key="postproduction_output",
        validity=output_validity,
        readiness=output_readiness,
        reason_code=output_code,
        reason=output_reason,
        tasks=tasks,
        current_input_fingerprint=h3_fp,
        built_input_fingerprint=output_fp,
        metrics={
            "postproduction_segment_count": _current_count(post_plan, "segment_count"),
            "completed_episode_count": len(completed_episodes),
            "episode_count": episode_count,
            "persisted_episode_output_count": persisted["episode_outputs"],
        },
        open_review_cases=max(post_review_count, int((post_plan or {}).get("review_count") or 0)),
    ))

    first_non_consumable = next((item for item in stages if not item["consumable"]), None)
    if active_command is not None:
        overall_status = "PROCESSING"
    elif first_non_consumable is None:
        overall_status = "COMPLETE"
    elif first_non_consumable["execution"] in {"FAILED", "INTERRUPTED"}:
        overall_status = "FAILED"
    elif first_non_consumable["readiness"] == "BLOCKED_REVIEW":
        overall_status = "BLOCKED_REVIEW"
    elif first_non_consumable["readiness"] == "WAITING_RUNTIME":
        overall_status = "WAITING_RUNTIME"
    elif first_non_consumable["readiness"] == "BLOCKED_DEPENDENCY":
        overall_status = "BLOCKED_DEPENDENCY"
    else:
        overall_status = "READY_TO_CONTINUE"

    action = _next_action(first_non_consumable, active_command=active_command, episode_count=episode_count)
    runtime_unique: dict[str, dict[str, Any]] = {}
    for item in runtime_items:
        runtime_unique[item["key"]] = item
    runtime_values = list(runtime_unique.values())
    review_summary = {
        "open_count": len(open_issues),
        "blocking_count": sum(str(item.get("severity") or "").upper() == "BLOCKING" for item in open_issues),
        "by_type": issues_by_type,
    }
    runtime_summary = {
        "blocking_runtime_count": sum(item.get("checked") and item.get("ready") is False for item in runtime_values),
        "items": runtime_values,
    }

    revision = _digest({
        "project": project,
        "episodes": episode_states,
        "stages": [
            {
                "stage_key": item["stage_key"],
                "validity": item["validity"],
                "readiness": item["readiness"],
                "execution": item["execution"],
                "reason_code": item["reason_code"],
                "current_input_fingerprint": item["current_input_fingerprint"],
                "built_input_fingerprint": item["built_input_fingerprint"],
                "open_review_cases": item["open_review_cases"],
                "metrics": item["metrics"],
            }
            for item in stages
        ],
        "open_review_ids": sorted(str(item.get("id") or "") for item in open_issues),
        "active_command": active_command,
        "runtime": [
            {"key": item["key"], "checked": item["checked"], "ready": item["ready"], "reason_code": item["reason_code"]}
            for item in runtime_values
        ],
    })
    now = utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "revision": revision,
        "generated_at": now.isoformat(),
        "overall_status": overall_status,
        "can_continue": bool(action.get("enabled")),
        "next_action": action,
        "active_command": active_command,
        "review_summary": review_summary,
        "runtime_summary": runtime_summary,
        "episodes": episode_states,
        "stages": stages,
    }
    return ProjectFlowStateV1.model_validate(payload).model_dump(mode="json")


__all__ = ["SCHEMA_VERSION", "get_project_flow_state_v1"]
