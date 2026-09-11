from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.core.config import Settings
from app.core.errors import AppError
from app.target_assets.schemas import TargetAssetReference


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_MEDIA_FORMATS = {"image/png": ("PNG", ".png"), "image/jpeg": ("JPEG", ".jpg")}


@dataclass(frozen=True)
class ValidatedImage:
    media_type: str
    sha256: str
    size_bytes: int
    width: int
    height: int
    extension: str


def _safe_component(value: str, *, label: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise AppError("P13_MEDIA_PATH_INVALID", f"{label} 不是安全的存储路径标识", status_code=422)
    return value


def validate_image_bytes(image_bytes: bytes, media_type: str, settings: Settings) -> ValidatedImage:
    expected = _MEDIA_FORMATS.get(media_type)
    if expected is None:
        raise AppError("P13_MEDIA_TYPE_UNSUPPORTED", "P13 reference media 只接受 PNG/JPEG", status_code=422)
    if not image_bytes:
        raise AppError("P13_MEDIA_EMPTY", "P13 reference media 为空", status_code=422)
    if len(image_bytes) > settings.p13_image_max_bytes:
        raise AppError("P13_MEDIA_TOO_LARGE", "P13 reference media 超过允许大小", status_code=422)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            detected_format = image.format
            width, height = image.size
            image.verify()
    except Exception as exc:
        raise AppError("P13_MEDIA_DECODE_FAILED", "P13 reference media 无法解码", status_code=422) from exc
    if detected_format != expected[0]:
        raise AppError(
            "P13_MEDIA_TYPE_MISMATCH",
            "P13 reference media 声明类型与实际图片格式不一致",
            status_code=422,
        )
    if width < settings.p13_image_min_width or height < settings.p13_image_min_height:
        raise AppError(
            "P13_MEDIA_DIMENSIONS_TOO_SMALL",
            "P13 reference media 尺寸不足，不能作为正式跨镜参考资产",
            status_code=422,
            details={"width": width, "height": height},
        )
    return ValidatedImage(
        media_type=media_type,
        sha256=hashlib.sha256(image_bytes).hexdigest(),
        size_bytes=len(image_bytes),
        width=width,
        height=height,
        extension=expected[1],
    )


def _root(settings: Settings) -> Path:
    root = settings.artifact_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_reference_path(settings: Settings, relative_path: str) -> Path:
    root = _root(settings)
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError("P13_MEDIA_PATH_INVALID", "P13 reference media 路径越界", status_code=500) from exc
    return candidate


def store_reference_image(
    *,
    settings: Settings,
    project_id: str,
    candidate_id: str,
    target_asset_id: str,
    reference_asset_id: str,
    image_bytes: bytes,
    media_type: str,
    provider_job_id: str,
    provider: str,
    model: str,
) -> TargetAssetReference:
    validated = validate_image_bytes(image_bytes, media_type, settings)
    parts = [
        "target-assets",
        _safe_component(project_id, label="project_id"),
        _safe_component(candidate_id, label="candidate_id"),
        _safe_component(target_asset_id, label="target_asset_id"),
    ]
    filename = f"{_safe_component(reference_asset_id, label='reference_asset_id')}{validated.extension}"
    relative = Path(*parts) / filename
    destination = resolve_reference_path(settings, relative.as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = destination.read_bytes()
        existing_validated = validate_image_bytes(existing, media_type, settings)
        if existing_validated.sha256 != validated.sha256:
            raise AppError(
                "P13_MEDIA_IMMUTABILITY_VIOLATION",
                "同一 reference_asset_id 已存在不同内容",
                status_code=409,
            )
    else:
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
        try:
            with temporary.open("xb") as handle:
                handle.write(image_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return TargetAssetReference(
        reference_asset_id=reference_asset_id,
        media_type=validated.media_type,
        relative_path=relative.as_posix(),
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
        width=validated.width,
        height=validated.height,
        provider_job_id=provider_job_id,
        provider=provider,
        model=model,
    )


def verify_reference_image(settings: Settings, reference: TargetAssetReference) -> Path:
    path = resolve_reference_path(settings, reference.relative_path)
    if not path.is_file():
        raise AppError("P13_MEDIA_MISSING", "P13 reference media 文件缺失，拒绝批准", status_code=409)
    image_bytes = path.read_bytes()
    validated = validate_image_bytes(image_bytes, reference.media_type, settings)
    if (
        validated.sha256 != reference.sha256
        or validated.size_bytes != reference.size_bytes
        or validated.width != reference.width
        or validated.height != reference.height
    ):
        raise AppError("P13_MEDIA_CHANGED", "P13 reference media 已被修改，拒绝批准", status_code=409)
    return path
