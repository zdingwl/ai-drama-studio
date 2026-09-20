"""Source-grounding for SCRIPT_TO_DRAMA visual assets only.

Never infer or manufacture source evidence. A repaired span must be taken literally
from the immutable source chunk. When a character's model-written *sentence* is
unsupported but its name is explicitly present in both the evidence and the source,
only the name can establish its presence. The unsupported description is flagged
for human review, not promoted to a source fact.
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


def _character_name_anchored(source: str, name: str, evidence: str) -> bool:
    """A name alone proves presence, never the narrated details in an invalid quote.

    Limit this recovery to explicitly named characters. A generic one-character
    name, inferred pronoun, partial name, location, or prop is not sufficient.
    """
    name = name.strip()
    return (
        len(name) >= 2
        and not any(char.isspace() for char in name)
        and name in source
        and any(candidate.startswith(name) for candidate in _candidates(evidence))
    )


def normalize_world_evidence(chunk: SourceChunk, value: dict) -> None:
    """Validate and minimally repair in-place before persisting a provider result."""
    for field, label in LABELS.items():
        for item in value.get(field, []):
            evidence = item["source_evidence"]
            actual = _actual_source_span(chunk.text, evidence)
            if actual is None and field == "characters":
                name = str(item.get("name", "")).strip()
                if _character_name_anchored(chunk.text, name, evidence):
                    # The exact source name establishes that this person is mentioned,
                    # NOT that the unsupported action/appearance in the quote is true.
                    # Block approval until a reviewer explicitly resolves this decision.
                    item["source_evidence"] = name
                    item["source_fact"] = ""
                    decision = (
                        f"第 {chunk.index} 段人物「{name}」：模型的原文引句未匹配，"
                        f"仅确认原文出现人物名称；原引句「{evidence[:75]}」及人物设定须人工核对"
                    )
                    value.setdefault("unresolved_decisions", []).append(decision)
                    continue
            if actual is None:
                name = str(item.get("name", ""))[:80]
                preview = evidence.replace("\n", "\\n")[:80]
                raise AppError(
                    "SCRIPT_TO_DRAMA_UNGROUNDED_WORLD",
                    f"第 {chunk.index} 段{label}「{name}」的原文证据无法定位：{preview!r}；请核对原文或重试该段",
                    status_code=422,
                )
            item["source_evidence"] = actual
