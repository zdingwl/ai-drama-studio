"""Character V9 Phase A/B identity adapter.

Identity decisions intentionally remain V8 until Phase C. This adapter exists to
make the V9 Person Instance + Person Image contracts end-to-end: V8 may rebuild
sub-tracks internally with historical selectors, so after identity returns we
recompute every track/candidate gallery from V9 CLEAN Person Instances and V9B
multi-channel diversity.
"""
from __future__ import annotations

from engine.app import character_gallery_v9 as gallery
from engine.app import character_identity_v8 as legacy
from engine.app import character_visual_v5 as v5

TrackDraft = v5.TrackDraft
CandidateDraft = v5.CandidateDraft


def _rebuild_candidate_gallery(candidate: CandidateDraft) -> None:
    for track in candidate.tracks:
        track.representatives = gallery.select_track_representatives(track)

    pool = [
        representative
        for track in candidate.tracks
        for representative in track.representatives
        if representative.clean
    ]
    pool.sort(key=lambda item: item.quality_score, reverse=True)
    selected: list[v5.TrackRepresentative] = []
    for item in pool:
        if selected and not any(gallery.representatives_diverse(item, existing) for existing in selected):
            continue
        selected.append(item)
        if len(selected) >= v5.CHARACTER_GALLERY_LIMIT:
            break
    candidate.gallery = selected


def resolve_global_identities(tracks: list[TrackDraft]) -> list[CandidateDraft]:
    candidates = legacy.resolve_global_identities(tracks)
    for candidate in candidates:
        _rebuild_candidate_gallery(candidate)
    return candidates
