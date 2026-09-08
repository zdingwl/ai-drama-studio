import hashlib
import json
import re
from dataclasses import dataclass
from uuid import uuid4

import av
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact_relation, invalidate_current_artifact_type
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.evidence.models import (
    AsrEvidenceSegment,
    OcrEvidenceObservation,
    ShotDialogueProjection,
    SourceDialogueUtterance,
    SourceEvidenceSet,
    SourceVisualTextSpan,
)
from app.evidence.providers import AsrSegmentResult, build_evidence_providers
from app.evidence.schemas import (
    DialogueUtteranceRead,
    EpisodeSourceEvidenceRead,
    SourceEvidenceResultStatus,
    VisualTextSpanRead,
)
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.enums import VIDEO_PROJECT_TYPES
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.sources.media import decode_preflight, probe_video
from app.sources.models import Episode, SourceAsset
from app.sources.storage import resolve_source_asset_path
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    publish_validated_task_artifact,
)
from app.workflow.worker import TaskExecutionContext

P6_TASK_TYPE = "P6_SOURCE_EVIDENCE"
P6_PROFILE_VERSION = "p6-source-evidence-v1"
_TERMINAL = ("。", "！", "？", "!", "?", "…")


@dataclass(frozen=True)
class CanonicalUtterance:
    start_us: int
    end_us: int
    text: str
    language: str | None
    segment_indexes: list[int]


@dataclass(frozen=True)
class OcrObservationResult:
    timestamp_us: int
    text: str
    confidence: float | None
    bbox: list
    sample_source: str
    provenance: dict


@dataclass(frozen=True)
class CanonicalVisualSpan:
    start_us: int
    end_us: int
    text: str
    confidence: float | None
    bbox: list
    observation_indexes: list[int]


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_p6_source_evidence_task(task: Task) -> bool:
    return task.task_type == P6_TASK_TYPE


def _episode_asset(db: Session, project_id: str, episode_id: str) -> tuple[Episode, SourceAsset]:
    row = db.execute(
        select(Episode, SourceAsset)
        .join(SourceAsset, Episode.source_asset_id == SourceAsset.id)
        .where(Episode.id == episode_id, Episode.project_id == project_id)
    ).one_or_none()
    if row is None:
        raise AppError("EPISODE_NOT_FOUND", "Episode 不存在", status_code=404)
    return row


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )


def _current_source(db: Session, project_id: str) -> ArtifactNode:
    node = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    if node is None:
        raise AppError("SOURCE_VIDEO_REQUIRED", "请先上传原片视频", status_code=409)
    return node


def _source_episode_ids(source: ArtifactNode) -> list[str]:
    raw_ids = source.metadata_json.get("episode_ids") or [
        item.get("episode_id") for item in (source.metadata_json.get("episodes") or [])
    ]
    episode_ids = [str(item) for item in raw_ids if item]
    if not episode_ids or len(episode_ids) != len(set(episode_ids)):
        raise AppError(
            "SOURCE_VIDEO_EPISODE_SET_INVALID",
            "SOURCE_VIDEO 缺少完整且唯一的 Episode 集合",
            status_code=409,
        )
    return episode_ids


def _shot_hint(
    db: Session,
    project_id: str,
    episode_id: str,
    source_id: str,
) -> tuple[ArtifactNode | None, ShotBoundarySet | None, list[ShotAnchor]]:
    artifact = _current_artifact(db, project_id, ArtifactType.SHOT_ANCHORS)
    if artifact is None or str(artifact.metadata_json.get("source_video_artifact_id")) != source_id:
        return None, None, []
    set_id = next(
        (
            str(item.get("shot_boundary_set_id"))
            for item in (artifact.metadata_json.get("episode_sets") or [])
            if str(item.get("episode_id")) == episode_id
        ),
        None,
    )
    if not set_id:
        return artifact, None, []
    boundary = db.get(ShotBoundarySet, set_id)
    if boundary is None or boundary.episode_id != episode_id or boundary.source_video_artifact_id != source_id:
        return artifact, None, []
    anchors = list(
        db.scalars(
            select(ShotAnchor)
            .where(ShotAnchor.shot_boundary_set_id == boundary.id)
            .order_by(ShotAnchor.shot_number)
        ).all()
    )
    return artifact, boundary, anchors


