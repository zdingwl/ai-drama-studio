"""Revision-safe single-Shot Breakdown rerun.

A complete BreakdownRun is immutable Episode truth and its publish validator requires full
ShotRevision coverage.  Re-running one Shot therefore must not create a fake/partial
BreakdownRun.  This module executes the existing P2 providers on a narrow scope and stores a
separate AI overlay anchored to the current complete BreakdownRun + ShotRevision.

Execution scope:
- ASR: only the target Shot audio window (+ small boundary padding), never the whole Episode;
- OCR: only the exact target Shot Reference Clip;
- VLM: target Shot plus at most one neighbouring Shot on each side for scene/continuity context;
- only target-Shot facts are projected back to the ordinary SceneTimeline.

Safety boundaries:
- immutable BreakdownRun / ShotSemanticDraft / TimelineEvent rows are never mutated;
- Scene segmentation and anonymous/Final Character identity are not rewritten by a single-Shot
  rerun; those need Episode/Scene context and remain owned by the full pipeline / asset flow;
- historical Runs never consume a current rerun because every artifact is anchored to
  source_breakdown_run_id as well as source_shot_revision_id;
- a new ShotRevision automatically makes all older reruns inapplicable;
- GET paths only read persisted artifacts and never run a provider.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
import tempfile
from typing import Any, Callable

from sqlalchemy import select

from engine.app import breakdown_p2_fusion_v1 as fusion
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import studio_v2
from engine.app.breakdown_p2_asr_v1 import FasterWhisperASRProvider
from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider
from engine.app.breakdown_p2_vlm_continuity_v1 import Qwen3VLSemanticProvider
from engine.app.breakdown_scene_timeline_assembler_v1 import assemble_scene_timeline_v1
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.media_v2 import MediaPipelineError, _run as _run_media_command
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem


SHOT_RERUN_SCHEMA_VERSION = "breakdown-shot-rerun-v1"
SHOT_RERUN_PROFILE = "breakdown-shot-rerun-p2-local-context-v1"
SHOT_RERUN_AUDIO_PADDING_US = 800_000
SHOT_RERUN_SCOPE_WARNING = (
    "部分分镜使用单镜重拉结果；Scene 边界和人物身份仍沿用当前整集拉片/原片确认结果。"
)
SHOT_RERUN_FALLBACK_WARNING = "单分镜重拉结果无法安全读取，当前继续展示整集拉片结果。"
_PROVIDER_ORDER = ("ASR", "OCR", "VLM")
_ALLOWED_DEGRADED = frozenset({"NO_EVIDENCE", "NOT_AVAILABLE"})
_WRITE_LOCK = RLock()

ProgressCallback = Callable[[float, str, str], None]


class BreakdownShotRerunError(RuntimeError):
    """Single-Shot rerun cannot be executed or projected safely."""


def _report(progress: ProgressCallback | None, percent: float, stage: str, message: str) -> None:
    if progress is not None:
        progress(max(0.0, min(100.0, float(percent))), stage, message)


def _run_payload(draft: Mapping[str, Any]) -> Mapping[str, Any]:
    run = draft.get("run")
    if not isinstance(run, Mapping):
        raise BreakdownShotRerunError("当前拉片结果缺少 Run 锚点")
    return run


def _anchors(draft: Mapping[str, Any]) -> tuple[str, str, str, str]:
    run = _run_payload(draft)
    run_id = str(run.get("id") or "").strip()
    project_id = str(run.get("project_id") or "").strip()
    episode_id = str(run.get("episode_id") or "").strip()
    revision_id = str(run.get("source_shot_revision_id") or "").strip()
    if not all((run_id, project_id, episode_id, revision_id)):
        raise BreakdownShotRerunError("当前拉片结果缺少 Run / Project / Episode / ShotRevision 锚点")
    if str(run.get("status") or "").strip().upper() not in {"READY", "READY_WITH_WARNINGS"}:
        raise BreakdownShotRerunError("单分镜重拉要求当前整集拉片已完成")
    if run.get("is_current") is not True:
        raise BreakdownShotRerunError("单分镜重拉只允许基于 Current BreakdownRun")
    return run_id, project_id, episode_id, revision_id


def _keyframes(raw: str | None) -> tuple[Any, ...]:
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    return tuple(value) if isinstance(value, list) else ()


def _load_full_context(draft: Mapping[str, Any], *, rerun_id: str) -> p2.P2RunContext:
    _run_id, project_id, episode_id, revision_id = _anchors(draft)
    with studio_v2.get_session() as session:
        project = session.get(studio_v2.Project, project_id)
        episode = session.get(studio_v2.Episode, episode_id)
        revision = session.get(ShotRevision, revision_id)
        if project is None or episode is None or revision is None:
            raise BreakdownShotRerunError("单镜重拉的 Project/Episode/ShotRevision 历史锚点不完整")
        current_revision = session.scalar(
            select(ShotRevision).where(
                ShotRevision.episode_id == episode_id,
                ShotRevision.is_current.is_(True),
            )
        )
        if current_revision is None or current_revision.id != revision_id or not revision.is_current:
            raise BreakdownShotRerunError("当前 ShotRevision 已变化，请先刷新页面再重拉")
        items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        if not items:
            raise BreakdownShotRerunError("当前 ShotRevision 没有可处理分镜")
        preprocess = session.scalar(
            select(studio_v2.Preprocess).where(studio_v2.Preprocess.episode_id == episode_id)
        )
        shots = tuple(
            p2.P2ShotInput(
                revision_item_id=item.id,
                original_shot_id=item.original_shot_id,
                ordinal=item.ordinal,
                start_us=item.start_us,
                end_us=item.end_us,
                duration_us=item.duration_us,
                reference_clip_path=item.reference_clip_path,
                thumbnail_path=item.thumbnail_path,
                keyframes=_keyframes(item.keyframes_json),
            )
            for item in items
        )
        return p2.P2RunContext(
            run_id=rerun_id,
            project_id=project_id,
            episode_id=episode_id,
            source_language=project.source_language,
            source_shot_revision_id=revision_id,
            audio_path=preprocess.audio_path if preprocess else None,
            shots=shots,
        )


def _target_shot(context: p2.P2RunContext, shot_ordinal: int) -> p2.P2ShotInput:
    if shot_ordinal <= 0:
        raise BreakdownShotRerunError("shot_ordinal 必须大于 0")
    for shot in context.shots:
        if shot.ordinal == shot_ordinal:
            return shot
    raise LookupError("当前 ShotRevision 中不存在该分镜")


def _timeline_scene_and_shot(
    timeline: Mapping[str, Any] | SceneTimelinePayloadV1,
    shot_ordinal: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = (
        timeline.model_dump(mode="json")
        if isinstance(timeline, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline).model_dump(mode="json")
    )
    for scene in normalized["scenes"]:
        for shot in scene["shots"]:
            if int(shot["ordinal"]) == shot_ordinal:
                return scene, shot
    raise LookupError("当前整集拉片结果中不存在该分镜")


def _vlm_context_shots(
    context: p2.P2RunContext,
    base_timeline: Mapping[str, Any] | SceneTimelinePayloadV1,
    target: p2.P2ShotInput,
) -> tuple[p2.P2ShotInput, ...]:
    """Prefer one neighbour each side inside the existing Scene, then fall back to global adjacency."""

    scene, _base_shot = _timeline_scene_and_shot(base_timeline, target.ordinal)
    same_scene_ordinals = [int(item["ordinal"]) for item in scene.get("shots") or []]
    selected: set[int] = {target.ordinal}
    if target.ordinal in same_scene_ordinals:
        index = same_scene_ordinals.index(target.ordinal)
        if index > 0:
            selected.add(same_scene_ordinals[index - 1])
        if index + 1 < len(same_scene_ordinals):
            selected.add(same_scene_ordinals[index + 1])

    ordered = list(context.shots)
    global_index = next((index for index, item in enumerate(ordered) if item.ordinal == target.ordinal), -1)
    if global_index >= 0:
        if len(selected) < 3 and global_index > 0:
            selected.add(ordered[global_index - 1].ordinal)
        if len(selected) < 3 and global_index + 1 < len(ordered):
            selected.add(ordered[global_index + 1].ordinal)

    candidates = [item for item in ordered if item.ordinal in selected]
    candidates.sort(key=lambda item: item.ordinal)
    if len(candidates) <= 3:
        return tuple(candidates)
    # Defensive cap: closest ordinals to target, then chronological order.
    candidates.sort(key=lambda item: (abs(item.ordinal - target.ordinal), item.ordinal))
    return tuple(sorted(candidates[:3], key=lambda item: item.ordinal))


def _provider_map(
    providers: Sequence[p2.BreakdownP2Provider] | None,
) -> dict[str, p2.BreakdownP2Provider]:
    source: Sequence[p2.BreakdownP2Provider]
    if providers is None:
        source = (
            FasterWhisperASRProvider(),
            RapidOCROCRProvider(),
            Qwen3VLSemanticProvider(),
        )
    else:
        source = providers
    result: dict[str, p2.BreakdownP2Provider] = {}
    for provider in source:
        component = str(provider.component).strip().upper()
        if component not in _PROVIDER_ORDER:
            raise BreakdownShotRerunError(f"单镜重拉收到未知 Provider component：{component}")
        if component in result:
            raise BreakdownShotRerunError(f"单镜重拉 Provider 重复：{component}")
        result[component] = provider
    missing = [component for component in _PROVIDER_ORDER if component not in result]
    if missing:
        raise BreakdownShotRerunError(f"单镜重拉缺少 Provider：{', '.join(missing)}")
    return result


def _execute_provider(
    provider: p2.BreakdownP2Provider,
    context: p2.P2RunContext,
) -> p2.P2ProviderResult:
    expected = str(provider.component).strip().upper()
    result = provider.analyze(context)
    if str(result.component).strip().upper() != expected:
        raise BreakdownShotRerunError("Provider.component 与 ProviderResult.component 不一致")
    p2.validate_provider_result(context, result)
    if result.status in {"FAILED", "NOT_CONFIGURED"}:
        detail = next((str(item).strip() for item in result.warnings if str(item).strip()), "")
        raise BreakdownShotRerunError(
            f"{expected} 单镜重拉失败（{result.status}）" + (f"：{detail}" if detail else "")
        )
    if expected == "VLM" and result.status != "READY":
        detail = next((str(item).strip() for item in result.warnings if str(item).strip()), "")
        raise BreakdownShotRerunError(
            f"VLM 单镜重拉要求 READY，当前为 {result.status}" + (f"：{detail}" if detail else "")
        )
    if expected in {"ASR", "OCR"} and result.status not in ({"READY"} | set(_ALLOWED_DEGRADED)):
        raise BreakdownShotRerunError(f"{expected} 单镜重拉状态不可消费：{result.status}")
    return result


def _materialize_audio_window(
    source: Path,
    output: Path,
    *,
    start_us: int,
    end_us: int,
) -> None:
    if end_us <= start_us:
        raise BreakdownShotRerunError("单镜 ASR 音频范围无效")
    try:
        _run_media_command([
            "ffmpeg",
            "-y",
            "-ss", f"{start_us / 1_000_000.0:.6f}",
            "-t", f"{(end_us - start_us) / 1_000_000.0:.6f}",
            "-i", str(source),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(output),
        ], timeout=20 * 60)
    except MediaPipelineError as exc:
        raise BreakdownShotRerunError("无法生成当前分镜 ASR 音频片段") from exc
    if not output.is_file():
        raise BreakdownShotRerunError("当前分镜 ASR 音频片段生成失败")


def _shift_asr_result(result: p2.P2ProviderResult, *, offset_us: int) -> p2.P2ProviderResult:
    if offset_us == 0 or not result.evidence:
        metadata = dict(result.metadata)
        metadata["source_time_offset_us"] = int(offset_us)
        return p2.P2ProviderResult(
            component=result.component,
            provider=result.provider,
            model=result.model,
            status=result.status,
            evidence=result.evidence,
            metadata=metadata,
            warnings=result.warnings,
        )
    shifted: list[p2.P2EvidenceRecord] = []
    for record in result.evidence:
        start = record.source_start_us + offset_us if record.source_start_us is not None else None
        end = record.source_end_us + offset_us if record.source_end_us is not None else None
        shifted.append(p2.P2EvidenceRecord(
            source_type=record.source_type,
            source_id=record.source_id,
            source_start_us=start,
            source_end_us=end,
            shot_revision_item_id=record.shot_revision_item_id,
            text=record.text,
            language=record.language,
            confidence=record.confidence,
            payload=dict(record.payload),
        ))
    metadata = dict(result.metadata)
    metadata["source_time_offset_us"] = int(offset_us)
    return p2.P2ProviderResult(
        component=result.component,
        provider=result.provider,
        model=result.model,
        status=result.status,
        evidence=tuple(shifted),
        metadata=metadata,
        warnings=result.warnings,
    )


def _normalized_text(value: Any) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    return "".join(text.split())


def _clean_text(value: Any, *, max_len: int = 4000) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_len] if text else None


def _best_existing_dialogue(
    base_dialogues: Sequence[Mapping[str, Any]],
    *,
    start_us: int,
    end_us: int,
    used: set[int],
) -> Mapping[str, Any] | None:
    best_index = -1
    best_overlap = 0
    for index, item in enumerate(base_dialogues):
        if index in used:
            continue
        try:
            old_start = int(item.get("start_us"))
            old_end = int(item.get("end_us"))
        except (TypeError, ValueError):
            continue
        overlap = min(end_us, old_end) - max(start_us, old_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index
    if best_index < 0:
        return None
    used.add(best_index)
    return base_dialogues[best_index]


def _dialogue_projection(
    target: p2.P2ShotInput,
    base_shot: Mapping[str, Any],
    result: p2.P2ProviderResult,
    *,
    rerun_id: str,
) -> list[dict[str, Any]] | None:
    if result.status == "NOT_AVAILABLE":
        return None
    if result.status == "NO_EVIDENCE":
        return []

    segments = [
        item for item in result.evidence
        if item.source_type.strip().upper() == "ASR_SEGMENT"
    ]
    words_by_segment: dict[str, list[p2.P2EvidenceRecord]] = {}
    for word in result.evidence:
        if word.source_type.strip().upper() != "ASR_WORD":
            continue
        payload = word.payload if isinstance(word.payload, Mapping) else {}
        segment_id = str(payload.get("segment_id") or "").strip()
        if segment_id:
            words_by_segment.setdefault(segment_id, []).append(word)

    raw_base_dialogues = base_shot.get("dialogue")
    base_dialogues = [item for item in raw_base_dialogues if isinstance(item, Mapping)] if isinstance(raw_base_dialogues, list) else []
    used_existing: set[int] = set()
    rows: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda item: (item.source_start_us or 0, item.source_id)):
        if segment.source_start_us is None or segment.source_end_us is None:
            continue
        overlap_start = max(int(segment.source_start_us), target.start_us)
        overlap_end = min(int(segment.source_end_us), target.end_us)
        if overlap_end <= overlap_start:
            continue
        segment_words = sorted(
            words_by_segment.get(segment.source_id, []),
            key=lambda item: (item.source_start_us or 0, item.source_id),
        )
        words = [
            word for word in segment_words
            if word.source_start_us is not None
            and word.source_end_us is not None
            and min(int(word.source_end_us), target.end_us) > max(int(word.source_start_us), target.start_us)
        ]
        if words:
            source_start = max(target.start_us, min(int(item.source_start_us) for item in words if item.source_start_us is not None))
            source_end = min(target.end_us, max(int(item.source_end_us) for item in words if item.source_end_us is not None))
            raw_parts: list[str] = []
            for word in words:
                payload = word.payload if isinstance(word.payload, Mapping) else {}
                raw_parts.append(str(payload.get("raw_word") or word.text or ""))
            content = "".join(raw_parts).strip() or " ".join(str(item.text or "").strip() for item in words).strip()
        else:
            source_start = overlap_start
            source_end = overlap_end
            content = str(segment.text or "").strip()
        if not content:
            continue
        source_start = max(target.start_us, min(target.end_us - 1, int(source_start)))
        source_end = max(source_start + 1, min(target.end_us, int(source_end)))
        existing = _best_existing_dialogue(
            base_dialogues,
            start_us=source_start,
            end_us=source_end,
            used=used_existing,
        )
        existing_group = str(existing.get("dialogue_group_id") or "").strip() if existing else ""
        existing_speakers = existing.get("speakers") if existing else []
        speakers = [str(item) for item in existing_speakers] if isinstance(existing_speakers, list) else []
        source_language = segment.language
        if not source_language and existing:
            source_language = str(existing.get("source_language") or "").strip() or None
        rows.append({
            "dialogue_group_id": existing_group or f"{rerun_id}:DG:{len(rows) + 1:04d}",
            "start_us": source_start,
            "end_us": source_end,
            "text": content,
            "source_language": source_language,
            "speakers": speakers,
        })
    return rows


def _ocr_projection(
    target: p2.P2ShotInput,
    result: p2.P2ProviderResult,
) -> list[dict[str, Any]] | None:
    if result.status == "NOT_AVAILABLE":
        return None
    if result.status == "NO_EVIDENCE":
        return []
    records = [
        item for item in result.evidence
        if item.source_type.strip().upper() == "OCR_OBSERVATION"
        and item.shot_revision_item_id == target.revision_item_id
    ]
    try:
        interval = max(1, int(result.metadata.get("sample_interval_us") or 500_000))
    except (TypeError, ValueError):
        interval = 500_000
    clusters, _warnings = fusion._ocr_clusters(
        records,
        {target.revision_item_id: target},
        sample_interval_us=interval,
    )
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        if not cluster.records:
            continue
        first = cluster.records[0]
        last = cluster.records[-1]
        if first.source_start_us is None or last.source_start_us is None:
            continue
        source_start = max(target.start_us, min(target.end_us - 1, int(first.source_start_us)))
        if len(cluster.records) == 1:
            source_end = min(target.end_us, source_start + 1)
        else:
            source_end = min(target.end_us, int(last.source_start_us) + interval)
            source_end = max(source_start + 1, source_end)
        rows.append({
            "start_us": source_start,
            "end_us": source_end,
            "text": cluster.text,
        })
    rows.sort(key=lambda item: (int(item["start_us"]), int(item["end_us"]), str(item["text"])))
    return rows


def _target_vlm_semantic(
    target: p2.P2ShotInput,
    result: p2.P2ProviderResult,
) -> Mapping[str, Any]:
    for record in result.evidence:
        if (
            record.source_type.strip().upper() == "VLM_OUTPUT"
            and record.shot_revision_item_id == target.revision_item_id
            and isinstance(record.payload, Mapping)
        ):
            semantic = record.payload.get("semantic")
            if isinstance(semantic, Mapping):
                return semantic
    raise BreakdownShotRerunError("VLM 已完成但没有当前 Shot 的 exact-Shot 语义")


def _performance_rows(semantic: Mapping[str, Any], base_shot: Mapping[str, Any]) -> list[dict[str, Any]]:
    texts: list[str] = []
    raw_events = semantic.get("events")
    if isinstance(raw_events, list):
        for event in raw_events:
            if not isinstance(event, Mapping) or str(event.get("event_type") or "").strip().upper() != "ACTION":
                continue
            content = _clean_text(event.get("content"), max_len=2000)
            if content and content not in texts:
                texts.append(content)
    raw_subjects = semantic.get("subjects")
    if isinstance(raw_subjects, list):
        for subject in raw_subjects:
            if not isinstance(subject, Mapping):
                continue
            activity = _clean_text(subject.get("activity_summary"), max_len=2000)
            if activity and activity not in texts:
                texts.append(activity)
    people = base_shot.get("people")
    safe_people = [str(item) for item in people] if isinstance(people, list) and len(people) == 1 else []
    return [{"text": item, "people": list(safe_people)} for item in texts]


def _prop_rows(semantic: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_props = semantic.get("props")
    if not isinstance(raw_props, list):
        return rows
    for raw in raw_props:
        if not isinstance(raw, Mapping):
            continue
        label = _clean_text(raw.get("label"), max_len=255)
        key = _normalized_text(label)
        if not label or not key or key in seen:
            continue
        seen.add(key)
        rows.append({
            "label": label,
            "interaction": _clean_text(raw.get("narrative_reason"), max_len=2000),
        })
    return rows


def build_shot_rerun_overlay_v1(
    *,
    target: p2.P2ShotInput,
    base_timeline: Mapping[str, Any] | SceneTimelinePayloadV1,
    asr_result: p2.P2ProviderResult,
    ocr_result: p2.P2ProviderResult,
    vlm_result: p2.P2ProviderResult,
    rerun_id: str,
) -> tuple[dict[str, Any], list[str]]:
    """Pure deterministic projection from scoped provider evidence to one Shot Timeline patch."""

    base_scene, base_shot = _timeline_scene_and_shot(base_timeline, target.ordinal)
    semantic = _target_vlm_semantic(target, vlm_result)
    shot_semantic = semantic.get("shot") if isinstance(semantic.get("shot"), Mapping) else {}

    overlay: dict[str, Any] = {}
    summary = _clean_text(shot_semantic.get("summary"), max_len=4000)
    visual = _clean_text(shot_semantic.get("visual_description"), max_len=8000)
    narrative = _clean_text(shot_semantic.get("narrative_function_hint"), max_len=4000)
    if summary is not None:
        overlay["summary"] = summary
    if visual is not None:
        overlay["visual_description"] = visual
    if narrative is not None:
        overlay["narrative_function"] = narrative

    overlay["performance"] = _performance_rows(semantic, base_shot)
    overlay["props"] = _prop_rows(semantic)
    camera: dict[str, Any] = {}
    for source_key, target_key in (
        ("shot_type_hint", "shot_type"),
        ("composition_hint", "composition"),
        ("camera_motion_hint", "camera_motion"),
    ):
        value = _clean_text(shot_semantic.get(source_key), max_len=1800)
        if value is not None:
            camera[target_key] = value
    if camera:
        overlay["cinematography"] = camera

    dialogue = _dialogue_projection(target, base_shot, asr_result, rerun_id=rerun_id)
    if dialogue is not None:
        overlay["dialogue"] = dialogue
    screen_text = _ocr_projection(target, ocr_result)
    if screen_text is not None:
        overlay["on_screen_text"] = screen_text

    user_warnings: list[str] = []
    raw_subjects = semantic.get("subjects")
    subject_count = len([item for item in raw_subjects if isinstance(item, Mapping)]) if isinstance(raw_subjects, list) else 0
    base_people = base_shot.get("people")
    base_people_count = len(base_people) if isinstance(base_people, list) else 0
    if subject_count != base_people_count:
        user_warnings.append(
            f"Shot {target.ordinal:02d} 单镜重拉检测到的人物数量与当前整集结果不同；"
            "为避免错误改身份，人物归属未自动覆盖，请在原片确认中复核。"
        )

    raw_scene = semantic.get("scene") if isinstance(semantic.get("scene"), Mapping) else {}
    new_location = _clean_text(raw_scene.get("location_hint"), max_len=255)
    old_scene_info = base_scene.get("scene_info") if isinstance(base_scene.get("scene_info"), Mapping) else {}
    old_location = _clean_text(old_scene_info.get("location"), max_len=255)
    if new_location and old_location and _normalized_text(new_location) != _normalized_text(old_location):
        user_warnings.append(
            f"Shot {target.ordinal:02d} 单镜重拉出现新的场景提示；"
            "单镜模式不会自动改写共享 Scene 边界，建议需要时执行整集拉片。"
        )

    return overlay, user_warnings


def _record_payload(record: p2.P2EvidenceRecord) -> dict[str, Any]:
    return {
        "source_type": record.source_type,
        "source_id": record.source_id,
        "source_start_us": record.source_start_us,
        "source_end_us": record.source_end_us,
        "shot_revision_item_id": record.shot_revision_item_id,
        "text": record.text,
        "language": record.language,
        "confidence": record.confidence,
        "payload": dict(record.payload),
    }


def _result_payload(result: p2.P2ProviderResult) -> dict[str, Any]:
    return {
        "component": result.component,
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "metadata": dict(result.metadata),
        "warnings": list(result.warnings),
        "evidence": [_record_payload(item) for item in result.evidence],
    }


def _canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "artifact_fingerprint"}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_dir(draft: Mapping[str, Any], shot_ordinal: int) -> Path:
    _run_id, project_id, episode_id, revision_id = _anchors(draft)
    return (
        studio_v2.episode_dir(project_id, episode_id)
        / "breakdown"
        / "shot-reruns"
        / revision_id
        / f"shot-{shot_ordinal:06d}"
    )


def shot_rerun_current_path_v1(draft: Mapping[str, Any], shot_ordinal: int) -> Path:
    return _artifact_dir(draft, shot_ordinal) / "current.json"


def _write_atomic(path: Path, serialized: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def persist_shot_rerun_artifact_v1(
    draft: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> Path:
    shot_ordinal = int(artifact.get("shot_ordinal") or 0)
    rerun_id = str(artifact.get("rerun_id") or "").strip()
    if shot_ordinal <= 0 or not rerun_id:
        raise BreakdownShotRerunError("单镜重拉 artifact 缺少 rerun_id/shot_ordinal")
    payload = dict(artifact)
    payload["artifact_fingerprint"] = _canonical_fingerprint(payload)
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise BreakdownShotRerunError("单镜重拉 artifact 无法安全序列化") from exc

    with _WRITE_LOCK:
        root = _artifact_dir(draft, shot_ordinal)
        root.mkdir(parents=True, exist_ok=True)
        archive = root / f"{rerun_id}.json"
        if archive.exists():
            raise BreakdownShotRerunError("单镜重拉 rerun_id 已存在，拒绝覆盖历史 artifact")
        _write_atomic(archive, serialized)
        _write_atomic(root / "current.json", serialized)
    return archive


def _artifact_compatible(
    draft: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> bool:
    run_id, project_id, episode_id, revision_id = _anchors(draft)
    expected = {
        "schema_version": SHOT_RERUN_SCHEMA_VERSION,
        "profile": SHOT_RERUN_PROFILE,
        "source_breakdown_run_id": run_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "source_shot_revision_id": revision_id,
    }
    if any(str(artifact.get(key) or "") != str(value) for key, value in expected.items()):
        return False
    fingerprint = str(artifact.get("artifact_fingerprint") or "").strip().lower()
    return len(fingerprint) == 64 and fingerprint == _canonical_fingerprint(artifact)


def apply_shot_rerun_overrides_v1(
    draft: Mapping[str, Any],
    timeline_payload: Mapping[str, Any] | SceneTimelinePayloadV1,
) -> dict[str, Any]:
    """Pure-read projection of persisted current single-Shot AI reruns."""

    timeline = (
        timeline_payload.model_dump(mode="json")
        if isinstance(timeline_payload, SceneTimelinePayloadV1)
        else SceneTimelinePayloadV1.model_validate(timeline_payload).model_dump(mode="json")
    )
    _run_id, project_id, episode_id, revision_id = _anchors(draft)
    root = (
        studio_v2.episode_dir(project_id, episode_id)
        / "breakdown"
        / "shot-reruns"
        / revision_id
    )
    if not root.is_dir():
        return timeline

    artifacts: list[Mapping[str, Any]] = []
    corrupt = False
    for path in sorted(root.glob("shot-*/current.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            corrupt = True
            continue
        if not isinstance(raw, Mapping):
            corrupt = True
            continue
        if _artifact_compatible(draft, raw):
            artifacts.append(raw)

    if not artifacts and not corrupt:
        return timeline

    by_ordinal: dict[int, dict[str, Any]] = {}
    scene_by_ordinal: dict[int, dict[str, Any]] = {}
    for scene in timeline["scenes"]:
        for shot in scene["shots"]:
            by_ordinal[int(shot["ordinal"])] = shot
            scene_by_ordinal[int(shot["ordinal"])] = scene

    applied = 0
    warnings = list(timeline.get("warnings") or [])
    for artifact in artifacts:
        try:
            ordinal = int(artifact.get("shot_ordinal") or 0)
            expected_start = int(artifact.get("source_start_us"))
            expected_end = int(artifact.get("source_end_us"))
        except (TypeError, ValueError):
            corrupt = True
            continue
        shot = by_ordinal.get(ordinal)
        if shot is None or shot.get("start_us") != expected_start or shot.get("end_us") != expected_end:
            continue
        overlay = artifact.get("overlay")
        if not isinstance(overlay, Mapping):
            corrupt = True
            continue
        for key in ("summary", "visual_description", "narrative_function"):
            if key in overlay:
                shot[key] = deepcopy(overlay[key])
        for key in ("performance", "dialogue", "props", "on_screen_text"):
            if key in overlay and isinstance(overlay[key], list):
                shot[key] = deepcopy(overlay[key])
        if isinstance(overlay.get("cinematography"), Mapping):
            camera = dict(shot.get("cinematography") or {})
            camera.update(deepcopy(dict(overlay["cinematography"])))
            shot["cinematography"] = camera
        raw_user_warnings = artifact.get("user_warnings")
        if isinstance(raw_user_warnings, list):
            for item in raw_user_warnings:
                value = str(item).strip()
                if value and value not in warnings:
                    warnings.append(value)
        applied += 1

    if applied and SHOT_RERUN_SCOPE_WARNING not in warnings:
        warnings.append(SHOT_RERUN_SCOPE_WARNING)
    if corrupt and SHOT_RERUN_FALLBACK_WARNING not in warnings:
        warnings.append(SHOT_RERUN_FALLBACK_WARNING)
    timeline["warnings"] = warnings
    return SceneTimelinePayloadV1.model_validate(timeline).model_dump(mode="json")


def run_shot_breakdown_rerun_v1(
    episode_id: str,
    shot_ordinal: int,
    *,
    providers: Sequence[p2.BreakdownP2Provider] | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run a real, narrow P2 analysis for one Shot and persist its AI overlay artifact."""

    draft = get_current_breakdown(episode_id)
    if draft is None:
        raise BreakdownShotRerunError("当前剧集还没有完整整集拉片结果，请先执行整集拉片")
    run_id, project_id, anchored_episode_id, revision_id = _anchors(draft)
    if anchored_episode_id != episode_id:
        raise BreakdownShotRerunError("当前 BreakdownRun 与请求 Episode 不一致")

    rerun_id = studio_v2.new_id("SHOTRERUN")
    full_context = _load_full_context(draft, rerun_id=rerun_id)
    target = _target_shot(full_context, shot_ordinal)
    base_timeline = assemble_scene_timeline_v1(draft)
    _timeline_scene_and_shot(base_timeline, shot_ordinal)
    provider_by_component = _provider_map(providers)

    _report(progress, 2.0, "breakdown_shot_prepare", f"准备 Shot {shot_ordinal:02d} 单镜拉片")
    target_context = replace(full_context, shots=(target,))
    vlm_shots = _vlm_context_shots(full_context, base_timeline, target)
    vlm_context = replace(full_context, shots=vlm_shots)

    max_source_end = max((item.end_us for item in full_context.shots), default=target.end_us)
    audio_start = max(0, target.start_us - SHOT_RERUN_AUDIO_PADDING_US)
    audio_end = min(max_source_end, target.end_us + SHOT_RERUN_AUDIO_PADDING_US)

    with tempfile.TemporaryDirectory(prefix="ai-drama-shot-rerun-") as temp_name:
        asr_context = target_context
        audio_path = Path(full_context.audio_path) if full_context.audio_path else None
        if audio_path is not None and audio_path.is_file():
            clip = Path(temp_name) / "shot-audio.wav"
            _materialize_audio_window(audio_path, clip, start_us=audio_start, end_us=audio_end)
            asr_context = replace(target_context, audio_path=str(clip))

        _report(progress, 10.0, "breakdown_shot_asr", "只识别当前分镜对白")
        raw_asr = _execute_provider(provider_by_component["ASR"], asr_context)
        asr_result = _shift_asr_result(raw_asr, offset_us=audio_start if asr_context.audio_path != full_context.audio_path else 0)
        p2.validate_provider_result(target_context, asr_result)
        _report(progress, 32.0, "breakdown_shot_asr", "当前分镜对白识别完成")

        _report(progress, 35.0, "breakdown_shot_ocr", "只识别当前分镜画面文字")
        ocr_result = _execute_provider(provider_by_component["OCR"], target_context)
        _report(progress, 50.0, "breakdown_shot_ocr", "当前分镜画面文字识别完成")

        _report(
            progress,
            53.0,
            "breakdown_shot_vlm",
            f"分析当前分镜，并读取 {len(vlm_shots) - 1} 个相邻镜头作为上下文",
        )
        vlm_result = _execute_provider(provider_by_component["VLM"], vlm_context)
        _report(progress, 88.0, "breakdown_shot_vlm", "当前分镜视觉语义识别完成")

    overlay, user_warnings = build_shot_rerun_overlay_v1(
        target=target,
        base_timeline=base_timeline,
        asr_result=asr_result,
        ocr_result=ocr_result,
        vlm_result=vlm_result,
        rerun_id=rerun_id,
    )
    _report(progress, 92.0, "breakdown_shot_fusion", "融合当前分镜 ASR / OCR / VLM 结果")

    artifact: dict[str, Any] = {
        "schema_version": SHOT_RERUN_SCHEMA_VERSION,
        "profile": SHOT_RERUN_PROFILE,
        "rerun_id": rerun_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "source_breakdown_run_id": run_id,
        "source_shot_revision_id": revision_id,
        "shot_ordinal": target.ordinal,
        "source_revision_item_id": target.revision_item_id,
        "source_start_us": target.start_us,
        "source_end_us": target.end_us,
        "context_shot_ordinals": [item.ordinal for item in vlm_shots],
        "audio_scope_start_us": audio_start,
        "audio_scope_end_us": audio_end,
        "created_at": studio_v2.utcnow().isoformat(),
        "providers": {
            "ASR": _result_payload(asr_result),
            "OCR": _result_payload(ocr_result),
            "VLM": _result_payload(vlm_result),
        },
        "overlay": overlay,
        "user_warnings": user_warnings,
        "artifact_fingerprint": "",
    }
    path = persist_shot_rerun_artifact_v1(draft, artifact)
    artifact["artifact_fingerprint"] = _canonical_fingerprint(artifact)
    _report(progress, 100.0, "breakdown_shot_ready", f"Shot {shot_ordinal:02d} 单镜拉片完成")
    return {
        "rerun_id": rerun_id,
        "episode_id": episode_id,
        "shot_ordinal": shot_ordinal,
        "source_breakdown_run_id": run_id,
        "source_shot_revision_id": revision_id,
        "context_shot_ordinals": [item.ordinal for item in vlm_shots],
        "artifact_path": str(path),
        "provider_status": {
            "ASR": asr_result.status,
            "OCR": ocr_result.status,
            "VLM": vlm_result.status,
        },
        "warnings": user_warnings,
    }


__all__ = [
    "BreakdownShotRerunError",
    "SHOT_RERUN_FALLBACK_WARNING",
    "SHOT_RERUN_PROFILE",
    "SHOT_RERUN_SCHEMA_VERSION",
    "SHOT_RERUN_SCOPE_WARNING",
    "apply_shot_rerun_overrides_v1",
    "build_shot_rerun_overlay_v1",
    "persist_shot_rerun_artifact_v1",
    "run_shot_breakdown_rerun_v1",
    "shot_rerun_current_path_v1",
]
