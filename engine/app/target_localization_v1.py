"""Automatic TargetCharacter and SceneLocalizationMapping planning.

The planner consumes only SourceDramaSnapshot + ProjectRemakePolicy.  Existing source
assets are never edited.  A configured local Qwen3-VL OpenAI-compatible endpoint is reused
for text-side localization planning; uncertain results become ReviewIssue rows.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from typing import Any, Mapping

import httpx
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.asset_semantics_v3 import semantic_model_status
from engine.app.remake_policy_v1 import get_project_remake_policy
from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Base, Project, get_session, new_id, utcnow
from engine.app.target_localization_contract_v1 import TargetLocalizationBundleV1

CHARACTER_REVIEW_PREFIX = "auto:target-character:"
SCENE_REVIEW_PREFIX = "auto:scene-localization:"
AUTO_CONFIDENCE_MIN = 0.72


class TargetCharacter(Base):
    __tablename__ = "v2_target_characters"
    __table_args__ = (
        UniqueConstraint("project_id", "source_character_id", name="uq_v2_target_character_source"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    source_character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_character_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_character_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(64), nullable=False)
    target_name: Mapped[str] = mapped_column(String(200), nullable=False)
    appearance_profile: Mapped[str] = mapped_column(Text, nullable=False)
    generation_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REVIEW")
    decision_source: Mapped[str] = mapped_column(String(24), nullable=False, default="AI")
    reference_assets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SceneLocalizationMapping(Base):
    __tablename__ = "v2_scene_localization_mappings"
    __table_args__ = (
        UniqueConstraint("project_id", "scene_key", name="uq_v2_scene_localization_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    scene_key: Mapped[str] = mapped_column(String(220), nullable=False)
    source_scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_scene_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_scene_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_policy: Mapped[str] = mapped_column(String(24), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    decision_source: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _clean(value: Any, max_len: int = 4000) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text[:max_len] if text else None


def _extract_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("本土化模型没有返回 JSON")
    payload = json.loads(value[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("本土化模型返回的不是 JSON object")
    return payload


def _request_text_model(prompt: str) -> dict[str, Any]:
    status = semantic_model_status()
    if not status.get("ready"):
        raise RuntimeError("本地 Qwen3-VL 服务未配置")
    base_url = str(status["base_url"])
    model = str(status["model"])
    api_key = os.getenv("AI_DRAMA_VLM_API_KEY", "EMPTY").strip() or "EMPTY"
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=180.0) as client:
        response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return _extract_json(str(content))


def _character_contexts(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {
        str(item["id"]): {
            "source_character_id": str(item["id"]),
            "source_name": str(item["name"]),
            "cover_url": item.get("cover_url"),
            "appearances": [],
            "story_context": [],
        }
        for item in snapshot.get("characters") or []
        if isinstance(item, Mapping) and item.get("id") and item.get("name")
    }
    for episode in snapshot.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, Mapping):
                continue
            for person in scene.get("people") or []:
                if not isinstance(person, Mapping):
                    continue
                character = person.get("character")
                if not isinstance(character, Mapping) or str(character.get("id") or "") not in by_id:
                    continue
                row = by_id[str(character["id"])]
                appearance = _clean(person.get("appearance"), 700)
                if appearance and appearance not in row["appearances"]:
                    row["appearances"].append(appearance)
                context = _clean(scene.get("story_summary") or scene.get("title"), 700)
                if context and context not in row["story_context"]:
                    row["story_context"].append(context)
    for row in by_id.values():
        row["appearances"] = row["appearances"][:8]
        row["story_context"] = row["story_context"][:6]
        row["signature"] = _digest(row)
    return [by_id[key] for key in sorted(by_id)]


def _scene_contexts(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in snapshot.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, Mapping):
                continue
            visible_text: list[str] = []
            for shot in scene.get("shots") or []:
                if not isinstance(shot, Mapping):
                    continue
                for text in shot.get("source_on_screen_text") or []:
                    if isinstance(text, Mapping):
                        value = _clean(text.get("source_text"), 300)
                        if value and value not in visible_text:
                            visible_text.append(value)
            final_scene = scene.get("final_scene") if isinstance(scene.get("final_scene"), Mapping) else None
            row = {
                "episode_id": str(episode.get("episode_id") or ""),
                "episode_order": episode.get("episode_order"),
                "scene_key": str(scene.get("scene_key") or ""),
                "title": scene.get("title"),
                "story_summary": scene.get("story_summary"),
                "scene_info": scene.get("scene_info") or {},
                "source_scene_id": final_scene.get("id") if final_scene else None,
                "source_scene_name": final_scene.get("name") if final_scene else None,
                "visible_text": visible_text[:12],
            }
            row["signature"] = _digest(row)
            rows.append(row)
    return rows


def _character_prompt(rows: list[dict[str, Any]], target_language: str, target_region: str) -> str:
    compact = [{key: value for key, value in row.items() if key != "signature"} for row in rows]
    return f"""你正在为短剧出海重拍设计目标演员角色。目标地区={target_region}，目标语言={target_language}。
