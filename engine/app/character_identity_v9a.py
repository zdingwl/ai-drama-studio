"""Character V9 Phase A identity adapter.

Identity decisions intentionally remain V8 during Phase A. This adapter exists to
make the Person Instance safety contract end-to-end: V8 may rebuild sub-tracks
internally with its historical representative selector, so after identity returns
we recompute every track/candidate gallery from V9 CLEAN Person Instances only.
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
        if selected and not any(v5._representative_diverse(item, existing) for existing in selected):
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
