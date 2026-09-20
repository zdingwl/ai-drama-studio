"""Project-scoped script shelf. Source assets remain immutable; selecting one creates a new
SourceDocument revision and invalidates downstream artifacts via the existing source service.
No Replica routes, tables, or workflow contracts are changed.
"""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.script_to_drama.service import require_project
from app.sources.enums import SourceAssetKind
from app.sources.models import SourceAsset, SourceDocument
from app.sources.service import _refresh_text_artifact, ingest_text_upload
from app.sources.storage import resolve_source_asset_path

router = APIRouter(prefix="/projects/{project_id}/script-to-drama/library", tags=["script-to-drama-library"])


class ScriptShelfItem(BaseModel):
    id: str
    title: str
    filename: str
    char_count: int
    latest_revision: int
    is_active: bool
    excerpt: str


class ScriptShelfRead(BaseModel):
    project_id: str
    current_document_id: str | None
    scripts: list[ScriptShelfItem]


class SelectScriptCommand(BaseModel):
    source_asset_id: str = Field(min_length=1, max_length=36)
    expected_current_document_id: str | None = None


class PasteScriptCommand(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=200_000)


def _current(db: Session, project_id: str) -> SourceDocument | None:
    return db.scalar(select(SourceDocument).where(
        SourceDocument.project_id == project_id,
        SourceDocument.is_current.is_(True),
    ))


def shelf(db: Session, project_id: str) -> ScriptShelfRead:
    require_project(db, project_id)
    current = _current(db, project_id)
    # Only list assets actually bound to a script document, never unrelated text files.
    rows = db.execute(
        select(SourceAsset, func.max(SourceDocument.revision), func.max(SourceDocument.char_count))
        .join(SourceDocument, SourceDocument.source_asset_id == SourceAsset.id)
        .where(SourceAsset.project_id == project_id, SourceDocument.project_id == project_id,
               SourceAsset.asset_kind == SourceAssetKind.TEXT)
        .group_by(SourceAsset.id)
        .order_by(func.max(SourceDocument.revision).desc())
    ).all()
    items: list[ScriptShelfItem] = []
    for asset, revision, char_count in rows:
        path = resolve_source_asset_path(asset.relative_path)
        if not path.is_file():
            raise AppError("SCRIPT_TO_DRAMA_LIBRARY_FILE_MISSING", "剧本库源文件缺失", status_code=409)
        with path.open("rb") as handle:
            excerpt = handle.read(2048).decode("utf-8-sig", errors="replace")[:200]
        items.append(ScriptShelfItem(
            id=asset.id,
            title=Path(asset.original_filename).stem or asset.original_filename,
            filename=asset.original_filename,
            char_count=int(char_count),
            latest_revision=int(revision),
            is_active=current is not None and current.source_asset_id == asset.id,
            excerpt=excerpt.strip(),
        ))
    return ScriptShelfRead(project_id=project_id,
                           current_document_id=current.id if current else None, scripts=items)


@router.get("", response_model=ScriptShelfRead)
def get_library(project_id: str, db: Session = Depends(get_db)) -> ScriptShelfRead:
    return shelf(db, project_id)


@router.post("/select", response_model=ScriptShelfRead)
def select_script(project_id: str, command: SelectScriptCommand,
                  db: Session = Depends(get_db)) -> ScriptShelfRead:
    require_project(db, project_id)
    current = _current(db, project_id)
    if command.expected_current_document_id != (current.id if current else None):
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_SELECTION_CONFLICT",
                       "当前剧本已经变化，请刷新后重新选择", status_code=409)
    asset = db.get(SourceAsset, command.source_asset_id)
    if asset is None or asset.project_id != project_id or asset.asset_kind != SourceAssetKind.TEXT:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_SCRIPT_NOT_FOUND", "该剧本不在当前项目的剧本库中", status_code=404)
    original = db.scalar(select(SourceDocument).where(
        SourceDocument.project_id == project_id, SourceDocument.source_asset_id == asset.id,
    ).order_by(SourceDocument.revision.desc()))
    if original is None:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_SCRIPT_NOT_FOUND", "该剧本没有正式来源版本", status_code=404)
    if current is not None and current.source_asset_id == asset.id:
        return shelf(db, project_id)
    if current is not None:
        current.is_current = False
        db.add(current)
    next_revision = int(db.scalar(select(func.max(SourceDocument.revision)).where(
        SourceDocument.project_id == project_id)) or 0) + 1
    document = SourceDocument(
        project_id=project_id, source_asset_id=asset.id, revision=next_revision,
        document_format=original.document_format, encoding=original.encoding,
        char_count=original.char_count, is_current=True,
    )
    db.add(document)
    db.flush()
    _refresh_text_artifact(db, project_id, document, asset)
    return shelf(db, project_id)


@router.post("/paste", response_model=ScriptShelfRead, status_code=201)
async def add_script(project_id: str, command: PasteScriptCommand,
                     db: Session = Depends(get_db)) -> ScriptShelfRead:
    require_project(db, project_id)
    title = command.title.strip()
    text = command.text.replace("\r\n", "\n").replace("\r", "\n")
    if not title or title in {".", ".."} or any(char in title for char in "/\\\x00\n\r"):
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_TITLE_INVALID", "剧本名称不能包含路径或控制字符", status_code=422)
    if not text.strip():
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_TEXT_EMPTY", "剧本内容不能为空", status_code=422)
    from io import BytesIO
    file = UploadFile(file=BytesIO(text.encode("utf-8")), filename=f"{title}.txt")
    await ingest_text_upload(db, project_id, file)
    return shelf(db, project_id)


@router.post("/uploads", response_model=ScriptShelfRead, status_code=201)
async def add_script_files(project_id: str, files: list[UploadFile] = File(...),
                           db: Session = Depends(get_db)) -> ScriptShelfRead:
    require_project(db, project_id)
    if not files or len(files) > 20:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_BATCH_SIZE_INVALID", "每批请选择 1–20 份剧本", status_code=422)
    # Fail fast on unsupported names, and avoid pretending a failed batch was fully imported.
    for file in files:
        if Path(file.filename or "").suffix.lower() not in {".txt", ".md", ".markdown"}:
            raise AppError("SCRIPT_TO_DRAMA_LIBRARY_FORMAT_UNSUPPORTED", "批量上传仅支持 TXT / MD", status_code=422)
    # The underlying immutable source service commits after each file. A partial failure
    # is explicit and all earlier uploads remain visible; callers should refresh library.
    for index, file in enumerate(files, start=1):
        try:
            await ingest_text_upload(db, project_id, file)
        except Exception as exc:
            raise AppError("SCRIPT_TO_DRAMA_LIBRARY_BATCH_PARTIAL",
                           f"第 {index} 份剧本上传失败；之前成功的文件已保存，请刷新剧本库核对后重试失败文件",
                           status_code=409) from exc
    return shelf(db, project_id)
