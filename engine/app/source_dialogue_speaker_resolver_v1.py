"""Automatic speaker resolution for source dialogue.

Resolution priority after the 2026-09-07 architecture change:
1. a current explicit human SourceDialogueSpeakerOverride;
2. a current materialized D-ORCA audio-visual attribution;
3. existing explicit source SPEAKER evidence;
4. deterministic scene/performance/dialogue-continuity fallback.

No model is ever invoked here. D-ORCA inference is an explicit POST/task elsewhere; this
resolver only reads a versioned artifact. Canonical source text/timing are never changed.
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


def _episode_and_revision(dialogues: Sequence[Mapping[str, Any]]) -> tuple[str | None, str | None]:
    for dialogue in dialogues:
        key = str(dialogue.get("dialogue_key") or "").strip()
        parts = key.split(":")
        if len(parts) >= 3 and parts[0] and parts[1]:
            return parts[0], parts[1]
    return None, None


def _manual_override_keys(dialogues: Sequence[Mapping[str, Any]]) -> set[str]:
    """Identify current human decisions so model evidence can never overwrite them."""

    episode_id, _revision = _episode_and_revision(dialogues)
    if not episode_id:
        return set()
    try:
        from engine.app.source_dialogue_speaker_override_v1 import (
            load_episode_source_dialogue_speaker_overrides_v1,
            source_dialogue_signature_v1,
        )
        overrides = load_episode_source_dialogue_speaker_overrides_v1(episode_id)
    except Exception:
        # The resolver is also used by pure unit tests / migration tools where a DB may not
        # exist. Missing optional human-overlay storage must not disable normal resolution.
        return set()
    return {
        str(dialogue.get("dialogue_key"))
        for dialogue in dialogues
        if (
            isinstance(overrides.get(str(dialogue.get("dialogue_key") or "")), Mapping)
            and str(overrides[str(dialogue.get("dialogue_key"))].get("dialogue_signature") or "")
            == source_dialogue_signature_v1(dialogue)
        )
    }


def _load_current_dorca_attributions(
    dialogues: Sequence[Mapping[str, Any]],
) -> Mapping[str, Mapping[str, Any]]:
    episode_id, revision_id = _episode_and_revision(dialogues)
    if not episode_id or not revision_id:
        return {}
    try:
        from engine.app.source_dialogue_attribution_v1 import load_current_dorca_attribution_index_v1
        return load_current_dorca_attribution_index_v1(
            episode_id,
            source_shot_revision_id=revision_id,
        )
    except Exception:
        # Artifact absence/corruption is not a content blocker. Existing deterministic
        # resolution remains the safe fallback; runtime failures are surfaced by the
        # explicit D-ORCA command itself.
        return {}


def _dorca_resolution(
    dialogue: Mapping[str, Any],
    *,
    attribution: Mapping[str, Any] | None,
    people_by_key: Mapping[str, Mapping[str, Any]],
) -> SourceSpeakerResolutionV1 | None:
    if not isinstance(attribution, Mapping):
        return None
    speaker_ref = str(attribution.get("speaker_ref") or "").strip()
    if not speaker_ref:
        return None
    candidates = [
        key
        for key, person in people_by_key.items()
        if str(person.get("scene_person_ref") or "").strip() == speaker_ref
    ]
    if len(candidates) != 1:
        return None
    return SourceSpeakerResolutionV1(
        (candidates[0],),
        "RESOLVED",
        "dorca-audiovisual",
        "D-ORCA 音视频联合判断当前对白说话人",
    )


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
        "对白已识别，但当前证据不能唯一确定说话人；流程可继续并保留自动纠错空间",
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
    dialogue_attributions: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[SourceSpeakerResolutionV1]:
    """Resolve all dialogue speakers without invoking a model.

    ``dialogue_attributions`` is injectable for tests/migrations. When omitted, the current
    materialized D-ORCA artifact is read by Episode/ShotRevision anchors derived from the
    dialogue keys. Missing/stale attribution simply falls through to existing rules.
    """

    people_by_key = {
        str(person.get("person_key")): person
        for person in scene_people
        if isinstance(person, Mapping) and person.get("person_key")
    }
    scene_keys = _dedupe(tuple(people_by_key))
    shot_keys = tuple(key for key in _dedupe(shot_people) if key in people_by_key)
    performance_keys = _performance_people(performance)
    attributions = dialogue_attributions if dialogue_attributions is not None else _load_current_dorca_attributions(dialogues)
    manual_keys = _manual_override_keys(dialogues) if dialogue_attributions is None else set()

    resolutions: list[SourceSpeakerResolutionV1] = []
    for dialogue in dialogues:
        dialogue_key = str(dialogue.get("dialogue_key") or "")
        explicit = tuple(key for key in _dedupe(dialogue.get("speakers") or []) if key in people_by_key)
        if dialogue_key in manual_keys and len(explicit) == 1:
            resolutions.append(SourceSpeakerResolutionV1(
                explicit,
                "RESOLVED",
                "manual-override",
                "用户已保存当前版本的正式说话人修正",
            ))
            continue

        group_id = str(dialogue.get("dialogue_group_id") or "")
        dorca = _dorca_resolution(
            dialogue,
            attribution=attributions.get(group_id),
            people_by_key=people_by_key,
        )
        if dorca is not None:
            resolutions.append(dorca)
            continue

        resolutions.append(_direct_resolution(
            dialogue,
            people_by_key=people_by_key,
            scene_people=scene_keys,
            shot_people=shot_keys,
            performance_people=performance_keys,
        ))

    # A missing speaker between two nearby lines spoken by the same resolved person can be
    # recovered as a last fallback. Never override D-ORCA, manual or explicit decisions.
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