def create_source_evidence_task(
    db: Session,
    *,
    project_id: str,
    episode_id: str,
    idempotency_key: str,
) -> Task:
    project = get_project(db, project_id)
    if project.project_type not in VIDEO_PROJECT_TYPES:
        raise AppError("SOURCE_EVIDENCE_NOT_ALLOWED", "当前项目类型不处理视频 Source Evidence", status_code=422)
    episode, asset = _episode_asset(db, project_id, episode_id)
    source = _current_source(db, project_id)
    shot_artifact, boundary, _ = _shot_hint(db, project_id, episode_id, source.id)
    providers = build_evidence_providers(get_settings())
    settings = get_settings()
    fingerprint = _sha(
        {
            "task": P6_TASK_TYPE,
            "profile": P6_PROFILE_VERSION,
            "source_video_artifact_id": source.id,
            "source_video_fingerprint": source.input_fingerprint,
            "episode_id": episode.id,
            "source_asset_id": asset.id,
            "source_sha256": asset.sha256,
            "duration_us": episode.duration_us,
            "has_audio": episode.has_audio,
            "asr_profile": providers.asr.profile,
            "ocr_profile": providers.ocr.profile,
            "ocr_sample_interval_ms": settings.p6_ocr_sample_interval_ms,
            "optional_shot_hint_artifact_id": shot_artifact.id if shot_artifact else None,
            "optional_shot_hint_fingerprint": shot_artifact.input_fingerprint if shot_artifact else None,
            "optional_shot_boundary_set_id": boundary.id if boundary else None,
        }
    )
    return create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P6_TASK_TYPE,
            task_name=f"第 {episode.episode_order} 集：对白与画面文字证据",
            input_fingerprint=fingerprint,
            input_artifact_ids=[source.id],
            episode_id=episode.id,
            max_attempts=3,
        ),
    )


def _canonical_dialogue(segments: list[AsrSegmentResult]) -> list[CanonicalUtterance]:
    result: list[CanonicalUtterance] = []
    current: CanonicalUtterance | None = None
    for index, segment in enumerate(segments):
        text = segment.text.strip()
        if not text or segment.end_us <= segment.start_us:
            continue
        if current is None:
            current = CanonicalUtterance(segment.start_us, segment.end_us, text, segment.language, [index])
            continue
        gap = max(0, segment.start_us - current.end_us)
        if (
            gap <= 500_000
            and segment.end_us - current.start_us <= 20_000_000
            and not current.text.rstrip().endswith(_TERMINAL)
        ):
            sep = " " if current.text and text and current.text[-1].isascii() else ""
            current = CanonicalUtterance(
                current.start_us,
                max(current.end_us, segment.end_us),
                f"{current.text.rstrip()}{sep}{text}",
                current.language or segment.language,
                [*current.segment_indexes, index],
            )
        else:
            result.append(current)
            current = CanonicalUtterance(segment.start_us, segment.end_us, text, segment.language, [index])
    if current is not None:
        result.append(current)
    return result


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _canonical_visual(
    observations: list[OcrObservationResult],
    duration_us: int,
    interval_us: int,
) -> list[CanonicalVisualSpan]:
    result: list[CanonicalVisualSpan] = []
    last_by_text: dict[str, int] = {}
    max_gap = max(1_500_000, interval_us * 3)
    for index, obs in enumerate(observations):
        key = _normalize(obs.text)
        if not key:
            continue
        prior_index = last_by_text.get(key)
        if prior_index is not None:
            prior = result[prior_index]
            if obs.timestamp_us - prior.end_us <= max_gap:
                scores = [value for value in (prior.confidence, obs.confidence) if value is not None]
                result[prior_index] = CanonicalVisualSpan(
                    prior.start_us,
                    min(duration_us, max(prior.end_us, obs.timestamp_us + interval_us)),
                    prior.text,
                    max(scores) if scores else None,
                    prior.bbox or obs.bbox,
                    [*prior.observation_indexes, index],
                )
                continue
        last_by_text[key] = len(result)
        result.append(
            CanonicalVisualSpan(
                obs.timestamp_us,
                min(duration_us, obs.timestamp_us + interval_us),
                obs.text.strip(),
                obs.confidence,
                obs.bbox,
                [index],
            )
        )
    return sorted(result, key=lambda item: (item.start_us, item.end_us, item.text))


