"""Character V7 final identity publish gate.

自动 Final Character 必须至少有 3 个独立 Face Shot。
两 Shot/单 Shot 的清晰脸仍完整保留为 UNRESOLVED Evidence，后续可以人工晋级；
但在自动链路稳定前绝不允许它们增加 Final Character 数。
"""
from __future__ import annotations

from typing import Any

MIN_AUTO_FACE_SHOTS = 3


def enforce_resolution_gate(candidates: list[Any]) -> list[Any]:
    for candidate in candidates:
        if str(getattr(candidate, "identity_status", "UNRESOLVED")) != "RESOLVED":
            continue
        metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
        face_shots = int(metadata.get("face_shot_count") or 0)
        if face_shots >= MIN_AUTO_FACE_SHOTS:
            metadata["v7_resolution_gate"] = "passed"
            metadata["v7_min_auto_face_shots"] = MIN_AUTO_FACE_SHOTS
            candidate.v6_metadata = metadata
            continue
        candidate.identity_status = "UNRESOLVED"
        metadata.update({
            "v7_resolution_gate": "demoted",
            "v7_resolution_reason": "fewer-than-3-distinct-face-shots",
            "v7_min_auto_face_shots": MIN_AUTO_FACE_SHOTS,
        })
        candidate.v6_metadata = metadata
    return candidates
