"""Read-only Character V10 classified Person Evidence API.

The asset UI needs three deliberately separate layers:
- CharacterTrack rows: exhaustive persisted AI identity evidence by Shot;
- Gallery images: a bounded/diversified subset used as strong identity representatives;
- Final ShotCharacterBinding: owned by the Asset workspace and not modified here.

For visual comparison the JSON endpoint exposes every persisted evidence Shot. If a
Shot was not selected into the bounded Gallery, the API adds one on-demand crop from
that Shot's persisted CharacterTrack representative. This keeps the UI exhaustive
without pretending the model Gallery itself is exhaustive.

Human-facing Shot labels are always resolved from `v2_shots.ordinal`; UUID suffixes
are never Shot numbers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import select

from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack
from engine.app.studio_v2 import Episode, Shot, get_session

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


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _shot_context_for_ids(shot_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = {str(value) for value in shot_ids if value}
    if not ids:
        return {}
    with get_session() as session:
        shots = list(session.scalars(select(Shot).where(Shot.id.in_(ids))).all())
        episode_ids = {shot.episode_id for shot in shots}
        episodes = list(session.scalars(select(Episode).where(Episode.id.in_(episode_ids))).all()) if episode_ids else []
    episode_order = {episode.id: episode.sort_order for episode in episodes}
    return {
        shot.id: {
            "shot_ordinal": shot.ordinal,
            "episode_id": shot.episode_id,
            "episode_order": episode_order.get(shot.episode_id),
        }
        for shot in shots
    }


def _gallery_shot_ids(manifest: dict[str, Any]) -> set[str]:
    return {
        str(raw.get("shot_id"))
        for raw in (manifest.get("images") or [])
        if isinstance(raw, dict) and raw.get("shot_id")
    }


def _candidate_tracks(candidate_id: str) -> list[CharacterTrack]:
    with get_session() as session:
        tracks = list(session.scalars(
            select(CharacterTrack).where(CharacterTrack.candidate_id == candidate_id)
        ).all())
        for track in tracks:
            session.expunge(track)
    return tracks


def _representative_tracks_by_shot(tracks: list[CharacterTrack]) -> dict[str, CharacterTrack]:
    result: dict[str, CharacterTrack] = {}
    for track in tracks:
        shot_id = str(track.shot_id)
        current = result.get(shot_id)
        if current is None or (int(track.sample_count or 0), int(track.representative_source_us or 0)) > (
            int(current.sample_count or 0), int(current.representative_source_us or 0)
        ):
            result[shot_id] = track
    return result


def _evidence_shots(tracks: list[CharacterTrack], context_by_shot: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return exhaustive persisted CharacterTrack Shot membership for one Candidate."""

    by_shot: dict[str, dict[str, Any]] = {}
    for track in tracks:
        shot_id = str(track.shot_id)
        row = by_shot.setdefault(shot_id, {
            "shot_id": shot_id,
            "track_count": 0,
            "sample_count": 0,
            "recovered_track_count": 0,
            "recovery_sources": set(),
        })
        row["track_count"] += 1
        row["sample_count"] += int(track.sample_count or 0)
        recovery = _json(track.evidence_json).get("identity_recovery")
        if isinstance(recovery, dict) and recovery:
            row["recovered_track_count"] += 1
            source = recovery.get("source")
            if source:
                row["recovery_sources"].add(str(source))

    result: list[dict[str, Any]] = []
    for shot_id, row in by_shot.items():
        context = context_by_shot.get(shot_id, {})
        result.append({
            "shot_id": shot_id,
            "shot_ordinal": context.get("shot_ordinal"),
            "episode_id": context.get("episode_id"),
            "episode_order": context.get("episode_order"),
            "track_count": row["track_count"],
            "sample_count": row["sample_count"],
            "recovered_track_count": row["recovered_track_count"],
            "recovery_sources": sorted(row["recovery_sources"]),
        })

    result.sort(key=lambda item: (
        item.get("episode_order") if item.get("episode_order") is not None else 999999,
        item.get("shot_ordinal") if item.get("shot_ordinal") is not None else 999999,
        item["shot_id"],
    ))
    return result


def _track_evidence_image(candidate_id: str, track: CharacterTrack, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": -1,
        "url": f"/api/content-analysis/characters/{candidate_id}/evidence-shot/{track.shot_id}",
        "source_kind": "track_representative",
        "shot_id": str(track.shot_id),
        "shot_ordinal": context.get("shot_ordinal"),
        "episode_id": context.get("episode_id"),
        "episode_order": context.get("episode_order"),
        "source_time_us": int(track.representative_source_us),
        "instance_id": None,
        "instance_class": None,
        "quality": None,
        "reliability": None,
        "seed_eligible": None,
        "face_visible": bool(track.face_visible),
        "feature_channels": [],
    }


