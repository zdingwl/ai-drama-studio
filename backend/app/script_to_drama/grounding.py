"""Source-grounding for SCRIPT_TO_DRAMA visual assets only.

Never infer or manufacture source evidence. The only repairs permitted below
select a literal span of the immutable source chunk, then persist that span.
"""

import re

from app.core.errors import AppError
from app.script_localization.long_text import SourceChunk

LABELS = {"characters": "人物", "locations": "场景", "props": "道具"}
_QUOTE_PAIRS = (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"))


def _candidates(evidence: str) -> list[str]:
    plain = evidence.strip()
    candidates = [plain]
    for left, right in _QUOTE_PAIRS:
        if len(plain) > 2 and plain.startswith(left) and plain.endswith(right):
            candidates.append(plain[len(left):len(plain) - len(right)].strip())
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _actual_source_span(source: str, evidence: str) -> str | None:
    if evidence in source:
        return evidence
    for candidate in _candidates(evidence):
        if candidate in source:
            return candidate
        # Whitespace differences only: return the EXACT original source bytes.
        # A unique match is required; ambiguous evidence is not auto-repaired.
        tokens = re.split(r"\s+", candidate)
        if len(tokens) < 2 or len(candidate) < 4:
            continue
        pattern = r"\s+".join(re.escape(token) for token in tokens)
        matches = list(re.finditer(pattern, source))
        if len(matches) == 1:
            return matches[0].group()
    return None


def normalize_world_evidence(chunk: SourceChunk, value: dict) -> None:
    """Validate and minimally repair in-place before persisting a provider result."""
    for field, label in LABELS.items():
        for item in value.get(field, []):
            evidence = item["source_evidence"]
            actual = _actual_source_span(chunk.text, evidence)
            if actual is None:
                name = str(item.get("name", ""))[:80]
                preview = evidence.replace("\n", "\\n")[:80]
                raise AppError(
                    "SCRIPT_TO_DRAMA_UNGROUNDED_WORLD",
                    f"第 {chunk.index} 段{label}「{name}」的原文证据无法定位：{preview!r}；请核对原文或重试该段",
                    status_code=422,
                )
            item["source_evidence"] = actual
