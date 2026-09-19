"""Read-only preflight for native dialogue; estimates are not measured audio."""
import re
from collections import Counter

from app.core.errors import AppError


# Text-only estimates are deliberately conservative, but ASR boundaries and human
# articulation are not frame exact. A small fixed tolerance prevents a one-syllable
# line such as "Jake!" in a 220 ms source window from becoming mathematically
# impossible while still rejecting material multi-second overflow.
SPEECH_ESTIMATE_TOLERANCE_SECONDS = 0.15


def estimate_spoken_seconds(text: str) -> float:
    """Optimistic language-agnostic ceiling used before native audio exists."""
    cjk = len(re.findall(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]', text))
    words = len(re.findall(r"[^\W_]+(?:['’][^\W_]+)*", re.sub(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]', ' ', text)))
    return cjk / 6 + words / 4


def estimated_speech_fits(text: str, available_seconds: float) -> bool:
    return estimate_spoken_seconds(text) <= available_seconds + SPEECH_ESTIMATE_TOLERANCE_SECONDS


def dialogue_owner_windows(shots) -> dict[tuple[str, str], tuple[str, int, int]]:
    """Assign each utterance to one stable maximum-overlap shot.

    Localization and H3 must use the same ownership rule: a cross-shot line is
    spoken once, in its largest authoritative overlap window. The first shot
    wins an exact tie, preserving source order deterministically.
    """
    owners: dict[tuple[str, str], tuple[int, str, int, int]] = {}
    for shot in shots:
        get = shot.get if isinstance(shot, dict) else lambda name, default=None: getattr(shot, name, default)
        episode_id = get("episode_id")
        shot_id = get("storyboard_shot_id") or get("shot_anchor_id")
        for dialogue in get("dialogue", []):
            ref_get = dialogue.get if isinstance(dialogue, dict) else lambda name, default=None: getattr(dialogue, name, default)
            start_us = int(ref_get("overlap_start_us", 0))
            end_us = int(ref_get("overlap_end_us", 0))
            key = (episode_id, ref_get("utterance_id"))
            candidate = (end_us - start_us, shot_id, start_us, end_us)
            if key not in owners or candidate[0] > owners[key][0]:
                owners[key] = candidate
    return {key: (shot_id, start_us, end_us) for key, (_, shot_id, start_us, end_us) in owners.items()}


def audit_segments(segments) -> list[dict]:
    counts = Counter((s.episode_id, d.utterance_id) for s in segments for d in s.dialogue_refs)
    issues = []
    for segment in segments:
        def add(code, message):
            issues.append(dict(code=code, generation_segment_id=segment.generation_segment_id, message=message))
        repeated = [d for d in segment.dialogue_refs if counts[(segment.episode_id, d.utterance_id)] > 1]
        if repeated:
            add('DIALOGUE_REPEATED', '跨镜对白被多个生成段重复携带全文，需要重新分配对白。')
        # Validate each explicit speech window, not merely the enclosing segment.
        for dialogue in segment.dialogue_refs:
            available_seconds = (dialogue.planned_speech_end_us - dialogue.planned_speech_start_us) / 1_000_000
            if not estimated_speech_fits(dialogue.final_target_dialogue, available_seconds):
                seconds = estimate_spoken_seconds(dialogue.final_target_dialogue)
                add('DIALOGUE_TOO_LONG', f'对白即使快速说出也估计需要 {seconds:.1f} 秒，但计划语音窗仅 {available_seconds:.2f} 秒；此为文本估算。')
        total_seconds = sum(estimate_spoken_seconds(dialogue.final_target_dialogue) for dialogue in segment.dialogue_refs)
        if total_seconds > segment.duration_us / 1_000_000 + SPEECH_ESTIMATE_TOLERANCE_SECONDS:
            add('DIALOGUE_TOO_LONG', f'本段对白合计即使快速说出也估计需要 {total_seconds:.1f} 秒，当前仅 {segment.duration_us / 1_000_000:.2f} 秒；此为文本估算。')
        required = {r.target_entity_id for r in segment.target_asset_refs}
        actual = {r.target_entity_id for r in segment.reference_conditions}
        if required != actual:
            add('REFERENCE_INCOMPLETE', '人物、场景或道具的参考图未完整传入。')
    return issues


def require_valid_segments(segments):
    issues = audit_segments(segments)
    if issues:
        raise AppError('H3_PREFLIGHT_FAILED', '对白分段、时长或参考图检查未通过，请先修订本土化分镜与生成分段。', status_code=409, details={'issues': issues})
