"""Whole-episode source understanding before semantic per-Shot breakdown.

This module implements the business order required by the remake workflow:

    ASR/OCR evidence + full source Episode -> Episode Intelligence -> per-Shot semantics

Gemini is an external/paid provider, so every remote call first materializes a local provider-job
record.  The resulting Episode Intelligence is evidence/context only: it may organize story,
characters, scenes and props, but it never overwrites canonical ASR/OCR dialogue and never creates
Final Character/Scene/Prop or any Target-side object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import mimetypes
import os
from pathlib import Path
import time
from typing import Any, Mapping, Protocol, Sequence

import httpx

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun

EPISODE_INTELLIGENCE_SCHEMA_VERSION = "source-episode-intelligence-v1"
EPISODE_INTELLIGENCE_PROFILE = "source-episode-understanding-gemini31-pro-v1"
GEMINI_PROVIDER_NAME = "google-gemini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
GEMINI_API_KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
CANONICAL_DIALOGUE_POLICY = "asr-ocr-owned-gemini-organizes-but-cannot-overwrite-v1"
RESULT_STATUSES = frozenset({"READY", "NOT_CONFIGURED", "FAILED"})


class SourceEpisodeUnderstandingError(RuntimeError):
    """Whole-episode understanding cannot safely produce a consumable artifact."""


@dataclass(frozen=True)
class EpisodeUnderstandingResult:
    status: str
    provider: str
    model: str
    data: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EpisodeIntelligenceArtifact:
    fingerprint: str
    path: str
    uri: str
    input_fingerprint: str


class SourceEpisodeUnderstandingProvider(Protocol):
    def analyze(
        self,
        context: p2.P2RunContext,
        evidence_artifacts: Sequence[p2.P2EvidenceArtifact],
    ) -> EpisodeUnderstandingResult:
        ...


class GeminiTransport(Protocol):
    def understand_video(
        self,
        *,
        video_path: Path,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        ...


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _api_key() -> str | None:
    for name in GEMINI_API_KEY_ENVS:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def _time_label(value_us: Any) -> str:
    try:
        total_ms = max(0, int(value_us) // 1000)
    except (TypeError, ValueError):
        return "--:--.---"
    minutes, rem_ms = divmod(total_ms, 60_000)
    seconds, millis = divmod(rem_ms, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _artifact_rows(artifact: p2.P2EvidenceArtifact) -> list[Mapping[str, Any]]:
    path = Path(artifact.path)
    if not path.is_file():
        raise SourceEpisodeUnderstandingError(f"上游 Evidence artifact 不存在: {artifact.component}")
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("evidence") if isinstance(value, Mapping) else None
    return [item for item in rows or [] if isinstance(item, Mapping)]


def _evidence_prompt(artifacts: Sequence[p2.P2EvidenceArtifact]) -> str:
    """Compact ASR/OCR evidence for Gemini; source text stays evidence-owned by ASR/OCR."""

    sections: list[str] = []
    for artifact in artifacts:
        component = artifact.component.strip().upper()
        if component not in {"ASR", "OCR"}:
            continue
        lines: list[str] = []
        for row in _artifact_rows(artifact):
            text = " ".join(str(row.get("text") or "").strip().split())
            if not text:
                continue
            source_id = str(row.get("source_id") or "").strip()
            start = _time_label(row.get("source_start_us"))
            end = _time_label(row.get("source_end_us"))
            lines.append(f"[{source_id}] {start}-{end} {text}")
        if lines:
            # Whole short-drama episodes are normally small enough, but cap pathological OCR spam.
            sections.append(f"## {component} EVIDENCE\n" + "\n".join(lines[:3000]))
    return "\n\n".join(sections)


def _shot_anchor_prompt(context: p2.P2RunContext) -> str:
    return "\n".join(
        f"ShotAnchor {shot.ordinal}: {_time_label(shot.start_us)}-{_time_label(shot.end_us)}"
        for shot in context.shots
    )


def _response_schema() -> dict[str, Any]:
    text = {"type": "string"}
    string_array = {"type": "array", "items": text}
    return {
        "type": "object",
        "properties": {
            "episode_summary": text,
            "source_world": {
                "type": "object",
                "properties": {
                    "era": text,
                    "region": text,
                    "social_context": text,
                    "visual_world": text,
                },
                "required": ["era", "region", "social_context", "visual_world"],
            },
            "story_beats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "beat_key": text,
                        "summary": text,
                        "start_time": text,
                        "end_time": text,
                    },
                    "required": ["beat_key", "summary", "start_time", "end_time"],
                },
            },
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "character_key": text,
                        "display_name": text,
                        "aliases": string_array,
                        "identity_summary": text,
                        "appearance_summary": text,
                        "role_in_story": text,
                        "first_seen_time": text,
                    },
                    "required": ["character_key", "display_name", "aliases", "identity_summary", "appearance_summary", "role_in_story", "first_seen_time"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from_character_key": text,
                        "to_character_key": text,
                        "relationship": text,
                        "evidence_summary": text,
                    },
                    "required": ["from_character_key", "to_character_key", "relationship", "evidence_summary"],
                },
            },
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "scene_key": text,
                        "name": text,
                        "location_summary": text,
                        "visual_summary": text,
                        "story_function": text,
                        "time_ranges": string_array,
                    },
                    "required": ["scene_key", "name", "location_summary", "visual_summary", "story_function", "time_ranges"],
                },
            },
            "props": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "prop_key": text,
                        "name": text,
                        "visual_summary": text,
                        "story_function": text,
                        "owner_or_user_character_keys": string_array,
                        "time_ranges": string_array,
                    },
                    "required": ["prop_key", "name", "visual_summary", "story_function", "owner_or_user_character_keys", "time_ranges"],
                },
            },
            "script_scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "scene_key": text,
                        "heading": text,
                        "start_time": text,
                        "end_time": text,
                        "action_summary": text,
                        "character_keys": string_array,
                        "dialogue_evidence_ids": string_array,
                        "story_beat_keys": string_array,
                    },
                    "required": ["scene_key", "heading", "start_time", "end_time", "action_summary", "character_keys", "dialogue_evidence_ids", "story_beat_keys"],
                },
            },
            "key_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "event_key": text,
                        "summary": text,
                        "time_range": text,
                        "character_keys": string_array,
                        "scene_key": text,
                        "prop_keys": string_array,
                    },
                    "required": ["event_key", "summary", "time_range", "character_keys", "scene_key", "prop_keys"],
                },
            },
            "unresolved": string_array,
        },
        "required": ["episode_summary", "source_world", "story_beats", "characters", "relationships", "scenes", "props", "script_scenes", "key_events", "unresolved"],
        "additionalProperties": False,
    }


def _prompt(context: p2.P2RunContext, artifacts: Sequence[p2.P2EvidenceArtifact]) -> str:
    return f"""你是短剧“整集理解”主分析器。现在分析完整 Episode，而不是逐镜拉片。

