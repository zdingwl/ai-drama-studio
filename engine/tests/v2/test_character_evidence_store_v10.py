from __future__ import annotations

import json

import numpy as np

from engine.app import character_evidence_store_v10 as store
from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import attach_v10_policy
from engine.app.character_person_features_v9 import FEATURE_VERSION, PersonFeatureBundle


def make_observation(*, shot: int, instance_class: str) -> v5.Observation:
    vector = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    observation = v5.Observation(
        shot_id=f"SHOT_{shot:04d}",
        episode_id="EP_1",
        episode_order=1,
        shot_ordinal=shot,
        source_time_us=shot * 1_000_000,
        local_time_us=100_000,
        bbox=(100, 80, 220, 720),
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.95,
        face_embedding=None,
        reid_embedding=vector,
        body_hist=vector,
        face_visible=False,
        detection_source="v10-test",
        frame_width=640,
        frame_height=960,
        face_score=0.0,
        clarity_score=0.9,
        body_completeness=0.85,
        interference_ratio=0.0,
        other_person_boxes=[],
    )
    observation.instance_id = f"{observation.shot_id}:{observation.source_time_us}:P01"
    observation.instance_class = instance_class
    observation.gallery_eligible = instance_class == "CLEAN"
    observation.person_bbox = observation.bbox
    observation.person_crop_bbox = observation.bbox
    observation.cannot_link_instance_ids = []
    observation.person_feature_quality = 0.78
    observation.person_feature_bundle = PersonFeatureBundle(
        feature_version=FEATURE_VERSION,
        instance_id=observation.instance_id,
        instance_class=instance_class,
        gallery_eligible=instance_class == "CLEAN",
        quality=0.78,
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


def track(observation: v5.Observation) -> v5.TrackDraft:
    value = v5.TrackDraft(
        shot_id=observation.shot_id,
        episode_id=observation.episode_id,
        episode_order=observation.episode_order,
        shot_ordinal=observation.shot_ordinal,
        observations=[observation],
    )
    v5._refresh_track(value)
    return value


def test_side_back_style_nonclean_person_evidence_is_persisted_before_classification(monkeypatch, tmp_path) -> None:
    # Class names represent crop safety, not view direction. The important contract is
    # that non-CLEAN model-usable Person Images are not discarded before classification.
    observations = [
        make_observation(shot=1, instance_class="OCCLUDED"),
        make_observation(shot=2, instance_class="CONTAMINATED"),
        make_observation(shot=3, instance_class="PARTIAL"),
    ]
    frame = np.zeros((960, 640, 3), dtype=np.uint8)
    monkeypatch.setattr(store.v5, "_read_frame", lambda *_args, **_kwargs: frame.copy())
    monkeypatch.setattr(store, "workspace_root", lambda: tmp_path)

    result = store.save_person_evidence("RUN_V10", observations)

    assert result["evidence_count"] == 3
    manifest_path = tmp_path / "analysis" / "RUN_V10" / "person_evidence" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["evidence_count"] == 3
    assert {item["instance_class"] for item in manifest["records"]} == {"OCCLUDED", "CONTAMINATED", "PARTIAL"}
    assert all(item["classification_status"] == "UNCLASSIFIED" for item in manifest["records"])
    assert all(item["image_path"].endswith(".jpg") for item in manifest["records"])
    assert all(item["feature_path"].endswith(".npz") for item in manifest["records"])


def test_saved_person_evidence_receives_model_identity_assignment_after_classification(monkeypatch, tmp_path) -> None:
    observations = [
        make_observation(shot=1, instance_class="CLEAN"),
        make_observation(shot=2, instance_class="OCCLUDED"),
        make_observation(shot=3, instance_class="CONTAMINATED"),
    ]
    frame = np.zeros((960, 640, 3), dtype=np.uint8)
    monkeypatch.setattr(store.v5, "_read_frame", lambda *_args, **_kwargs: frame.copy())
    monkeypatch.setattr(store, "workspace_root", lambda: tmp_path)
    store.save_person_evidence("RUN_V10", observations)

    resolved = v5.CandidateDraft(id="C_RESOLVED", identity_status="RESOLVED")
    resolved.tracks = [track(observations[0]), track(observations[1])]
    unresolved = v5.CandidateDraft(id="C_UNRESOLVED", identity_status="UNRESOLVED")
    unresolved.tracks = [track(observations[2])]

    counts = store.update_person_evidence_classification("RUN_V10", [resolved, unresolved])

    assert counts == {"classified_count": 3, "resolved_count": 2, "unresolved_count": 1}
    manifest_path = tmp_path / "analysis" / "RUN_V10" / "person_evidence" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_instance = {item["instance_id"]: item for item in manifest["records"]}
    assert by_instance[observations[0].instance_id]["classification_status"] == "RESOLVED"
    assert by_instance[observations[0].instance_id]["identity_ordinal"] == 1
    assert by_instance[observations[1].instance_id]["candidate_id"] == "C_RESOLVED"
    assert by_instance[observations[2].instance_id]["classification_status"] == "UNRESOLVED"
    assert by_instance[observations[2].instance_id]["identity_ordinal"] is None
