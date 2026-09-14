# Replica Storyboard Localization

## Purpose

Turn the accepted source storyboard into the actual working target storyboard. This is the primary localization surface: not a separate Target Bible followed by a separate Target Script.

## Hard input

`CURRENT SOURCE_VIDEO_SNAPSHOT` only, plus project target language/region settings.

## Output language contract

- Visual/action/setting review prose: Simplified Chinese.
- Camera explanation: Simplified Chinese while preserving the original structured camera facts.
- Spoken dialogue: `target_language`.
- Every spoken line also carries `target_dialogue_zh` for Chinese human understanding.
- `target_dialogue_zh` is review metadata and must never be spoken by the video model unless target language itself is Chinese.

## Preservation

Shot order, shot anchor identity, source start/end/duration and structured camera language are frozen source facts. Localization may replace people, locations, culturally specific props and expression, but cannot silently restructure the episode.

## Identity

Provider may propose localized names/descriptions. Stable target entity IDs are generated and bound by the server from stable source identities; Provider must not invent IDs.

## Review

Generation produces a NEEDS_REVIEW candidate. Explicit ACCEPT publishes CURRENT TARGET_STORYBOARD v2.