目标：先建立整集 Source Bible，供后面的逐镜拉片使用。必须从完整视频/音频、ASR/OCR 证据和时间锚点综合理解：原剧剧情、角色、角色关系、场景、关键道具、剧情事件和剧本结构。
原始语言：{context.source_language}

硬规则：
1. 这是逐镜拉片的上游。先理解整集，不要输出逐镜摄影参数、镜头景别或逐镜动作清单。
2. character_key / scene_key / prop_key 是本次分析的“候选稳定键”，不是 Final Character/Scene/Prop ID。
3. ASR/OCR 是 canonical source dialogue 的唯一文字证据所有者。你不得改写、润色、翻译或凭空补写原对白。
4. script_scenes 只组织场景、动作和 dialogue_evidence_ids；不要重复生成对白正文。
5. 视频自带音频可用于理解人物关系、情绪和事件，但若与你看到的 ASR/OCR 文字冲突，不得覆盖 canonical text。
6. ShotAnchor 只是时间定位，不代表业务上已经做过逐镜拉片；不要因为 Shot 边界把同一场景强行拆开。
7. 同一个人物跨镜头要尽量归为同一个 character_key；同一真实地点跨多个镜头尽量归为同一个 scene_key；同一道具重复出现尽量归为同一 prop_key。
8. 只输出源片事实；禁止任何 TargetCharacter、目标语言、目标场景或出海改编内容。
9. 不确定的信息写进 unresolved，不要为了填满字段而编造。
10. 时间使用 MM:SS 或 MM:SS.mmm，并尽量引用真实区间。

