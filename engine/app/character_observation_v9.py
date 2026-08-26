"""Character V9 Phase A observation adapter.

The detector remains the currently validated 12fps YOLOX/partial pipeline. This
adapter adds the V9 Person Instance contract before MOT/identity:
- one explicit instance id per detected person in a sampled frame;
- explicit person/crop bbox;
- CLEAN/OCCLUDED/CONTAMINATED/PARTIAL classification;
- gallery eligibility;
- same-sample spatial cannot-link ids.

No identity decision is made here.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from engine.app import character_observation_v63 as legacy
from engine.app import character_visual_v5 as v5
from engine.app.character_person_instance_v9 import classify_person_instance

CharacterProgress = v5.CharacterProgress
Observation = v5.Observation
sample_times_us = legacy.sample_times_us

CANNOT_LINK_MAX_IOU = 0.35


def _instance_id(observation: Observation, ordinal: int) -> str:
    return f"{observation.shot_id}:{int(observation.source_time_us)}:P{ordinal:02d}"


def _spatially_distinct(left: Observation, right: Observation) -> bool:
    return v5.bbox_iou(left.bbox, right.bbox) < CANNOT_LINK_MAX_IOU


def annotate_person_instances(observations: list[Observation]) -> list[Observation]:
    """Attach V9 Person Instance safety metadata in-place and return observations."""

    by_sample: dict[tuple[str, int], list[Observation]] = defaultdict(list)
    for observation in observations:
        by_sample[(observation.shot_id, int(observation.source_time_us))].append(observation)

    for sample in by_sample.values():
        ordered = sorted(sample, key=lambda item: (item.bbox[0], item.bbox[1], -item.bbox[2] * item.bbox[3]))
        ids: dict[int, str] = {}
        for ordinal, observation in enumerate(ordered, start=1):
            ids[id(observation)] = _instance_id(observation, ordinal)

        for observation in ordered:
            others = [item.bbox for item in ordered if item is not observation]
            source = str(observation.detection_source or "")
            safety = classify_person_instance(
                person_bbox=observation.bbox,
                other_person_boxes=others,
                frame_width=observation.frame_width,
                frame_height=observation.frame_height,
                proposal_source=source,
                # Synthetic face fallback is not a detector-backed clean body crop.
                force_partial="face-fallback" in source.lower(),
            )
            observation.instance_id = ids[id(observation)]  # type: ignore[attr-defined]
            observation.person_bbox = safety.person_bbox  # type: ignore[attr-defined]
            observation.person_crop_bbox = safety.crop_bbox  # type: ignore[attr-defined]
            observation.instance_class = safety.instance_class  # type: ignore[attr-defined]
            observation.gallery_eligible = safety.gallery_eligible  # type: ignore[attr-defined]
            observation.crop_contamination_ratio = safety.contamination_ratio  # type: ignore[attr-defined]
            observation.max_other_overlap_ratio = safety.max_other_overlap_ratio  # type: ignore[attr-defined]
            observation.person_instance_reason = safety.reason  # type: ignore[attr-defined]
            observation.cannot_link_instance_ids = [  # type: ignore[attr-defined]
                ids[id(other)]
                for other in ordered
                if other is not observation and _spatially_distinct(observation, other)
            ]

    return observations


def detect_observations(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[Observation]:
    def report(current: int, total: int, message: str) -> None:
        if progress is None:
            return
        progress(
            current,
            total,
            message.replace("人物 V6.3", "人物 V9A · Person Instance Safety"),
        )

    observations = legacy.detect_observations(shots, progress=report if progress is not None else None)
    return annotate_person_instances(observations)
