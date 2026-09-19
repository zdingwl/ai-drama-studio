"""Script-localization-only API. All model work requires explicit POST commands."""

from enum import StrEnum
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Header, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.script_localization.long_pipeline import is_long_document, start_long_stage
from app.script_localization.schemas import ScriptLocalizationStateRead, StageRead, TargetScriptEditCommand
from app.script_localization.service import (
    export_current_script, get_state, save_target_edit, start_stage,
)
from app.sources.models import SourceAsset, SourceDocument
from app.sources.schemas import SourceDocumentRead
from app.sources.service import ingest_text_upload
from app.sources.storage import resolve_source_asset_path
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(prefix="/projects/{project_id}/script-localization", tags=["script-localization"])


class PasteScriptCommand(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)


class ScriptSourceRead(BaseModel):
    project_id: str
    document_id: str | None = None
    revision: int | None = None
    filename: str | None = None
    text: str | None = None


class StageName(StrEnum):
    ANALYZE = "analyze"
    PLAN = "plan"
    GENERATE = "generate"


def _require_script_localization(db: Session, project_id: str) -> None:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.SCRIPT_LOCALIZATION:
        raise AppError("SCRIPT_LOCALIZATION_NOT_ALLOWED", "当前工作区仅适用于剧本本土化项目", status_code=422)


@router.get("/source", response_model=ScriptSourceRead)
def get_script_source(project_id: str, db: Session = Depends(get_db)) -> ScriptSourceRead:
    _require_script_localization(db, project_id)
    document = db.scalar(select(SourceDocument).where(
        SourceDocument.project_id == project_id, SourceDocument.is_current.is_(True),
    ))
    if document is None:
        return ScriptSourceRead(project_id=project_id)
    asset = db.get(SourceAsset, document.source_asset_id)
    if asset is None or asset.project_id != project_id:
        raise AppError("SOURCE_ASSET_INCONSISTENT", "原剧本文档对应的源文件不存在", status_code=500)
    path = resolve_source_asset_path(asset.relative_path)
    if not path.is_file():
        raise AppError("SOURCE_FILE_NOT_FOUND", "原剧本文档内容不存在", status_code=500)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise AppError("SOURCE_ENCODING_INVALID", "原剧本不符合 UTF-8 编码", status_code=500) from exc
    return ScriptSourceRead(
        project_id=project_id, document_id=document.id, revision=document.revision,
        filename=asset.original_filename, text=text,
    )


@router.post("/paste", response_model=SourceDocumentRead, status_code=201)
async def paste_script_source(
    project_id: str, payload: PasteScriptCommand, db: Session = Depends(get_db),
) -> SourceDocumentRead:
    _require_script_localization(db, project_id)
    text = payload.text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise AppError("TEXT_CONTENT_EMPTY", "原剧本内容不能为空", status_code=422)
    upload = UploadFile(file=BytesIO(text.encode("utf-8")), filename="粘贴剧本.txt")
    return await ingest_text_upload(db, project_id, upload)


@router.get("/state", response_model=ScriptLocalizationStateRead)
def get_script_localization_state(project_id: str, db: Session = Depends(get_db)) -> ScriptLocalizationStateRead:
    return get_state(db, project_id)


@router.post("/commands/run/{stage}", response_model=TaskRead, status_code=202)
def run_script_localization_stage(
    project_id: str, stage: StageName,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    if is_long_document(db, project_id):
        return task_to_read(start_long_stage(db, project_id, stage.value, idempotency_key))
    return task_to_read(start_stage(db, project_id, stage.value, idempotency_key))


@router.post("/commands/save", response_model=StageRead)
def save_localized_script(
    project_id: str, command: TargetScriptEditCommand, db: Session = Depends(get_db),
) -> StageRead:
    return save_target_edit(db, project_id, command)


@router.post("/commands/export", response_model=StageRead)
def export_localized_script(project_id: str, db: Session = Depends(get_db)) -> StageRead:
    return export_current_script(db, project_id)
