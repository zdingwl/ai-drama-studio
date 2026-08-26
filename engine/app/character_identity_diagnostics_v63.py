"""Character V6.3 identity diagnostics。

不参与身份决策，只在 resolver 完成后记录 Final-ready Candidate 之间的相似度与时空冲突，
用于定位“真实 3 人却发布 4/5 人”时到底是哪一对没有合并，以及为什么。
"""
from __future__ import annotations

import logging
from typing import Any

from engine.app import character_identity_v63 as identity
from engine.app import character_visual_v5 as v5

logger = logging.getLogger(__name__)


def _interval(track: Any) -> tuple[int | None, int | None]:
    if not getattr(track, "observations", None):
        return None, None
    return (
        min(int(item.source_time_us) for item in track.observations),
        max(int(item.source_time_us) for item in track.observations),
    )


def _simultaneous_distinct(left: Any, right: Any) -> bool:
    if left.shot_id != right.shot_id:
        return False
    li = _interval(left)
    ri = _interval(right)
    if li[0] is None or ri[0] is None:
        return True
    overlap = max(li[0], ri[0]) <= min(li[1] or li[0], ri[1] or ri[0])
    if not overlap:
        return False
    return not identity._simultaneous_duplicate(left, right)


def annotate_and_log(candidates: list[Any]) -> None:
    resolved = [item for item in candidates if getattr(item, "identity_status", None) == "RESOLVED"]
    pair_rows: dict[int, list[dict[str, object]]] = {id(item): [] for item in resolved}

    for left_index, left in enumerate(resolved):
        for right_index in range(left_index + 1, len(resolved)):
            right = resolved[right_index]
            face = v5.cosine(left.face_embedding, right.face_embedding)
            reid = v5.cosine(left.reid_embedding, right.reid_embedding)
            left_shots = {track.shot_id for track in left.tracks}
            right_shots = {track.shot_id for track in right.tracks}
            shared_shots = sorted(left_shots & right_shots)
            simultaneous_conflict = any(
                _simultaneous_distinct(a, b)
                for a in left.tracks
                for b in right.tracks
                if a.shot_id == b.shot_id
            )
            row = {
                "other_resolved_ordinal": right_index + 1,
                "face": round(float(face), 4) if face is not None else None,
                "reid": round(float(reid), 4) if reid is not None else None,
                "shared_shots": shared_shots,
                "simultaneous_distinct_conflict": simultaneous_conflict,
            }
            reverse = dict(row)
            reverse["other_resolved_ordinal"] = left_index + 1
            pair_rows[id(left)].append(row)
            pair_rows[id(right)].append(reverse)
            logger.info(
                "[CharacterV6.3] resolved-pair %d<->%d face=%s reid=%s shared_shots=%s simultaneous_distinct=%s",
                left_index + 1,
                right_index + 1,
                f"{face:.4f}" if face is not None else "None",
                f"{reid:.4f}" if reid is not None else "None",
                shared_shots,
                simultaneous_conflict,
            )

    for index, candidate in enumerate(resolved, start=1):
        metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
        neighbors = sorted(
            pair_rows[id(candidate)],
            key=lambda item: max(
                float(item.get("face") or -1.0),
                float(item.get("reid") or -1.0),
            ),
            reverse=True,
        )[:4]
        metadata["resolved_ordinal_debug"] = index
        metadata["nearest_resolved_neighbors"] = neighbors
        candidate.v6_metadata = metadata  # type: ignore[attr-defined]
