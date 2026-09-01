"""R5 target dialogue localization + target voice/TTS materialization.

Source text remains owned by SourceDramaSnapshot. This module persists target-only text,
voice profiles and generated audio. Translation uses the existing local Qwen service;
voice audio uses the isolated official Qwen3-TTS worker when available.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.local_qwen_text_v1 import LocalQwenTextError, request_local_qwen_json
from engine.app.qwen3_tts_runtime_v1 import (
    Qwen3TTSRuntimeError,
    RUNTIME_PROFILE,
    design_voice_reference,
    reference_text_for_language,
    runtime_status,
    synthesize_clone,
    tts_language,
    wav_duration_us,
)
from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Base, Episode, Project, get_session, new_id, project_dir, utcnow
from engine.app.target_dialogue_contract_v1 import TargetDialogueBundleV1
from engine.app.target_localization_v1 import TargetCharacter, get_target_localization_v1


LOCALIZATION_REVIEW_PREFIX = "auto:target-dialogue:"
TRANSLATION_CONFIDENCE_MIN = 0.74


class TargetDialogueError(RuntimeError):
    pass


class TargetVoiceProfile(Base):
    __tablename__ = "v2_target_voice_profiles"
    __table_args__ = (
        UniqueConstraint("project_id", "target_character_id", name="uq_v2_target_voice_character"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    target_character_id: Mapped[str] = mapped_column(ForeignKey("v2_target_characters.id", ondelete="CASCADE"), index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_character_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_profile: Mapped[str] = mapped_column(String(64), nullable=False, default=RUNTIME_PROFILE)
    voice_design_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TargetDialogue(Base):
    __tablename__ = "v2_target_dialogues"
    __table_args__ = (
        UniqueConstraint("project_id", "source_dialogue_key", name="uq_v2_target_dialogue_source"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    shot_key: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    source_dialogue_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_dialogue_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_character_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_character_id: Mapped[str | None] = mapped_column(ForeignKey("v2_target_characters.id", ondelete="SET NULL"), nullable=True)
    target_voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("v2_target_voice_profiles.id", ondelete="SET NULL"), nullable=True)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(64), nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    localized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_source: Mapped[str] = mapped_column(String(24), nullable=False, default="AI")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REVIEW")
    audio_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    audio_input_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    speech_duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tts_runtime_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _clean(value: Any, limit: int = 12000) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text[:limit] if text else None


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _voice_character_signature(character: Mapping[str, Any]) -> str:
    return _digest({
        "target_name": character.get("target_name"),
        "appearance_profile": character.get("appearance_profile"),
        "generation_prompt": character.get("generation_prompt"),
        "target_language": character.get("target_language"),
        "target_region": character.get("target_region"),
    })


def _voice_prompt(character: Mapping[str, Any]) -> str:
    return (
        f"Design a distinctive, natural native voice for a screen-drama character in {character['target_region']}. "
        f"Character name: {character['target_name']}. Stable character design: {character['appearance_profile']}. "
        "Match the apparent age range and gender presentation of the character; use a believable contemporary speaking voice, "
        "clear dialogue diction, emotionally flexible delivery, no announcer voice, no imitation of a known real person."
    )


def _serialize_voice(row: TargetVoiceProfile) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "target_character_id": row.target_character_id,
        "source_fingerprint": row.source_fingerprint,
        "target_character_signature": row.target_character_signature,
        "target_language": row.target_language,
        "target_region": row.target_region,
        "runtime_profile": row.runtime_profile,
        "voice_design_prompt": row.voice_design_prompt,
        "reference_text": row.reference_text,
        "reference_audio_path": row.reference_audio_path,
        "voice_fingerprint": row.voice_fingerprint,
        "status": row.status,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_dialogue(row: TargetDialogue) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "episode_id": row.episode_id,
        "shot_key": row.shot_key,
        "source_dialogue_key": row.source_dialogue_key,
        "source_dialogue_signature": row.source_dialogue_signature,
        "source_fingerprint": row.source_fingerprint,
        "source_start_us": row.source_start_us,
        "source_end_us": row.source_end_us,
        "source_text": row.source_text,
        "source_character_id": row.source_character_id,
        "target_character_id": row.target_character_id,
        "target_voice_profile_id": row.target_voice_profile_id,
        "target_language": row.target_language,
        "target_region": row.target_region,
        "translated_text": row.translated_text,
        "localized_text": row.localized_text,
        "final_text": row.final_text,
        "translation_confidence": row.translation_confidence,
        "decision_source": row.decision_source,
        "status": row.status,
        "audio_status": row.audio_status,
        "audio_input_signature": row.audio_input_signature,
        "audio_path": row.audio_path,
        "speech_duration_us": row.speech_duration_us,
        "tts_runtime_profile": row.tts_runtime_profile,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _dialogue_issue_key(dialogue_key: str) -> str:
    return f"{LOCALIZATION_REVIEW_PREFIX}{hashlib.sha1(dialogue_key.encode('utf-8')).hexdigest()[:28]}"


def _resolve_issue(project_id: str, source_key: str, reason: str) -> None:
    with get_session() as session:
        row = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == source_key,
            ReviewIssue.status == "OPEN",
        ))
        if row is None:
            return
        now = utcnow()
        row.status = "RESOLVED"
        row.resolution_json = json.dumps({"automatic": True, "reason": reason}, ensure_ascii=False)
        row.resolved_at = now
        row.updated_at = now
        session.commit()


def _resolve_stale_issues(project_id: str, active: set[str]) -> None:
    with get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.status == "OPEN",
            ReviewIssue.source_key.like(f"{LOCALIZATION_REVIEW_PREFIX}%"),
        )).all()
        changed = False
        now = utcnow()
        for row in rows:
            if row.source_key in active:
                continue
            row.status = "RESOLVED"
            row.resolution_json = json.dumps({"automatic": True, "reason": "当前 TargetDialogue 已不再报告此文本问题"}, ensure_ascii=False)
            row.resolved_at = now
            row.updated_at = now
            changed = True
        if changed:
            session.commit()


def _target_characters(project_id: str) -> dict[str, dict[str, Any]]:
    bundle = get_target_localization_v1(project_id)
    return {
        str(item["source_character_id"]): item
        for item in bundle.get("target_characters") or []
        if item.get("status") == "READY"
    }


def _dialogue_contexts(snapshot: Mapping[str, Any], target_characters: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in snapshot.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        episode_id = str(episode.get("episode_id") or "")
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, Mapping):
                continue
            people = {
                str(person.get("person_key")): person
                for person in scene.get("people") or []
                if isinstance(person, Mapping) and person.get("person_key")
            }
            for shot in scene.get("shots") or []:
                if not isinstance(shot, Mapping):
                    continue
                shot_key = str(shot.get("shot_key") or "")
                for dialogue in shot.get("source_dialogue") or []:
                    if not isinstance(dialogue, Mapping) or not dialogue.get("dialogue_key") or not dialogue.get("source_text"):
                        continue
                    speaker_keys = [str(item) for item in dialogue.get("speakers") or []]
                    source_character_ids: list[str] = []
                    for person_key in speaker_keys:
                        person = people.get(person_key)
                        character = person.get("character") if isinstance(person, Mapping) else None
                        character_id = str(character.get("id") or "") if isinstance(character, Mapping) else ""
                        if character_id and character_id not in source_character_ids:
                            source_character_ids.append(character_id)
                    source_character_id = source_character_ids[0] if len(source_character_ids) == 1 else None
                    target_character = target_characters.get(source_character_id or "")
                    context = {
                        "episode_id": episode_id,
                        "shot_key": shot_key,
                        "source_dialogue_key": str(dialogue["dialogue_key"]),
                        "source_start_us": int(dialogue.get("start_us") or 0),
                        "source_end_us": int(dialogue.get("end_us") or 0),
                        "source_text": str(dialogue["source_text"]),
                        "speaker_person_keys": speaker_keys,
                        "source_character_ids": source_character_ids,
                        "source_character_id": source_character_id,
                        "target_character_id": target_character.get("id") if target_character else None,
                        "target_speaker_name": target_character.get("target_name") if target_character else None,
                        "scene_title": scene.get("title"),
                        "story_summary": scene.get("story_summary"),
                        "visual_description": shot.get("visual_description"),
                    }
                    context["signature"] = _digest({
                        "shot_key": shot_key,
                        "source_dialogue_key": context["source_dialogue_key"],
                        "source_start_us": context["source_start_us"],
                        "source_end_us": context["source_end_us"],
                        "source_text": context["source_text"],
                        "source_character_ids": source_character_ids,
                    })
                    rows.append(context)
    return rows


def _translation_prompt(rows: list[dict[str, Any]], *, source_language: str, target_language: str, target_region: str, name_map: Mapping[str, str]) -> str:
    payload = [{k: v for k, v in row.items() if k != "signature"} for row in rows]
    return f"""你正在把短剧对白本土化到目标市场。源语言={source_language}，目标语言={target_language}，目标地区={target_region}。