【Shot 时间锚点，仅用于定位】
{_shot_anchor_prompt(context)}

【ASR/OCR 原始证据】
{_evidence_prompt(artifacts)}
"""


def episode_understanding_input_fingerprint(
    context: p2.P2RunContext,
    artifacts: Sequence[p2.P2EvidenceArtifact],
    *,
    model: str = DEFAULT_GEMINI_MODEL,
) -> str:
    payload = {
        "schema_version": EPISODE_INTELLIGENCE_SCHEMA_VERSION,
        "profile": EPISODE_INTELLIGENCE_PROFILE,
        "model": model,
        "episode_id": context.episode_id,
        "source_language": context.source_language,
        "source_sha256": context.source_sha256,
        "source_shot_revision_id": context.source_shot_revision_id,
        "evidence": [
            {"component": item.component, "fingerprint": item.fingerprint}
            for item in artifacts
            if item.component in {"ASR", "OCR"}
        ],
    }
    return _sha(payload)


def _provider_job_path(context: p2.P2RunContext, input_fingerprint: str) -> Path:
    root = studio_v2.episode_dir(context.project_id, context.episode_id) / "breakdown" / context.run_id / "provider_jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"episode_intelligence_{input_fingerprint}.json"


def _write_provider_job(
    context: p2.P2RunContext,
    *,
    input_fingerprint: str,
    status: str,
    model: str,
    error_type: str | None = None,
    remote_file_name: str | None = None,
) -> None:
    path = _provider_job_path(context, input_fingerprint)
    now = studio_v2.utcnow().isoformat()
    previous: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                previous = raw
        except (OSError, ValueError):
            previous = {}
    payload = {
        "schema_version": "provider-job-v1",
        "capability": "SOURCE_EPISODE_UNDERSTANDING",
        "scope": {"project_id": context.project_id, "episode_id": context.episode_id, "run_id": context.run_id},
        "provider": GEMINI_PROVIDER_NAME,
        "model": model,
        "payload_hash": input_fingerprint,
        "status": status,
        "attempt_count": int(previous.get("attempt_count") or 0) + (1 if status == "RUNNING" else 0),
        "created_at": previous.get("created_at") or now,
        "updated_at": now,
        "remote_file_name": remote_file_name,
        "error_type": error_type,
    }
    temp = path.with_suffix(".tmp")
    temp.write_text(_stable_json(payload), encoding="utf-8")
    os.replace(temp, path)


class HttpxGeminiTransport:
    """Minimal current Gemini REST transport; API key is never persisted in artifacts/jobs."""

    def __init__(self, api_key: str, *, model: str = DEFAULT_GEMINI_MODEL, timeout_seconds: float = 900.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = float(timeout_seconds)

    def understand_video(
        self,
        *,
        video_path: Path,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        mime_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
        size = video_path.stat().st_size
        headers = {"x-goog-api-key": self.api_key}
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            start = client.post(
                f"{GEMINI_API_BASE}/upload/v1beta/files",
                headers={
                    **headers,
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(size),
                    "X-Goog-Upload-Header-Content-Type": mime_type,
                    "Content-Type": "application/json",
                },
                json={"file": {"display_name": video_path.name}},
            )
            start.raise_for_status()
            upload_url = start.headers.get("x-goog-upload-url")
            if not upload_url:
                raise SourceEpisodeUnderstandingError("Gemini Files API 未返回 upload URL")
            with video_path.open("rb") as handle:
                uploaded = client.post(
                    upload_url,
                    headers={
                        "Content-Length": str(size),
                        "X-Goog-Upload-Offset": "0",
                        "X-Goog-Upload-Command": "upload, finalize",
                    },
                    content=handle,
                )
            uploaded.raise_for_status()
            file_obj = uploaded.json().get("file") or {}
            file_name = str(file_obj.get("name") or "").strip()
            file_uri = str(file_obj.get("uri") or "").strip()
            state = str(file_obj.get("state") or "").strip().upper()
            if not file_name or not file_uri:
                raise SourceEpisodeUnderstandingError("Gemini Files API 返回的文件引用不完整")

            deadline = time.monotonic() + self.timeout_seconds
            while state not in {"ACTIVE", "FAILED"}:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Gemini 视频处理超时")
                time.sleep(3.0)
                status = client.get(f"{GEMINI_API_BASE}/v1beta/{file_name}", headers=headers)
                status.raise_for_status()
                file_obj = status.json()
                state = str(file_obj.get("state") or "").strip().upper()
            if state != "ACTIVE":
                raise SourceEpisodeUnderstandingError("Gemini 视频预处理失败")

            response = client.post(
                f"{GEMINI_API_BASE}/v1beta/models/{self.model}:generateContent",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "contents": [{
                        "role": "user",
                        "parts": [
                            {"fileData": {"mimeType": mime_type, "fileUri": file_uri}},
                            {"text": prompt},
                        ],
                    }],
                    "generationConfig": {
                        "responseFormat": {
                            "text": {"mimeType": "application/json", "schema": dict(response_schema)}
                        }
                    },
                },
            )
            response.raise_for_status()
            body = response.json()
            candidates = body.get("candidates") or []
            parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
            text = next((str(item.get("text")) for item in parts if isinstance(item, Mapping) and item.get("text")), "")
            if not text:
                raise SourceEpisodeUnderstandingError("Gemini 未返回整集结构化结果")
            value = json.loads(text)
            if not isinstance(value, Mapping):
                raise SourceEpisodeUnderstandingError("Gemini 整集结果不是 JSON object")
            return dict(value), {
                "remote_file_name": file_name,
                "mime_type": mime_type,
                "usage_metadata": body.get("usageMetadata") or {},
            }


class Gemini31ProEpisodeUnderstandingProvider:
    provider_name = GEMINI_PROVIDER_NAME

    def __init__(
        self,
        *,
        model: str = DEFAULT_GEMINI_MODEL,
        transport: GeminiTransport | None = None,
    ) -> None:
        self.model = model
        self._transport = transport

    def analyze(
        self,
        context: p2.P2RunContext,
        evidence_artifacts: Sequence[p2.P2EvidenceArtifact],
    ) -> EpisodeUnderstandingResult:
        if not context.source_video_path:
            return EpisodeUnderstandingResult(
                status="FAILED", provider=self.provider_name, model=self.model,
                warnings=("Episode source video path missing",),
            )
        video_path = Path(context.source_video_path)
        if not video_path.is_file():
            return EpisodeUnderstandingResult(
                status="FAILED", provider=self.provider_name, model=self.model,
                warnings=("Episode source video file missing",),
            )

        input_fingerprint = episode_understanding_input_fingerprint(context, evidence_artifacts, model=self.model)
        transport = self._transport
        if transport is None:
            key = _api_key()
            if not key:
                _write_provider_job(context, input_fingerprint=input_fingerprint, status="NOT_CONFIGURED", model=self.model)
                return EpisodeUnderstandingResult(
                    status="NOT_CONFIGURED",
                    provider=self.provider_name,
                    model=self.model,
                    metadata={"input_fingerprint": input_fingerprint, "provider_profile": EPISODE_INTELLIGENCE_PROFILE},
                    warnings=("Gemini API key 未配置（GEMINI_API_KEY / GOOGLE_API_KEY）",),
                )
            transport = HttpxGeminiTransport(key, model=self.model)

        _write_provider_job(context, input_fingerprint=input_fingerprint, status="CREATED", model=self.model)
        _write_provider_job(context, input_fingerprint=input_fingerprint, status="RUNNING", model=self.model)
        try:
            data, remote_meta = transport.understand_video(
                video_path=video_path,
                prompt=_prompt(context, evidence_artifacts),
                response_schema=_response_schema(),
            )
            # Defensive boundary: no Target-side payload and no model-authored canonical dialogue body.
            forbidden = {"target_character", "target_scene", "target_dialogue", "canonical_dialogue", "dialogue_text"}
            lowered = {str(key).casefold() for key in data.keys()}
            if lowered & forbidden:
                raise SourceEpisodeUnderstandingError("Gemini Episode Intelligence 包含禁止的 Target/canonical dialogue 字段")
            _write_provider_job(
                context,
                input_fingerprint=input_fingerprint,
                status="SUCCEEDED",
                model=self.model,
                remote_file_name=str(remote_meta.get("remote_file_name") or "") or None,
            )
            return EpisodeUnderstandingResult(
                status="READY",
                provider=self.provider_name,
                model=self.model,
                data=dict(data),
                metadata={
                    "input_fingerprint": input_fingerprint,
                    "provider_profile": EPISODE_INTELLIGENCE_PROFILE,
                    "canonical_dialogue_policy": CANONICAL_DIALOGUE_POLICY,
                    **dict(remote_meta),
                },
            )
        except Exception as exc:
            _write_provider_job(
                context,
                input_fingerprint=input_fingerprint,
                status="FAILED",
                model=self.model,
                error_type=type(exc).__name__,
            )
            return EpisodeUnderstandingResult(
                status="FAILED",
                provider=self.provider_name,
                model=self.model,
                metadata={"input_fingerprint": input_fingerprint, "provider_profile": EPISODE_INTELLIGENCE_PROFILE},
                warnings=(f"Gemini whole-episode understanding failed: {type(exc).__name__}",),
            )


def persist_episode_intelligence(
    context: p2.P2RunContext,
    result: EpisodeUnderstandingResult,
) -> EpisodeIntelligenceArtifact:
    if result.status != "READY" or not result.data:
        raise SourceEpisodeUnderstandingError("只有 READY Episode Intelligence 可以固化")
    input_fingerprint = str(result.metadata.get("input_fingerprint") or "").strip()
    if not input_fingerprint:
        raise SourceEpisodeUnderstandingError("Episode Intelligence 缺少 input_fingerprint")
    payload = {
        "schema_version": EPISODE_INTELLIGENCE_SCHEMA_VERSION,
        "run_id": context.run_id,
        "project_id": context.project_id,
        "episode_id": context.episode_id,
        "source_shot_revision_id": context.source_shot_revision_id,
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "metadata": dict(result.metadata),
        "warnings": list(result.warnings),
        "data": dict(result.data),
    }
    serialized = _stable_json(payload)
    fingerprint = sha256(serialized.encode("utf-8")).hexdigest()
    root = studio_v2.episode_dir(context.project_id, context.episode_id) / "breakdown" / context.run_id / "episode_intelligence"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{fingerprint}.json"
    if not path.exists():
        temp = root / f".{fingerprint}.tmp"
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, path)

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, context.run_id)
        if run is None or run.status != "PROCESSING" or run.source_shot_revision_id != context.source_shot_revision_id:
            raise SourceEpisodeUnderstandingError("Episode Intelligence 完成时 BreakdownRun 已不可写")
        statuses = json.loads(run.component_status_json or "{}")
        providers = json.loads(run.provider_metadata_json or "{}")
        statuses["EPISODE_INTELLIGENCE"] = {
            "status": "READY",
            "provider": result.provider,
            "model": result.model,
            "artifact_uri": path.resolve().as_uri(),
            "fingerprint": fingerprint,
            "input_fingerprint": input_fingerprint,
        }
        providers["episode_intelligence"] = {
            "provider": result.provider,
            "model": result.model,
            "profile": EPISODE_INTELLIGENCE_PROFILE,
            "input_fingerprint": input_fingerprint,
        }
        run.component_status_json = _stable_json(statuses)
        run.provider_metadata_json = _stable_json(providers)
        session.commit()

    return EpisodeIntelligenceArtifact(
        fingerprint=fingerprint,
        path=str(path),
        uri=path.resolve().as_uri(),
        input_fingerprint=input_fingerprint,
    )


__all__ = [
    "CANONICAL_DIALOGUE_POLICY",
    "DEFAULT_GEMINI_MODEL",
    "EPISODE_INTELLIGENCE_PROFILE",
    "EPISODE_INTELLIGENCE_SCHEMA_VERSION",
    "EpisodeIntelligenceArtifact",
    "EpisodeUnderstandingResult",
    "Gemini31ProEpisodeUnderstandingProvider",
    "HttpxGeminiTransport",
    "SourceEpisodeUnderstandingError",
    "SourceEpisodeUnderstandingProvider",
    "episode_understanding_input_fingerprint",
    "persist_episode_intelligence",
]
