"""Character-only target localization planning for the character asset workspace.

This module deliberately reuses target_localization_v1's character context/prompt/upsert
implementation. It does not create a second TargetCharacter authority and it never touches
scene localization mappings.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import select

from engine.app.local_qwen_text_v1 import local_qwen_text_runtime_status
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.source_person_assets_v1 import LOCK, inventory
from engine.app.studio_v2 import Project, get_session
from engine.app.target_localization_v1 import (
    TargetCharacter,
    TargetLocalizationError,
    _character_contexts,
    _character_prompt,
    _request_text_model_many,
    _upsert_character_rows,
)


def _design_digest(row: TargetCharacter) -> str:
    payload = {
        "source_character_signature": row.source_character_signature,
        "target_language": row.target_language,
        "target_region": row.target_region,
        "target_name": row.target_name,
        "appearance_profile": row.appearance_profile,
        "generation_prompt": row.generation_prompt,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _character_proposals(
    contexts: list[dict[str, Any]],
    *,
    target_language: str,
    target_region: str,
) -> dict[str, Mapping[str, Any]]:
    if not contexts:
        return {}

    runtime = local_qwen_text_runtime_status()
    if not runtime.get("ready"):
        missing = [str(item) for item in runtime.get("missing") or [] if str(item).strip()]
        detail = f"；缺少：{'、'.join(missing)}" if missing else ""
        raise TargetLocalizationError(
            "目标人物自动设计 Qwen3-VL 运行时未就绪；程序会复用拉片阶段的本地模型"
            f"{detail}"
        )

    chunks = [contexts[offset : offset + 12] for offset in range(0, len(contexts), 12)]
    prompts = [
        _character_prompt(chunk, target_language, target_region)
        for chunk in chunks
    ]
    raw_results = _request_text_model_many(prompts)
    if len(raw_results) != len(chunks):
        raise TargetLocalizationError("目标人物模型批量返回数量与请求不一致")

    proposals: dict[str, Mapping[str, Any]] = {}
    for raw in raw_results:
        for item in raw.get("characters") or []:
            if isinstance(item, Mapping) and item.get("source_character_id"):
                proposals[str(item["source_character_id"])] = item

    expected = {str(item["source_character_id"]) for item in contexts}
    missing_ids = sorted(expected - set(proposals))
    if missing_ids:
        raise TargetLocalizationError(
            f"目标人物模型输出不完整，缺少 {len(missing_ids)} 个人物；本次不写入不完整设计"
        )
    return proposals


def generate_target_characters_only_v1(project_id: str, *, expected_revision: str) -> dict[str, Any]:
    """Generate/update target character text designs without running scene localization.

    The source-person revision and SourceDramaSnapshot fingerprint are checked both before and
    after the model call. Manual target designs are preserved by _upsert_character_rows.
    """

    current = inventory(project_id)
    if current["revision"] != expected_revision:
        raise ValueError("原片人物已变化，请刷新人物资产后重新自动设计")

    snapshot = load_project_source_drama_snapshot_v1(project_id)
    source_fingerprint = str(snapshot["source_fingerprint"])
    contexts = _character_contexts(snapshot)

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        target_language = project.target_language
        target_region = project.target_region
        session.expunge(project)

    proposals = _character_proposals(
        contexts,
        target_language=target_language,
        target_region=target_region,
    )

    with LOCK:
        if inventory(project_id)["revision"] != expected_revision:
            raise ValueError("自动设计期间原片人物发生变化，本次结果未写入，请刷新后重试")
        latest_snapshot = load_project_source_drama_snapshot_v1(project_id)
        if str(latest_snapshot["source_fingerprint"]) != source_fingerprint:
            raise ValueError("自动设计期间原片快照发生变化，本次结果未写入，请刷新后重试")

        with get_session() as session:
            before = {
                row.source_character_id: _design_digest(row)
                for row in session.scalars(
                    select(TargetCharacter).where(TargetCharacter.project_id == project_id)
                ).all()
            }

        rows = _upsert_character_rows(project, source_fingerprint, contexts, proposals)

        # Any changed text/source design invalidates previously selected reference images.
        # Four-view task receipts remain as history, but their fingerprint will no longer be current.
        with get_session() as session:
            changed = False
            for row in session.scalars(
                select(TargetCharacter).where(TargetCharacter.project_id == project_id)
            ).all():
                old_digest = before.get(row.source_character_id)
                if old_digest is not None and old_digest != _design_digest(row) and row.reference_assets_json != "[]":
                    row.reference_assets_json = "[]"
                    changed = True
            if changed:
                session.commit()

    review_count = sum(item.get("status") == "REVIEW" for item in rows)
    return {
        "status": "REVIEW" if review_count else "READY",
        "target_character_count": len(rows),
        "review_count": review_count,
        "source_fingerprint": source_fingerprint,
    }


__all__ = ["generate_target_characters_only_v1"]
