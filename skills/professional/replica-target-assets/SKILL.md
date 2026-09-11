# Replica Target Assets Skill

## Purpose

Convert the CURRENT `TARGET_BIBLE` into formal Character / Scene / Prop visual assets that later Target Storyboard and Video Generation can reference by stable ID.

The invariant is:

```text
TARGET_BIBLE = semantic truth
TARGET_ASSETS = visual realization
```

This skill must improve visual specificity and cross-shot continuity without changing the Target Bible's narrative identity or function.

## Hard input

The only Artifact hard input is:

```text
CURRENT TARGET_BIBLE
```

Do not directly consume `SOURCE_VIDEO_SNAPSHOT`, `TARGET_SCRIPT`, or earlier Source artifacts. P12 PASS / `TARGET_SCRIPT = AVAILABLE` is a stage-admission fact, not a P13 Artifact input.

## Identity rules

- Reuse P11 `target_character_id`, `target_scene_id`, and `target_prop_id` exactly.
- The server deterministically creates one stable `target_asset_id` for each Target entity.
- The Provider never creates or edits Target entity IDs, Target Asset IDs, database IDs, Artifact IDs, revisions, or CURRENT/STALE state.
- First build is exact 1:1 coverage of every Target Bible Character / Scene / Prop.
- Targeted regeneration may replace selected stable assets only when a CURRENT `TARGET_ASSETS` set is based on the same CURRENT Target Bible.

## Visual specification

Character assets should lock reusable face, hair, silhouette, wardrobe baseline, signature features, palette/material cues, continuity constraints, generation guidance, and negative constraints.

Scene assets should lock spatial identity, layout, architecture/interior style, material palette, fixed landmarks, lighting/time-of-day baseline, continuity constraints, generation guidance, and negative constraints.

Prop assets should lock visual form, material, color, scale, functional identity, signature details, continuity constraints, generation guidance, and negative constraints.

The Provider may make these fields more visually concrete but may not change the locked semantic fields copied by the server from Target Bible.

## Reference media

Every formal Target Asset requires at least one persisted `REFERENCE_SHEET` image. A sheet can contain multiple useful views, but it is not a storyboard and must not contain shot timing or generation-segment semantics.

The server must validate image bytes before a candidate can exist: media format, decode, dimensions, byte size, immutable relative path, and sha256. Provider temporary URLs or placeholders are not formal assets.

If the image Provider is not configured, fail closed with a safe configuration error. Never synthesize a fake image or publish a text-only formal asset.

## Provider boundary

The Visual Spec Provider receives only typed Target Bible content plus the exact server-generated scope manifest. It must return the exact requested Target entity IDs.

The Image Provider receives a server-composed reference-sheet prompt and returns image bytes. Each external call must have a committed `ProviderJob` before the remote request.

Any missing spec, identity mismatch, provider failure, undecodable image, media validation failure, or storage failure fails the whole generation task. Successful ProviderJobs remain for audit, but no `READY_FOR_REVIEW` candidate or CURRENT Artifact may be fabricated.

## Candidate and approval

Generation produces a complete typed candidate only after strict validation:

```text
Generate -> validate specs -> generate/validate media -> READY_FOR_REVIEW
```

A candidate is not an `ArtifactNode` and cannot be consumed by downstream stages.

Only an explicit user approval command may publish:

```text
READY_FOR_REVIEW -> APPROVE -> CURRENT TARGET_ASSETS
```

Approval must re-check that the same Target Bible is still CURRENT and that every persisted reference file still matches its recorded hash, size and dimensions. Publication is one database transaction: old CURRENT/downstream STALE, new Artifact + typed revision + Graph edge + SUPERSEDES edge + candidate PUBLISHED + plan invalidation.

## Revisions and stale

- Parent `TARGET_ASSETS` Artifact revision increments for every approved complete set.
- Stable `target_asset_id` does not change across regeneration.
- A regenerated entity increments its `asset_revision`; carried-forward entities keep their previous entity-level revision.
- A new Target Bible revision makes existing Target Assets and all future downstream artifacts STALE through Artifact Graph lineage.
- A candidate whose Target Bible is no longer CURRENT cannot be approved.

## Graph

P13 creates only the direct hard-input edge:

```text
TARGET_BIBLE --DERIVED_FROM--> TARGET_ASSETS
```

A newer approved set also creates:

```text
new TARGET_ASSETS --SUPERSEDES--> old TARGET_ASSETS
```

Do not add direct P13 input edges from Source Snapshot or Target Script.

## Read and command behavior

GET endpoints are strictly read-only. They may return the formal result, revision history, latest review candidate, reference media, and stale/review reasons, but they must never create a Task, call a Provider, generate media, retry, approve, or write an Artifact.

Generation and approval are explicit idempotent commands.

## Stage boundary

P13 must not create or implement Voice, TTS, actual speech duration, Timing, Target Storyboard, Generation Segments, Video Generation, QC/Selection, Lip Sync, Post Production, or Final Output.

Engineering success does not equal stage PASS. Until real Provider validation, real-project manual acceptance, and an explicit user message `P13 PASS`, `TARGET_ASSETS` remains `PLANNED`.
