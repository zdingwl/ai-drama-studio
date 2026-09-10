"""Explicit human adjudication for P6 canonical dialogue.

Automatic P6 v4 remains unchanged. This module adds a user-initiated command that can select the
original ASR text, choose a temporally overlapping OCR canonical span, or provide custom text.
Every save creates a new SourceEvidenceSet revision and, when the project Episode set is complete,
a new SOURCE_DIALOGUE Artifact revision. Raw ASR/OCR text is cloned unchanged and retained.
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.evidence import service as _base
from app.evidence import service_v4 as _v4
from app.evidence.models import (
    AsrEvidenceSegment,
    OcrEvidenceObservation,
    SourceDialogueUtterance,
    SourceEvidenceSet,
    SourceVisualTextSpan,
)
from app.evidence.providers import AsrSegmentResult
from app.evidence.schemas import (
    DialogueManualAdjudicationCommand,
    DialogueTextSource,
    EpisodeSourceEvidenceRead,
    ManualDialogueChoice,
)
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import create_task_from_command, mark_task_failed, mark_task_succeeded


P6_MANUAL_ADJUDICATION_TASK_TYPE = "P6_DIALOGUE_ADJUDICATION"
P6_MANUAL_ADJUDICATION_POLICY = "human-dialogue-adjudication-v1"


def _overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def _current_set(db: Session, project_id: str, episode_id: str) -> SourceEvidenceSet:
    source = _base._current_source(db, project_id)
    row = db.scalar(
        select(SourceEvidenceSet).where(
            SourceEvidenceSet.project_id == project_id,
            SourceEvidenceSet.episode_id == episode_id,
            SourceEvidenceSet.source_video_artifact_id == source.id,
            SourceEvidenceSet.is_current.is_(True),
        )
    )
    if row is None:
        raise AppError(
            "CURRENT_SOURCE_EVIDENCE_REQUIRED",
            "请先生成当前 Episode 的 CURRENT P6 Source Evidence",
            status_code=409,
        )
    return row


def _source_segment_rows(
    db: Session,
    evidence_set_id: str,
) -> list[AsrEvidenceSegment]:
    return list(
        db.scalars(
            select(AsrEvidenceSegment)
            .where(AsrEvidenceSegment.source_evidence_set_id == evidence_set_id)
            .order_by(AsrEvidenceSegment.segment_number)
        ).all()
    )


def _ocr_observation_rows(
    db: Session,
    evidence_set_id: str,
) -> list[OcrEvidenceObservation]:
    return list(
        db.scalars(
            select(OcrEvidenceObservation)
            .where(OcrEvidenceObservation.source_evidence_set_id == evidence_set_id)
            .order_by(OcrEvidenceObservation.observation_number)
        ).all()
    )


def _dialogue_rows(
    db: Session,
    evidence_set_id: str,
) -> list[SourceDialogueUtterance]:
    return list(
        db.scalars(
            select(SourceDialogueUtterance)
            .where(SourceDialogueUtterance.source_evidence_set_id == evidence_set_id)
            .order_by(SourceDialogueUtterance.utterance_number)
        ).all()
    )


def _visual_rows(db: Session, evidence_set_id: str) -> list[SourceVisualTextSpan]:
    return list(
        db.scalars(
            select(SourceVisualTextSpan)
            .where(SourceVisualTextSpan.source_evidence_set_id == evidence_set_id)
            .order_by(SourceVisualTextSpan.span_number)
        ).all()
    )


def _original_asr_text(
    utterance: SourceDialogueUtterance,
    segment_by_id: dict[str, AsrEvidenceSegment],
) -> str:
    provenances = [
        segment_by_id[segment_id].provenance_json or {}
        for segment_id in (utterance.source_segment_ids_json or [])
        if segment_id in segment_by_id
    ]
    for key in ("manual_original_asr_text", "canonical_asr_text"):
        values = [str(item.get(key)).strip() for item in provenances if item.get(key)]
        if values:
            return values[0]
    return utterance.text


def _claim_task(db: Session, task: Task, worker_id: str) -> Task:
    if task.status == TaskStatus.SUCCEEDED:
        return task
    if task.status != TaskStatus.QUEUED:
        raise AppError("P6_MANUAL_ADJUDICATION_BUSY", "该人工裁决命令当前不能重复执行", status_code=409)
    now = utc_now()
    task.status = TaskStatus.RUNNING
    task.attempt = max(1, task.attempt + 1)
    task.worker_id = worker_id
    task.started_at = task.started_at or now
    task.heartbeat_at = now
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _manual_text_source(choice: ManualDialogueChoice) -> str:
    if choice == ManualDialogueChoice.ASR:
        return DialogueTextSource.USER_ASR_SELECTED.value
    if choice == ManualDialogueChoice.OCR:
        return DialogueTextSource.USER_OCR_SELECTED.value
    return DialogueTextSource.USER_EDITED.value


def adjudicate_dialogue_manually(
    db: Session,
    *,
    project_id: str,
    episode_id: str,
    command: DialogueManualAdjudicationCommand,
    idempotency_key: str,
) -> EpisodeSourceEvidenceRead:
    parent = _current_set(db, project_id, episode_id)
    if parent.revision != command.expected_revision:
        raise AppError(
            "SOURCE_EVIDENCE_REVISION_CHANGED",
            "P6 Evidence 已更新，请刷新后重新选择",
            status_code=409,
            details={"expected_revision": command.expected_revision, "current_revision": parent.revision},
        )

    utterances = _dialogue_rows(db, parent.id)
    target = next((row for row in utterances if row.id == command.utterance_id), None)
    if target is None:
        raise AppError(
            "SOURCE_DIALOGUE_UTTERANCE_NOT_CURRENT",
            "要修改的对白不属于当前 P6 Evidence revision",
            status_code=409,
        )

    asr_rows = _source_segment_rows(db, parent.id)
    ocr_rows = _ocr_observation_rows(db, parent.id)
    visual_rows = _visual_rows(db, parent.id)
    segment_by_id = {row.id: row for row in asr_rows}
    original_asr_text = _original_asr_text(target, segment_by_id)

    selected_span: SourceVisualTextSpan | None = None
    if command.choice == ManualDialogueChoice.OCR:
        selected_span = next(
            (row for row in visual_rows if row.span_number == command.ocr_span_number),
            None,
        )
        if selected_span is None:
            raise AppError(
                "SOURCE_EVIDENCE_OCR_SPAN_NOT_CURRENT",
                "选择的 OCR span 不属于当前 P6 Evidence revision",
                status_code=422,
            )
        if _overlap(target.start_us, target.end_us, selected_span.start_us, selected_span.end_us) <= 0:
            raise AppError(
                "SOURCE_EVIDENCE_OCR_SPAN_NOT_OVERLAPPING",
                "只能选择与该对白时间真实重叠的 OCR span",
                status_code=422,
            )

    if command.choice == ManualDialogueChoice.ASR:
        canonical_text = original_asr_text.strip()
    elif command.choice == ManualDialogueChoice.OCR and selected_span is not None:
        canonical_text = selected_span.text.strip()
    else:
        canonical_text = (command.custom_text or "").strip()
    if not canonical_text:
        raise AppError("SOURCE_DIALOGUE_TEXT_EMPTY", "Canonical 对白不能为空", status_code=422)

    source = _base._current_source(db, project_id)
    fingerprint = _base._sha(
        {
            "profile": P6_MANUAL_ADJUDICATION_POLICY,
            "source_video_artifact_id": source.id,
            "parent_source_evidence_set_id": parent.id,
            "parent_source_evidence_fingerprint": parent.input_fingerprint,
            "expected_revision": command.expected_revision,
            "utterance_id": target.id,
            "utterance_number": target.utterance_number,
            "choice": command.choice.value,
            "ocr_span_number": selected_span.span_number if selected_span else None,
            "canonical_text": canonical_text,
        }
    )
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P6_MANUAL_ADJUDICATION_TASK_TYPE,
            task_name=f"第 {target.utterance_number} 条对白：人工确认 / 修改",
            input_fingerprint=fingerprint,
            input_artifact_ids=[source.id],
            episode_id=episode_id,
            max_attempts=1,
        ),
    )
    if task.status == TaskStatus.SUCCEEDED:
        return get_episode_source_evidence(db, project_id, episode_id)

    worker_id = f"p6-human-adjudication-{uuid4()}"
    task = _claim_task(db, task, worker_id)
    new_set: SourceEvidenceSet | None = None
    try:
        asr_index_by_id = {row.id: index for index, row in enumerate(asr_rows)}
        ocr_index_by_id = {row.id: index for index, row in enumerate(ocr_rows)}
        target_segment_ids = set(target.source_segment_ids_json or [])
        selected_ocr_numbers = [selected_span.span_number] if selected_span else []
        selected_ocr_text = selected_span.text if selected_span else None

        cloned_asr: list[AsrSegmentResult] = []
        for row in asr_rows:
            provenance = dict(row.provenance_json or {})
            if row.id in target_segment_ids:
                provenance.update(
                    {
                        "manual_adjudication_policy": P6_MANUAL_ADJUDICATION_POLICY,
                        "manual_choice": command.choice.value,
                        "manual_parent_evidence_set_id": parent.id,
                        "manual_parent_utterance_id": target.id,
                        "manual_parent_canonical_text": target.text,
                        "manual_original_asr_text": original_asr_text,
                        "manual_selected_ocr_span_numbers": selected_ocr_numbers,
                        "manual_selected_ocr_text": selected_ocr_text,
                        "manual_canonical_text": canonical_text,
                        "manual_text_source": _manual_text_source(command.choice),
                    }
                )
            cloned_asr.append(
                AsrSegmentResult(
                    start_us=row.start_us,
                    end_us=row.end_us,
                    text=row.text,
                    language=row.language,
                    confidence=row.confidence,
                    provenance=provenance,
                )
            )

        cloned_ocr = [
            _base.OcrObservationResult(
                timestamp_us=row.timestamp_us,
                text=row.text,
                confidence=row.confidence,
                bbox=list(row.bbox_json or []),
                sample_source=row.sample_source,
                provenance=dict(row.provenance_json or {}),
            )
            for row in ocr_rows
        ]

        cloned_dialogue: list[_base.CanonicalUtterance] = []
        for row in utterances:
            try:
                segment_indexes = [asr_index_by_id[value] for value in (row.source_segment_ids_json or [])]
            except KeyError as exc:
                raise AppError(
                    "SOURCE_EVIDENCE_PROVENANCE_INVALID",
                    "Canonical 对白引用的 raw ASR Evidence 已损坏",
                    status_code=409,
                ) from exc
            cloned_dialogue.append(
                _base.CanonicalUtterance(
                    start_us=row.start_us,
                    end_us=row.end_us,
                    text=canonical_text if row.id == target.id else row.text,
                    language=row.language,
                    segment_indexes=segment_indexes,
                )
            )

        cloned_visual: list[_base.CanonicalVisualSpan] = []
        for row in visual_rows:
            try:
                observation_indexes = [
                    ocr_index_by_id[value] for value in (row.source_observation_ids_json or [])
                ]
            except KeyError as exc:
                raise AppError(
                    "SOURCE_EVIDENCE_PROVENANCE_INVALID",
                    "Canonical OCR span 引用的 raw OCR Evidence 已损坏",
                    status_code=409,
                ) from exc
            cloned_visual.append(
                _base.CanonicalVisualSpan(
                    start_us=row.start_us,
                    end_us=row.end_us,
                    text=row.text,
                    confidence=row.confidence,
                    bbox=list(row.bbox_json or []),
                    observation_indexes=observation_indexes,
                )
            )

        _, _, anchors = _base._shot_hint(db, project_id, episode_id, source.id)
        hints = {
            **dict(parent.sampling_hints_json or {}),
            "manual_adjudication_policy": P6_MANUAL_ADJUDICATION_POLICY,
            "manual_parent_evidence_set_id": parent.id,
            "manual_utterance_number": target.utterance_number,
            "manual_choice": command.choice.value,
        }
        snapshot = TaskWorkerRead.model_validate(task)
        new_set = _v4._ORIGINAL_PERSIST(
            db,
            set_id=str(uuid4()),
            task=snapshot,
            source_id=source.id,
            asr_profile=dict(parent.asr_profile_json or {}),
            ocr_profile=dict(parent.ocr_profile_json or {}),
            hints=hints,
            asr=cloned_asr,
            ocr=cloned_ocr,
            dialogue=cloned_dialogue,
            visual=cloned_visual,
            anchors=anchors,
        )

        running = db.get(Task, task.id)
        if running is not None:
            running.checkpoint_json = {"source_evidence_set_id": new_set.id}
            db.add(running)
            db.commit()
        mark_task_succeeded(db, task.id, worker_id=worker_id)
        _base._publish(db, task.id, new_set.id)
    except Exception as exc:
        db.rollback()
        failed = db.get(Task, task.id)
        if failed is not None and failed.status == TaskStatus.RUNNING:
            mark_task_failed(
                db,
                task.id,
                safe_error=f"P6 人工对白裁决失败（{type(exc).__name__}）",
                worker_id=worker_id,
            )
        raise

    return get_episode_source_evidence(db, project_id, episode_id)


def get_episode_source_evidence(
    db: Session,
    project_id: str,
    episode_id: str,
) -> EpisodeSourceEvidenceRead:
    result = _v4.get_episode_source_evidence(db, project_id, episode_id)
    if not result.dialogue:
        return result

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
        return result

    utterance_rows = _dialogue_rows(db, evidence_set.id)
    utterance_by_id = {row.id: row for row in utterance_rows}
    segment_ids = {
        segment_id
        for row in utterance_rows
        for segment_id in (row.source_segment_ids_json or [])
    }
    segments = (
        list(db.scalars(select(AsrEvidenceSegment).where(AsrEvidenceSegment.id.in_(segment_ids))).all())
        if segment_ids
        else []
    )
    segment_by_id = {row.id: row for row in segments}

    enriched = []
    for item in result.dialogue:
        row = utterance_by_id.get(item.id)
        provenances = [
            segment_by_id[segment_id].provenance_json or {}
            for segment_id in ((row.source_segment_ids_json if row else None) or [])
            if segment_id in segment_by_id
        ]
        manual = next(
            (
                value
                for value in provenances
                if value.get("manual_adjudication_policy") == P6_MANUAL_ADJUDICATION_POLICY
            ),
            None,
        )
        if manual is None:
            enriched.append(item)
            continue
        enriched.append(
            item.model_copy(
                update={
                    "text_source": str(manual.get("manual_text_source") or DialogueTextSource.USER_EDITED.value),
                    "asr_text": str(manual.get("manual_original_asr_text") or item.asr_text or item.text),
                    "ocr_text": (
                        str(manual.get("manual_selected_ocr_text"))
                        if manual.get("manual_selected_ocr_text")
                        else None
                    ),
                    "ocr_span_numbers": [
                        int(value) for value in (manual.get("manual_selected_ocr_span_numbers") or [])
                    ],
                    "adjudication_policy": P6_MANUAL_ADJUDICATION_POLICY,
                    "adjudication_reason": f"USER_SELECTED_{manual.get('manual_choice', 'CUSTOM')}",
                }
            )
        )
    return result.model_copy(update={"dialogue": enriched})
