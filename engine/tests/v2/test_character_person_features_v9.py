from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from engine.app import character_gallery_v9 as gallery
from engine.app.character_person_features_v9 import (
    FEATURE_VERSION,
    extract_person_features,
    feature_channel_scores,
)


def observation(*, face: np.ndarray | None = None, reid: np.ndarray | None = None):
    return SimpleNamespace(
        instance_id="SHOT_1:1000000:P01",
        instance_class="CLEAN",
        gallery_eligible=True,
        frame_width=120,
        frame_height=200,
        bbox=(30, 20, 60, 160),
        person_bbox=(30, 20, 60, 160),
        detection_score=0.95,
        clarity_score=0.9,
        body_completeness=0.92,
        reid_embedding=reid,
        body_hist=np.asarray([0.8, 0.2, 0.1], dtype=np.float32),
        face_embedding=face,
        face_score=0.93 if face is not None else 0.0,
    )


def frame_with_clothes(*, upper: tuple[int, int, int], lower: tuple[int, int, int], outside: int = 0) -> np.ndarray:
    frame = np.full((200, 120, 3), outside, dtype=np.uint8)
    # Person bbox: x=30..90, y=20..180. Paint only inside that person instance.
    frame[20:180, 30:90] = (40, 40, 40)
    frame[46:113, 36:84] = upper
    frame[106:170, 37:83] = lower
    return frame


def test_whole_frame_background_cannot_change_person_identity_features() -> None:
    obs = observation(reid=np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    left = frame_with_clothes(upper=(0, 0, 255), lower=(255, 0, 0), outside=0)
    right = frame_with_clothes(upper=(0, 0, 255), lower=(255, 0, 0), outside=255)

    a = extract_person_features(left, obs)
    b = extract_person_features(right, obs)

    assert np.allclose(a.clothing_upper, b.clothing_upper, atol=1e-6)
    assert np.allclose(a.clothing_lower, b.clothing_lower, atol=1e-6)
    assert np.allclose(a.body_structure, b.body_structure, atol=1e-6)


def test_upper_and_lower_clothing_are_preserved_as_separate_channels() -> None:
    obs = observation(reid=np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    red_blue = extract_person_features(
        frame_with_clothes(upper=(0, 0, 255), lower=(255, 0, 0)),
        obs,
    )
    green_blue = extract_person_features(
        frame_with_clothes(upper=(0, 255, 0), lower=(255, 0, 0)),
        obs,
    )

    scores = feature_channel_scores(red_blue, green_blue)

    assert scores["clothing_lower"] is not None
    assert scores["clothing_upper"] is not None
    assert scores["clothing_lower"] > scores["clothing_upper"]


def test_face_is_optional_not_the_person_identity_definition() -> None:
    obs = observation(face=None, reid=np.asarray([0.2, 0.8, 0.1], dtype=np.float32))
    bundle = extract_person_features(
        frame_with_clothes(upper=(20, 80, 160), lower=(40, 120, 60)),
        obs,
    )

    assert bundle.face is None
    assert bundle.person_reid is not None
    assert bundle.clothing_upper is not None
    assert bundle.clothing_lower is not None
    assert bundle.body_structure is not None
    assert "face" not in bundle.available_channels


def test_similarity_contract_has_interpretable_channels_and_no_total_embedding() -> None:
    reid = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    face = np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
    obs = observation(face=face, reid=reid)
    a = extract_person_features(frame_with_clothes(upper=(0, 0, 255), lower=(255, 0, 0)), obs)
    b = extract_person_features(frame_with_clothes(upper=(0, 0, 255), lower=(255, 0, 0)), obs)

    scores = feature_channel_scores(a, b)

    assert set(scores) == {
        "person_reid",
        "clothing_upper",
        "clothing_lower",
        "body_hist",
        "body_structure",
        "face",
    }
    assert "total" not in scores
    assert "combined" not in scores
    assert scores["person_reid"] is not None and scores["person_reid"] > 0.99
    assert scores["face"] is not None and scores["face"] > 0.99


def test_gallery_feature_sidecar_keeps_channels_separate(tmp_path) -> None:
    obs = observation(
        face=np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
        reid=np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
    )
    bundle = extract_person_features(
        frame_with_clothes(upper=(0, 0, 255), lower=(255, 0, 0)),
        obs,
    )
    obs.person_feature_bundle = bundle

    feature_path, dimensions = gallery._save_feature_sidecar(tmp_path, 1, obs)

    assert feature_path is not None
    arrays = np.load(feature_path)
    assert set(arrays.files) == set(bundle.available_channels)
    assert dimensions["person_reid"] == 3
    assert dimensions["face"] == 3
    assert bundle.feature_version == FEATURE_VERSION
