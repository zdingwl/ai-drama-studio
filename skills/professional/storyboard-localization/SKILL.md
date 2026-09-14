# Replica Storyboard Localization

## Purpose

Turn the accepted source storyboard into the actual working target storyboard. This is the primary localization surface: not a separate Target Bible followed by a separate Target Script.

## Hard input

`CURRENT SOURCE_VIDEO_SNAPSHOT` only, plus project target language/region settings.

## Runtime provider

The current Step 2 runtime uses Volcengine Ark / Doubao directly. It does **not** inherit the project's Step 1 `source_understanding_provider`; a project may use local Qwen for source understanding while storyboard localization still executes through Volcengine Ark. The current default model is `doubao-seed-2-1-pro-260628`, using the configured Ark endpoint and credentials.

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
