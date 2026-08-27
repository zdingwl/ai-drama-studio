from __future__ import annotations

import numpy as np

from engine.app import character_tracking_v10 as tracking
from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import attach_v10_policy
from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle


def make_observation() -> v5.Observation:
    vector = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    observation = v5.Observation(
        shot_id="SHOT_0001",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=1,
        source_time_us=1_000_000,
        local_time_us=100_000,
        bbox=(100, 50, 220, 760),
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=None,
        reid_embedding=vector,
        body_hist=vector,
        face_visible=False,
        detection_source="v10-test",
        frame_width=1000,
        frame_height=1000,
        face_score=0.0,
        clarity_score=0.9,
        body_completeness=0.9,
        interference_ratio=0.0,
        other_person_boxes=[],
    )
    observation.instance_id = "SHOT_0001:1000000:P01"
    observation.instance_class = "CLEAN"
    observation.gallery_eligible = True
    observation.person_bbox = observation.bbox
    observation.person_crop_bbox = observation.bbox
    observation.cannot_link_instance_ids = []
    observation.person_feature_quality = 0.92
    observation.person_feature_bundle = PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=observation.instance_id,
        instance_class="CLEAN",
        gallery_eligible=True,
        quality=0.92,
        person_reid=vector,
        clothing_upper=vector,
        clothing_lower=vector,
        body_hist=vector,
        body_structure=vector,
        face=None,
        face_score=0.0,
    )
    attach_v10_policy(observation)
    return observation


def test_valid_person_evidence_survives_when_mot_drops_it(monkeypatch) -> None:
    observation = make_observation()
    monkeypatch.setattr(tracking.legacy, "build_tracks", lambda observations: [])

    tracks = tracking.build_tracks([observation])

    assert len(tracks) == 1
    assert tracks[0].observations == [observation]
    assert tracks[0].representatives
    assert tracks[0].representatives[0].observation is observation