原短剧人物只提供叙事角色和视觉参考，最终演员必须换成符合目标地区的新人物，不能复制原人物的独特身份/脸。
保持剧情功能、年龄层、性别呈现、气质和表演需求；姓名使用目标地区自然常见的姓名。不要改变亲属/职业/权力关系等剧情功能。
appearance_profile 写适合选角和角色参考图生成的稳定外观设定，避免镜头瞬时动作、表情、衣服褶皱等动态信息。
generation_prompt 写给后续人物参考资产生成/H3 使用的稳定人物身份描述。
confidence 0..1；如果原片信息不足以安全判断核心人物属性，降低 confidence。
只返回 JSON object：{{"characters":[{{"source_character_id":"","target_name":"","appearance_profile":"","generation_prompt":"","confidence":0.0}}]}}。
必须逐个返回输入人物，不允许新增人物。
输入：{json.dumps(compact, ensure_ascii=False)}"""


def _scene_prompt(rows: list[dict[str, Any]], target_language: str, target_region: str, policy: str) -> str:
    compact = [{key: value for key, value in row.items() if key != "signature"} for row in rows]
    return f"""你正在为短剧出海重拍判断场景是否需要本土化。目标地区={target_region}，目标语言={target_language}，项目策略={policy}。
KEEP 表示原空间可以直接作为 H3 Reference Video 场景参考；LOCALIZE 表示需要生成符合目标地区的新场景。
项目策略规则：KEEP 必须 KEEP；LOCALIZE 必须 LOCALIZE；AUTO 时，普通卧室/办公室/客厅/酒店等没有明显地域冲突的空间优先 KEEP；只有明显的源地区文字招牌、货币、制度设施、建筑/商业标识/学校医院警察等文化地域元素会影响出海可信度时才 LOCALIZE。
LOCALIZE 时给 target_label 和 target_description，描述目标地区对应空间，但保持原镜头动作、空间功能和可拍性。KEEP 时 target_label/target_description 可为 null。
confidence 0..1。信息不足时不要硬猜，返回 decision=REVIEW。
只返回 JSON object：{{"scenes":[{{"scene_key":"","decision":"KEEP|LOCALIZE|REVIEW","target_label":null,"target_description":null,"reason":"","confidence":0.0}}]}}。
必须逐个返回输入 scene_key，不允许新增场景。
输入：{json.dumps(compact, ensure_ascii=False)}"""


def _serialize_character(row: TargetCharacter) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "source_character_id": row.source_character_id,
        "source_character_name": row.source_character_name,
        "source_character_signature": row.source_character_signature,
        "source_fingerprint": row.source_fingerprint,
        "target_language": row.target_language,
        "target_region": row.target_region,
        "target_name": row.target_name,
        "appearance_profile": row.appearance_profile,
        "generation_prompt": row.generation_prompt,
        "confidence": row.confidence,
        "status": row.status,
        "decision_source": row.decision_source,
        "reference_assets": _json(row.reference_assets_json, []),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_scene(row: SceneLocalizationMapping) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "episode_id": row.episode_id,
        "scene_key": row.scene_key,
        "source_scene_id": row.source_scene_id,
        "source_scene_name": row.source_scene_name,
        "source_scene_signature": row.source_scene_signature,
        "source_fingerprint": row.source_fingerprint,
        "project_policy": row.project_policy,
        "decision": row.decision,
        "decision_source": row.decision_source,
        "confidence": row.confidence,
        "target_label": row.target_label,
        "target_description": row.target_description,
        "reason": row.reason,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _resolve_review_key(project_id: str, source_key: str, reason: str) -> None:
    with get_session() as session:
        row = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == source_key,
            ReviewIssue.status == "OPEN",
        ))
        if row is not None:
            now = utcnow()
            row.status = "RESOLVED"
            row.resolution_json = json.dumps({"automatic": True, "reason": reason}, ensure_ascii=False)
            row.resolved_at = now
            row.updated_at = now
            session.commit()


def _character_issue_key(source_character_id: str) -> str:
    return f"{CHARACTER_REVIEW_PREFIX}{source_character_id}"


def _scene_issue_key(scene_key: str) -> str:
    return f"{SCENE_REVIEW_PREFIX}{hashlib.sha1(scene_key.encode('utf-8')).hexdigest()[:24]}"


def _upsert_character_rows(
    *,
    project: Project,
    source_fingerprint: str,
    contexts: list[dict[str, Any]],
    proposals: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    active_ids = {str(item["source_character_id"]) for item in contexts}
    with get_session() as session:
        stale_rows = session.scalars(select(TargetCharacter).where(TargetCharacter.project_id == project.id)).all()
        for stale in stale_rows:
            if stale.source_character_id not in active_ids:
                session.delete(stale)
        session.commit()

    for context in contexts:
        source_id = str(context["source_character_id"])
        proposal = proposals.get(source_id) or {}
        confidence = _confidence(proposal.get("confidence"))
        valid = bool(
            _clean(proposal.get("target_name"), 200)
            and _clean(proposal.get("appearance_profile"))
            and _clean(proposal.get("generation_prompt"))
            and confidence is not None
            and confidence >= AUTO_CONFIDENCE_MIN
        )
        with get_session() as session:
            row = session.scalar(select(TargetCharacter).where(
                TargetCharacter.project_id == project.id,
                TargetCharacter.source_character_id == source_id,
            ))
            source_changed = row is not None and row.source_character_signature != context["signature"]
            preserve_manual = row is not None and row.decision_source == "MANUAL" and not source_changed
            if row is None:
                row = TargetCharacter(
                    id=new_id("TARGETCHAR"),
                    project_id=project.id,
                    source_character_id=source_id,
                    source_character_name=str(context["source_name"]),
                    source_character_signature=str(context["signature"]),
                    source_fingerprint=source_fingerprint,
                    target_language=project.target_language,
                    target_region=project.target_region,
                    target_name="待确认目标角色",
                    appearance_profile="等待本地模型或人工确认目标人物设定",
                    generation_prompt="等待目标人物设定完成后生成稳定人物参考",
                    status="REVIEW",
                    decision_source="AI",
                    reference_assets_json="[]",
                )
                session.add(row)
            row.source_character_name = str(context["source_name"])
            row.source_fingerprint = source_fingerprint
            row.target_language = project.target_language
            row.target_region = project.target_region
            if preserve_manual:
                row.source_character_signature = str(context["signature"])
            elif source_changed and row.decision_source == "MANUAL":
                row.source_character_signature = str(context["signature"])
                row.status = "REVIEW"
            else:
                row.source_character_signature = str(context["signature"])
                row.target_name = _clean(proposal.get("target_name"), 200) or "待确认目标角色"
                row.appearance_profile = _clean(proposal.get("appearance_profile")) or "等待本地模型或人工确认目标人物设定"
                row.generation_prompt = _clean(proposal.get("generation_prompt")) or "等待目标人物设定完成后生成稳定人物参考"
                row.confidence = confidence
                row.status = "READY" if valid else "REVIEW"
                row.decision_source = "AI"
            row.updated_at = utcnow()
            session.commit()
            session.refresh(row)
            serialized = _serialize_character(row)
        issue_key = _character_issue_key(source_id)
        if serialized["status"] == "REVIEW":
            reason = "目标人物自动设计置信度不足，需要确认姓名和稳定外观设定"
            if source_changed and serialized["decision_source"] == "MANUAL":
                reason = "原人物源事实已变化，需要确认之前的人工目标人物设定是否仍适用"
            upsert_review_issue(
                project_id=project.id,
                source_key=issue_key,
                issue_type="TARGET_CHARACTER",
                severity="BLOCKING",
                reason=reason,
                ai_suggestion=proposal or None,
                editable_payload=serialized,
            )
        else:
            _resolve_review_key(project.id, issue_key, "目标人物已形成可用设定")
        output.append(serialized)
    return output


def _upsert_scene_rows(
    *,
    project: Project,
    source_fingerprint: str,
    policy: str,
    contexts: list[dict[str, Any]],
    proposals: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    active_keys = {str(item["scene_key"]) for item in contexts}
    with get_session() as session:
        stale_rows = session.scalars(select(SceneLocalizationMapping).where(SceneLocalizationMapping.project_id == project.id)).all()
        for stale in stale_rows:
            if stale.scene_key not in active_keys:
                session.delete(stale)
        session.commit()

    for context in contexts:
        scene_key = str(context["scene_key"])
        proposal = proposals.get(scene_key) or {}
        ai_decision = str(proposal.get("decision") or "REVIEW").upper()
        confidence = _confidence(proposal.get("confidence"))
        if policy == "KEEP":
            decision, decision_source, status = "KEEP", "PROJECT_POLICY", "READY"
            confidence = 1.0
        elif policy == "LOCALIZE":
            description = _clean(proposal.get("target_description"))
            if description and confidence is not None and confidence >= AUTO_CONFIDENCE_MIN:
                decision, decision_source, status = "LOCALIZE", "PROJECT_POLICY", "READY"
            else:
                decision, decision_source, status = "REVIEW", "PROJECT_POLICY", "REVIEW"
        elif ai_decision in {"KEEP", "LOCALIZE"} and confidence is not None and confidence >= AUTO_CONFIDENCE_MIN:
            if ai_decision == "LOCALIZE" and not _clean(proposal.get("target_description")):
                decision, decision_source, status = "REVIEW", "AI", "REVIEW"
            else:
                decision, decision_source, status = ai_decision, "AI", "READY"
        else:
            decision, decision_source, status = "REVIEW", "AI", "REVIEW"

        with get_session() as session:
            row = session.scalar(select(SceneLocalizationMapping).where(
                SceneLocalizationMapping.project_id == project.id,
                SceneLocalizationMapping.scene_key == scene_key,
            ))
            source_changed = row is not None and row.source_scene_signature != context["signature"]
            preserve_manual = row is not None and row.decision_source == "MANUAL" and not source_changed
            if row is None:
                row = SceneLocalizationMapping(
                    id=new_id("SCENELOCAL"), project_id=project.id,
                    episode_id=str(context["episode_id"]), scene_key=scene_key,
                    source_scene_signature=str(context["signature"]), source_fingerprint=source_fingerprint,
                    project_policy=policy, decision="REVIEW", decision_source="AI", status="REVIEW",
                )
                session.add(row)
            row.episode_id = str(context["episode_id"])
            row.source_scene_id = context.get("source_scene_id")
            row.source_scene_name = _clean(context.get("source_scene_name"), 200)
            row.source_fingerprint = source_fingerprint
            row.project_policy = policy
            if preserve_manual:
                row.source_scene_signature = str(context["signature"])
            elif source_changed and row.decision_source == "MANUAL":
                row.source_scene_signature = str(context["signature"])
                row.status = "REVIEW"
                row.decision = "REVIEW"
            else:
                row.source_scene_signature = str(context["signature"])
                row.decision = decision
                row.decision_source = decision_source
                row.confidence = confidence
                row.target_label = _clean(proposal.get("target_label"), 200)
                row.target_description = _clean(proposal.get("target_description"))
                row.reason = _clean(proposal.get("reason"), 1200)
                row.status = status
                if row.decision == "KEEP":
                    row.target_label = None
                    row.target_description = None
            row.updated_at = utcnow()
            session.commit()
            session.refresh(row)
            serialized = _serialize_scene(row)
        issue_key = _scene_issue_key(scene_key)
        if serialized["status"] == "REVIEW":
            reason = "场景是否需要本土化无法安全自动决定"
            if policy == "LOCALIZE":
                reason = "项目要求场景本土化，但目标场景描述尚未可靠生成"
            if source_changed and serialized["decision_source"] == "MANUAL":
                reason = "原场景源事实已变化，需要重新确认之前的人工场景决策"
            upsert_review_issue(
                project_id=project.id,
                episode_id=str(context["episode_id"]),
                source_key=issue_key,
                issue_type="SCENE_LOCALIZATION",
                severity="REVIEW",
                reason=reason,
                ai_suggestion=proposal or None,
                editable_payload=serialized,
            )
        else:
            _resolve_review_key(project.id, issue_key, "场景本土化策略已确定")
        output.append(serialized)
    return output


def generate_target_localization_v1(project_id: str) -> dict[str, Any]:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        session.expunge(project)
    policy_row = get_project_remake_policy(project_id) or {}
    policy = str(policy_row.get("scene_policy") or "AUTO")
    character_contexts = _character_contexts(snapshot)
    scene_contexts = _scene_contexts(snapshot)

    character_proposals: dict[str, Mapping[str, Any]] = {}
    scene_proposals: dict[str, Mapping[str, Any]] = {}
    model_ready = bool(semantic_model_status().get("ready"))
    if model_ready and character_contexts:
        for offset in range(0, len(character_contexts), 12):
            chunk = character_contexts[offset : offset + 12]
            try:
                raw = _request_text_model(_character_prompt(chunk, project.target_language, project.target_region))
                for item in raw.get("characters") or []:
                    if isinstance(item, Mapping) and item.get("source_character_id"):
                        character_proposals[str(item["source_character_id"])] = item
            except Exception:
                pass
    if policy != "KEEP" and model_ready and scene_contexts:
        for offset in range(0, len(scene_contexts), 12):
            chunk = scene_contexts[offset : offset + 12]
            try:
                raw = _request_text_model(_scene_prompt(chunk, project.target_language, project.target_region, policy))
                for item in raw.get("scenes") or []:
                    if isinstance(item, Mapping) and item.get("scene_key"):
                        scene_proposals[str(item["scene_key"])] = item
            except Exception:
                pass

    characters = _upsert_character_rows(
        project=project,
        source_fingerprint=str(snapshot["source_fingerprint"]),
        contexts=character_contexts,
        proposals=character_proposals,
    )
    scenes = _upsert_scene_rows(
        project=project,
        source_fingerprint=str(snapshot["source_fingerprint"]),
        policy=policy,
        contexts=scene_contexts,
        proposals=scene_proposals,
    )
    review_count = sum(item["status"] == "REVIEW" for item in characters) + sum(item["status"] == "REVIEW" for item in scenes)
    bundle = {
        "schema_version": "target-localization-v1",
        "project_id": project_id,
        "source_fingerprint": snapshot["source_fingerprint"],
        "target_language": project.target_language,
        "target_region": project.target_region,
        "scene_policy": policy,
        "status": "READY_WITH_WARNINGS" if review_count else "READY",
        "target_character_count": len(characters),
        "scene_mapping_count": len(scenes),
        "review_count": review_count,
        "target_characters": characters,
        "scene_mappings": scenes,
    }
    # Contract exposes REVIEW rather than READY_WITH_WARNINGS.
    bundle["status"] = "REVIEW" if review_count else "READY"
    return TargetLocalizationBundleV1.model_validate(bundle).model_dump(mode="json")


def get_target_localization_v1(project_id: str) -> dict[str, Any]:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        characters = list(session.scalars(select(TargetCharacter).where(TargetCharacter.project_id == project_id).order_by(TargetCharacter.source_character_name)).all())
        scenes = list(session.scalars(select(SceneLocalizationMapping).where(SceneLocalizationMapping.project_id == project_id).order_by(SceneLocalizationMapping.episode_id, SceneLocalizationMapping.scene_key)).all())
    policy = str((get_project_remake_policy(project_id) or {}).get("scene_policy") or "AUTO")
    character_rows = [_serialize_character(item) for item in characters]
    scene_rows = [_serialize_scene(item) for item in scenes]
    review_count = sum(item["status"] == "REVIEW" for item in character_rows) + sum(item["status"] == "REVIEW" for item in scene_rows)
    return TargetLocalizationBundleV1.model_validate({
        "schema_version": "target-localization-v1",
        "project_id": project_id,
        "source_fingerprint": snapshot["source_fingerprint"],
        "target_language": project.target_language,
        "target_region": project.target_region,
        "scene_policy": policy,
        "status": "REVIEW" if review_count else "READY",
        "target_character_count": len(character_rows),
        "scene_mapping_count": len(scene_rows),
        "review_count": review_count,
        "target_characters": character_rows,
        "scene_mappings": scene_rows,
    }).model_dump(mode="json")


def update_target_character_v1(target_character_id: str, *, target_name: str, appearance_profile: str, generation_prompt: str) -> dict[str, Any]:
    values = [_clean(target_name, 200), _clean(appearance_profile), _clean(generation_prompt)]
    if any(value is None for value in values):
        raise ValueError("目标人物姓名、外观设定和生成描述不能为空")
    with get_session() as session:
        row = session.get(TargetCharacter, target_character_id)
        if row is None:
            raise LookupError("目标人物不存在")
        row.target_name, row.appearance_profile, row.generation_prompt = values  # type: ignore[assignment]
        row.status = "READY"
        row.decision_source = "MANUAL"
        row.confidence = 1.0
        row.updated_at = utcnow()
        project_id, source_id = row.project_id, row.source_character_id
        session.commit()
        session.refresh(row)
        payload = _serialize_character(row)
    _resolve_review_key(project_id, _character_issue_key(source_id), "用户已确认目标人物设定")
    return payload


def delete_target_character_v1(target_character_id: str) -> None:
    with get_session() as session:
        row = session.get(TargetCharacter, target_character_id)
        if row is None:
            raise LookupError("目标人物不存在")
        session.delete(row)
        session.commit()


def update_scene_localization_v1(mapping_id: str, *, decision: str, target_label: str | None = None, target_description: str | None = None, reason: str | None = None) -> dict[str, Any]:
    normalized = decision.strip().upper()
    if normalized not in {"KEEP", "LOCALIZE"}:
        raise ValueError("场景人工决策只支持 KEEP / LOCALIZE")
    description = _clean(target_description)
    if normalized == "LOCALIZE" and not description:
        raise ValueError("LOCALIZE 必须填写目标场景描述")
    with get_session() as session:
        row = session.get(SceneLocalizationMapping, mapping_id)
        if row is None:
            raise LookupError("场景本土化映射不存在")
        row.decision = normalized
        row.decision_source = "MANUAL"
        row.confidence = 1.0
        row.target_label = _clean(target_label, 200) if normalized == "LOCALIZE" else None
        row.target_description = description if normalized == "LOCALIZE" else None
        row.reason = _clean(reason, 1200) or "用户人工确认"
        row.status = "READY"
        row.updated_at = utcnow()
        project_id, scene_key = row.project_id, row.scene_key
        session.commit()
        session.refresh(row)
        payload = _serialize_scene(row)
    _resolve_review_key(project_id, _scene_issue_key(scene_key), "用户已确认场景本土化策略")
    return payload


def delete_scene_localization_v1(mapping_id: str) -> None:
    with get_session() as session:
        row = session.get(SceneLocalizationMapping, mapping_id)
        if row is None:
            raise LookupError("场景本土化映射不存在")
        session.delete(row)
        session.commit()


__all__ = [
    "SceneLocalizationMapping",
    "TargetCharacter",
    "delete_scene_localization_v1",
    "delete_target_character_v1",
    "generate_target_localization_v1",
    "get_target_localization_v1",
    "update_scene_localization_v1",
    "update_target_character_v1",
]