def _frame_time_us(frame) -> int | None:
    if frame.pts is None:
        return None
    if frame.time is not None:
        return max(0, int(round(float(frame.time) * 1_000_000)))
    return max(0, int(round(float(frame.pts * frame.time_base) * 1_000_000))) if frame.time_base else None


def _sample_targets(duration_us: int, interval_us: int, anchors: list[ShotAnchor]) -> list[tuple[int, str]]:
    sources: dict[int, set[str]] = {}
    for value in range(0, max(1, duration_us), interval_us):
        sources.setdefault(value, set()).add("TIMELINE")
    if duration_us > 0:
        sources.setdefault(duration_us - 1, set()).add("TIMELINE")
    for anchor in anchors:
        for value in (anchor.start_us, anchor.start_us + max(1, anchor.duration_us // 2)):
            if 0 <= value < duration_us:
                sources.setdefault(value, set()).add("SHOT_HINT")
    return [(value, "+".join(sorted(kinds))) for value, kinds in sorted(sources.items())]


def _run_ocr(
    source_path,
    *,
    duration_us: int,
    provider,
    anchors: list[ShotAnchor],
    context: TaskExecutionContext,
) -> list[OcrObservationResult]:
    interval_us = get_settings().p6_ocr_sample_interval_ms * 1000
    targets = _sample_targets(duration_us, interval_us, anchors)
    output: list[OcrObservationResult] = []
    target_index = 0
    last_progress = 45
    last_frame = None
    last_time = None
    processed_times: set[int] = set()

    def process(frame, timestamp_us: int, kinds: str, target_us: int) -> None:
        nonlocal last_progress
        if timestamp_us in processed_times:
            return
        processed_times.add(timestamp_us)
        try:
            image = frame.to_ndarray(format="bgr24")
        except Exception as exc:
            raise AppError("P6_OCR_FRAME_DECODE_FAILED", "OCR 抽帧失败", status_code=422) from exc
        for item in provider.recognize(image):
            output.append(
                OcrObservationResult(
                    min(max(0, timestamp_us), max(0, duration_us - 1)),
                    item.text,
                    item.confidence,
                    item.bbox,
                    kinds,
                    {
                        "provider": provider.profile.get("provider"),
                        "timeline_source": "FULL_EPISODE",
                        "sample_target_us": target_us,
                    },
                )
            )
        progress = 45 + int(min(1.0, target_index / max(1, len(targets))) * 37)
        if progress >= last_progress + 2:
            last_progress = progress
            context.checkpoint(
                {
                    "stage": "ocr_timeline",
                    "sampled_targets": target_index,
                    "total_targets": len(targets),
                },
                progress_percent=min(progress, 82),
            )

    try:
        with av.open(str(source_path)) as container:
            stream = next((stream for stream in container.streams if stream.type == "video"), None)
            if stream is None:
                raise AppError("SOURCE_VIDEO_TRACK_REQUIRED", "原片缺少视频轨", status_code=422)
            for frame in container.decode(stream):
                timestamp_us = _frame_time_us(frame)
                if timestamp_us is None:
                    continue
                last_frame, last_time = frame, timestamp_us
                if target_index >= len(targets):
                    break
                if timestamp_us < targets[target_index][0]:
                    continue
                kinds: set[str] = set()
                first_target = targets[target_index][0]
                while target_index < len(targets) and targets[target_index][0] <= timestamp_us:
                    kinds.update(targets[target_index][1].split("+"))
                    target_index += 1
                process(frame, timestamp_us, "+".join(sorted(kinds)), first_target)
                if target_index >= len(targets):
                    break
    except AppError:
        raise
    except Exception as exc:
        raise AppError("P6_OCR_TIMELINE_FAILED", "完整视频时间轴 OCR 失败", status_code=422) from exc
    if target_index < len(targets) and last_frame is not None and last_time is not None:
        first_target = targets[target_index][0]
        kinds: set[str] = set()
        while target_index < len(targets):
            kinds.update(targets[target_index][1].split("+"))
            target_index += 1
        process(last_frame, last_time, "+".join(sorted(kinds)), first_target)
    context.checkpoint(
        {"stage": "ocr_timeline", "sampled_targets": len(targets), "total_targets": len(targets)},
        progress_percent=82,
    )
    return sorted(output, key=lambda item: (item.timestamp_us, item.text))


def _validate_asr(segments: list[AsrSegmentResult], duration_us: int) -> None:
    previous = -1
    for item in segments:
        if (
            not item.text.strip()
            or item.start_us < 0
            or item.end_us <= item.start_us
            or item.start_us < previous
        ):
            raise AppError("P6_ASR_EVIDENCE_INVALID", "ASR evidence 文本或时间戳无效", status_code=422)
        if item.start_us > duration_us + 500_000:
            raise AppError("P6_ASR_TIME_OUT_OF_RANGE", "ASR evidence 超出 Episode 时长", status_code=422)
        previous = item.start_us


def _persist(
    db: Session,
    *,
    set_id: str,
    task: TaskWorkerRead,
    source_id: str,
    asr_profile: dict,
    ocr_profile: dict,
    hints: dict,
    asr: list[AsrSegmentResult],
    ocr: list[OcrObservationResult],
    dialogue: list[CanonicalUtterance],
    visual: list[CanonicalVisualSpan],
    anchors: list[ShotAnchor],
) -> SourceEvidenceSet:
    if task.episode_id is None:
        raise AppError("TASK_EPISODE_SCOPE_INVALID", "Source Evidence 任务缺少 Episode", status_code=422)
    if _current_source(db, task.project_id).id != source_id:
        raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，Evidence 不能发布", status_code=409)
    latest = db.scalar(
        select(func.max(SourceEvidenceSet.revision)).where(SourceEvidenceSet.episode_id == task.episode_id)
    )
    db.execute(
        update(SourceEvidenceSet)
        .where(SourceEvidenceSet.episode_id == task.episode_id, SourceEvidenceSet.is_current.is_(True))
        .values(is_current=False)
    )
    evidence_set = SourceEvidenceSet(
        id=set_id,
        project_id=task.project_id,
        episode_id=task.episode_id,
        source_video_artifact_id=source_id,
        task_id=task.id,
        revision=(latest or 0) + 1,
        input_fingerprint=task.input_fingerprint,
        asr_profile_json=asr_profile,
        ocr_profile_json=ocr_profile,
        sampling_hints_json=hints,
        is_current=True,
    )
    db.add(evidence_set)
    db.flush()

    asr_rows: list[AsrEvidenceSegment] = []
    for number, item in enumerate(asr, 1):
        row = AsrEvidenceSegment(
            project_id=task.project_id,
            episode_id=task.episode_id,
            source_evidence_set_id=set_id,
            segment_number=number,
            start_us=item.start_us,
            end_us=item.end_us,
            text=item.text,
            language=item.language,
            confidence=item.confidence,
            provenance_json=item.provenance,
        )
        db.add(row)
        asr_rows.append(row)
    db.flush()

    ocr_rows: list[OcrEvidenceObservation] = []
    for number, item in enumerate(ocr, 1):
        row = OcrEvidenceObservation(
            project_id=task.project_id,
            episode_id=task.episode_id,
            source_evidence_set_id=set_id,
            observation_number=number,
            timestamp_us=item.timestamp_us,
            text=item.text,
            confidence=item.confidence,
            bbox_json=item.bbox,
            sample_source=item.sample_source,
            provenance_json=item.provenance,
        )
        db.add(row)
        ocr_rows.append(row)
    db.flush()

    dialogue_rows: list[SourceDialogueUtterance] = []
    for number, item in enumerate(dialogue, 1):
        row = SourceDialogueUtterance(
            project_id=task.project_id,
            episode_id=task.episode_id,
            source_evidence_set_id=set_id,
            utterance_number=number,
            start_us=item.start_us,
            end_us=item.end_us,
            text=item.text,
            language=item.language,
            source_segment_ids_json=[asr_rows[index].id for index in item.segment_indexes],
        )
        db.add(row)
        dialogue_rows.append(row)
    db.flush()

    for number, item in enumerate(visual, 1):
        db.add(
            SourceVisualTextSpan(
                project_id=task.project_id,
                episode_id=task.episode_id,
                source_evidence_set_id=set_id,
                span_number=number,
                start_us=item.start_us,
                end_us=item.end_us,
                text=item.text,
                confidence=item.confidence,
                bbox_json=item.bbox,
                source_observation_ids_json=[ocr_rows[index].id for index in item.observation_indexes],
            )
        )
    for utterance in dialogue_rows:
        for anchor in anchors:
            start = max(utterance.start_us, anchor.start_us)
            end = min(utterance.end_us, anchor.end_us)
            if end > start:
                db.add(
                    ShotDialogueProjection(
                        project_id=task.project_id,
                        episode_id=task.episode_id,
                        source_evidence_set_id=set_id,
                        source_dialogue_utterance_id=utterance.id,
                        shot_anchor_id=anchor.id,
                        shot_number=anchor.shot_number,
                        overlap_start_us=start,
                        overlap_end_us=end,
                    )
                )
    db.commit()
    db.refresh(evidence_set)
    return evidence_set


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> SourceEvidenceSet:
    if task.episode_id is None:
        raise AppError("TASK_EPISODE_SCOPE_INVALID", "Source Evidence 任务缺少 Episode", status_code=422)
    with context.session_factory() as db:
        source = _current_source(db, task.project_id)
        if source.id not in task.input_artifact_ids_json:
            raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，请重新提取 Source Evidence", status_code=409)
        episode, asset = _episode_asset(db, task.project_id, task.episode_id)
        project = get_project(db, task.project_id)
        shot_artifact, boundary, anchors = _shot_hint(db, task.project_id, task.episode_id, source.id)
        source_path = resolve_source_asset_path(asset.relative_path)

    context.checkpoint({"stage": "media_preflight"}, progress_percent=3)
    probe = probe_video(source_path)
    decode_preflight(source_path)
    duration_us = min(episode.duration_us, probe.duration_us)
    if abs(episode.duration_us - probe.duration_us) > 250_000:
        raise AppError("SOURCE_TIMEBASE_CHANGED", "原片媒体时长与入库记录不一致", status_code=409)

    providers = build_evidence_providers(get_settings())
    asr_profile = dict(providers.asr.profile)
    ocr_profile = dict(providers.ocr.profile)
    asr: list[AsrSegmentResult] = []
    if episode.has_audio:
        context.checkpoint({"stage": "continuous_asr", "input": "FULL_EPISODE"}, progress_percent=8)
        last = 8

        def progress(ratio: float) -> None:
            nonlocal last
            value = 8 + int(max(0.0, min(1.0, ratio)) * 34)
            if value > last:
                last = value
                context.checkpoint(
                    {
                        "stage": "continuous_asr",
                        "input": "FULL_EPISODE",
                        "scan_percent": int(ratio * 100),
                    },
                    progress_percent=min(value, 42),
                )

        asr = providers.asr.transcribe(
            source_path,
            language_hint=project.source_language,
            duration_us=duration_us,
            on_progress=progress,
        )
        _validate_asr(asr, duration_us)
    else:
        asr_profile["skipped"] = "episode_has_no_audio"
        context.checkpoint({"stage": "continuous_asr", "skipped": "no_audio"}, progress_percent=42)

    dialogue = _canonical_dialogue(asr)
    context.checkpoint(
        {"stage": "canonical_dialogue", "utterance_count": len(dialogue)},
        progress_percent=44,
    )
    ocr = _run_ocr(
        source_path,
        duration_us=duration_us,
        provider=providers.ocr,
        anchors=anchors,
        context=context,
    )
    interval_us = get_settings().p6_ocr_sample_interval_ms * 1000
    visual = _canonical_visual(ocr, duration_us, interval_us)
    context.checkpoint(
        {
            "stage": "canonicalize_evidence",
            "dialogue_count": len(dialogue),
            "visual_text_count": len(visual),
        },
        progress_percent=90,
    )
    hints = {
        "timeline_source": "FULL_EPISODE",
        "ocr_sample_interval_ms": get_settings().p6_ocr_sample_interval_ms,
        "shot_anchors_optional": True,
        "shot_anchors_artifact_id": shot_artifact.id if shot_artifact else None,
        "shot_boundary_set_id": boundary.id if boundary else None,
        "shot_anchor_count": len(anchors),
    }
    context.checkpoint({"stage": "persist_evidence"}, progress_percent=94)
    with context.session_factory() as db:
        if _current_source(db, task.project_id).id != source.id:
            raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，Evidence 不能写入", status_code=409)
        _, current_boundary, current_anchors = _shot_hint(
            db,
            task.project_id,
            task.episode_id,
            source.id,
        )
        if current_boundary is None or (boundary is not None and current_boundary.id != boundary.id):
            current_anchors = []
            hints["projection_note"] = "shot_hint_changed_during_task"
        return _persist(
            db,
            set_id=str(uuid4()),
            task=task,
            source_id=source.id,
            asr_profile=asr_profile,
            ocr_profile=ocr_profile,
            hints=hints,
            asr=asr,
            ocr=ocr,
            dialogue=dialogue,
            visual=visual,
            anchors=current_anchors,
        )


def _aggregate(db: Session, project_id: str, source_id: str) -> list[dict]:
    rows = list(
        db.execute(
            select(SourceEvidenceSet, Episode)
            .join(Episode, SourceEvidenceSet.episode_id == Episode.id)
            .where(
                SourceEvidenceSet.project_id == project_id,
                SourceEvidenceSet.source_video_artifact_id == source_id,
                SourceEvidenceSet.is_current.is_(True),
            )
            .order_by(Episode.episode_order)
        ).all()
    )
    result = []
    for evidence_set, episode in rows:
        dialogue_count = int(
            db.scalar(
                select(func.count(SourceDialogueUtterance.id)).where(
                    SourceDialogueUtterance.source_evidence_set_id == evidence_set.id
                )
            )
            or 0
        )
        visual_count = int(
            db.scalar(
                select(func.count(SourceVisualTextSpan.id)).where(
                    SourceVisualTextSpan.source_evidence_set_id == evidence_set.id
                )
            )
            or 0
        )
        result.append(
            {
                "episode_id": episode.id,
                "episode_order": episode.episode_order,
                "source_evidence_set_id": evidence_set.id,
                "set_revision": evidence_set.revision,
                "set_fingerprint": evidence_set.input_fingerprint,
                "dialogue_count": dialogue_count,
                "visual_text_count": visual_count,
            }
        )
    return result


def _publish(db: Session, task_id: str, set_id: str) -> ArtifactNode | None:
    task = db.get(Task, task_id)
    evidence_set = db.get(SourceEvidenceSet, set_id)
    if task is None or evidence_set is None or evidence_set.task_id != task.id:
        raise AppError("SOURCE_EVIDENCE_SET_NOT_FOUND", "Source Evidence 结果不存在", status_code=404)
    source = _current_source(db, task.project_id)
    if evidence_set.source_video_artifact_id != source.id:
        raise AppError("STALE_ARTIFACT_INPUT", "原片素材已变化，Evidence 不能发布", status_code=409)

    required_episode_ids = _source_episode_ids(source)
    aggregate = _aggregate(db, task.project_id, source.id)
    aggregate_episode_ids = [str(item["episode_id"]) for item in aggregate]
    if len(aggregate_episode_ids) != len(required_episode_ids) or set(aggregate_episode_ids) != set(
        required_episode_ids
    ):
        invalidate_current_artifact_type(
            db,
            project_id=task.project_id,
            artifact_type=ArtifactType.SOURCE_DIALOGUE,
        )
        return None

    fingerprint = _sha(
        {
            "source_video_artifact_id": source.id,
            "source_video_fingerprint": source.input_fingerprint,
            "episodes": aggregate,
        }
    )
    existing = _current_artifact(db, task.project_id, ArtifactType.SOURCE_DIALOGUE)
    if existing is not None and existing.input_fingerprint == fingerprint:
        return existing

    project = get_project(db, task.project_id)
    artifact = publish_validated_task_artifact(
        db,
        task_id=task.id,
        validation_passed=True,
        artifact_type=ArtifactType.SOURCE_DIALOGUE,
        namespace=ArtifactNamespace.SOURCE,
        label=f"原片对白与画面文字证据（{len(required_episode_ids)} 集）",
        input_fingerprint=fingerprint,
        skill_id=project.root_skill_id,
        skill_version=project.root_skill_version,
        metadata_json={
            "source_video_artifact_id": source.id,
            "episode_sets": aggregate,
            "episode_count": len(required_episode_ids),
            "complete": True,
            "evidence_profile": P6_PROFILE_VERSION,
            "canonical_policy": "ASR_OCR_IMMUTABLE_SOURCE_EVIDENCE",
        },
    )
    create_artifact_relation(
        db,
        project_id=task.project_id,
        source_node_id=source.id,
        target_node_id=artifact.id,
        relation_type=ArtifactRelationType.DERIVED_FROM,
    )
    return artifact


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if (
        task is None
        or task.task_type != P6_TASK_TYPE
        or task.status != TaskStatus.QUEUED
        or task.attempt >= task.max_attempts
    ):
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == P6_TASK_TYPE,
            Task.status == TaskStatus.QUEUED,
            Task.attempt < Task.max_attempts,
        )
        .values(
            status=TaskStatus.RUNNING,
            attempt=task.attempt + 1,
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Task.started_at, now),
            finished_at=None,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    claimed = db.get(Task, task_id)
    if claimed is not None:
        db.refresh(claimed)
    return claimed


def _fail_if_running(
    factory: sessionmaker[Session],
    task_id: str,
    worker_id: str,
    error: str,
) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_failed(db, task_id, safe_error=error, worker_id=worker_id)


def _discard(factory: sessionmaker[Session], set_id: str) -> None:
    with factory() as db:
        row = db.get(SourceEvidenceSet, set_id)
        if row is not None:
            db.delete(row)
            db.commit()


def _invalidate_published_evidence(factory: sessionmaker[Session], project_id: str) -> None:
    with factory() as db:
        invalidate_current_artifact_type(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_DIALOGUE,
        )


def run_p6_source_evidence_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p6-source-evidence-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(
        session_factory=session_factory,
        task_id=snapshot.id,
        worker_id=worker_id,
    )
    try:
        evidence_set = _execute(context, snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"Source Evidence 提取失败（{exc.code}）",
        )
        return
    except Exception as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"Source Evidence 提取失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        _invalidate_published_evidence(session_factory, snapshot.project_id)
        _discard(session_factory, evidence_set.id)
        return

    try:
        with session_factory() as db:
            _publish(db, snapshot.id, evidence_set.id)
    except Exception as exc:
        _invalidate_published_evidence(session_factory, snapshot.project_id)
        _discard(session_factory, evidence_set.id)
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.SUCCEEDED:
                now = utc_now()
                task.status = TaskStatus.FAILED
                task.progress_percent = min(task.progress_percent, 99)
                task.last_error = f"Source Evidence 结果发布失败（{type(exc).__name__}）"
                task.finished_at = now
                task.updated_at = now
                db.add(task)
                db.commit()


def get_episode_source_evidence(
    db: Session,
    project_id: str,
    episode_id: str,
) -> EpisodeSourceEvidenceRead:
    episode, asset = _episode_asset(db, project_id, episode_id)
    evidence_set = db.scalar(
        select(SourceEvidenceSet)
        .where(
            SourceEvidenceSet.project_id == project_id,
            SourceEvidenceSet.episode_id == episode_id,
        )
        .order_by(SourceEvidenceSet.revision.desc())
        .limit(1)
    )
    if evidence_set is None:
        return EpisodeSourceEvidenceRead(
            episode_id=episode.id,
            episode_order=episode.episode_order,
            source_filename=asset.original_filename,
            status=SourceEvidenceResultStatus.NOT_BUILT,
            revision=None,
            artifact_revision=None,
            dialogue_count=0,
            visual_text_count=0,
            raw_asr_segment_count=0,
            raw_ocr_observation_count=0,
            dialogue=[],
            visual_text=[],
        )

    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    artifact = _current_artifact(db, project_id, ArtifactType.SOURCE_DIALOGUE)
    set_ids = {
        str(item.get("source_evidence_set_id"))
        for item in ((artifact.metadata_json.get("episode_sets") if artifact else None) or [])
    }
    current = (
        evidence_set.is_current
        and source is not None
        and evidence_set.source_video_artifact_id == source.id
    )
    artifact_matches_set = artifact is not None and evidence_set.id in set_ids

    utterances = list(
        db.scalars(
            select(SourceDialogueUtterance)
            .where(SourceDialogueUtterance.source_evidence_set_id == evidence_set.id)
            .order_by(SourceDialogueUtterance.utterance_number)
        ).all()
    )
    projections = list(
        db.scalars(
            select(ShotDialogueProjection)
            .where(ShotDialogueProjection.source_evidence_set_id == evidence_set.id)
            .order_by(ShotDialogueProjection.shot_number)
        ).all()
    )
    by_utterance: dict[str, list[int]] = {}
    for item in projections:
        by_utterance.setdefault(item.source_dialogue_utterance_id, []).append(item.shot_number)
    visual = list(
        db.scalars(
            select(SourceVisualTextSpan)
            .where(SourceVisualTextSpan.source_evidence_set_id == evidence_set.id)
            .order_by(SourceVisualTextSpan.span_number)
        ).all()
    )
    raw_asr = int(
        db.scalar(
            select(func.count(AsrEvidenceSegment.id)).where(
                AsrEvidenceSegment.source_evidence_set_id == evidence_set.id
            )
        )
        or 0
    )
    raw_ocr = int(
        db.scalar(
            select(func.count(OcrEvidenceObservation.id)).where(
                OcrEvidenceObservation.source_evidence_set_id == evidence_set.id
            )
        )
        or 0
    )
    return EpisodeSourceEvidenceRead(
        episode_id=episode.id,
        episode_order=episode.episode_order,
        source_filename=asset.original_filename,
        status=SourceEvidenceResultStatus.CURRENT if current else SourceEvidenceResultStatus.STALE,
        revision=evidence_set.revision,
        artifact_revision=artifact.revision if current and artifact_matches_set else None,
        dialogue_count=len(utterances),
        visual_text_count=len(visual),
        raw_asr_segment_count=raw_asr,
        raw_ocr_observation_count=raw_ocr,
        dialogue=[
            DialogueUtteranceRead(
                id=row.id,
                utterance_number=row.utterance_number,
                start_us=row.start_us,
                end_us=row.end_us,
                text=row.text,
                language=row.language,
                projected_shot_numbers=by_utterance.get(row.id, []),
            )
            for row in utterances
        ],
        visual_text=[
            VisualTextSpanRead(
                id=row.id,
                span_number=row.span_number,
                start_us=row.start_us,
                end_us=row.end_us,
                text=row.text,
                confidence=row.confidence,
            )
            for row in visual
        ],
    )
