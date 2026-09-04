"""P2 VLM provider contract and normalization helpers.

This module keeps model-specific payloads behind a stable semantic shape consumed by Fusion.
Visible Shot facts are normalized conservatively: missing or unknown values stay empty instead of
being guessed. New H3 directing fields remain optional so historical provider payloads continue to
validate unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Sequence

from engine.app import breakdown_p2_sidecar_v1 as p2


VLM_PROVIDER = "qwen3-vl"
VLM_MODEL = "Qwen3-VL"
VLM_PROFILE = "breakdown-p2-vlm-v1"


def _text(value: Any, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).strip().split())
    return text[:limit]


def _enum(value: Any, allowed: set[str], *, fallback: str) -> str:
    text = _text(value, limit=64).upper()
    return text if text in allowed else fallback


def _number(value: Any, *, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _ratio(value: Any, *, fallback: float) -> float:
    return max(0.0, min(1.0, _number(value, fallback=fallback)))


def _labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, limit=128)
        if text and text not in result:
            result.append(text)
    return result


def _normalize_scene(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "location_hint": _text(source.get("location_hint"), limit=255),
        "interior_exterior": _enum(
            source.get("interior_exterior"),
            {"INT", "EXT", "MIXED", "UNKNOWN"},
            fallback="UNKNOWN",
        ),
        "time_of_day": _text(source.get("time_of_day"), limit=128) or "未知",
        "environment_description": _text(source.get("environment_description"), limit=2000),
    }


def _normalize_shot(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "summary": _text(source.get("summary"), limit=4000),
        "visual_description": _text(source.get("visual_description"), limit=8000),
        "shot_type_hint": _text(source.get("shot_type_hint"), limit=128),
        "camera_angle_hint": _text(source.get("camera_angle_hint"), limit=256),
        "camera_motion_hint": _text(source.get("camera_motion_hint"), limit=256),
        "lighting_hint": _text(source.get("lighting_hint"), limit=1000),
        "continuity_hint": _text(source.get("continuity_hint"), limit=1000),
        "narrative_function_hint": _text(source.get("narrative_function_hint"), limit=2000),
        "composition_hint": _text(source.get("composition_hint"), limit=1000),
    }


def _normalize_subjects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    used_labels: set[str] = set()
    for index, raw in enumerate(value, start=1):
        source = raw if isinstance(raw, Mapping) else {}
        label = _text(source.get("label"), limit=128) or f"subject_{index}"
        if label in used_labels:
            suffix = 2
            base = label
            while f"{base}_{suffix}" in used_labels:
                suffix += 1
            label = f"{base}_{suffix}"
        used_labels.add(label)
        result.append({
            "label": label,
            "appearance_summary": _text(source.get("appearance_summary"), limit=2000),
            "activity_summary": _text(source.get("activity_summary"), limit=2000),
            "expression_summary": _text(source.get("expression_summary"), limit=1000),
            "posture_summary": _text(source.get("posture_summary"), limit=1000),
            "gaze_summary": _text(source.get("gaze_summary"), limit=1000),
            "interaction_summary": _text(source.get("interaction_summary"), limit=1500),
            "screen_position": _text(source.get("screen_position"), limit=256),
            "visibility": _enum(
                source.get("visibility"),
                {"FULL", "PARTIAL", "OCCLUDED", "UNKNOWN"},
                fallback="UNKNOWN",
            ),
            "speaking_state": _enum(
                source.get("speaking_state"),
                {"LIKELY_SPEAKING", "NOT_SPEAKING", "UNKNOWN"},
                fallback="UNKNOWN",
            ),
        })
    return result


def _normalize_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        source = raw if isinstance(raw, Mapping) else {}
        content = _text(source.get("content"), limit=4000)
        if not content:
            continue
        start_ratio = _ratio(source.get("start_ratio"), fallback=0.0)
        end_ratio = _ratio(source.get("end_ratio"), fallback=1.0)
        if end_ratio < start_ratio:
            start_ratio, end_ratio = end_ratio, start_ratio
        result.append({
            "event_type": _enum(source.get("event_type"), {"VISUAL", "ACTION"}, fallback="VISUAL"),
            "start_ratio": start_ratio,
            "end_ratio": end_ratio,
            "content": content,
            "subject_labels": _labels(source.get("subject_labels")),
        })
    return result


def _normalize_props(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        source = raw if isinstance(raw, Mapping) else {}
        label = _text(source.get("label"), limit=255)
        if not label:
            continue
        result.append({
            "label": label,
            "importance": _enum(source.get("importance"), {"LOW", "MEDIUM", "HIGH"}, fallback="LOW"),
            "narrative_reason": _text(source.get("narrative_reason"), limit=2000),
            "subject_labels": _labels(source.get("subject_labels")),
        })
    return result


def _normalize_semantic(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "scene": _normalize_scene(source.get("scene")),
        "shot": _normalize_shot(source.get("shot")),
        "subjects": _normalize_subjects(source.get("subjects")),
        "events": _normalize_events(source.get("events")),
        "props": _normalize_props(source.get("props")),
    }


def _record_semantic(record: p2.P2EvidenceRecord) -> dict[str, Any]:
    payload = record.payload if isinstance(record.payload, Mapping) else {}
    semantic = payload.get("semantic")
    if isinstance(semantic, Mapping):
        return _normalize_semantic(semantic)
    return _normalize_semantic(payload)


class Qwen3VLSemanticProvider:
    """Stable VLM provider interface used by the P2 orchestration layer.

    Concrete runtime implementations may override ``_run``. This legacy base intentionally keeps
    the provider contract lightweight and deterministic for tests and alternate runtimes.
    """

    component = "VLM"
    provider = VLM_PROVIDER
    model = VLM_MODEL

    def __init__(
        self,
        *,
        runner: Callable[[p2.P2RunContext], Sequence[p2.P2EvidenceRecord] | p2.P2ProviderResult] | None = None,
    ) -> None:
        self._runner = runner

    def _run(self, context: p2.P2RunContext) -> Sequence[p2.P2EvidenceRecord] | p2.P2ProviderResult:
        if self._runner is None:
            return ()
        return self._runner(context)

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        raw = self._run(context)
        if isinstance(raw, p2.P2ProviderResult):
            return raw
        evidence = tuple(raw)
        if not evidence:
            return p2.P2ProviderResult(
                component=self.component,
                provider=self.provider,
                model=self.model,
                status="NO_EVIDENCE",
                evidence=(),
                metadata={"profile": VLM_PROFILE},
                warnings=("VLM 没有产生可消费 evidence",),
            )
        normalized: list[p2.P2EvidenceRecord] = []
        for record in evidence:
            semantic = _record_semantic(record)
            payload = dict(record.payload)
            payload["semantic"] = semantic
            normalized.append(p2.P2EvidenceRecord(
                source_type=record.source_type,
                source_id=record.source_id,
                source_start_us=record.source_start_us,
                source_end_us=record.source_end_us,
                shot_revision_item_id=record.shot_revision_item_id,
                text=record.text,
                language=record.language,
                confidence=record.confidence,
                payload=payload,
            ))
        return p2.P2ProviderResult(
            component=self.component,
            provider=self.provider,
            model=self.model,
            status="READY",
            evidence=tuple(normalized),
            metadata={"profile": VLM_PROFILE},
            warnings=(),
        )


__all__ = [
    "Qwen3VLSemanticProvider",
    "VLM_MODEL",
    "VLM_PROFILE",
    "VLM_PROVIDER",
    "_normalize_semantic",
    "_record_semantic",
]
