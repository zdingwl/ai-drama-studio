"""Read only published CURRENT media from a script-to-drama project.

A bare reference/segment ID must never fall back to an old asset revision or a
clip from another project when the user regenerates media.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.script_to_drama import production as base
from app.skills.models import ArtifactType


def media_path(db: Session, project_id: str, reference_id: str) -> Path:
    base._require_project(db, project_id)
    reference = reference_id.strip()
    if not reference:
        raise AppError("SCRIPT_TO_DRAMA_MEDIA_NOT_FOUND", "媒体引用不能为空", status_code=404)

    reference_row: dict | None = None
    for kind, key in (
        (ArtifactType.TARGET_ASSET_IMAGES, "assets"),
        (ArtifactType.GENERATED_VIDEO, "clips"),
        (ArtifactType.FINAL_OUTPUT, "final"),
    ):
        artifact = base._current(db, project_id, kind)
        if artifact is None:
            continue
        content = base._content(db, artifact)
        if key == "assets":
            for asset in content.get("assets", []):
                for media in asset.get("media", []):
                    if media.get("reference_id") == reference:
                        reference_row = media
                        break
                if reference_row is not None:
                    break
        elif key == "clips":
            for clip in content.get("clips", []):
                if clip.get("generation_segment_id") == reference:
                    reference_row = clip
                    break
        elif reference == "final":
            reference_row = content
        if reference_row is not None:
            break

    if reference_row is None:
        raise AppError("SCRIPT_TO_DRAMA_MEDIA_NOT_FOUND", "当前版本没有对应媒体", status_code=404)
    relpath = str(reference_row.get("storage_relpath") or "")
    expected_sha = str(reference_row.get("sha256") or "")
    root = get_settings().artifact_root.resolve()
    output = (root / relpath).resolve()
    if not relpath or root not in output.parents or not output.is_file():
        raise AppError("SCRIPT_TO_DRAMA_MEDIA_NOT_FOUND", "当前媒体文件不存在", status_code=404)
    if base._file_sha(output) != expected_sha:
        raise AppError("SCRIPT_TO_DRAMA_MEDIA_CHANGED", "媒体文件与正式版本不一致", status_code=409)
    return output