@router.get("/{candidate_id}/gallery")
def get_character_gallery(candidate_id: str) -> dict[str, Any]:
    candidate, _root, manifest = _manifest(candidate_id)
    tracks = _candidate_tracks(candidate_id)
    track_shot_ids = {str(track.shot_id) for track in tracks}
    gallery_shot_ids = _gallery_shot_ids(manifest)
    context_by_shot = _shot_context_for_ids(track_shot_ids | gallery_shot_ids)
    evidence_shots = _evidence_shots(tracks, context_by_shot)

    images: list[dict[str, Any]] = []
    for index, raw in enumerate(manifest.get("images") or []):
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("shot_id")) if raw.get("shot_id") else None
        context = context_by_shot.get(shot_id or "", {})
        images.append({
            "index": index,
            "url": f"/api/content-analysis/characters/{candidate_id}/gallery/{index}",
            "source_kind": "gallery",
            "shot_id": shot_id,
            "shot_ordinal": context.get("shot_ordinal", raw.get("shot_ordinal")),
            "episode_id": context.get("episode_id", raw.get("episode_id")),
            "episode_order": context.get("episode_order", raw.get("episode_order")),
            "source_time_us": raw.get("source_time_us"),
            "instance_id": raw.get("instance_id"),
            "instance_class": raw.get("instance_class"),
            "quality": raw.get("quality"),
            "reliability": raw.get("reliability"),
            "seed_eligible": raw.get("seed_eligible"),
            "face_visible": raw.get("face_visible"),
            "feature_channels": raw.get("feature_channels") or [],
        })

    # Gallery selection is intentionally bounded. Add one real persisted Track crop only
    # for evidence Shots that otherwise have no visual representative in this response.
    representatives = _representative_tracks_by_shot(tracks)
    missing_shots = track_shot_ids - {str(item["shot_id"]) for item in images if item.get("shot_id")}
    for shot_id in sorted(missing_shots, key=lambda value: (
        context_by_shot.get(value, {}).get("episode_order") or 999999,
        context_by_shot.get(value, {}).get("shot_ordinal") or 999999,
        value,
    )):
        track = representatives.get(shot_id)
        if track is not None:
            images.append(_track_evidence_image(candidate_id, track, context_by_shot.get(shot_id, {})))

    return {
        "candidate_id": candidate.id,
        "identity_status": manifest.get("identity_status"),
        "policy": manifest.get("policy"),
        "evidence_shot_count": len(evidence_shots),
        "evidence_shots": evidence_shots,
        "gallery_image_count": sum(1 for item in images if item.get("source_kind") == "gallery"),
        "image_count": len(images),
        "images": images,
    }


@router.get("/{candidate_id}/evidence-shot/{shot_id}")
def get_character_track_evidence_image(candidate_id: str, shot_id: str) -> Response:
    tracks = [track for track in _candidate_tracks(candidate_id) if str(track.shot_id) == shot_id]
    if not tracks:
        raise HTTPException(status_code=404, detail="人物 Shot Evidence 不存在")
    track = max(tracks, key=lambda item: (int(item.sample_count or 0), int(item.representative_source_us or 0)))

    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            raise HTTPException(status_code=404, detail="Shot 不存在")
        reference_path = str(shot.reference_clip_path)
        local_time_us = max(0, int(track.representative_source_us) - int(shot.start_us))

    try:
        bbox_value = json.loads(track.bbox_json or "[]")
        x, y, width, height = [int(value) for value in bbox_value[:4]]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="人物 Track bbox 损坏") from exc

    from engine.app import character_visual_v5 as v5
    frame = v5._read_frame(reference_path, local_time_us)
    if frame is None:
        raise HTTPException(status_code=404, detail="人物 Shot Evidence 帧不可读取")
    frame_height, frame_width = frame.shape[:2]
    left = max(0, min(x, frame_width - 1))
    top = max(0, min(y, frame_height - 1))
    right = max(left + 1, min(frame_width, x + max(1, width)))
    bottom = max(top + 1, min(frame_height, y + max(1, height)))
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        raise HTTPException(status_code=404, detail="人物 Shot Evidence crop 为空")

    import cv2
    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise HTTPException(status_code=500, detail="人物 Shot Evidence 图片编码失败")
    return Response(content=encoded.tobytes(), media_type="image/jpeg")


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
