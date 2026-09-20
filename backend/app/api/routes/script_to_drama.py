"""Script-to-drama only: script ingestion, preproduction and independent media stages."""

from enum import StrEnum
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Header, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.script_to_drama.schemas import ScriptToDramaState, SelectionCommand
from app.script_to_drama.production import accept_generated_video, start_stage as start_production_stage
from app.script_to_drama.media_read import media_path
from app.script_to_drama.service import require_project, start_stage, state
from app.sources.models import SourceAsset, SourceDocument
from app.sources.schemas import SourceDocumentRead
from app.sources.service import ingest_text_upload
from app.sources.storage import resolve_source_asset_path
from app.workflow.schemas import TaskRead
from app.workflow.task_service import task_to_read

router = APIRouter(prefix="/projects/{project_id}/script-to-drama", tags=["script-to-drama"])


class SourceRead(BaseModel):
    project_id: str
    document_id: str | None = None
    revision: int | None = None
    filename: str | None = None
    text: str | None = None


class PasteCommand(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class StageName(StrEnum):
    ANALYZE = "analyze"
    WORLD = "world"
    STORYBOARD = "storyboard"


class ProductionStageName(StrEnum):
    ASSET_IMAGES = "asset_images"
    PROMPTS = "prompts"
    GENERATE = "generate"
    POST = "post"


def _require_approved_assets(db: Session, project_id: str) -> None:
    snapshot = state(db, project_id)
    if snapshot.world.status != "CURRENT" or snapshot.assets.status != "CURRENT":
        raise AppError("SCRIPT_TO_DRAMA_ASSETS_NOT_READY", "请先提取当前剧本的人物、场景和道具", status_code=409)
    if (snapshot.world.content or {}).get("review_status") != "APPROVED" or \
            (snapshot.assets.content or {}).get("review_status") != "APPROVED":
        raise AppError("SCRIPT_TO_DRAMA_ASSETS_NOT_APPROVED", "请先在资产库人工核对并确认人物、场景和道具", status_code=409)
    if (snapshot.world.content or {}).get("unresolved_decisions"):
        raise AppError("SCRIPT_TO_DRAMA_ASSETS_UNRESOLVED", "资产仍有未决事项，不能进入分镜或出图", status_code=409)
    if (snapshot.assets.content or {}).get("target_bible_artifact_id") != snapshot.world.artifact_id:
        raise AppError("SCRIPT_TO_DRAMA_ASSET_LINEAGE_INVALID", "资产定义与当前目标世界版本不匹配", status_code=409)


@router.get("/source", response_model=SourceRead)
def get_source(project_id: str, db: Session = Depends(get_db)) -> SourceRead:
    require_project(db, project_id)
    doc = db.scalar(select(SourceDocument).where(
        SourceDocument.project_id == project_id, SourceDocument.is_current.is_(True)))
    if doc is None:
        return SourceRead(project_id=project_id)
    asset = db.get(SourceAsset, doc.source_asset_id)
    if asset is None or asset.project_id != project_id:
        raise AppError("SCRIPT_TO_DRAMA_SOURCE_MISSING", "原剧本源文件不存在", status_code=409)
    path = resolve_source_asset_path(asset.relative_path)
    if not path.is_file():
        raise AppError("SCRIPT_TO_DRAMA_SOURCE_MISSING", "原剧本内容不存在", status_code=409)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise AppError("SCRIPT_TO_DRAMA_ENCODING_INVALID", "原剧本编码必须为 UTF-8", status_code=422) from exc
    return SourceRead(project_id=project_id, document_id=doc.id,
                      revision=doc.revision, filename=asset.original_filename, text=text)


@router.post("/paste", response_model=SourceDocumentRead, status_code=201)
async def paste_source(project_id: str, payload: PasteCommand,
                       db: Session = Depends(get_db)) -> SourceDocumentRead:
    require_project(db, project_id)
    text = payload.text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise AppError("SCRIPT_TO_DRAMA_SOURCE_EMPTY", "剧本文本不能为空", status_code=422)
    upload = UploadFile(file=BytesIO(text.encode("utf-8")), filename="粘贴原剧本.txt")
    return await ingest_text_upload(db, project_id, upload)


@router.get("/state", response_model=ScriptToDramaState)
def get_state(project_id: str, db: Session = Depends(get_db)) -> ScriptToDramaState:
    return state(db, project_id)


@router.post("/commands/run/{stage}", response_model=TaskRead, status_code=202)
def run_stage(project_id: str, stage: StageName,
              idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
              db: Session = Depends(get_db)) -> TaskRead:
    if stage == StageName.STORYBOARD:
        _require_approved_assets(db, project_id)
    return task_to_read(start_stage(db, project_id, stage.value, idempotency_key))


@router.post("/commands/production/{stage}", response_model=TaskRead, status_code=202)
def run_production_stage(
    project_id: str,
    stage: ProductionStageName,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    db: Session = Depends(get_db),
) -> TaskRead:
    if stage == ProductionStageName.ASSET_IMAGES:
        _require_approved_assets(db, project_id)
    return task_to_read(start_production_stage(db, project_id, stage.value, idempotency_key))


@router.post("/commands/accept-generated", response_model=ScriptToDramaState)
def accept_generated(
    project_id: str,
    command: SelectionCommand,
    db: Session = Depends(get_db),
) -> ScriptToDramaState:
    accept_generated_video(db, project_id, command)
    return state(db, project_id)


@router.get("/media/{reference_id}")
def read_media(project_id: str, reference_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path = media_path(db, project_id, reference_id)
    media_type = "image/png" if path.suffix.lower() == ".png" else "video/mp4"
    return FileResponse(path, media_type=media_type)
