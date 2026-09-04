"""Automatic target reference assets for R8 H3 generation.

TargetCharacter text design is not enough to keep cast identity stable when Ref2VA also sees
source actors. This module uses the local H3 FL2VA service in text-to-video mode to generate
one deterministic casting reference clip per current TargetCharacter and one empty environment
reference per localized Scene, then extracts reusable still images. These are runtime assets,
not new product pages.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.studio_v2 import get_session, project_dir, utcnow
from engine.app.target_localization_v1 import TargetCharacter, get_target_localization_v1
from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1


class H3ReferenceAssetError(RuntimeError):
    pass


CHARACTER_REFERENCE_PROFILE = "H3_TARGET_CHARACTER_REFERENCE_V1"
SCENE_REFERENCE_PROFILE = "H3_TARGET_SCENE_REFERENCE_V1"


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _full_character_mapping(character: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalize both full TargetCharacter rows and compact GenerationSegment contexts."""

    target_id = str(character.get("id") or character.get("target_character_id") or "").strip()
    if not target_id:
        return None
    required = {
        "project_id",
        "target_language",
        "target_region",
        "target_name",
        "appearance_profile",
        "generation_prompt",
    }
    if all(character.get(key) for key in required):
        return {**dict(character), "id": target_id}
    with get_session() as session:
        row = session.get(TargetCharacter, target_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "project_id": row.project_id,
            "target_language": row.target_language,
            "target_region": row.target_region,
            "target_name": row.target_name,
            "appearance_profile": row.appearance_profile,
            "generation_prompt": row.generation_prompt,
        }


def target_character_reference_signature_v1(character: Mapping[str, Any]) -> str:
    normalized = _full_character_mapping(character) or dict(character)
    return _digest({
        "profile": CHARACTER_REFERENCE_PROFILE,
        "id": normalized.get("id") or normalized.get("target_character_id"),
        "target_language": normalized.get("target_language"),
        "target_region": normalized.get("target_region"),
        "target_name": normalized.get("target_name"),
        "appearance_profile": normalized.get("appearance_profile"),
        "generation_prompt": normalized.get("generation_prompt"),
    })


def target_scene_reference_signature_v1(scene: Mapping[str, Any], *, target_region: str) -> str:
    return _digest({
        "profile": SCENE_REFERENCE_PROFILE,
        "id": scene.get("id"),
        "decision": scene.get("decision"),
        "target_region": target_region,
        "target_label": scene.get("target_label"),
        "target_description": scene.get("target_description"),
    })


