"""原片人物自动解析 API。

POST 是显式写入口；GET /character-assets 继续保持只读。
自动链路分两层：
1. Character V10.1 Candidate/Final Binding 硬条件唯一时直接自动归并；
2. 只对剩余 2..6 个多人候选使用 LocalSubject 外观 + V10.1 Person Crop + Qwen3-VL 闭集裁决。

Qwen 推理期间不持有人物写锁；写回前再次校验 workspace revision，避免长推理覆盖用户刚完成的人工修改。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.app.source_person_assets_v1 import LOCK, inventory
from engine.app.source_person_auto_resolver_v1 import (
    build_auto_resolution_plan,
    persist_auto_resolutions,
)
from engine.app.source_person_vlm_adjudicator_v1 import (
    build_vlm_adjudication_plan,
    persist_vlm_resolution_plan,
)

router = APIRouter(prefix="/api", tags=["character-assets"])


class AutoResolveRequest(BaseModel):
    expected_revision: str


@router.post("/projects/{project_id}/character-assets/auto-resolve")
def auto_resolve_source_people(project_id: str, payload: AutoResolveRequest):
    """先跑 V10.1 硬解析，再对真正的多人歧义运行 Qwen3-VL 闭集裁决。"""

    # 第一层是纯 DB / Evidence 解析，保持原有同步事务边界。
    with LOCK:
        current = inventory(project_id)
        if current["revision"] != payload.expected_revision:
            raise HTTPException(409, "人物或镜头已更新，请刷新后重新执行 AI 人物整理")
        deterministic = persist_auto_resolutions(project_id, current["observations"])
        workspace = inventory(project_id) if deterministic["changed"] else current
        vlm_expected_revision = workspace["revision"]
        vlm_observations = workspace["observations"]

    # 第二层可能加载本地 4B VLM，绝不能在这段时间持有 LOCK。
    # 配置错误 / runtime 缺失不能让已经完成的第一层写入变成前端 500；直接安全退回人工确认。
    vlm_error: str | None = None
    try:
        vlm_plan = build_vlm_adjudication_plan(project_id, vlm_observations)
    except (ValueError, OSError) as exc:
        vlm_plan = {}
        vlm_error = f"Qwen3-VL 多人裁决暂不可用：{type(exc).__name__}"

    vlm_write = {"changed": False, "auto_bound_count": 0}
    vlm_stale = False
    if any(proposal.get("decision") == "AUTO" for proposal in vlm_plan.values()):
        with LOCK:
            try:
                vlm_write = persist_vlm_resolution_plan(
                    project_id,
                    vlm_observations,
                    vlm_plan,
                    expected_revision=vlm_expected_revision,
                )
            except ValueError:
                # 用户可能在 Qwen 推理期间已经人工修改。保留用户新事实，本次模型结果直接失效，不覆盖、不报 500。
                vlm_stale = True
                vlm_plan = {}
                workspace = inventory(project_id)
            else:
                if vlm_write["changed"]:
                    workspace = inventory(project_id)

    # 返回值只保留最终仍未解决的 Review proposal。自动完成的 LocalSubject 已经从 pending 消失。
    final_pending_keys = {
        str(row.get("key") or "")
        for row in workspace["observations"]
        if not row.get("character_id")
    }
    deterministic_review = build_auto_resolution_plan(project_id, workspace["observations"])
    review_rows = {
        key: proposal
        for key, proposal in deterministic_review.items()
        if key in final_pending_keys and proposal.get("decision") == "REVIEW"
    }
    review_rows.update({
        key: proposal
        for key, proposal in vlm_plan.items()
        if key in final_pending_keys and proposal.get("decision") == "REVIEW"
    })

    auto_bound_count = int(deterministic["auto_bound_count"]) + int(vlm_write["auto_bound_count"])
    return {
        "changed": bool(deterministic["changed"] or vlm_write["changed"]),
        "auto_bound_count": auto_bound_count,
        "deterministic_auto_bound_count": int(deterministic["auto_bound_count"]),
        "vlm_auto_bound_count": int(vlm_write["auto_bound_count"]),
        "vlm_adjudication_count": len(vlm_plan),
        "vlm_stale": vlm_stale,
        "vlm_error": vlm_error,
        "review_count": len(review_rows),
        "review_proposals": review_rows,
        "workspace": workspace,
    }
