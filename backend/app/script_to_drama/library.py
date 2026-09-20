"""Project-scoped multi-script shelf, isolated from the current production SourceDocument.

Creating/uploading a script NEVER changes the active document. Selecting or editing the
active script explicitly publishes its latest revision to the existing source pipeline.
Legacy source documents are adopted once without modifying their immutable files.
"""

import hashlib
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.script_to_drama.service import require_project
from app.script_to_drama.shelf_models import DramaShelfRevision, DramaShelfScript
from app.sources.enums import SourceAssetKind
from app.sources.models import SourceAsset, SourceDocument
from app.sources.service import ingest_text_upload
from app.sources.storage import resolve_source_asset_path

router = APIRouter(prefix="/projects/{project_id}/script-to-drama/library", tags=["script-to-drama-library"])
MAX_CHARS = 200_000
MAX_BYTES = 800_000
SUFFIXES = {".txt", ".md", ".markdown"}


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


class ScriptDetailRead(ScriptShelfItem):
    text: str
    sha256: str


class SelectScriptCommand(BaseModel):
    source_asset_id: str = Field(min_length=1, max_length=36)  # Stable script ID; keep request compatibility.
    expected_current_document_id: str | None = None


class PasteScriptCommand(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=MAX_CHARS)


class UpdateScriptCommand(PasteScriptCommand):
    expected_revision: int = Field(ge=1)


def _current(db: Session, project_id: str) -> SourceDocument | None:
    return db.scalar(select(SourceDocument).where(
        SourceDocument.project_id == project_id, SourceDocument.is_current.is_(True),
    ))


def _normalized_title(value: str) -> str:
    title = value.strip()
    if not title or len(title) > 160 or title in {".", ".."} or any(c in title for c in "/\\\x00\n\r"):
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_TITLE_INVALID", "剧本名称不能包含路径或控制字符", status_code=422)
    return title


def _normalized_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip() or len(text) > MAX_CHARS:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_TEXT_INVALID", "剧本内容不能为空且不得超过 200,000 字符", status_code=422)
    return text


def _latest(db: Session, script: DramaShelfScript) -> DramaShelfRevision:
    version = db.scalar(select(DramaShelfRevision).where(
        DramaShelfRevision.script_id == script.id,
        DramaShelfRevision.revision == script.latest_revision,
    ))
    if version is None:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_REVISION_MISSING", "剧本版本记录缺失", status_code=409)
    return version


def _script(db: Session, project_id: str, script_id: str) -> DramaShelfScript:
    script = db.get(DramaShelfScript, script_id)
    if script is None or script.project_id != project_id:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_SCRIPT_NOT_FOUND", "该剧本不在当前项目的剧本库中", status_code=404)
    return script


def _is_active(script: DramaShelfScript, current: SourceDocument | None) -> bool:
    return bool(current and script.active_document_id == current.id and script.active_revision == script.latest_revision)


def _adopt_legacy(db: Session, project_id: str) -> None:
    """Import old shelf items, preserving their original IDs and the current production source."""
    current = _current(db, project_id)
    old_assets = db.scalars(
        select(SourceAsset).join(SourceDocument, SourceDocument.source_asset_id == SourceAsset.id)
        .where(SourceAsset.project_id == project_id, SourceDocument.project_id == project_id,
               SourceAsset.asset_kind == SourceAssetKind.TEXT)
        .distinct()
    ).all()
    changed = False
    for asset in old_assets:
        # Explicitly activated new versions already have a shelf owner. Source
        # deduplication is content-based; sharing a source must not merge scripts.
        exists = db.scalar(select(DramaShelfRevision.id).where(DramaShelfRevision.source_asset_id == asset.id))
        if exists is not None or db.get(DramaShelfScript, asset.id) is not None:
            continue
        path = resolve_source_asset_path(asset.relative_path)
        if not path.is_file():
            raise AppError("SCRIPT_TO_DRAMA_LIBRARY_FILE_MISSING", "旧剧本源文件缺失", status_code=409)
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError("SCRIPT_TO_DRAMA_LIBRARY_ENCODING_INVALID", "旧剧本不是 UTF-8 编码", status_code=409) from exc
        title = _normalized_title(Path(asset.original_filename).stem or "未命名剧本")
        item = DramaShelfScript(
            id=asset.id, project_id=project_id, title=title, latest_revision=1,
            active_document_id=current.id if current and current.source_asset_id == asset.id else None,
            active_revision=1 if current and current.source_asset_id == asset.id else None,
        )
        db.add(item)
        db.flush()
        db.add(DramaShelfRevision(
            script_id=item.id, revision=1, text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            char_count=len(text), filename=asset.original_filename, source_asset_id=asset.id,
        ))
        changed = True
    if changed:
        db.commit()


def shelf(db: Session, project_id: str) -> ScriptShelfRead:
    require_project(db, project_id)
    _adopt_legacy(db, project_id)
    current = _current(db, project_id)
    scripts = db.scalars(select(DramaShelfScript).where(
        DramaShelfScript.project_id == project_id,
    ).order_by(DramaShelfScript.created_at.desc(), DramaShelfScript.id.desc())).all()
    items = []
    for script in scripts:
        version = _latest(db, script)
        items.append(ScriptShelfItem(
            id=script.id, title=script.title, filename=version.filename,
            char_count=version.char_count, latest_revision=script.latest_revision,
            is_active=_is_active(script, current), excerpt=version.text[:200].strip(),
        ))
    return ScriptShelfRead(project_id=project_id,
                           current_document_id=current.id if current else None, scripts=items)


