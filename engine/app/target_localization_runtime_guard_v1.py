"""Runtime guard for automatic TargetCharacter / SceneLocalization generation.

Infrastructure/model failure must never be converted into blank human work.  The core R4
service intentionally remains responsible for domain persistence; this guard is used by
product entry points to distinguish a genuine low-confidence proposal from "the model did
not produce a proposal at all".
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import select

from engine.app.asset_semantics_v3 import semantic_model_status
from engine.app.remake_policy_v1 import get_project_remake_policy
from engine.app.review_issue_v1 import ReviewIssue
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import get_session, utcnow
from engine.app.target_localization_v1 import SceneLocalizationMapping, TargetCharacter


DEFAULT_TARGET_NAME = "待确认目标角色"
DEFAULT_APPEARANCE_PREFIX = "等待本地模型"
DEFAULT_PROMPT_PREFIX = "等待目标人物"


class TargetLocalizationRuntimeUnavailable(RuntimeError):
    """Automatic localization cannot run because the local model/runtime did not deliver."""


def _json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _is_placeholder_character(row: TargetCharacter) -> bool:
    return bool(
        row.decision_source == "AI"
        and row.status == "REVIEW"
        and (
            row.target_name == DEFAULT_TARGET_NAME
            or row.appearance_profile.startswith(DEFAULT_APPEARANCE_PREFIX)
            or row.generation_prompt.startswith(DEFAULT_PROMPT_PREFIX)
        )
    )


def _resolve_issue(row: ReviewIssue, reason: str) -> None:
    now = utcnow()
    row.status = "RESOLVED"
    row.resolution_json = json.dumps({"automatic": True, "reason": reason}, ensure_ascii=False)
    row.resolved_at = now
    row.updated_at = now


def cleanup_automatic_localization_placeholders_v1(project_id: str) -> int:
    """Remove old blank AI placeholders so they disappear from Review Center immediately."""

    removed_ids: set[str] = set()
    with get_session() as session:
        character_rows = session.scalars(select(TargetCharacter).where(
            TargetCharacter.project_id == project_id,
            TargetCharacter.status == "REVIEW",
            TargetCharacter.decision_source == "AI",
        )).all()
        for row in character_rows:
            if _is_placeholder_character(row):
                removed_ids.add(row.id)
                session.delete(row)

        issue_rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.issue_type.in_(("TARGET_CHARACTER", "SCENE_LOCALIZATION")),
        )).all()
        for issue in issue_rows:
            editable = _json(issue.editable_payload_json)
            if editable.get("decision_source") != "AI":
                continue
            domain_id = str(editable.get("id") or "")
            no_proposal = issue.ai_suggestion_json is None
            character_placeholder = issue.issue_type == "TARGET_CHARACTER" and (
                domain_id in removed_ids
                or editable.get("target_name") == DEFAULT_TARGET_NAME
                or str(editable.get("appearance_profile") or "").startswith(DEFAULT_APPEARANCE_PREFIX)
                or str(editable.get("generation_prompt") or "").startswith(DEFAULT_PROMPT_PREFIX)
            )
            scene_placeholder = bool(
                issue.issue_type == "SCENE_LOCALIZATION"
                and no_proposal
                and str(editable.get("decision") or "") == "REVIEW"
                and not editable.get("target_label")
                and not editable.get("target_description")
            )
            if not (character_placeholder or scene_placeholder):
                continue
            if scene_placeholder and domain_id:
                mapping = session.get(SceneLocalizationMapping, domain_id)
                if mapping is not None and mapping.decision_source == "AI" and mapping.status == "REVIEW":
                    removed_ids.add(mapping.id)
                    session.delete(mapping)
            _resolve_issue(issue, "自动模型未生成实际方案，属于系统运行状态，不进入人工待确认")

        if removed_ids or any(row.status == "RESOLVED" for row in issue_rows):
            session.commit()
    return len(removed_ids)


def require_target_localization_runtime_v1(project_id: str) -> dict[str, Any]:
    """Fail before R4 writes blank placeholders when a model is actually required."""

    snapshot = load_project_source_drama_snapshot_v1(project_id)
    policy = str((get_project_remake_policy(project_id) or {}).get("scene_policy") or "AUTO")
    has_characters = bool(snapshot.get("characters") or [])
    has_scenes = any(
        bool(episode.get("scenes") or [])
        for episode in snapshot.get("episodes") or []
        if isinstance(episode, Mapping)
    )
    needs_model = has_characters or (policy != "KEEP" and has_scenes)
    status = dict(semantic_model_status() or {})
    if needs_model and not status.get("ready"):
        cleanup_automatic_localization_placeholders_v1(project_id)
        raise TargetLocalizationRuntimeUnavailable(
            "目标人物/场景自动设计需要本地 Qwen3-VL，但当前模型服务未就绪；请恢复模型服务后重新自动处理"
        )
    return status


def validate_target_localization_generation_v1(project_id: str, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Reject silent model-call failure after R4 returns.

    Low-confidence proposals remain legitimate REVIEW items. Only AI REVIEW rows with no
    actual proposal/default placeholder text are classified as runtime failure.
    """

    missing_proposal = False
    for item in bundle.get("target_characters") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") != "REVIEW" or item.get("decision_source") != "AI":
            continue
        if (
            item.get("target_name") == DEFAULT_TARGET_NAME
            or str(item.get("appearance_profile") or "").startswith(DEFAULT_APPEARANCE_PREFIX)
            or str(item.get("generation_prompt") or "").startswith(DEFAULT_PROMPT_PREFIX)
        ):
            missing_proposal = True
            break

    if not missing_proposal:
        with get_session() as session:
            issues = session.scalars(select(ReviewIssue).where(
                ReviewIssue.project_id == project_id,
                ReviewIssue.status == "OPEN",
                ReviewIssue.issue_type.in_(("TARGET_CHARACTER", "SCENE_LOCALIZATION")),
                ReviewIssue.ai_suggestion_json.is_(None),
            )).all()
            for issue in issues:
                editable = _json(issue.editable_payload_json)
                if editable.get("decision_source") == "AI":
                    missing_proposal = True
                    break

    if missing_proposal:
        cleanup_automatic_localization_placeholders_v1(project_id)
        raise TargetLocalizationRuntimeUnavailable(
            "本地 Qwen3-VL 已启动，但本次目标人物/场景自动设计没有返回可用方案；未生成的内容不会转成人工填写任务"
        )
    return dict(bundle)


__all__ = [
    "TargetLocalizationRuntimeUnavailable",
    "cleanup_automatic_localization_placeholders_v1",
    "require_target_localization_runtime_v1",
    "validate_target_localization_generation_v1",
]