目标不是逐字直译，而是在不改变剧情事实、人物关系、威胁/承诺/反转/信息量的前提下，写成目标地区观众自然会说的短剧对白。
必须保留每条 source_dialogue_key，不新增、不合并、不拆分对白。人物姓名按 name_map 使用目标人物姓名；不要继续输出原人物姓名。
translated_text=忠实翻译层；localized_text=目标地区自然表达层；final_text=当前推荐成片对白，优先自然、可表演、简洁，但此阶段不要为了卡原镜头时长而损失语义，真正的时长优化在后续 Timing Engine。
不要添加原文没有的剧情事实。confidence=0..1；歧义、文化转换可能改变剧情或原文不清楚时降低 confidence。
只返回 JSON object：{{"dialogues":[{{"source_dialogue_key":"","translated_text":"","localized_text":"","final_text":"","confidence":0.0}}]}}。
name_map={json.dumps(name_map, ensure_ascii=False)}
input={json.dumps(payload, ensure_ascii=False)}"""


def _upsert_voice_profiles(project: Project, fingerprint: str, target_characters: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    active_target_ids = {str(item["id"]) for item in target_characters.values()}
    with get_session() as session:
        for row in session.scalars(select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project.id)).all():
            if row.target_character_id not in active_target_ids:
                session.delete(row)
        session.commit()

    output: dict[str, dict[str, Any]] = {}
    reference_text = reference_text_for_language(project.target_language) or f"This is the reference voice for a localized drama character in {project.target_region}."
    for character in target_characters.values():
        target_id = str(character["id"])
        signature = _voice_character_signature(character)
        design_prompt = _voice_prompt(character)
        voice_fingerprint = _digest({
            "profile": RUNTIME_PROFILE,
            "target_character_signature": signature,
            "voice_design_prompt": design_prompt,
            "reference_text": reference_text,
        })
        with get_session() as session:
            row = session.scalar(select(TargetVoiceProfile).where(
                TargetVoiceProfile.project_id == project.id,
                TargetVoiceProfile.target_character_id == target_id,
            ))
            changed = row is not None and row.voice_fingerprint != voice_fingerprint
            old_reference = Path(row.reference_audio_path) if row is not None and row.reference_audio_path else None
            if row is None:
                row = TargetVoiceProfile(
                    id=new_id("TARGETVOICE"), project_id=project.id, target_character_id=target_id,
                    source_fingerprint=fingerprint, target_character_signature=signature,
                    target_language=project.target_language, target_region=project.target_region,
                    runtime_profile=RUNTIME_PROFILE, voice_design_prompt=design_prompt,
                    reference_text=reference_text, voice_fingerprint=voice_fingerprint, status="PLANNED",
                )
                session.add(row)
            row.source_fingerprint = fingerprint
            row.target_character_signature = signature
            row.target_language = project.target_language
            row.target_region = project.target_region
            row.runtime_profile = RUNTIME_PROFILE
            row.voice_design_prompt = design_prompt
            row.reference_text = reference_text
            row.voice_fingerprint = voice_fingerprint
            if changed:
                row.reference_audio_path = None
                row.status = "PLANNED"
                row.error_message = None
            row.updated_at = utcnow()
            session.commit(); session.refresh(row)
            serialized = _serialize_voice(row)
        if changed and old_reference is not None:
            try:
                old_reference.unlink(missing_ok=True)
            except OSError:
                pass
        output[target_id] = serialized
    return output


def generate_target_dialogue_text_v1(project_id: str) -> dict[str, Any]:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        session.expunge(project)
    target_characters = _target_characters(project_id)
    voice_profiles = _upsert_voice_profiles(project, str(snapshot["source_fingerprint"]), target_characters)
    contexts = _dialogue_contexts(snapshot, target_characters)
    active_dialogue_keys = {str(item["source_dialogue_key"]) for item in contexts}
    with get_session() as session:
        for row in session.scalars(select(TargetDialogue).where(TargetDialogue.project_id == project_id)).all():
            if row.source_dialogue_key not in active_dialogue_keys:
                session.delete(row)
        session.commit()

    name_map = {
        str(item.get("source_character_name") or source_id): str(item["target_name"])
        for source_id, item in target_characters.items()
    }
    proposals: dict[str, Mapping[str, Any]] = {}
    translatable = [item for item in contexts if item.get("target_character_id")]
    for offset in range(0, len(translatable), 20):
        chunk = translatable[offset:offset + 20]
        try:
            result = request_local_qwen_json(_translation_prompt(
                chunk,
                source_language=str(snapshot.get("source_language") or project.source_language),
                target_language=project.target_language,
                target_region=project.target_region,
                name_map=name_map,
            ))
            for item in result.get("dialogues") or []:
                if isinstance(item, Mapping) and item.get("source_dialogue_key"):
                    proposals[str(item["source_dialogue_key"])] = item
        except LocalQwenTextError:
            pass

    active_localization_issues: set[str] = set()
    dialogue_rows: list[dict[str, Any]] = []
    fingerprint = str(snapshot["source_fingerprint"])
    for context in contexts:
        source_key = str(context["source_dialogue_key"])
        proposal = proposals.get(source_key) or {}
        confidence = _confidence(proposal.get("confidence"))
        translated = _clean(proposal.get("translated_text"))
        localized = _clean(proposal.get("localized_text"))
        final_text = _clean(proposal.get("final_text"))
        target_character_id = str(context.get("target_character_id") or "") or None
        source_character_id = str(context.get("source_character_id") or "") or None
        unique_source_speaker = len(context.get("source_character_ids") or []) == 1
        valid_text = bool(target_character_id and unique_source_speaker and translated and localized and final_text and confidence is not None and confidence >= TRANSLATION_CONFIDENCE_MIN)
        with get_session() as session:
            row = session.scalar(select(TargetDialogue).where(
                TargetDialogue.project_id == project_id,
                TargetDialogue.source_dialogue_key == source_key,
            ))
            source_changed = row is not None and row.source_dialogue_signature != context["signature"]
            preserve_manual = row is not None and row.decision_source == "MANUAL" and not source_changed and row.target_character_id == target_character_id
            if row is None:
                row = TargetDialogue(
                    id=new_id("TARGETDIALOGUE"), project_id=project_id,
                    episode_id=str(context["episode_id"]), shot_key=str(context["shot_key"]),
                    source_dialogue_key=source_key, source_dialogue_signature=str(context["signature"]),
                    source_fingerprint=fingerprint, source_start_us=int(context["source_start_us"]),
                    source_end_us=int(context["source_end_us"]), source_text=str(context["source_text"]),
                    target_language=project.target_language, target_region=project.target_region,
                    decision_source="AI", status="REVIEW", audio_status="PENDING",
                )
                session.add(row)
            row.episode_id = str(context["episode_id"])
            row.shot_key = str(context["shot_key"])
            row.source_dialogue_signature = str(context["signature"])
            row.source_fingerprint = fingerprint
            row.source_start_us = int(context["source_start_us"])
            row.source_end_us = int(context["source_end_us"])
            row.source_text = str(context["source_text"])
            row.source_character_id = source_character_id
            row.target_character_id = target_character_id
            row.target_language = project.target_language
            row.target_region = project.target_region
            if preserve_manual:
                pass
            elif source_changed and row.decision_source == "MANUAL":
                row.status = "REVIEW"
                row.audio_status = "PENDING"
                row.audio_input_signature = None
            else:
                row.translated_text = translated
                row.localized_text = localized
                row.final_text = final_text
                row.translation_confidence = confidence
                row.decision_source = "AI"
                row.status = "READY" if valid_text else "REVIEW"
                row.audio_status = "PENDING" if valid_text else "PENDING"
                row.audio_input_signature = None
                row.audio_path = None
                row.speech_duration_us = None
                row.error_message = None
            voice = voice_profiles.get(target_character_id or "")
            row.target_voice_profile_id = str(voice["id"]) if voice else None
            row.updated_at = utcnow()
            session.commit(); session.refresh(row)
            serialized = _serialize_dialogue(row)
        issue_key = _dialogue_issue_key(source_key)
        if serialized["status"] == "REVIEW":
            # Source speaker/TargetCharacter ambiguity already has a more authoritative ReviewIssue.
            # Only publish LOCALIZATION when the speaker/character is known but the target text itself is unsafe.
            if target_character_id and unique_source_speaker:
                active_localization_issues.add(issue_key)
                upsert_review_issue(
                    project_id=project_id,
                    episode_id=str(context["episode_id"]),
                    source_key=issue_key,
                    issue_type="LOCALIZATION",
                    severity="BLOCKING",
                    reason="目标对白自动翻译/本土化置信度不足，需要确认最终台词",
                    ai_suggestion=proposal or None,
                    editable_payload=serialized,
                )
        else:
            _resolve_issue(project_id, issue_key, "目标对白已形成可用文本")
        dialogue_rows.append(serialized)

    _resolve_stale_issues(project_id, active_localization_issues)
    return _bundle(project, fingerprint, list(voice_profiles.values()), dialogue_rows)


def _bundle(project: Project, fingerprint: str, voices: list[dict[str, Any]], dialogues: list[dict[str, Any]]) -> dict[str, Any]:
    review_count = sum(item["status"] == "REVIEW" for item in dialogues)
    audio_ready = sum(item["audio_status"] == "READY" for item in dialogues)
    if review_count:
        status = "REVIEW"
    elif audio_ready == len(dialogues):
        status = "READY"
    else:
        status = "TEXT_READY_AUDIO_PENDING"
    return TargetDialogueBundleV1.model_validate({
        "schema_version": "target-dialogue-v1",
        "project_id": project.id,
        "source_fingerprint": fingerprint,
        "target_language": project.target_language,
        "target_region": project.target_region,
        "status": status,
        "voice_profile_count": len(voices),
        "dialogue_count": len(dialogues),
        "review_count": review_count,
        "audio_ready_count": audio_ready,
        "voice_profiles": voices,
        "dialogues": dialogues,
    }).model_dump(mode="json")


def _ensure_voice_reference(project_id: str, voice: TargetVoiceProfile, language: str) -> None:
    reference_path = project_dir(project_id) / "target" / "voices" / voice.id / "reference.wav"
    if voice.status == "REFERENCE_READY" and voice.reference_audio_path and Path(voice.reference_audio_path).is_file():
        return
    try:
        design_voice_reference(
            language=language,
            voice_design_prompt=voice.voice_design_prompt,
            reference_text=voice.reference_text,
            output_path=reference_path,
        )
        voice.reference_audio_path = str(reference_path)
        voice.status = "REFERENCE_READY"
        voice.error_message = None
    except Qwen3TTSRuntimeError as exc:
        voice.status = "FAILED"
        voice.error_message = str(exc)
        raise


def materialize_target_dialogue_audio_v1(project_id: str) -> dict[str, Any]:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        language = tts_language(project.target_language)
        voices = list(session.scalars(select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)).all())
        dialogues = list(session.scalars(select(TargetDialogue).where(TargetDialogue.project_id == project_id).order_by(TargetDialogue.episode_id, TargetDialogue.source_start_us)).all())
        if not language:
            for row in dialogues:
                if row.status == "READY":
                    row.audio_status = "UNSUPPORTED_LANGUAGE"
                    row.error_message = f"Qwen3-TTS V1 does not support target language {project.target_language}"
                    row.updated_at = utcnow()
            session.commit()
            return _bundle(project, str(snapshot["source_fingerprint"]), [_serialize_voice(v) for v in voices], [_serialize_dialogue(d) for d in dialogues])

    status = runtime_status()
    if not status.get("ready"):
        with get_session() as session:
            project = session.get(Project, project_id)
            voices = list(session.scalars(select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)).all())
            dialogues = list(session.scalars(select(TargetDialogue).where(TargetDialogue.project_id == project_id).order_by(TargetDialogue.episode_id, TargetDialogue.source_start_us)).all())
            for row in dialogues:
                if row.status == "READY" and row.audio_status != "READY":
                    row.audio_status = "NOT_CONFIGURED"
                    row.error_message = "local Qwen3-TTS worker is not ready"
                    row.updated_at = utcnow()
            session.commit()
            return _bundle(project, str(snapshot["source_fingerprint"]), [_serialize_voice(v) for v in voices], [_serialize_dialogue(d) for d in dialogues])

    # Generate stable reference voices first, one per TargetCharacter.
    with get_session() as session:
        voices = list(session.scalars(select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)).all())
        for voice in voices:
            try:
                _ensure_voice_reference(project_id, voice, language)
            except Qwen3TTSRuntimeError:
                pass
            voice.updated_at = utcnow()
        session.commit()

    # Then synthesize each READY line from the reusable target-character reference.
    with get_session() as session:
        project = session.get(Project, project_id)
        voice_by_id = {v.id: v for v in session.scalars(select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)).all()}
        dialogues = list(session.scalars(select(TargetDialogue).where(TargetDialogue.project_id == project_id).order_by(TargetDialogue.episode_id, TargetDialogue.source_start_us)).all())
        for row in dialogues:
            if row.status != "READY" or not row.final_text or not row.target_voice_profile_id:
                continue
            voice = voice_by_id.get(row.target_voice_profile_id)
            if voice is None or voice.status != "REFERENCE_READY" or not voice.reference_audio_path:
                row.audio_status = "FAILED"
                row.error_message = "target voice reference is unavailable"
                continue
            audio_signature = _digest({
                "final_text": row.final_text,
                "voice_fingerprint": voice.voice_fingerprint,
                "language": language,
                "runtime": RUNTIME_PROFILE,
            })
            current_path = Path(row.audio_path) if row.audio_path else None
            if row.audio_status == "READY" and row.audio_input_signature == audio_signature and current_path and current_path.is_file():
                continue
            output = project_dir(project_id) / "target" / "dialogue" / row.episode_id / f"{row.id}.wav"
            try:
                synthesize_clone(
                    language=language,
                    text=row.final_text,
                    reference_audio_path=Path(voice.reference_audio_path),
                    reference_text=voice.reference_text,
                    output_path=output,
                )
                row.audio_status = "READY"
                row.audio_input_signature = audio_signature
                row.audio_path = str(output)
                row.speech_duration_us = wav_duration_us(output)
                row.tts_runtime_profile = RUNTIME_PROFILE
                row.error_message = None
            except Qwen3TTSRuntimeError as exc:
                row.audio_status = "FAILED"
                row.audio_input_signature = audio_signature
                row.audio_path = None
                row.speech_duration_us = None
                row.tts_runtime_profile = RUNTIME_PROFILE
                row.error_message = str(exc)
            row.updated_at = utcnow()
        session.commit()
        voices_out = [_serialize_voice(item) for item in voice_by_id.values()]
        dialogues_out = [_serialize_dialogue(item) for item in dialogues]
        return _bundle(project, str(snapshot["source_fingerprint"]), voices_out, dialogues_out)


def generate_target_dialogue_v1(project_id: str, *, synthesize_audio: bool = True) -> dict[str, Any]:
    text_bundle = generate_target_dialogue_text_v1(project_id)
    if text_bundle["review_count"]:
        return text_bundle
    return materialize_target_dialogue_audio_v1(project_id) if synthesize_audio else text_bundle


def get_target_dialogue_v1(project_id: str) -> dict[str, Any]:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        voices = list(session.scalars(select(TargetVoiceProfile).where(TargetVoiceProfile.project_id == project_id)).all())
        dialogues = list(session.scalars(select(TargetDialogue).where(TargetDialogue.project_id == project_id).order_by(TargetDialogue.episode_id, TargetDialogue.source_start_us)).all())
    contexts = _dialogue_contexts(snapshot, _target_characters(project_id))
    expected = {str(item["source_dialogue_key"]): str(item["signature"]) for item in contexts}
    if len(dialogues) != len(contexts):
        raise TargetDialogueError("TargetDialogue has not been generated for current SourceDramaSnapshot")
    serialized_dialogues = [_serialize_dialogue(item) for item in dialogues]
    if any(expected.get(item["source_dialogue_key"]) != item["source_dialogue_signature"] for item in serialized_dialogues):
        raise TargetDialogueError("TargetDialogue source anchors are stale")
    return _bundle(project, str(snapshot["source_fingerprint"]), [_serialize_voice(item) for item in voices], serialized_dialogues)


def update_target_dialogue_v1(target_dialogue_id: str, *, translated_text: str | None = None, localized_text: str | None = None, final_text: str) -> dict[str, Any]:
    final = _clean(final_text)
    if not final:
        raise ValueError("最终目标对白不能为空")
    with get_session() as session:
        row = session.get(TargetDialogue, target_dialogue_id)
        if row is None:
            raise LookupError("目标对白不存在")
        if not row.target_character_id:
            raise ValueError("目标对白还没有可靠目标说话人，请先修正源说话人/人物绑定")
        row.translated_text = _clean(translated_text) or row.translated_text or final
        row.localized_text = _clean(localized_text) or final
        row.final_text = final
        row.translation_confidence = 1.0
        row.decision_source = "MANUAL"
        row.status = "READY"
        row.audio_status = "PENDING"
        row.audio_input_signature = None
        row.audio_path = None
        row.speech_duration_us = None
        row.error_message = None
        row.updated_at = utcnow()
        project_id, source_key = row.project_id, row.source_dialogue_key
        session.commit(); session.refresh(row)
        result = _serialize_dialogue(row)
    _resolve_issue(project_id, _dialogue_issue_key(source_key), "用户已确认目标对白")
    return result


__all__ = [
    "TargetDialogue",
    "TargetDialogueError",
    "TargetVoiceProfile",
    "generate_target_dialogue_text_v1",
    "generate_target_dialogue_v1",
    "get_target_dialogue_v1",
    "materialize_target_dialogue_audio_v1",
    "update_target_dialogue_v1",
]
