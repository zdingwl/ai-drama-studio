"""Read-only Character V10 classified Person Gallery API.

The asset library uses this API to show the actual isolated Person Instance crops
that the identity model classified to a Character.  Shot thumbnails remain a
separate concept: they show occurrence context, not identity gallery content.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from engine.app.content_analysis_v2 import CharacterCandidate
from engine.app.studio_v2 import get_session

router = APIRouter(prefix="/api/content-analysis/characters", tags=["character-v10-gallery"])


def _candidate(candidate_id: str) -> CharacterCandidate:
    with get_session() as session:
        candidate = session.get(CharacterCandidate, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="人物候选不存在")
        session.expunge(candidate)
        return candidate


def _gallery_root(candidate: CharacterCandidate) -> Path | None:
    if not candidate.cover_path:
        return None
    root = Path(candidate.cover_path).resolve().parent
    return root if root.is_dir() else None


def _manifest(candidate_id: str) -> tuple[CharacterCandidate, Path, dict[str, Any]]:
    candidate = _candidate(candidate_id)
    root = _gallery_root(candidate)
    if root is None:
        raise HTTPException(status_code=404, detail="人物 Gallery 不存在")
    path = root / "gallery.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="人物 Gallery 清单不存在")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="人物 Gallery 清单损坏") from exc
    if not isinstance(value, dict) or not isinstance(value.get("images"), list):
        raise HTTPException(status_code=500, detail="人物 Gallery 清单格式错误")
    return candidate, root, value


@router.get("/{candidate_id}/gallery")
def get_character_gallery(candidate_id: str) -> dict[str, Any]:
    candidate, _root, manifest = _manifest(candidate_id)
    images: list[dict[str, Any]] = []
    for index, raw in enumerate(manifest.get("images") or []):
        if not isinstance(raw, dict):
            continue
        images.append({
            "index": index,
            "url": f"/api/content-analysis/characters/{candidate_id}/gallery/{index}",
            "shot_id": raw.get("shot_id"),
            "source_time_us": raw.get("source_time_us"),
            "instance_id": raw.get("instance_id"),
            "instance_class": raw.get("instance_class"),
            "quality": raw.get("quality"),
            "reliability": raw.get("reliability"),
            "seed_eligible": raw.get("seed_eligible"),
            "face_visible": raw.get("face_visible"),
            "feature_channels": raw.get("feature_channels") or [],
        })
    return {
        "candidate_id": candidate.id,
        "identity_status": manifest.get("identity_status"),
        "policy": manifest.get("policy"),
        "image_count": len(images),
        "images": images,
    }


@router.get("/{candidate_id}/gallery/{image_index}")
def get_character_gallery_image(candidate_id: str, image_index: int) -> FileResponse:
    _candidate_row, root, manifest = _manifest(candidate_id)
    images = manifest.get("images") or []
    if image_index < 0 or image_index >= len(images):
        raise HTTPException(status_code=404, detail="人物 Gallery 图片不存在")
    raw = images[image_index]
    if not isinstance(raw, dict) or not raw.get("path"):
        raise HTTPException(status_code=404, detail="人物 Gallery 图片不存在")
    path = Path(str(raw["path"])).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="人物 Gallery 图片路径非法") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="人物 Gallery 图片文件不存在")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)
