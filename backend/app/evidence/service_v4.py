"""P6 canonical Evidence v4 adapter.

V4 keeps the complete-Episode continuous ASR / timeline OCR architecture and every v3
micro-duplicate guard. It adds one explicit, conservative cross-evidence adjudication step:
a high-confidence OCR span in the subtitle region may replace a near-match ASR canonical text.

This is deliberately not a silent OCR override. Raw ASR text remains unchanged and receives audit
provenance describing the original ASR text, chosen OCR text, supporting canonical OCR span numbers,
policy, edit distance and reason. Ambiguous or weak OCR evidence leaves ASR canonical text intact.
P7/P8/VLM text is never consulted here.
"""

import math
import re
from dataclasses import dataclass

from sqlalchemy import select

# Import v3 first so the base lifecycle already includes the micro-duplicate admission guard.
from app.evidence import service_v3 as _v3  # noqa: F401
from app.evidence import service as _base
from app.evidence.models import AsrEvidenceSegment, SourceDialogueUtterance, SourceEvidenceSet
from app.evidence.providers import AsrSegmentResult
from app.sources.models import Episode


P6_PROFILE_VERSION = "p6-source-evidence-v4"
P6_CANONICAL_POLICY = "segment-preserving-dialogue-v4"
P6_CANONICAL_GUARD = "adjacent-duplicate-microsegment-v1"
P6_TEXT_ADJUDICATION_POLICY = "ocr-subtitle-near-match-v1"

_MIN_OCR_CONFIDENCE = 0.85
_MIN_SUBTITLE_CENTER_Y_RATIO = 0.55
_MAX_LENGTH_DELTA = 2

_PERSIST_V3 = _base._persist
_GET_V3 = _base.get_episode_source_evidence


@dataclass(frozen=True)
class DialogueTextAdjudication:
    utterance_index: int
    asr_text: str
    canonical_text: str
    ocr_text: str | None
    ocr_span_numbers: list[int]
    edit_distance: int | None
    reason: str
    text_source: str


def _normalized_text(text: str) -> str:
    # Python's Unicode \w keeps CJK letters while removing whitespace / punctuation.
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _bbox_center_y(bbox: list) -> float | None:
    if not bbox:
        return None
    ys: list[float] = []
    if all(isinstance(value, (int, float)) for value in bbox):
        ys = [float(bbox[index]) for index in range(1, len(bbox), 2)]
    else:
        for point in bbox:
            if (
                isinstance(point, (list, tuple))
                and len(point) >= 2
                and isinstance(point[1], (int, float))
            ):
                ys.append(float(point[1]))
    return sum(ys) / len(ys) if ys else None


def _temporal_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def _eligible_ocr_candidate(utterance, span, frame_height: int) -> tuple[int, int] | None:
    if span.confidence is None or span.confidence < _MIN_OCR_CONFIDENCE:
        return None
    center_y = _bbox_center_y(span.bbox)
    if center_y is None or center_y < frame_height * _MIN_SUBTITLE_CENTER_Y_RATIO:
        return None
    overlap_us = _temporal_overlap(utterance.start_us, utterance.end_us, span.start_us, span.end_us)
    if overlap_us <= 0:
        return None

    asr_text = _normalized_text(utterance.text)
    ocr_text = _normalized_text(span.text)
    if len(asr_text) < 2 or len(ocr_text) < 2:
        return None
    if abs(len(asr_text) - len(ocr_text)) > _MAX_LENGTH_DELTA:
        return None

    distance = _levenshtein(asr_text, ocr_text)
    max_distance = max(1, math.floor(max(len(asr_text), len(ocr_text)) / 3))
    if distance > max_distance:
        return None
    return distance, overlap_us


