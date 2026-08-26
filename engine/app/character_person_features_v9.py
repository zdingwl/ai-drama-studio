"""Character V9 Phase B multi-channel Person Image features.

Identity evidence is extracted from an isolated Person Instance crop, never from a
whole frame. The channels intentionally stay separate so Phase C can reason about
why two person images match instead of hiding every signal inside one opaque vector.

Channels:
- person_reid: existing YoutuReID embedding (primary body appearance signal);
- clothing_upper / clothing_lower: HSV/Lab colour + gradient texture descriptors;
- body_hist: historical lightweight HSV body histogram (supporting signal);
- body_structure: coarse gradient/body-shape descriptor;
- face: optional SFace embedding, a strong supporting channel but never the sole
  definition of a person.

No demographic attribute (including inferred gender) is generated here. Identity
uses observable visual appearance only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from engine.app import character_visual_v5 as v5

FEATURE_VERSION = "v9b-person-multichannel-1"


@dataclass(frozen=True)
class PersonFeatureBundle:
    feature_version: str
    instance_id: str | None
    instance_class: str
    gallery_eligible: bool
    quality: float
    person_reid: Any | None
    clothing_upper: Any | None
    clothing_lower: Any | None
    body_hist: Any | None
    body_structure: Any | None
    face: Any | None
    face_score: float

    @property
    def available_channels(self) -> tuple[str, ...]:
        values: list[str] = []
        for name in (
            "person_reid",
            "clothing_upper",
            "clothing_lower",
            "body_hist",
            "body_structure",
            "face",
        ):
            if getattr(self, name) is not None:
                values.append(name)
        return tuple(values)


def _normalize(value: Any | None) -> Any | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    if not array.size:
        return None
    norm = float(np.linalg.norm(array))
    return array / norm if norm > 1e-9 else None


def _normalized_or_zero(value: Any) -> Any:
    normalized = _normalize(value)
    if normalized is not None:
        return normalized
    return np.zeros(np.asarray(value).reshape(-1).shape[0], dtype=np.float32)


def _safe_region(frame: Any, box: tuple[int, int, int, int]) -> Any | None:
    height, width = frame.shape[:2]
    x, y, w, h = box
    left = max(0, min(width - 1, int(x)))
    top = max(0, min(height - 1, int(y)))
    right = max(left + 1, min(width, int(x + w)))
    bottom = max(top + 1, min(height, int(y + h)))
    crop = frame[top:bottom, left:right]
    return crop if crop.size else None


def _subregion(
    frame: Any,
    box: tuple[int, int, int, int],
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> Any | None:
    x, y, w, h = box
    region = (
        int(round(x + w * x0)),
        int(round(y + h * y0)),
        max(1, int(round(w * (x1 - x0)))),
        max(1, int(round(h * (y1 - y0)))),
    )
    return _safe_region(frame, region)


def _appearance_descriptor(region: Any | None) -> Any | None:
    """Colour + texture descriptor for one visible clothing/body region."""

    if region is None or region.size == 0 or min(region.shape[:2]) < 8:
        return None
    import cv2

    resized = cv2.resize(region, (64, 96), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    hs = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
    ab = cv2.calcHist([lab], [1, 2], None, [8, 8], [0, 256, 0, 256]).reshape(-1).astype(np.float32)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    orientation = np.mod(angle, 180.0)
    bins = np.floor(orientation / 15.0).astype(np.int32)
    texture = np.zeros(12, dtype=np.float32)
    for index in range(12):
        texture[index] = float(magnitude[bins == index].sum())

    descriptor = np.concatenate([
        _normalized_or_zero(hs),
        _normalized_or_zero(ab),
        _normalized_or_zero(texture),
    ])
    return _normalize(descriptor)


def _body_structure_descriptor(region: Any | None) -> Any | None:
    """Coarse visible-structure descriptor; deliberately low weight in Phase C."""

    if region is None or region.size == 0 or min(region.shape[:2]) < 12:
        return None
    import cv2

    gray = cv2.cvtColor(cv2.resize(region, (48, 96), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    orientation = np.mod(angle, 180.0)

    features: list[float] = []
    cell_h, cell_w = 24, 16
    for row in range(4):
        for col in range(3):
            mag = magnitude[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w]
            ang = orientation[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w]
            bins = np.floor(ang / 30.0).astype(np.int32)
            for index in range(6):
                features.append(float(mag[bins == index].sum()))
    return _normalize(np.asarray(features, dtype=np.float32))


def _person_quality(observation: Any) -> float:
    frame_area = max(1, int(observation.frame_width) * int(observation.frame_height))
    person_area = max(1, int(observation.bbox[2]) * int(observation.bbox[3]))
    size = min(1.0, (person_area / float(frame_area)) / 0.28)
    clarity = max(0.0, min(1.0, float(getattr(observation, "clarity_score", 0.0))))
    completeness = max(0.0, min(1.0, float(getattr(observation, "body_completeness", 0.0))))
    detection = max(0.0, min(1.0, float(observation.detection_score)))
    cleanliness = 1.0 if bool(getattr(observation, "gallery_eligible", False)) else 0.35
    value = size * 0.24 + clarity * 0.30 + completeness * 0.24 + detection * 0.14 + cleanliness * 0.08
    return max(0.0, min(1.0, value))


def extract_person_features(frame: Any, observation: Any) -> PersonFeatureBundle:
    """Extract features from one Person Instance only; the whole frame is never encoded."""

    person_box = tuple(int(value) for value in getattr(observation, "person_bbox", observation.bbox))
    person_crop = _safe_region(frame, person_box)
    # Torso/lower-body regions are deliberately inset to reduce background leakage.
    upper = _subregion(frame, person_box, x0=0.10, y0=0.16, x1=0.90, y1=0.58)
    lower = _subregion(frame, person_box, x0=0.12, y0=0.54, x1=0.88, y1=0.94)

    return PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=getattr(observation, "instance_id", None),
        instance_class=str(getattr(observation, "instance_class", "UNKNOWN")),
        gallery_eligible=bool(getattr(observation, "gallery_eligible", False)),
        quality=_person_quality(observation),
        person_reid=_normalize(getattr(observation, "reid_embedding", None)),
        clothing_upper=_appearance_descriptor(upper),
        clothing_lower=_appearance_descriptor(lower),
        body_hist=_normalize(getattr(observation, "body_hist", None)),
        body_structure=_body_structure_descriptor(person_crop),
        face=_normalize(getattr(observation, "face_embedding", None)),
        face_score=max(0.0, min(1.0, float(getattr(observation, "face_score", 0.0)))),
    )


def attach_person_features(observation: Any, bundle: PersonFeatureBundle) -> Any:
    """Attach separate Phase B channels without changing the historical dataclass schema."""

    observation.person_feature_bundle = bundle
    observation.person_feature_version = bundle.feature_version
    observation.person_feature_quality = bundle.quality
    observation.person_reid_feature = bundle.person_reid
    observation.clothing_upper_feature = bundle.clothing_upper
    observation.clothing_lower_feature = bundle.clothing_lower
    observation.body_hist_feature = bundle.body_hist
    observation.body_structure_feature = bundle.body_structure
    observation.face_identity_feature = bundle.face
    observation.person_feature_channels = list(bundle.available_channels)
    return observation


def feature_channel_scores(left: PersonFeatureBundle, right: PersonFeatureBundle) -> dict[str, float | None]:
    """Return interpretable per-channel similarity. There is intentionally no total score here."""

    return {
        "person_reid": v5.cosine(left.person_reid, right.person_reid),
        "clothing_upper": v5.cosine(left.clothing_upper, right.clothing_upper),
        "clothing_lower": v5.cosine(left.clothing_lower, right.clothing_lower),
        "body_hist": v5.cosine(left.body_hist, right.body_hist),
        "body_structure": v5.cosine(left.body_structure, right.body_structure),
        "face": v5.cosine(left.face, right.face),
    }


def feature_dimensions(bundle: PersonFeatureBundle) -> dict[str, int]:
    result: dict[str, int] = {}
    for channel in bundle.available_channels:
        value = getattr(bundle, channel)
        result[channel] = int(np.asarray(value).reshape(-1).shape[0])
    return result