def _ffmpeg(command: list[str], *, timeout_seconds: int = 900) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise H3ReferenceAssetError("找不到 ffmpeg，请先把 FFmpeg 加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise H3ReferenceAssetError("参考资产 FFmpeg 处理超时") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-3000:]
        raise H3ReferenceAssetError(f"参考资产 FFmpeg 处理失败：{detail}") from exc


def _extract_frame(video: Path, seconds: float, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([
        "ffmpeg", "-y", "-ss", f"{max(0.0, seconds):.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", "scale=min(1280\\,iw):-2", "-q:v", "2", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise H3ReferenceAssetError("H3 参考视频未能抽出有效参考帧")
    return output


def _wait_for_job(provider: Any, *, mode: str, job_id: str) -> None:
    timeout = max(60.0, float(os.getenv("AI_DRAMA_H3_REFERENCE_TIMEOUT", "1800")))
    interval = max(1.0, float(os.getenv("AI_DRAMA_H3_POLL_INTERVAL", "3")))
    deadline = time.monotonic() + timeout
    while True:
        status = provider.get_status(mode=mode, external_job_id=job_id)
        if status.terminal:
            if status.succeeded:
                return
            raise H3ReferenceAssetError(status.error_message or f"H3 参考资产生成失败：{status.provider_status}")
        if time.monotonic() >= deadline:
            raise H3ReferenceAssetError("H3 参考资产生成等待超时")
        time.sleep(interval)


def _read_meta(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def current_target_character_reference_assets_v1(character: Mapping[str, Any]) -> list[Path]:
    selected = selected_four_view_references(character)
    if selected is not None:
        return selected
    normalized = _full_character_mapping(character)
    if normalized is None:
        return []
    project_id = str(normalized["project_id"])
    target_id = str(normalized["id"])
    signature = target_character_reference_signature_v1(normalized)
    root = project_dir(project_id) / "target" / "h3" / "reference-characters" / target_id / signature[:16]
    meta = _read_meta(root / "metadata.json")
    if not meta or meta.get("signature") != signature:
        return []
    paths = [Path(str(item)) for item in meta.get("images") or []]
    return [path for path in paths if path.is_file() and path.stat().st_size > 0]


def selected_four_view_references(character: Mapping[str, Any]) -> list[Path] | None:
    """Once a user starts the four-view workflow, only an accepted current version is usable."""
    from sqlalchemy import select
    from engine.app.task_progress_v2 import BackgroundTaskRecord
    target_id = str(character.get("id") or character.get("target_character_id") or "")
    found = False
    with get_session() as session:
        for task in session.scalars(select(BackgroundTaskRecord).where(BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS")).all():
            receipt = json.loads(task.result_json or "{}")
            if receipt.get("target_id") != target_id:
                continue
            found = True
            if task.status != "READY" or not receipt.get("accepted"):
                continue
            from engine.app.character_assets_routes_v1 import require_current, signature, version_root, VIEWS
            try:
                current = require_current(target_id)
            except Exception:
                return []
            if signature(current) != receipt.get("fingerprint"):
                continue
            paths = [version_root(task.project_id, task.id) / f"{view}.jpg" for view in VIEWS]
            if all(p.is_file() and p.stat().st_size for p in paths):
                return paths
    return [] if found else None


def current_target_scene_reference_asset_v1(scene: Mapping[str, Any], *, target_region: str) -> Path | None:
    if str(scene.get("decision") or "") != "LOCALIZE":
        return None
    project_id = str(scene.get("project_id") or "")
    mapping_id = str(scene.get("id") or "")
    if not project_id or not mapping_id:
        return None
    signature = target_scene_reference_signature_v1(scene, target_region=target_region)
    root = project_dir(project_id) / "target" / "h3" / "reference-scenes" / mapping_id / signature[:16]
    meta = _read_meta(root / "metadata.json")
    if not meta or meta.get("signature") != signature:
        return None
    image = Path(str(meta.get("image") or ""))
    return image if image.is_file() and image.stat().st_size > 0 else None


def _character_prompt(character: Mapping[str, Any]) -> str:
    name = str(character.get("target_name") or "Target Character")
    appearance = str(character.get("appearance_profile") or "").strip()
    generation = str(character.get("generation_prompt") or "").strip()
    return (
        "integrated_multimodal_description: [Shot 1] Live-action neutral casting reference for a fictional drama character. "
        f"{name}: {appearance}. {generation}. Show exactly one person against a simple neutral studio background. "
        "Begin with a natural three-quarter full-body standing pose, then make a slow quarter turn and finish in a calm medium close-up. "
        "Keep the same facial identity, hair, body proportions, skin details, clothing design and age throughout the entire shot. "
        "No other person enters. No speaking; lips stay closed. No text or logos. The camera moves slowly and steadily with no cuts.\n\n"
        "overall_soundscape: Quiet neutral room tone only.\n\n"
        "non_diegetic_music: N/A"
    )


def _scene_prompt(scene: Mapping[str, Any], *, target_region: str) -> str:
    label = str(scene.get("target_label") or scene.get("source_scene_name") or "localized environment")
    description = str(scene.get("target_description") or "").strip()
    return (
        "integrated_multimodal_description: [Shot 1] Live-action empty environment reference for a localized short-drama set. "
        f"Target region: {target_region}. Location: {label}. {description}. "
        "Show the complete usable acting space, entrances, exits, furniture and major practical light sources. "
        "No people, faces, readable text, subtitles or logos. Preserve realistic production-design detail. "
        "The camera makes a very slow small-amplitude push in with no cut so the environment remains easy to reuse as a visual reference.\n\n"
        "overall_soundscape: Quiet natural room or location ambience only.\n\n"
        "non_diegetic_music: N/A"
    )


def _submit_reference_video(*, prompt: str, seed: int, destination: Path) -> Path:
    provider = get_video_generation_provider_v1("MINIMAX_H3_LOCAL")
    status = provider.status()
    if not bool((status.get("fl2va") or {}).get("ready")):
        raise H3ReferenceAssetError("本地 MiniMax H3 FL2VA Runtime 尚未 READY")
    request = VideoGenerationRequestV1.model_validate({
        "provider": "MINIMAX_H3_LOCAL",
        "mode": "FL2VA",
        "prompt": prompt,
        "conditions": [],
        "duration_seconds": 4,
        "short_edge": 768,
        "aspect_ratio": "9:16",
        "seed": seed,
    })
    submission = provider.submit(request)
    _wait_for_job(provider, mode="FL2VA", job_id=submission.external_job_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return provider.download(
        mode="FL2VA",
        external_job_id=submission.external_job_id,
        destination=destination,
    )


def ensure_target_character_references_v1(project_id: str) -> dict[str, Any]:
    bundle = get_target_localization_v1(project_id)
    generated = 0
    reused = 0
    failed: list[dict[str, str]] = []
    for character in bundle.get("target_characters") or []:
        if not isinstance(character, Mapping) or character.get("status") != "READY":
            continue
        current = current_target_character_reference_assets_v1(character)
        if current:
            reused += 1
            continue
        if selected_four_view_references(character) is not None:
            failed.append({"target_character_id": str(character["id"]), "error": "请先审核并采用当前目标人物四视图"})
            continue
        signature = target_character_reference_signature_v1(character)
        target_id = str(character["id"])
        root = project_dir(project_id) / "target" / "h3" / "reference-characters" / target_id / signature[:16]
        video = root / "reference.mp4"
        images = [root / "front.jpg", root / "three-quarter.jpg", root / "close.jpg"]
        try:
            _submit_reference_video(
                prompt=_character_prompt(character),
                seed=int(signature[:8], 16) & 0x7FFFFFFF,
                destination=video,
            )
            _extract_frame(video, 0.45, images[0])
            _extract_frame(video, 1.85, images[1])
            _extract_frame(video, 3.35, images[2])
            meta = {
                "profile": CHARACTER_REFERENCE_PROFILE,
                "signature": signature,
                "video": str(video),
                "images": [str(path) for path in images],
                "created_at": utcnow().isoformat(),
            }
            root.mkdir(parents=True, exist_ok=True)
            (root / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            with get_session() as session:
                row = session.get(TargetCharacter, target_id)
                if row is not None:
                    row.reference_assets_json = json.dumps([str(path) for path in images], ensure_ascii=False)
                    row.updated_at = utcnow()
                    session.commit()
            generated += 1
        except Exception as exc:
            failed.append({"target_character_id": target_id, "error": str(exc)})
    return {"generated": generated, "reused": reused, "failed": failed}


def ensure_target_scene_references_v1(project_id: str) -> dict[str, Any]:
    bundle = get_target_localization_v1(project_id)
    region = str(bundle.get("target_region") or "")
    generated = 0
    reused = 0
    failed: list[dict[str, str]] = []
    for scene in bundle.get("scene_mappings") or []:
        if not isinstance(scene, Mapping) or scene.get("status") != "READY" or scene.get("decision") != "LOCALIZE":
            continue
        if current_target_scene_reference_asset_v1(scene, target_region=region) is not None:
            reused += 1
            continue
        signature = target_scene_reference_signature_v1(scene, target_region=region)
        mapping_id = str(scene["id"])
        root = project_dir(project_id) / "target" / "h3" / "reference-scenes" / mapping_id / signature[:16]
        video = root / "reference.mp4"
        image = root / "scene.jpg"
        try:
            _submit_reference_video(
                prompt=_scene_prompt(scene, target_region=region),
                seed=int(signature[:8], 16) & 0x7FFFFFFF,
                destination=video,
            )
            _extract_frame(video, 2.0, image)
            meta = {
                "profile": SCENE_REFERENCE_PROFILE,
                "signature": signature,
                "video": str(video),
                "image": str(image),
                "created_at": utcnow().isoformat(),
            }
            root.mkdir(parents=True, exist_ok=True)
            (root / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            generated += 1
        except Exception as exc:
            failed.append({"scene_mapping_id": mapping_id, "error": str(exc)})
    return {"generated": generated, "reused": reused, "failed": failed}


__all__ = [
    "H3ReferenceAssetError",
    "current_target_character_reference_assets_v1",
    "current_target_scene_reference_asset_v1",
    "ensure_target_character_references_v1",
    "ensure_target_scene_references_v1",
    "target_character_reference_signature_v1",
    "target_scene_reference_signature_v1",
]
