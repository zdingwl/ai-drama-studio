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

## Dialogue timing contract

Each canonical utterance carries its authoritative source start/end time, available seconds, and an optimistic target-language word/character budget. The localized spoken line must fit that window at no more than 4 whitespace-delimited words per second or 6 CJK characters per second. Text-only preflight allows a fixed 0.15-second ASR-boundary tolerance for very short one-syllable lines; this does not relax material overflow. When literal translation does not fit, rewrite it into shorter natural target-language speech while preserving the story information, tone, and relationship. A timing-invalid candidate fails closed here; H3 Prompt Skill must not repair or accelerate finalized dialogue later.

## Preservation

Shot order, shot anchor identity, source start/end/duration and structured camera language are frozen source facts. Localization may replace people, locations, culturally specific props and expression, but cannot silently restructure the episode.

## Plan the whole target world before localizing shots

Read every episode's frozen story, dialogue and shot context first. In the same task, produce one complete target-world design, continuity rules and full Character / Scene / Prop definitions before any shot batch. This is internal planning, not a separate Target Bible product prerequisite.

Redesign names, family relationships and forms of address, appearance and wardrobe, housing and room relationships, architecture and furnishings, props and cultural conventions for the configured target language and region. Source actor appearance, surnames and furniture are not target design defaults. Target language does not determine ethnicity; neither force a single ethnicity nor assume an immigrant setting because the source is Chinese. Preserve dramatic function, relationships, conflict, action logic and frozen timing.

Specify concrete target details instead of saying "retain the original" or "equivalent to the source amount". Names, aliases, family surnames, addresses, currency decisions and room layouts must be consistent across the complete plan, dialogue and every shot. Cultural equivalents must retain the conditions that make the original conflict possible.

Persist the validated complete plan before shot rewriting. Every shot batch receives that same plan, including entities appearing in other episodes. Batches write only shots and dialogue; the server supplies immutable planned entity definitions. Do not independently redesign identities in later batches or merge competing definitions by keeping the first one.

## Identity

Provider may propose localized names/descriptions. Stable target entity IDs are generated and bound by the server from stable source identities; Provider must not invent IDs.

The validated global plan freezes each complete Character, Scene and Prop definition before the first shot batch. Batches may not cross Episode boundaries or split a cross-shot utterance. Plan and validated batch semantics are checkpointed so resume does not repeat completed remote calls. Changed source/configuration/contracts cannot reuse the checkpoint.

## Review

Generation produces a NEEDS_REVIEW candidate. Explicit ACCEPT publishes CURRENT TARGET_STORYBOARD v2.

Storyboard revisions carry separate visual and dialogue projection fingerprints. Dialogue-only revisions may deterministically rebind already persisted asset media to the new storyboard lineage; they must still invalidate H3 prompts and generated video, but must not call the image runtime again.
