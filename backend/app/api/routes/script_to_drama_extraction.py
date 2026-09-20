"""One-click analysis + asset extraction for the selected script only."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.script_to_drama.extraction import start_extraction
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(prefix="/projects/{project_id}/script-to-drama", tags=["script-to-drama"])


@router.post("/commands/extract-assets", response_model=TaskRead, status_code=202)
def extract_assets(
    project_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    return task_to_read(start_extraction(db, project_id, idempotency_key))
