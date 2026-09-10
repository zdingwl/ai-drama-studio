"""P6 canonical Evidence v3 adapter.

P6 v2 fixed aggressive cross-segment merging. V3 keeps that conservative segmentation policy and
adds one admission guard for adjacent duplicate ASR micro-segments whose duration cannot plausibly
contain the recognized text. Raw ASR evidence is never deleted: rejected micro-segments remain
persisted with explicit canonical provenance, while only canonical SourceDialogueUtterance materialization
is suppressed.

This module deliberately does not use OCR, P7/P8 semantics, speaker candidates, sample-specific text,
or sample-specific timestamps to repair ASR.
"""

import re

from app.evidence import service as _base
from app.evidence.providers import AsrSegmentResult


P6_PROFILE_VERSION = "p6-source-evidence-v3"
P6_CANONICAL_POLICY = "segment-preserving-dialogue-v3"
P6_CANONICAL_GUARD = "adjacent-duplicate-microsegment-v1"

_MAX_DUPLICATE_GAP_US = 300_000
_MIN_DUPLICATE_MICRO_UNITS = 4
_MIN_US_PER_SPEECH_UNIT = 30_000
_SPEECH_UNIT_RE = re.compile(
    r"[A-Za-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]"
)

_ORIGINAL_CANONICAL_DIALOGUE = _base._canonical_dialogue
_ORIGINAL_PERSIST = _base._persist


def _speech_unit_count(text: str) -> int:
    """Return a conservative speech-information unit count.

    CJK/kana/hangul characters count individually; contiguous Latin/digit text counts as one word.
    Punctuation and whitespace do not increase the count. The threshold is intentionally permissive:
    it only catches durations that are far outside plausible speech timing.
    """

    return len(_SPEECH_UNIT_RE.findall(text))


def _is_implausible_micro_segment(segment: AsrSegmentResult) -> bool:
    units = _speech_unit_count(segment.text.strip())
    if units < _MIN_DUPLICATE_MICRO_UNITS:
        return False
    duration_us = max(0, segment.end_us - segment.start_us)
    return duration_us < units * _MIN_US_PER_SPEECH_UNIT


def _rejected_duplicate_micro_indexes(segments: list[AsrSegmentResult]) -> set[int]:
    """Find only implausible members of adjacent exact-text duplicate pairs.

    Short duration alone is never enough to reject a segment. Exact normalized duplicate text plus a
    near-adjacent timestamp is required. If one copy has plausible duration, only the implausible copy
    is rejected; if both copies are implausible, both remain raw-only evidence.
    """

    rejected: set[int] = set()
    for index in range(len(segments) - 1):
        left = segments[index]
        right = segments[index + 1]
        left_text = _base._normalize(left.text)
        right_text = _base._normalize(right.text)
        if not left_text or left_text != right_text:
            continue
        gap_us = max(0, right.start_us - left.end_us)
        if gap_us > _MAX_DUPLICATE_GAP_US:
            continue
        if _is_implausible_micro_segment(left):
            rejected.add(index)
        if _is_implausible_micro_segment(right):
            rejected.add(index + 1)
    return rejected


def _canonical_dialogue(segments: list[AsrSegmentResult]):
    rejected = _rejected_duplicate_micro_indexes(segments)
    if not rejected:
        return _ORIGINAL_CANONICAL_DIALOGUE(segments)

    kept = [(index, segment) for index, segment in enumerate(segments) if index not in rejected]
    canonical = _ORIGINAL_CANONICAL_DIALOGUE([segment for _, segment in kept])
    return [
        _base.CanonicalUtterance(
            start_us=item.start_us,
            end_us=item.end_us,
            text=item.text,
            language=item.language,
            segment_indexes=[kept[index][0] for index in item.segment_indexes],
        )
        for item in canonical
    ]


def _persist_v3(
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
    rejected = _rejected_duplicate_micro_indexes(asr)
    annotated_asr: list[AsrSegmentResult] = []
    for index, item in enumerate(asr):
        provenance = {
            **item.provenance,
            "canonical_policy": P6_CANONICAL_POLICY,
            "canonical_guard": P6_CANONICAL_GUARD,
            "canonical_included": index not in rejected,
        }
        if index in rejected:
            provenance["canonical_exclusion_reason"] = (
                "IMPLAUSIBLE_ADJACENT_DUPLICATE_MICROSEGMENT"
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

    audited_hints = {
        **hints,
        "canonical_dialogue_policy": P6_CANONICAL_POLICY,
        "canonical_guard": P6_CANONICAL_GUARD,
        "canonical_excluded_asr_segment_count": len(rejected),
    }
    return _ORIGINAL_PERSIST(
        db,
        set_id=set_id,
        task=task,
        source_id=source_id,
        asr_profile=asr_profile,
        ocr_profile=ocr_profile,
        hints=audited_hints,
        asr=annotated_asr,
        ocr=ocr,
        dialogue=dialogue,
        visual=visual,
        anchors=anchors,
    )


# Base service owns the Task / publication lifecycle. Patch only versioned canonical admission and
# raw-evidence audit behavior; every other P6 guardrail remains the existing implementation.
_base.P6_PROFILE_VERSION = P6_PROFILE_VERSION
_base.P6_CANONICAL_POLICY = P6_CANONICAL_POLICY
_base._canonical_dialogue = _canonical_dialogue
_base._persist = _persist_v3

P6_TASK_TYPE = _base.P6_TASK_TYPE
CanonicalUtterance = _base.CanonicalUtterance
create_source_evidence_task = _base.create_source_evidence_task
get_episode_source_evidence = _base.get_episode_source_evidence
is_p6_source_evidence_task = _base.is_p6_source_evidence_task
run_p6_source_evidence_task = _base.run_p6_source_evidence_task
