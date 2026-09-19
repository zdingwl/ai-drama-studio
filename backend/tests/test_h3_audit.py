from types import SimpleNamespace as NS

import pytest

from app.core.errors import AppError
from app.replica_pipeline.h3_audit import audit_segments, dialogue_owner_windows, estimated_speech_fits, require_valid_segments
from app.replica_pipeline.h3_prompting import _dialogue_refs
from app.shot_breakdown.schemas import DialogueDelivery


def segment(name='s1', episode='e1', text='Hello.', duration=3_000_000, speech_start=0, speech_end=None):
    speech_end = duration if speech_end is None else speech_end
    return NS(generation_segment_id=name, episode_id=episode, duration_us=duration,
              dialogue_refs=[NS(utterance_id='u1', final_target_dialogue=text, planned_speech_start_us=speech_start, planned_speech_end_us=speech_end)],
              target_asset_refs=[], reference_conditions=[])


def test_cross_shot_full_dialogue_repetition_is_blocked():
    with pytest.raises(AppError) as exc:
        require_valid_segments([segment(), segment('s2')])
    assert exc.value.code == 'H3_PREFLIGHT_FAILED'
    assert len(exc.value.details['issues']) == 2


def test_same_id_in_different_episodes_is_not_duplicate():
    assert not audit_segments([segment(), segment('s2', 'e2')])


def test_optimistic_speech_estimate_still_detects_obvious_overflow():
    issues = audit_segments([segment(text='Those flowers were just left out in the hallway!', duration=800_000)])
    assert issues[0]['code'] == 'DIALOGUE_TOO_LONG'


def test_speech_window_not_full_segment_is_used_for_overflow_audit():
    issues = audit_segments([segment(text='This is a long enough line.', duration=3_000_000, speech_start=2_600_000, speech_end=3_000_000)])
    assert issues[0]['code'] == 'DIALOGUE_TOO_LONG'


def test_one_syllable_line_allows_small_asr_boundary_tolerance():
    assert estimated_speech_fits('Jake!', 0.22)
    assert not estimated_speech_fits('Jake, come over here right now!', 0.22)


def test_missing_scene_or_prop_slot_is_reported():
    item = segment()
    item.target_asset_refs = [NS(target_entity_id='scene')]
    assert audit_segments([item])[0]['code'] == 'REFERENCE_INCOMPLETE'


def test_short_dialogue_and_silent_shot_pass():
    item = segment()
    require_valid_segments([item])
    item.dialogue_refs = []
    require_valid_segments([item])


def test_dialogue_overlapping_adjacent_shots_is_assigned_once():
    dialogue = NS(
        utterance_id='u-shared', utterance_number=1,
        delivery=DialogueDelivery.DIALOGUE,
        target_character_id='char-1', target_dialogue='Hello there.',
        target_dialogue_zh='你好。', overlap_start_us=900_000,
        overlap_end_us=1_200_000,
    )
    assigned: set[str] = set()
    first = _dialogue_refs(NS(dialogue=[dialogue]), 0, 1_000_000, assigned)
    second = _dialogue_refs(NS(dialogue=[dialogue]), 1_000_000, 2_000_000, assigned)
    assert [item.utterance_id for item in first] == ['u-shared']
    assert second == []


def test_cross_shot_dialogue_is_owned_by_the_largest_overlap() -> None:
    dialogue = NS(
        utterance_id='u-shared', utterance_number=1,
        delivery=DialogueDelivery.DIALOGUE,
        target_character_id='char-1', target_dialogue='Hello.',
        target_dialogue_zh='你好。', overlap_start_us=900_000,
        overlap_end_us=1_000_000,
    )
    owner = {'u-shared': 'shot-2'}
    first = _dialogue_refs(NS(storyboard_shot_id='shot-1', dialogue=[dialogue]), 0, 1_000_000, owner_shot_by_utterance=owner)
    dialogue.overlap_start_us = 1_000_000
    dialogue.overlap_end_us = 1_900_000
    second = _dialogue_refs(NS(storyboard_shot_id='shot-2', dialogue=[dialogue]), 1_000_000, 2_000_000, owner_shot_by_utterance=owner)

    assert first == []
    assert [item.utterance_id for item in second] == ['u-shared']


def test_shared_owner_rule_selects_largest_authoritative_overlap() -> None:
    owners = dialogue_owner_windows([
        {"episode_id": "episode", "shot_anchor_id": "shot-a", "dialogue": [{"utterance_id": "line", "overlap_start_us": 0, "overlap_end_us": 600_000}]},
        {"episode_id": "episode", "shot_anchor_id": "shot-b", "dialogue": [{"utterance_id": "line", "overlap_start_us": 600_000, "overlap_end_us": 1_300_000}]},
    ])
    assert owners[("episode", "line")] == ("shot-b", 600_000, 1_300_000)
