"""Character V9 Phase A: Person Instance safety layer.

This module does NOT resolve identity. It only turns a detected person bbox into a
well-defined single-person Evidence unit and decides whether that crop is safe to
enter a future Person Gallery.

Hard rules:
- identity never consumes the whole frame as a person image;
- every person observation owns an explicit person bbox / crop bbox;
- multi-person overlap is measured before gallery admission;
- PARTIAL / OCCLUDED / CONTAMINATED remain useful Evidence but are never gallery seeds;
- only CLEAN Person Instance crops are gallery-eligible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PersonInstanceClass = Literal["CLEAN", "OCCLUDED", "CONTAMINATED", "PARTIAL"]

# Gallery admission is intentionally stricter than presence detection.
OCCLUDED_OVERLAP_RATIO = 0.025
CONTAMINATED_OVERLAP_RATIO = 0.15
CLEAN_MARGIN_RATIO = 0.04
CLEAN_EXPANDED_CONTAMINATION_MAX = 0.015
PARTIAL_EDGE_MARGIN_RATIO = 0.012
PARTIAL_MAX_FRAME_COVERAGE_WITH_EDGE_TRUNCATION = 0.88


@dataclass(frozen=True)
class PersonInstanceSafety:
    instance_class: PersonInstanceClass
    person_bbox: tuple[int, int, int, int]
    crop_bbox: tuple[int, int, int, int]
    contamination_ratio: float
    max_other_overlap_ratio: float
    touches_frame_edges: int
    gallery_eligible: bool
    reason: str


def _clamp_box(
    box: tuple[int | float, int | float, int | float, int | float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x, y, w, h = box
    left = max(0, min(int(round(x)), max(0, width - 1)))
    top = max(0, min(int(round(y)), max(0, height - 1)))
    right = max(left + 1, min(int(round(x + w)), width))
    bottom = max(top + 1, min(int(round(y + h)), height))
    return left, top, max(1, right - left), max(1, bottom - top)


def _intersection_area(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> int:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    x1, y1 = max(lx, rx), max(ly, ry)
    x2, y2 = min(lx + lw, rx + rw), min(ly + lh, ry + rh)
    return max(0, x2 - x1) * max(0, y2 - y1)


def _overlap_metrics(
    target: tuple[int, int, int, int],
    others: list[tuple[int, int, int, int]],
) -> tuple[float, float]:
    area = max(1, target[2] * target[3])
    overlaps = [_intersection_area(target, other) / float(area) for other in others]
    if not overlaps:
        return 0.0, 0.0
    return min(1.0, sum(overlaps)), min(1.0, max(overlaps))


def _touch_count(box: tuple[int, int, int, int], width: int, height: int) -> int:
    x, y, w, h = box
    mx = max(2, int(round(width * PARTIAL_EDGE_MARGIN_RATIO)))
    my = max(2, int(round(height * PARTIAL_EDGE_MARGIN_RATIO)))
    return int(x <= mx) + int(y <= my) + int(x + w >= width - mx) + int(y + h >= height - my)


def _expanded_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    margin_ratio: float,
) -> tuple[int, int, int, int]:
    x, y, w, h = box
    pad_x = int(round(w * margin_ratio))
    pad_y = int(round(h * margin_ratio))
    return _clamp_box((x - pad_x, y - pad_y, w + pad_x * 2, h + pad_y * 2), width, height)


def classify_person_instance(
    *,
    person_bbox: tuple[int, int, int, int],
    other_person_boxes: list[tuple[int, int, int, int]],
    frame_width: int,
    frame_height: int,
    proposal_source: str = "",
    force_partial: bool = False,
) -> PersonInstanceSafety:
    """Classify one detected person into the V9 Phase-A crop safety contract.

    The result is deliberately identity-agnostic. A dirty crop is not discarded;
    it simply cannot enter a confirmed Person Gallery or seed a new identity.
    """

    width = max(1, int(frame_width))
    height = max(1, int(frame_height))
    target = _clamp_box(person_bbox, width, height)
    others = [_clamp_box(item, width, height) for item in other_person_boxes]
    contamination, max_overlap = _overlap_metrics(target, others)
    touches = _touch_count(target, width, height)
    frame_coverage = (target[2] * target[3]) / float(width * height)
    source_is_partial = "partial" in str(proposal_source or "").lower()
    geometry_partial = touches >= 2 and frame_coverage < PARTIAL_MAX_FRAME_COVERAGE_WITH_EDGE_TRUNCATION

    if force_partial or source_is_partial or geometry_partial:
        instance_class: PersonInstanceClass = "PARTIAL"
        reason = "partial proposal or frame-edge truncation"
    elif max_overlap >= CONTAMINATED_OVERLAP_RATIO or contamination >= CONTAMINATED_OVERLAP_RATIO:
        instance_class = "CONTAMINATED"
        reason = "another person occupies a substantial part of the target crop"
    elif max_overlap >= OCCLUDED_OVERLAP_RATIO or contamination >= OCCLUDED_OVERLAP_RATIO:
        instance_class = "OCCLUDED"
        reason = "another person overlaps the target crop"
    else:
        instance_class = "CLEAN"
        reason = "isolated single-person crop"

    crop = target
    if instance_class == "CLEAN":
        expanded = _expanded_box(target, width, height, CLEAN_MARGIN_RATIO)
        expanded_contamination, _expanded_max = _overlap_metrics(expanded, others)
        if expanded_contamination <= CLEAN_EXPANDED_CONTAMINATION_MAX:
            crop = expanded

    return PersonInstanceSafety(
        instance_class=instance_class,
        person_bbox=target,
        crop_bbox=crop,
        contamination_ratio=contamination,
        max_other_overlap_ratio=max_overlap,
        touches_frame_edges=touches,
        gallery_eligible=instance_class == "CLEAN",
        reason=reason,
    )


def gallery_crop_is_valid(
    safety: PersonInstanceSafety,
    *,
    frame_width: int,
    frame_height: int,
) -> bool:
    """Final guard before a crop is admitted to a Person Gallery."""

    if not safety.gallery_eligible or safety.instance_class != "CLEAN":
        return False
    x, y, w, h = safety.crop_bbox
    if w <= 0 or h <= 0:
        return False
    if x < 0 or y < 0 or x + w > frame_width or y + h > frame_height:
        return False
    # A valid gallery image must be derived from an explicit detected Person bbox.
    return safety.person_bbox[2] > 0 and safety.person_bbox[3] > 0