def _detail(db: Session, project_id: str, script: DramaShelfScript) -> ScriptDetailRead:
    version = _latest(db, script)
    return ScriptDetailRead(
        id=script.id, title=script.title, filename=version.filename,
        char_count=version.char_count, latest_revision=script.latest_revision,
        is_active=_is_active(script, _current(db, project_id)),
        excerpt=version.text[:200].strip(), text=version.text, sha256=version.sha256,
    )


def _insert_script(db: Session, project_id: str, title: str, text: str, filename: str) -> None:
    script = DramaShelfScript(id=str(uuid4()), project_id=project_id, title=title, latest_revision=1)
    db.add(script)
    db.flush()
    db.add(DramaShelfRevision(
        script_id=script.id, revision=1, text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        char_count=len(text), filename=filename,
    ))
    db.commit()


async def _activate(db: Session, project_id: str, script: DramaShelfScript) -> None:
    """Only an explicit selection/active edit replaces the current production source."""
    version = _latest(db, script)
    upload = UploadFile(file=BytesIO(version.text.encode("utf-8")), filename=f"{script.title}.txt")
    document = await ingest_text_upload(db, project_id, upload)
    db.execute(update(DramaShelfScript).where(DramaShelfScript.project_id == project_id)
               .values(active_document_id=None, active_revision=None))
    script.active_document_id = document.id
    script.active_revision = script.latest_revision
    version.source_asset_id = document.source_asset.id
    db.commit()


@router.get("", response_model=ScriptShelfRead)
def get_library(project_id: str, db: Session = Depends(get_db)) -> ScriptShelfRead:
    return shelf(db, project_id)


@router.get("/{script_id}", response_model=ScriptDetailRead)
def get_script(project_id: str, script_id: str, db: Session = Depends(get_db)) -> ScriptDetailRead:
    require_project(db, project_id)
    _adopt_legacy(db, project_id)
    return _detail(db, project_id, _script(db, project_id, script_id))


@router.post("/select", response_model=ScriptShelfRead)
async def select_script(project_id: str, command: SelectScriptCommand,
                        db: Session = Depends(get_db)) -> ScriptShelfRead:
    require_project(db, project_id)
    _adopt_legacy(db, project_id)
    current = _current(db, project_id)
    if command.expected_current_document_id != (current.id if current else None):
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_SELECTION_CONFLICT", "当前剧本已变化，请刷新后重试", status_code=409)
    script = _script(db, project_id, command.source_asset_id)
    if not _is_active(script, current):
        await _activate(db, project_id, script)
    return shelf(db, project_id)


@router.post("/paste", response_model=ScriptShelfRead, status_code=201)
async def add_script(project_id: str, command: PasteScriptCommand,
                     db: Session = Depends(get_db)) -> ScriptShelfRead:
    require_project(db, project_id)
    _adopt_legacy(db, project_id)
    title = _normalized_title(command.title)
    text = _normalized_text(command.text)
    _insert_script(db, project_id, title, text, f"{title}.txt")
    return shelf(db, project_id)


@router.post("/uploads", response_model=ScriptShelfRead, status_code=201)
async def add_script_files(project_id: str, files: list[UploadFile] = File(...),
                           db: Session = Depends(get_db)) -> ScriptShelfRead:
    require_project(db, project_id)
    _adopt_legacy(db, project_id)
    if not files or len(files) > 20:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_BATCH_SIZE_INVALID", "每批请选择 1–20 份剧本", status_code=422)
    if any(Path(file.filename or "").suffix.lower() not in SUFFIXES for file in files):
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_FORMAT_UNSUPPORTED", "批量上传仅支持 TXT / MD", status_code=422)
    for index, file in enumerate(files, start=1):
        try:
            filename = Path(file.filename or "").name
            title = _normalized_title(Path(filename).stem)
            if len(filename) > 255:
                raise AppError("SCRIPT_TO_DRAMA_LIBRARY_FILENAME_INVALID", "文件名过长", status_code=422)
            raw = await file.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise AppError("SCRIPT_TO_DRAMA_LIBRARY_FILE_TOO_LARGE", "剧本不能超过 800 KB", status_code=422)
            try:
                text = _normalized_text(raw.decode("utf-8-sig"))
            except UnicodeDecodeError as exc:
                raise AppError("SCRIPT_TO_DRAMA_LIBRARY_ENCODING_INVALID", "剧本必须为 UTF-8 编码", status_code=422) from exc
            _insert_script(db, project_id, title, text, filename)
        except Exception as exc:
            db.rollback()
            raise AppError("SCRIPT_TO_DRAMA_LIBRARY_BATCH_PARTIAL",
                           f"第 {index} 份剧本上传失败；之前成功的文件已保存，请刷新核对后重试失败文件",
                           status_code=409) from exc
    return shelf(db, project_id)


@router.put("/{script_id}", response_model=ScriptDetailRead)
async def update_script(project_id: str, script_id: str, command: UpdateScriptCommand,
                        db: Session = Depends(get_db)) -> ScriptDetailRead:
    require_project(db, project_id)
    _adopt_legacy(db, project_id)
    script = _script(db, project_id, script_id)
    if script.latest_revision != command.expected_revision:
        raise AppError("SCRIPT_TO_DRAMA_LIBRARY_EDIT_CONFLICT", "剧本已有更新，请刷新后编辑", status_code=409)
    title = _normalized_title(command.title)
    text = _normalized_text(command.text)
    previous = _latest(db, script)
    was_active = _is_active(script, _current(db, project_id))
    script.title = title
    if text != previous.text:
        script.latest_revision += 1
        db.add(DramaShelfRevision(
            script_id=script.id, revision=script.latest_revision, text=text,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), char_count=len(text),
            filename=f"{title}.txt",
        ))
        db.flush()
        if was_active:
            await _activate(db, project_id, script)
        else:
            db.commit()
    else:
        db.commit()  # Rename-only: source fingerprint and downstream remain unchanged.
    return _detail(db, project_id, script)
