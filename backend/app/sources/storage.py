import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.artifacts import artifact_root
from app.core.config import get_settings
from app.core.errors import AppError
from app.sources.enums import SourceAssetKind

_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,12}$")


def validate_client_filename(filename: str | None) -> str:
    if not filename:
        raise AppError("SOURCE_FILENAME_REQUIRED", "上传文件缺少文件名", status_code=422)
    if filename in {".", ".."} or "/" in filename or "\\" in filename or Path(filename).name != filename:
        raise AppError("SOURCE_PATH_TRAVERSAL", "文件名包含不安全路径", status_code=422)
    if len(filename) > 255:
        raise AppError("SOURCE_FILENAME_TOO_LONG", "文件名过长", status_code=422)
    return filename


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if _SAFE_SUFFIX.fullmatch(suffix) else ""


def project_source_root(project_id: str) -> Path:
    root = artifact_root() / "projects" / project_id / "source"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_source_asset_path(relative_path: str) -> Path:
    root = artifact_root().resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError("SOURCE_PATH_TRAVERSAL", "SourceAsset 路径越界", status_code=422) from exc
    return candidate


async def stream_upload_to_temp(
    upload: UploadFile,
    *,
    project_id: str,
    asset_kind: SourceAssetKind,
) -> tuple[Path, str, int, str]:
    filename = validate_client_filename(upload.filename)
    settings = get_settings()
    max_bytes = (
        settings.max_video_source_bytes
        if asset_kind == SourceAssetKind.VIDEO
        else settings.max_text_source_bytes
    )
    temp_root = project_source_root(project_id) / ".incoming"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_path = temp_root / f"{uuid4().hex}.upload"
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with temp_path.open("xb") as handle:
            while True:
                chunk = await upload.read(settings.upload_chunk_bytes)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise AppError(
                        "SOURCE_FILE_TOO_LARGE",
                        "上传文件超过允许大小",
                        status_code=413,
                        details={"max_bytes": max_bytes},
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size_bytes == 0:
        temp_path.unlink(missing_ok=True)
        raise AppError("SOURCE_FILE_EMPTY", "上传文件为空", status_code=422)

    return temp_path, digest.hexdigest(), size_bytes, filename


def move_temp_to_immutable_source(
    temp_path: Path,
    *,
    project_id: str,
    asset_id: str,
    original_filename: str,
) -> tuple[Path, str]:
    suffix = _safe_suffix(original_filename)
    asset_dir = project_source_root(project_id) / "raw" / asset_id
    asset_dir.mkdir(parents=True, exist_ok=False)
    final_path = asset_dir / f"source{suffix}"
    temp_path.replace(final_path)
    root = artifact_root().resolve()
    relative = final_path.resolve().relative_to(root).as_posix()
    return final_path, relative


def cleanup_asset_file(relative_path: str) -> None:
    path = resolve_source_asset_path(relative_path)
    try:
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent.name and parent.parent.name == "raw":
            parent.rmdir()
    except OSError:
        pass
