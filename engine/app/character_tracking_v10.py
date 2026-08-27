"""Character V10 tracking adapter.

MOT remains the validated V6 implementation.  V10 only changes representative
selection: track representatives are model-usable Person Evidence, not CLEAN-only
front-facing crops.
"""
from __future__ import annotations

from engine.app import character_gallery_v10 as gallery
from engine.app import character_tracking_v6 as legacy
from engine.app import character_visual_v5 as v5

Observation = v5.Observation
TrackDraft = v5.TrackDraft
tracker_runtime_status = legacy.tracker_runtime_status


def build_tracks(observations: list[Observation]) -> list[TrackDraft]:
    tracks = legacy.build_tracks(observations)
    for track in tracks:
        track.representatives = gallery.select_track_representatives(track)
    return tracks
