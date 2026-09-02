"""Workflow V2 unified project flow-state HTTP API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.project_flow_state_contract_v1 import ProjectFlowStateV1
from engine.app.project_flow_state_read_v1 import get_project_flow_state_read_v1


router = APIRouter(prefix="/api", tags=["project-flow-state"])


@router.get(
    "/projects/{project_id}/flow-state",
    response_model=ProjectFlowStateV1,
)
def api_get_project_flow_state(project_id: str):
    """Return the one read-only Workflow V2 state snapshot shared by all formal pages."""

    try:
        return get_project_flow_state_read_v1(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Contract/data corruption is not a normal lifecycle state.  Missing/stale business
        # results are represented inside ProjectFlowState and therefore still return HTTP 200.
        raise HTTPException(status_code=409, detail=f"工作流状态数据不一致：{exc}") from exc


__all__ = ["api_get_project_flow_state", "router"]
