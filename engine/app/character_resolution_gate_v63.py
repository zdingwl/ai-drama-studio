"""Character V6.3 Final-resolution safety gate。

Global Identity Graph 负责聚类；这里负责最后回答“这个 cluster 是否真的足够可靠，可以发布为 Final Character”。
旧规则只要求两个 Shot 出现 Face Track，可能把两个弱/污染 Face anchor 错误升级成第 4、5 个人物。

V6.3 要求至少存在一组跨 Shot 的强 Face，或 Face + CLEAN ReID 强联合证据。
不满足时只降级为 UNRESOLVED，不删除 Track/Evidence。
"""
from __future__ import annotations

from typing import Any

from engine.app import character_identity_v6 as base

RESOLVE_FACE_STRONG = 0.46
RESOLVE_FACE_SUPPORTED = 0.39
RESOLVE_REID_SUPPORTED = 0.86


def _cross_shot_support(candidate: Any) -> tuple[bool, dict[str, object]]:
    face_tracks = [track for track in candidate.tracks if base._face_vectors(track)]
    face_shots = {track.shot_id for track in face_tracks}
    best_face: float | None = None
    best_reid: float | None = None
    strong = False
    supported = False

    for left_index, left in enumerate(face_tracks):
        for right in face_tracks[left_index + 1:]:
            if left.shot_id == right.shot_id:
                continue
            face = base._face_similarity(left, right)
            reid = base._reid_similarity(left, right)
            if face is not None and (best_face is None or face > best_face):
                best_face = float(face)
            if reid is not None and (best_reid is None or reid > best_reid):
                best_reid = float(reid)
            if face is not None and face >= RESOLVE_FACE_STRONG:
                strong = True
            if (
                face is not None
                and face >= RESOLVE_FACE_SUPPORTED
                and reid is not None
                and reid >= RESOLVE_REID_SUPPORTED
            ):
                supported = True

    ok = len(face_shots) >= 2 and (strong or supported)
    return ok, {
        "face_track_count": len(face_tracks),
        "face_shot_count": len(face_shots),
        "best_cross_shot_face": round(best_face, 4) if best_face is not None else None,
        "best_cross_shot_reid": round(best_reid, 4) if best_reid is not None else None,
        "strong_face_support": strong,
        "face_reid_joint_support": supported,
    }


def enforce_resolution_gate(candidates: list[Any]) -> None:
    for candidate in candidates:
        if getattr(candidate, "identity_status", None) != "RESOLVED":
            continue
        ok, details = _cross_shot_support(candidate)
        metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
        metadata["v6.3_resolution_gate"] = details
        if not ok:
            candidate.identity_status = "UNRESOLVED"
            metadata["resolved"] = False
            metadata["resolution_gate_reason"] = "insufficient robust cross-shot face identity support"
        else:
            metadata["resolution_gate_reason"] = "passed"
        candidate.v6_metadata = metadata  # type: ignore[attr-defined]
