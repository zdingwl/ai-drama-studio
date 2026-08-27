# Session Handoff — Character V10.1 Fragmented Shot Presence

> Date: 2026-08-27 13:40 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Scope: Character identity remains correct; improve ShotCharacterBinding recall without weakening new-identity rules.

## User-visible regression

Real-video screenshots showed the Final Character Gallery correctly separated:

```text
人物 001 = elderly woman
人物 002 = young woman
人物 003 = young man
```

but Shot bindings still missed visible known Characters:

```text
SHOT 0001: none                              expected none
SHOT 0002: young woman visible               missing 人物002
SHOT 0003: elderly woman                     correct 人物001
SHOT 0004: elderly + young woman             only 人物001, missing 人物002
SHOT 0005: elderly woman                     correct 人物001
SHOT 0006: elderly woman close-up            missing 人物001
SHOT 0007: young woman partial/body view     missing 人物002
SHOT 0008: hand-only                         none is reasonable
SHOT 0009: elderly + young woman likely      only 人物001, verify 人物002
```

This confirms global identity cardinality/classification can be correct while Shot-presence recall is still insufficient.

## Root cause

`character_identity_v101` can conservatively leave individual observations unresolved. MOT/classification may therefore produce several short unresolved Track fragments inside one Shot.

Existing `recover_unresolved_tracks()` is intentionally strict and requires one Track itself to contain enough repeated evidence. A group of 1–2 observation fragments cannot satisfy that pass individually.

Do not solve this by weakening the global identity/new-Character thresholds.

## Implemented architecture

Formal flow now is:

```text
resolve_global_identities(tracks)
→ recover_unresolved_tracks(candidates)
   Pass 1: one repeated unresolved Track
→ recover_fragmented_shot_presence(candidates)
   Pass 2: aggregate remaining short fragments by Shot + known Character
→ update Person Evidence assignment
→ persist Candidate / Track recovery provenance
→ Final Gate
→ ShotCharacterBinding
```

Both passes only attach evidence to an already-confirmed `RESOLVED` identity. Neither pass creates a Character.

## Code commits

### 1. Fragmented Shot presence pass

Commit:

```text
9f984fd19d24cc7bb4a61f067e484d5507c7721c
fix: aggregate fragmented shot presence for known characters
```

File:

```text
engine/app/character_shot_presence_v101.py
```

Key source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Policy:

```text
remaining unresolved short fragments
→ Person-ReID primary comparison to confirmed galleries
→ clothing/body support
→ optional strong high-quality Face positive support
→ unique known-Character winner
→ mutually-compatible fragment aggregation inside one Shot
→ cannot-link / high-quality Face conflict fail closed
```

Body-only aggregation requires:

```text
>=3 supporting observations
>=3 distinct source timestamps
aggregate median >=0.76
```

Strong Face known-presence support requires high-quality Face and support from independent Gallery Shots. Face remains optional and cannot create an identity.

### 2. Runtime wiring

Commit:

```text
087f3c4316f694efc40b874336d3e8edec758ea8
fix: run fragmented shot presence recovery
```

File:

```text
engine/app/character_runtime_v6.py
```

Adds Pass 2 after existing Track recovery and before persistence/classification writeback.

### 3. Focused tests

Commit:

```text
9c8352f3224e4673ef617bb836e5d3e58b94e79c
test: cover fragmented shot presence recovery
```

File:

```text
engine/tests/v2/test_character_shot_presence_v101.py
```

Cases:

```text
three singleton fragments in one Shot → recover known Character
one strong Face fragment → may confirm presence of known identity
one weak body fragment → remains unresolved
same-sample cannot-link → cannot be counted as duplicate support
```

### 4. Workspace recovery provenance

Commit:

```text
4b83bfd6100efd8fe1460aa8c982cab23359baae
fix: preserve actual shot recovery provenance
```

File:

```text
engine/app/asset_workspace_character_v101.py
```

The Workspace now reads `identity_recovery.source` from the exact Track rather than hard-coding the Pass-1 source. Pass-2 evidence therefore reports `V10_1_SHOT_FRAGMENT_AGGREGATION`.

### 5. Character Gallery Shot-label defect

Backend commit:

```text
f177d6b48431a2d8246da1f31a4cc37732196d14
fix: show real Shot ordinals in Character gallery
```

Frontend commit:

```text
1c5c0727af2f0cc38ecdfff75f129e9520c85290
fix: stop deriving Shot labels from UUID suffixes
```

The screenshot exposed that Gallery cards displayed UUID suffix digits as Shot numbers (for example `SHOT 4592`). `shot_id` is UUID-based and is not the ordinal.

Current API resolves `shot_id` against `v2_shots.ordinal`; frontend renders `SHOT ####` from `shot_ordinal`.

This is display-only and does not alter binding logic.

## CI reality

Workflow run after the focused fragment tests:

```text
run id: 33042855979
backend full summary: 28 failed, 176 passed, 1 skipped
```

The new `test_character_shot_presence_v101.py` was not among failures. Backend compile and FastAPI import passed.

Whole CI remains not green because of existing repository-level categories such as incomplete `cv2`/MOT/media runtime, FFmpeg assumptions and legacy assertions. Frontend build still has the existing `vue-tsc` / TypeScript compatibility failure.

Do not claim all tests pass.

## Documentation commits

```text
da92ec9ceb526212bc5b4a44b4d96a335f781d04  docs: sync V10.1 fragmented Shot presence recovery
ec11564775fb3b28414e96adfad1173d384a1be5  docs: manifest two-pass Shot presence recovery
00beac4a5be3e4290400caa806c15dcb60f907b1  docs: document fragmented Shot presence recovery
```

Active docs synchronized:

```text
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

## Next Windows validation

A fresh Analysis Run is mandatory; old Runs do not gain the new Track recovery metadata or bindings.

```text
1. git pull
2. restart backend/frontend
3. rerun asset extraction
4. confirm Final Character count still equals the real cast first
5. recheck SHOT 0002 / 0004 / 0006 / 0007 / 0009
6. inspect CharacterTrack.evidence_json.identity_recovery on recovered Shots
```

Expected new fragment source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

If a row still fails:

```text
0002 / 0006 close-ups:
  inspect YuNet Face detection, face_score, SFace support

0004 / 0009 two-person Shots:
  verify YOLOX actually produced a separate Person Instance for the second person;
  missing detection/capture cannot be repaired by binding logic

0007 partial/body:
  inspect fragment support_count, distinct timestamps, ReID winner margin;
  do not lower thresholds blindly
```

## Invariants to keep

```text
Track != Character
recovery never creates Character
UNRESOLVED never enters Final Character
Face optional, not mandatory
same-sample cannot-link is hard
high-quality Face conflict is hard
identity confidence != Shot-presence confidence
one Character per Shot materializes at most one ShotCharacterBinding
```

Do not mark V10.1 STABLE/FROZEN until user accepts the fresh real-video result.
