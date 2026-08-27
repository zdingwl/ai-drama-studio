"""Character V10 tracking adapter.

MOT remains the validated V6 implementation. V10 changes two things:
- track representatives are model-usable Person Evidence, not CLEAN-only crops;
- valid Person Evidence dropped by mature-MOT is preserved as an evidence-only
  singleton Track so short side/back/occluded appearances can still be classified.

Singleton evidence cannot create a new identity unless its observation separately
passes the V10 seed policy and later gets multi-shot support.
"""
from __future__ import annotations

from engine.app import character_gallery_v10 as gallery
from engine.app import character_tracking_v6 as legacy
from engine.app import character_visual_v5 as v5
from engine.app.character_person_evidence_v10 import observation_policy

Observation = v5.Observation
TrackDraft = v5.TrackDraft
tracker_runtime_status = legacy.tracker_runtime_status


def _singleton_track(observation: Observation) -> TrackDraft:
    track = TrackDraft(
        shot_id=observation.shot_id,
        episode_id=observation.episode_id,
        episode_order=observation.episode_order,
        shot_ordinal=observation.shot_ordinal,
        observations=[observation],
    )
    v5._refresh_track(track)
    track.representatives = gallery.select_track_representatives(track)
    return track


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    tracks = legacy.build_tracks(observations)
    covered_ids = {
        id(observation)
        for track in tracks
        for observation in track.observations
    }

    # Capture-first contract: a valid detected Person Instance must reach identity
    # classification even when MOT cannot build a mature trajectory for it.
    for observation in observations:
        if id(observation) in covered_ids:
            continue
        policy = observation_policy(observation)
        if not policy.evidence_eligible:
            continue
        tracks.append(_singleton_track(observation))

    tracks.sort(key=lambda item: (
        item.episode_order,
        item.shot_ordinal,
        item.start_us if item.start_us is not None else -1,
    ))
    for track in tracks:
        track.representatives = gallery.select_track_representatives(track)
    return tracks
