"""Character V10 observation entry: capture first, classify second.

Reuses V9 detector/person split/multi-channel feature extraction, then attaches a
separate evidence/seed policy.  CLEAN no longer means "the only images identity can
see".  Side/back/multi-person-frame crops remain available to the classifier when
Person ReID features are present.
"""
from __future__ import annotations

from typing import Any

from engine.app.character_observation_v9 import (
    annotate_person_instances,
    attach_multichannel_features,
    detect_observations as detect_observations_v9,
    sample_times_us,
)
from engine.app.character_person_evidence_v10 import attach_v10_policy
from engine.app.character_visual_v5 import CharacterProgress, Observation


def attach_person_evidence_policy(observations: list[Observation]) -> list[Observation]:
    for observation in observations:
        attach_v10_policy(observation)
    return observations


def detect_observations(
    shots: list[dict[str, Any]],
    progress: CharacterProgress | None = None,
) -> list[Observation]:
    observations = detect_observations_v9(shots, progress=progress)
    return attach_person_evidence_policy(observations)


__all__ = [
    "Observation",
    "CharacterProgress",
    "annotate_person_instances",
    "attach_multichannel_features",
    "attach_person_evidence_policy",
    "detect_observations",
    "sample_times_us",
]
