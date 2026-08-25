"""Character V5 Gallery 持久化硬门槛。

职责：
- 正式 Gallery 复用 character_visual_v5 的 clean-person 保存；
- 没有干净身体图时，face-only UI cover 也必须通过“不能带入其他 Person”检查；
- cover 只是 UI 辅助，不会反向污染 Character Gallery / Identity。
"""
from __future__ import annotations

from pathlib import Path

from engine.app import character_visual_v5 as v5
from engine.app.studio_v2 import workspace_root

CandidateDraft = v5.CandidateDraft


def save_candidate_gallery(run_id: str, candidate: CandidateDraft, ordinal: int) -> list[str]:
    return v5.save_candidate_gallery(run_id, candidate, ordinal)


def _strict_face_only_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    import cv2

    face_observations = [
        obs for track in candidate.tracks for obs in track.observations
        if isinstance(obs, v5.Observation) and obs.face_visible and obs.face_bbox is not None
    ]
    if not face_observations:
        return None
    obs = max(face_observations, key=lambda item: item.face_score)
    frame = v5._read_frame(obs.reference_path, obs.local_time_us)
    if frame is None or obs.face_bbox is None:
        return None

    x, y, w, h = obs.face_bbox
    height, width = frame.shape[:2]
    pad = int(max(w, h) * 0.24)
    bounds = (
        max(0, x - pad),
        max(0, y - pad),
        min(width, x + w + pad),
        min(height, y + h + pad),
    )
    if v5._crop_contamination(bounds, obs.other_person_boxes) > v5.SAVE_CONTAMINATION_MAX:
        bounds = (max(0, x), max(0, y), min(width, x + w), min(height, y + h))
    if v5._crop_contamination(bounds, obs.other_person_boxes) > v5.SAVE_CONTAMINATION_MAX:
        return None

    left, top, right, bottom = bounds
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    path: Path = workspace_root() / "analysis" / run_id / "characters" / f"character_{ordinal:03d}" / "cover_face_only.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path) if cv2.imwrite(str(path), crop) else None


def save_candidate_cover(run_id: str, candidate: CandidateDraft, ordinal: int) -> str | None:
    """封面优先使用正式单人 Gallery；无 Gallery 时只允许严格单人 face-only fallback。"""

    paths = save_candidate_gallery(run_id, candidate, ordinal)
    if paths:
        return paths[0]
    return _strict_face_only_cover(run_id, candidate, ordinal)