def _adjudicate_dialogue_texts(dialogue, visual, frame_height: int):
    """Return canonical dialogue plus an audit decision per affected utterance.

    An exact OCR match corroborates ASR but never counts as a rewrite. A single distinct eligible
    near-match candidate may become canonical text. If multiple distinct near-match texts compete,
    ASR remains canonical and the conflict is recorded for audit instead of guessed away.
    """

    corrected = []
    audits: dict[int, DialogueTextAdjudication] = {}
    for utterance_index, utterance in enumerate(dialogue):
        asr_norm = _normalized_text(utterance.text)
        exact_span_numbers: list[int] = []
        candidates: dict[str, list[tuple[int, object, int, int]]] = {}
        for span_index, span in enumerate(visual):
            eligible = _eligible_ocr_candidate(utterance, span, frame_height)
            if eligible is None:
                continue
            distance, overlap_us = eligible
            normalized = _normalized_text(span.text)
            if normalized == asr_norm:
                exact_span_numbers.append(span_index + 1)
                continue
            candidates.setdefault(normalized, []).append((span_index + 1, span, distance, overlap_us))

        # If high-confidence subtitle OCR independently agrees with ASR, do not let another noisy
        # near-match rewrite it.
        if exact_span_numbers:
            corrected.append(utterance)
            audits[utterance_index] = DialogueTextAdjudication(
                utterance_index=utterance_index,
                asr_text=utterance.text,
                canonical_text=utterance.text,
                ocr_text=None,
                ocr_span_numbers=sorted(exact_span_numbers),
                edit_distance=0,
                reason="HIGH_CONFIDENCE_SUBTITLE_CORROBORATION",
                text_source="ASR",
            )
            continue

        if len(candidates) == 1:
            rows = next(iter(candidates.values()))
            # Prefer highest confidence, then most temporal overlap. Same normalized OCR text is one
            # candidate even if it was seen on multiple sampled frames.
            chosen = max(rows, key=lambda item: (float(item[1].confidence or 0), item[3]))
            span_number, span, distance, _ = chosen
            supporting = sorted(item[0] for item in rows)
            canonical = _base.CanonicalUtterance(
                start_us=utterance.start_us,
                end_us=utterance.end_us,
                text=span.text.strip(),
                language=utterance.language,
                segment_indexes=list(utterance.segment_indexes),
            )
            corrected.append(canonical)
            audits[utterance_index] = DialogueTextAdjudication(
                utterance_index=utterance_index,
                asr_text=utterance.text,
                canonical_text=canonical.text,
                ocr_text=canonical.text,
                ocr_span_numbers=supporting,
                edit_distance=distance,
                reason="HIGH_CONFIDENCE_TEMPORAL_SUBTITLE_NEAR_MATCH",
                text_source="OCR_SUBTITLE_ADJUDICATED",
            )
            continue

        corrected.append(utterance)
        if len(candidates) > 1:
            candidate_rows = [row for rows in candidates.values() for row in rows]
            audits[utterance_index] = DialogueTextAdjudication(
                utterance_index=utterance_index,
                asr_text=utterance.text,
                canonical_text=utterance.text,
                ocr_text=None,
                ocr_span_numbers=sorted(row[0] for row in candidate_rows),
                edit_distance=None,
                reason="AMBIGUOUS_OCR_SUBTITLE_CANDIDATES",
                text_source="ASR",
            )

    return corrected, audits


def _persist_v4(
    db,
    *,
    set_id,
    task,
    source_id,
    asr_profile,
    ocr_profile,
    hints,
    asr,
    ocr,
    dialogue,
    visual,
    anchors,
):
    if task.episode_id is None:
        return _PERSIST_V3(
            db,
            set_id=set_id,
            task=task,
            source_id=source_id,
            asr_profile=asr_profile,
            ocr_profile=ocr_profile,
            hints=hints,
            asr=asr,
            ocr=ocr,
            dialogue=dialogue,
            visual=visual,
            anchors=anchors,
        )
    episode = db.get(Episode, task.episode_id)
    frame_height = int(episode.height) if episode is not None else 0
    corrected_dialogue, audits = _adjudicate_dialogue_texts(dialogue, visual, frame_height)

    audit_by_segment: dict[int, DialogueTextAdjudication] = {}
    for utterance_index, decision in audits.items():
        for segment_index in dialogue[utterance_index].segment_indexes:
            audit_by_segment[segment_index] = decision

    annotated_asr: list[AsrSegmentResult] = []
    for segment_index, item in enumerate(asr):
        decision = audit_by_segment.get(segment_index)
        provenance = dict(item.provenance)
        if decision is not None:
            provenance.update(
                {
                    "canonical_text_source": decision.text_source,
                    "canonical_asr_text": decision.asr_text,
                    "canonical_text": decision.canonical_text,
                    "canonical_ocr_text": decision.ocr_text,
                    "canonical_ocr_span_numbers": decision.ocr_span_numbers,
                    "canonical_adjudication_policy": P6_TEXT_ADJUDICATION_POLICY,
                    "canonical_adjudication_edit_distance": decision.edit_distance,
                    "canonical_adjudication_reason": decision.reason,
                }
            )
        annotated_asr.append(
            AsrSegmentResult(
                start_us=item.start_us,
                end_us=item.end_us,
                text=item.text,
                language=item.language,
                confidence=item.confidence,
                provenance=provenance,
            )
        )

    rewritten_count = sum(1 for item in audits.values() if item.text_source == "OCR_SUBTITLE_ADJUDICATED")
    conflict_count = sum(1 for item in audits.values() if item.reason == "AMBIGUOUS_OCR_SUBTITLE_CANDIDATES")
    audited_hints = {
        **hints,
        "canonical_dialogue_policy": P6_CANONICAL_POLICY,
        "canonical_guard": P6_CANONICAL_GUARD,
        "canonical_text_adjudication": P6_TEXT_ADJUDICATION_POLICY,
        "canonical_text_adjudicated_count": rewritten_count,
        "canonical_text_conflict_count": conflict_count,
    }
    return _PERSIST_V3(
        db,
        set_id=set_id,
        task=task,
        source_id=source_id,
        asr_profile=asr_profile,
        ocr_profile=ocr_profile,
        hints=audited_hints,
        asr=annotated_asr,
        ocr=ocr,
        dialogue=corrected_dialogue,
        visual=visual,
        anchors=anchors,
    )


