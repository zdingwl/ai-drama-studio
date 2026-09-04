"""原片人物自动解析 API。

POST 是显式写入口；GET /character-assets 继续保持只读。
前端先读取当前 workspace revision，再提交 expected_revision，避免自动任务覆盖用户刚完成的人工修改。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.app.source_person_assets_v1 import LOCK, inventory
from engine.app.source_person_auto_resolver_v1 import (
    build_auto_resolution_plan,
    persist_auto_resolutions,
)

router = APIRouter(prefix="/api", tags=["character-assets"])


class AutoResolveRequest(BaseModel):
    expected_revision: str


@router.post("/projects/{project_id}/character-assets/auto-resolve")
def auto_resolve_source_people(project_id: str, payload: AutoResolveRequest):
    """把 V10.1 硬条件满足的 LocalSubject 自动映射到当前 FinalCharacter。"""

    with LOCK:
        current = inventory(project_id)
        if current["revision"] != payload.expected_revision:
            raise HTTPException(409, "人物或镜头已更新，请刷新后重新执行 AI 人物整理")

        result = persist_auto_resolutions(project_id, current["observations"])
        workspace = inventory(project_id) if result["changed"] else current
        review_plan = build_auto_resolution_plan(project_id, workspace["observations"])
        review_rows = {
            key: proposal
            for key, proposal in review_plan.items()
            if proposal.get("decision") == "REVIEW"
        }
        return {
            "changed": bool(result["changed"]),
            "auto_bound_count": int(result["auto_bound_count"]),
            "review_count": len(review_rows),
            "review_proposals": review_rows,
            "workspace": workspace,
        }
