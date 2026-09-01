"""Translate existing automatic QC signals into the unified ReviewIssue queue."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.studio_v2 import get_session, list_episode_records, list_shots, utcnow

SHOT_PREFIX = "auto:shot:"
ASSET_PREFIX = "auto:asset:"


def _boundary_meta(shot: dict[str, Any]) -> dict[str, Any]:
    for item in shot.get("keyframes") or []:
        if isinstance(item, dict) and item.get("kind") == "boundary_meta":
            return item
    return {}


def _shot_problem(shot: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    meta = _boundary_meta(shot)
    reasons = [str(item) for item in (meta.get("review_reasons") or []) if str(item).strip()]
    duration_us = int(shot.get("duration_us") or 0)
    confidence = meta.get("confidence")
    if duration_us < 500_000 and not any("极短" in item for item in reasons):
        reasons.append("镜头过短（少于 0.5 秒）")
    if isinstance(confidence, (int, float)) and float(confidence) < 0.68:
        reasons.append(f"镜头边界可信度较低（{round(float(confidence) * 100)}%）")
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        return None
    return "；".join(reasons), {
        "start_us": shot.get("start_us"),
        "end_us": shot.get("end_us"),
        "duration_us": duration_us,
        "reference_url": shot.get("reference_url"),
        "thumbnail_url": shot.get("thumbnail_url"),
        "confidence": confidence,
    }


def _confidence(item: dict[str, Any] | None, threshold: float) -> bool:
    if not item or not item.get("final_asset_id"):
        return False
    value = item.get("confidence")
    return isinstance(value, (int, float)) and float(value) >= threshold


def _asset_problem(evidence: dict[str, Any], binding: dict[str, Any]) -> str | None:
    characters = [item for item in (evidence.get("characters") or []) if isinstance(item, dict)]
    props = [item for item in (evidence.get("props") or []) if isinstance(item, dict)]
    scene = evidence.get("scene") if isinstance(evidence.get("scene"), dict) else None
    character_ids = set(str(item) for item in (binding.get("character_ids") or []))
    prop_ids = set(str(item) for item in (binding.get("prop_ids") or []))
    scene_id = str(binding.get("scene_id") or "") or None

    strong_characters = [item for item in characters if _confidence(item, 0.75)]
    strong_props = [item for item in props if _confidence(item, 0.8)]
    strong_scene = scene if _confidence(scene, 0.75) else None

    if not character_ids and strong_characters:
        return "检测到高置信度人物，但当前镜头还没有最终人物绑定"
    if scene_id is None and strong_scene:
        return "检测到高置信度场景，但当前镜头还没有最终场景绑定"
    if character_ids and any(str(item.get("final_asset_id")) not in character_ids for item in strong_characters):
        return "人物识别建议与当前最终人物绑定冲突"
    if scene_id and strong_scene and str(strong_scene.get("final_asset_id")) != scene_id:
        return "场景识别建议与当前最终场景绑定冲突"
    if prop_ids and any(str(item.get("final_asset_id")) not in prop_ids for item in strong_props):
        return "道具识别建议与当前最终道具绑定冲突"

    low_character = any(
        isinstance(item.get("confidence"), (int, float))
        and float(item["confidence"]) < 0.75
        and item.get("final_asset_id")
        and str(item["final_asset_id"]) not in character_ids
        for item in characters
    )
    low_scene = bool(
        scene
        and isinstance(scene.get("confidence"), (int, float))
        and float(scene["confidence"]) < 0.75
        and scene.get("final_asset_id")
        and str(scene["final_asset_id"]) != str(scene_id or "")
    )
    low_prop = any(
        isinstance(item.get("confidence"), (int, float))
        and float(item["confidence"]) < 0.75
        and item.get("final_asset_id")
        and str(item["final_asset_id"]) not in prop_ids
        for item in props
    )
    if low_character or low_scene or low_prop:
        return "存在低置信度人物 / 场景 / 道具建议，需要人工确认"
    return None


def _auto_resolve_missing(project_id: str, prefix: str, active_keys: set[str]) -> None:
    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.source_key.like(f"{prefix}%"),
        )).all()
        changed = False
        for row in rows:
            if row.source_key in active_keys:
                continue
            row.status = "RESOLVED"
            row.resolution_json = '{"automatic":true,"reason":"自动结果已不再报告此问题"}'
            row.resolved_at = utcnow()
            row.updated_at = utcnow()
            changed = True
        if changed:
            session.commit()


def sync_shot_review_issues(project_id: str) -> int:
    active: set[str] = set()
    count = 0
    for episode in list_episode_records(project_id):
        for shot in list_shots(episode.id):
            problem = _shot_problem(shot)
            if problem is None:
                continue
            reason, payload = problem
            source_key = f"{SHOT_PREFIX}{shot['id']}"
            active.add(source_key)
            upsert_review_issue(
                project_id=project_id,
                episode_id=episode.id,
                shot_id=shot["id"],
                source_key=source_key,
                issue_type="SHOT_BOUNDARY",
                severity="REVIEW",
                reason=reason,
                editable_payload=payload,
            )
            count += 1
    _auto_resolve_missing(project_id, SHOT_PREFIX, active)
    return count


def sync_asset_review_issues(project_id: str, workspace: dict[str, Any]) -> int:
    active: set[str] = set()
    count = 0
    evidence_by_shot = workspace.get("evidence_by_shot") or {}
    bindings_by_shot = workspace.get("bindings_by_shot") or {}
    episode_by_shot: dict[str, str] = {}
    for episode in list_episode_records(project_id):
        for shot in list_shots(episode.id):
            episode_by_shot[shot["id"]] = episode.id

    for shot_id, evidence in evidence_by_shot.items():
        if not isinstance(evidence, dict):
            continue
        binding = bindings_by_shot.get(shot_id) or {"character_ids": [], "scene_id": None, "prop_ids": []}
        reason = _asset_problem(evidence, binding)
        if reason is None:
            continue
        source_key = f"{ASSET_PREFIX}{shot_id}"
        active.add(source_key)
        upsert_review_issue(
            project_id=project_id,
            episode_id=episode_by_shot.get(str(shot_id)),
            shot_id=str(shot_id),
            source_key=source_key,
            issue_type="ASSET_BINDING",
            severity="REVIEW",
            reason=reason,
            ai_suggestion=evidence,
            editable_payload=binding,
        )
        count += 1
    _auto_resolve_missing(project_id, ASSET_PREFIX, active)
    return count


__all__ = ["sync_asset_review_issues", "sync_shot_review_issues"]