def get_episode_source_evidence(db, project_id: str, episode_id: str):
    result = _GET_V3(db, project_id, episode_id)
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

    utterance_rows = list(
        db.scalars(
            select(SourceDialogueUtterance).where(
                SourceDialogueUtterance.source_evidence_set_id == evidence_set.id
            )
        ).all()
    )
    utterance_by_id = {row.id: row for row in utterance_rows}
    segment_ids = {
        segment_id
        for row in utterance_rows
        for segment_id in (row.source_segment_ids_json or [])
    }
    segments = list(
        db.scalars(select(AsrEvidenceSegment).where(AsrEvidenceSegment.id.in_(segment_ids))).all()
    ) if segment_ids else []
    segment_by_id = {row.id: row for row in segments}

    enriched = []
    for item in result.dialogue:
        row = utterance_by_id.get(item.id)
        provenances = [
            segment_by_id[segment_id].provenance_json or {}
            for segment_id in ((row.source_segment_ids_json if row else None) or [])
            if segment_id in segment_by_id
        ]
        audit = next(
            (
                value
                for value in provenances
                if value.get("canonical_adjudication_policy") == P6_TEXT_ADJUDICATION_POLICY
                and value.get("canonical_text_source") == "OCR_SUBTITLE_ADJUDICATED"
            ),
            None,
        )
        enriched.append(
            item.model_copy(
                update={
                    "text_source": "OCR_SUBTITLE_ADJUDICATED" if audit else "ASR",
                    "asr_text": str(audit.get("canonical_asr_text")) if audit else item.text,
                    "ocr_text": str(audit.get("canonical_ocr_text")) if audit and audit.get("canonical_ocr_text") else None,
                    "ocr_span_numbers": [int(value) for value in (audit.get("canonical_ocr_span_numbers") or [])] if audit else [],
                    "adjudication_policy": str(audit.get("canonical_adjudication_policy")) if audit else None,
                    "adjudication_reason": str(audit.get("canonical_adjudication_reason")) if audit else None,
                }
            )
        )
    return result.model_copy(update={"dialogue": enriched})


# The base lifecycle owns task creation/execution/publication. Pin it to v4 so the version participates
# in task fingerprints and formal SOURCE_DIALOGUE artifact metadata, while v3's canonical admission
# function remains installed underneath this text adjudication layer.
_base.P6_PROFILE_VERSION = P6_PROFILE_VERSION
_base.P6_CANONICAL_POLICY = P6_CANONICAL_POLICY
_base._persist = _persist_v4

P6_TASK_TYPE = _base.P6_TASK_TYPE
CanonicalUtterance = _base.CanonicalUtterance
create_source_evidence_task = _base.create_source_evidence_task
is_p6_source_evidence_task = _base.is_p6_source_evidence_task
run_p6_source_evidence_task = _base.run_p6_source_evidence_task
