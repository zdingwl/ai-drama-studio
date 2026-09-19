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


def audit_segments(segments) -> list[dict]:
    counts = Counter((s.episode_id, d.utterance_id) for s in segments for d in s.dialogue_refs)
    issues = []
    for segment in segments:
        def add(code, message):
            issues.append(dict(code=code, generation_segment_id=segment.generation_segment_id, message=message))
        repeated = [d for d in segment.dialogue_refs if counts[(segment.episode_id, d.utterance_id)] > 1]
        if repeated:
            add('DIALOGUE_REPEATED', '跨镜对白被多个生成段重复携带全文，需要重新分配对白。')
        # Optimistic screening ceiling, deliberately not a claim of actual speech duration.
        seconds = sum(estimate_spoken_seconds(dialogue.final_target_dialogue) for dialogue in segment.dialogue_refs)
        if seconds > segment.duration_us / 1_000_000 + SPEECH_ESTIMATE_TOLERANCE_SECONDS:
            add('DIALOGUE_TOO_LONG', f'对白即使快速说出也估计需要 {seconds:.1f} 秒，当前仅 {segment.duration_us / 1_000_000:.2f} 秒；此为文本估算。')
        required = {r.target_entity_id for r in segment.target_asset_refs}
        actual = {r.target_entity_id for r in segment.reference_conditions}
        if required != actual:
            add('REFERENCE_INCOMPLETE', '人物、场景或道具的参考图未完整传入。')
    return issues


def require_valid_segments(segments):
    issues = audit_segments(segments)
    if issues:
        raise AppError('H3_PREFLIGHT_FAILED', '对白分段、时长或参考图检查未通过，请先修订本土化分镜与生成分段。', status_code=409, details={'issues': issues})
