"""模块 3：只生成动作与表演建议；只有明确采用才写人工修订。"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from engine.app import breakdown_shot_rerun_v1 as rerun
from engine.app import breakdown_manual_override_v1 as manual
from engine.app.breakdown_scene_timeline_result_v1 import build_scene_timeline_result_v1
from engine.app.project_flow_state_v1 import get_project_flow_state_v1
from engine.app.task_progress_v2 import start_task, finish_task, fail_task

TASK_TYPE = "SHOT_PERFORMANCE_SUGGESTION"
FIELDS = ("performance_text", "expression", "posture", "gaze", "interaction")
_UNKNOWN = re.compile(r"^(未知|不明|不确定|无法判断|无法确认|看不清|待补充|待确认|暂无.*|unknown|unclear|n/?a|[-—]+)$", re.I)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def current_input(episode_id: str, ordinal: int) -> tuple[dict, dict, dict]:
    draft = rerun.get_current_breakdown(episode_id)
    if not draft:
        raise ValueError("请先完成本集拉片")
    run_id, project_id, _, revision_id = rerun._anchors(draft)
    timeline = build_scene_timeline_result_v1(draft)
    _, shot = rerun._timeline_scene_and_shot(timeline, ordinal)
    before = {"performance_text": "；".join(row["text"] for row in shot.get("performance", []))}
    before.update({key: (shot.get("performance_details") or {}).get(key) or "" for key in FIELDS[1:]})
    anchor = {"run_id": run_id, "revision_id": revision_id, "shot": shot}
    return draft, shot, {
        "project_id": project_id, "episode_id": episode_id, "shot_ordinal": ordinal,
        "input_fingerprint": fingerprint(anchor), "before": before,
        "reference_url": shot.get("reference_url"),
    }


def context(episode_id: str, ordinal: int) -> dict:
    _, _, result = current_input(episode_id, ordinal)
    result["workflow_revision"] = get_project_flow_state_v1(result["project_id"])["revision"]
    return result


def suggested_fields(semantic: dict, shot: dict) -> dict[str, str]:
    subjects = [item for item in semantic.get("subjects", []) if isinstance(item, dict)]
    if len(subjects) > 1:
        # 不把“皱眉；微笑”混为一个人的表情，也不猜模型主体对应哪个正式人物。
        sources = dict(performance_text="activity_summary", expression="expression_summary",
                       posture="posture_summary", gaze="gaze_summary", interaction="interaction_summary")
        result = {}
        for key, source in sources.items():
            rows = []
            for index, subject in enumerate(subjects, 1):
                value = str(subject.get(source) or "").strip()
                if not value or _UNKNOWN.fullmatch(value):
                    continue
                label = str(subject.get("appearance_summary") or f"画面人物{index}（身份未归属）")[:80]
                rows.append(f"{label}：{value}")
            if rows:
                result[key] = "；".join(rows)[:8000 if key == "performance_text" else 2000]
        return result
    rows = rerun._performance_rows(semantic, shot)
    result = {"performance_text": "；".join(row["text"] for row in rows)[:8000]}
    result.update({key: str((rerun._performance_details(semantic) or {}).get(key) or "")[:2000] for key in FIELDS[1:]})
    return {key: value for key, value in result.items() if value.strip() and not _UNKNOWN.fullmatch(value.strip())}


def propose(command: dict, *, provider: Any = None) -> dict:
    draft, shot, current = current_input(command["episode_id"], command["shot_ordinal"])
    if current["input_fingerprint"] != command["input_fingerprint"]:
        raise ValueError("镜头内容已变化，请重新生成建议")
    full = rerun._load_full_context(draft, rerun_id=rerun.studio_v2.new_id("PERFORMANCE"))
    target = rerun._target_shot(full, command["shot_ordinal"])
    # 只读当前分镜，窗口视频提供时间变化，exact-Shot 帧提供细节；不重跑 ASR/OCR。
    scoped = replace(full, shots=(target,))
    if provider is None:
        provider = rerun.Qwen3VLSemanticProvider(runner_script=str(
            Path(__file__).resolve().parents[2] / "scripts" / "run_breakdown_performance_qwen3.py"
        ))
    result = rerun._execute_provider(provider, scoped)
    semantic = rerun._target_vlm_semantic(target, result)
    # 不输出其他模型字段，不自动替换现有值；无证据的空值供用户查看但不能清空原值。
    suggested = suggested_fields(semantic, shot)
    return {"command": command, "suggested": suggested, "warnings": list(result.warnings), "adopted": False}


def run_task(task_id: str, command: dict) -> None:
    try:
        start_task(task_id, stage_key="performance_vlm", stage_label="分析当前镜头动作与表演", message="只生成建议，不修改原片事实")
        result = propose(command)
        finish_task(task_id, result=result, message="建议已生成，等待预览并采用")
    except Exception as exc:
        fail_task(task_id, str(exc))


def adopt(result: dict, selected_fields: list[str]) -> None:
    command = result["command"]
    if not selected_fields or set(selected_fields) - set(FIELDS):
        raise ValueError("请选择需要采用的动作与表演字段")
    edits = {key: result["suggested"][key] for key in selected_fields if result["suggested"].get(key)}
    if len(edits) != len(set(selected_fields)):
        raise ValueError("不能采用没有画面证据的空建议")
    # 与人工编辑共享锁；防止预览期间的新编辑被旧建议覆盖。
    with manual._WRITE_LOCK, rerun._WRITE_LOCK:
        draft, _, current = current_input(command["episode_id"], command["shot_ordinal"])
        if current["input_fingerprint"] != command["input_fingerprint"]:
            raise ValueError("镜头内容或版本已变化，旧建议不能覆盖新内容，请重新生成")
        manual.persist_shot_manual_edit_v1(
            draft, rerun.assemble_scene_timeline_v1(draft),
            shot_ordinal=command["shot_ordinal"], edits=edits,
        )
