"""Conservative automatic speaker resolution for source dialogue.

This module is intentionally pure and product-facing: raw ASR/VLM uncertainty stays
internal unless source facts still cannot identify one source character after safe,
deterministic context checks.  It never invents a new person and never changes source
text/timing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence


SpeakerResolutionStatus = Literal["RESOLVED", "AMBIGUOUS"]


@dataclass(frozen=True)
class SourceSpeakerResolutionV1:
    speaker_keys: tuple[str, ...]
    status: SpeakerResolutionStatus
    method: str
    reason: str | None = None


def _dedupe(values: Sequence[Any]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _character_id(person: Mapping[str, Any] | None) -> str | None:
    if not isinstance(person, Mapping):
        return None
    character = person.get("character")
    if not isinstance(character, Mapping):
        return None
    value = str(character.get("id") or "").strip()
    return value or None


def _performance_people(performance: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for item in performance:
        if not isinstance(item, Mapping):
            continue
        values.extend(str(value) for value in (item.get("people") or []))
    return _dedupe(values)


def _direct_resolution(
    dialogue: Mapping[str, Any],
    *,
    people_by_key: Mapping[str, Mapping[str, Any]],
    scene_people: tuple[str, ...],
    shot_people: tuple[str, ...],
    performance_people: tuple[str, ...],
) -> SourceSpeakerResolutionV1:
    explicit = tuple(key for key in _dedupe(dialogue.get("speakers") or []) if key in people_by_key)

    if len(explicit) == 1:
        return SourceSpeakerResolutionV1(explicit, "RESOLVED", "explicit-single")

    if len(explicit) > 1:
        character_ids = {
            character_id
            for key in explicit
            if (character_id := _character_id(people_by_key.get(key))) is not None
        }
        if len(character_ids) == 1 and all(_character_id(people_by_key.get(key)) for key in explicit):
            return SourceSpeakerResolutionV1(
                (explicit[0],),
                "RESOLVED",
                "same-final-character",
                "多个 Scene-local 人物引用已归属同一 Final Character",
            )

        performance_candidates = tuple(key for key in performance_people if key in explicit)
        if len(performance_candidates) == 1:
            return SourceSpeakerResolutionV1(
                performance_candidates,
                "RESOLVED",
                "performance-disambiguation",
                "镜头表演信息只指向一个候选说话人",
            )

        if len(scene_people) == 1 and scene_people[0] in explicit:
            return SourceSpeakerResolutionV1(
                (scene_people[0],),
                "RESOLVED",
                "sole-scene-person",
                "当前 Scene 只有一个人物",
            )

        return SourceSpeakerResolutionV1(
            explicit,
            "AMBIGUOUS",
            "explicit-multiple",
            "同一条对白仍关联多个不同人物",
        )

    # No explicit speaker. Prefer contextual facts that identify exactly one known person.
    performance_candidates = tuple(key for key in performance_people if key in people_by_key)
    if len(performance_candidates) == 1:
        return SourceSpeakerResolutionV1(
            performance_candidates,
            "RESOLVED",
            "performance-single",
            "镜头表演信息只指向一个人物",
        )

    if len(scene_people) == 1 and len(shot_people) == 1 and scene_people[0] == shot_people[0]:
        return SourceSpeakerResolutionV1(
            (scene_people[0],),
            "RESOLVED",
            "sole-scene-visible-person",
            "当前 Scene 与 Shot 都只有同一个人物",
        )

    return SourceSpeakerResolutionV1(
        (),
        "AMBIGUOUS",
        "missing-speaker",
        "对白已识别，但现有源事实还不能安全确定唯一说话人",
    )


def _time_value(dialogue: Mapping[str, Any], key: str) -> int:
    try:
        return int(dialogue.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def resolve_shot_dialogue_speakers_v1(
    dialogues: Sequence[Mapping[str, Any]],
    *,
    scene_people: Sequence[Mapping[str, Any]],
    shot_people: Sequence[Any],
    performance: Sequence[Mapping[str, Any]],
) -> list[SourceSpeakerResolutionV1]:
    """Resolve all dialogue speakers in one Shot without model calls.

    The resolver only uses already accepted source facts: explicit speaker refs, Final
    Character identity, Shot/Scene people, performance references and short-range dialogue
    continuity. Ambiguous multi-speaker evidence is preserved instead of guessed.
    """

    people_by_key = {
        str(person.get("person_key")): person
        for person in scene_people
        if isinstance(person, Mapping) and person.get("person_key")
    }
    scene_keys = _dedupe(tuple(people_by_key))
    shot_keys = tuple(key for key in _dedupe(shot_people) if key in people_by_key)
    performance_keys = _performance_people(performance)

    resolutions = [
        _direct_resolution(
            dialogue,
            people_by_key=people_by_key,
            scene_people=scene_keys,
            shot_people=shot_keys,
            performance_people=performance_keys,
        )
        for dialogue in dialogues
    ]

    # A missing speaker between two nearby lines spoken by the same resolved person can be
    # recovered safely. Do not use continuity to override explicit multi-speaker evidence.
    for index, resolution in enumerate(tuple(resolutions)):
        if resolution.status == "RESOLVED" or resolution.speaker_keys:
            continue

        previous_index = next(
            (cursor for cursor in range(index - 1, -1, -1) if resolutions[cursor].status == "RESOLVED"),
            None,
        )
        next_index = next(
            (cursor for cursor in range(index + 1, len(resolutions)) if resolutions[cursor].status == "RESOLVED"),
            None,
        )
        if previous_index is None or next_index is None:
            continue

        previous = resolutions[previous_index]
        following = resolutions[next_index]
        if len(previous.speaker_keys) != 1 or previous.speaker_keys != following.speaker_keys:
            continue

        current_dialogue = dialogues[index]
        previous_dialogue = dialogues[previous_index]
        following_dialogue = dialogues[next_index]
        previous_gap = max(0, _time_value(current_dialogue, "start_us") - _time_value(previous_dialogue, "end_us"))
        next_gap = max(0, _time_value(following_dialogue, "start_us") - _time_value(current_dialogue, "end_us"))
        if previous_gap > 3_000_000 or next_gap > 3_000_000:
            continue

        resolutions[index] = SourceSpeakerResolutionV1(
            previous.speaker_keys,
            "RESOLVED",
            "dialogue-continuity",
            "前后相邻对白均由同一人物说出",
        )

    return resolutions


__all__ = [
    "SourceSpeakerResolutionV1",
    "resolve_shot_dialogue_speakers_v1",
]
