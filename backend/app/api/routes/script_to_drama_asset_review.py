"""Human-review endpoint for script-to-drama asset definitions only."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.script_to_drama.asset_review import ReviewWorldCommand, review_world
from app.script_to_drama.schemas import ScriptToDramaState

router = APIRouter(prefix="/projects/{project_id}/script-to-drama", tags=["script-to-drama"])


@router.post("/commands/review-world", response_model=ScriptToDramaState)
def review_world_command(project_id: str, command: ReviewWorldCommand,
                         db: Session = Depends(get_db)) -> ScriptToDramaState:
    return review_world(db, project_id, command)
