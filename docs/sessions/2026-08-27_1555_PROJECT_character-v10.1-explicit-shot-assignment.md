# Session Handoff — Character V10.1 Explicit Shot Character Assignment

> Date: 2026-08-27 15:55 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Status: IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO ACCEPTANCE

## User goal

The user explicitly wants **precise automatic Character → Shot binding**. Extra Gallery/Evidence comparison UI is diagnostic only and is not the product goal.

Real-video state before this change:

```text
Global identities 人物001 / 002 / 003 were correct
but Shot binding still missed visible people
```

Priority expected rows:

```text
SHOT 0001 → []
SHOT 0002 → [人物002]
SHOT 0003 → [人物001]
SHOT 0004 → [人物001, 人物002]
SHOT 0005 → [人物001]
SHOT 0006 → [人物001]
SHOT 0007 → [人物002]
SHOT 0008 → []
SHOT 0009 → verify every actually visible known Character
```

## Architecture decision

The old V10.1 two-pass approach tried to improve binding by moving unresolved Tracks into already-confirmed identities. It improved some rows but kept Final Shot binding coupled to Candidate Track ownership.

That coupling is now removed.

Formal semantic layers:

```text
Observation / Person Evidence / CharacterTrack
= visual evidence

CharacterCandidate / Identity Class
= project-level person identity

Shot Character Assignment
= whether an already-confirmed Character is present in one Shot

Character / ShotCharacterBinding
= editable Final asset / binding
```

Critical invariant:

```text
candidate.tracks is NOT the current V10.1 Final Shot-binding source
```

## Formal runtime wiring

```text
detect_observations
→ save_person_evidence
→ build_tracks
→ resolve_global_identities
→ assign_shot_characters(all_original_tracks, candidates)
→ update_person_evidence_classification
→ persistence
→ Final Character Gate
→ ShotCharacterBinding from explicit shot_presence_assignments
```

Formal runtime no longer calls:

```text
recover_unresolved_tracks
recover_fragmented_shot_presence
```

Historical modules remain in the repository only for compatibility/tests:

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

## New formal module

```text
engine/app/character_shot_assignment_v101.py
```

Version/source:

```text
v10.1-shot-character-assignment-1
V10_1_SHOT_CHARACTER_ASSIGNMENT
```

The engine consumes all original Track/Observation evidence and every already-RESOLVED identity Gallery. It never creates a new identity and never moves Track ownership.

Assignment modes:

```text
DIRECT_IDENTITY
FACE_STRONG
FACE_REPEATED
BODY_REID
```

### Face known-presence gates

```text
FACE_PAIR_MIN_SCORE = 0.72
FACE_SUPPORTED = 0.36
FACE_STRONG = 0.50
FACE_WINNER_MARGIN = 0.08
MIN_FACE_REPEAT_OBSERVATIONS = 2
MIN_FACE_REPEAT_TIMESTAMPS = 2
MIN_FACE_REPEAT_MEDIAN = 0.40
```

Face support is aggregated against >=2 independent confirmed Gallery Shots. Strong unique Face may confirm one known Character from one current observation; moderate Face must repeat in the current Shot.

### Body / Person-ReID gates

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
REID_WINNER_MARGIN = 0.07
MIN_BODY_SUPPORT_OBSERVATIONS = 3
MIN_BODY_SUPPORT_TIMESTAMPS = 3
MIN_BODY_MEDIAN = 0.76
```

Non-direct body presence must repeat temporally and have a unique known-identity winner.

### Multi-person occupancy

Same-sample cannot-link is used during Shot assignment. If one simultaneous Person Instance is already direct evidence for 人物001, its cannot-link counterpart cannot also be assigned to 人物001. This specifically targets two-person Shots such as `SHOT 0004`.

Ambiguous winner, repeated high-quality Face conflict or insufficient support stays unassigned. The engine does not guess just to fill a Shot.

## Persistence contract

Each RESOLVED Candidate now carries:

```text
shot_assignment_version
shot_assignment_source
shot_assignment_policy
shot_presence_assignments[]
shot_presence_shot_ids
shot_presence_count
shot_presence_recovered_count
```

A Shot assignment contains mode, confidence, support counts/timestamps, track count, Face support and winner margin.

Existing `character_persistence_v6.py` already bridges Candidate V10 metadata into `CharacterCandidate.evidence_json`, so no DB migration was needed.

Historical `CharacterTrack.evidence_json.identity_recovery` remains readable for old Runs but is no longer the formal current binding source.

## Final Gate contract

Project-level Character identity cardinality gate is unchanged:

```text
identity_status == RESOLVED
formal resolver allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

For a Run with `shot_assignment_version`:

```text
ShotCharacterBinding = shot_presence_assignments ONLY
```

An explicit empty assignment list does not fall back to Candidate Tracks.

Old persisted Runs without `shot_assignment_version` retain the historical Track-derived fallback for backward compatibility.

## Workspace contract

`asset_workspace_character_v101.py` now also follows explicit assignments for current Runs:

```text
evidence_by_shot.characters
= RESOLVED Character Shot presence from assignment map

evidence_by_shot.character_diagnostics
= UNRESOLVED visual diagnostics
```

A RESOLVED Candidate Track omitted by the explicit assignment map cannot leak back into the main Character suggestion.

## Main code commits in this change

```text
38e888d2e160cd901377d59763372f63cd216992
feat: add independent V10.1 Shot Character assignment engine

badb18daf80ec561fba23a665bdcbb80c42f5a48
refactor: make Shot Character assignment explicit in V10.1 runtime

1777b65b008a2c16ec33da74620b0ac577c60117
refactor: materialize Final Character bindings from explicit Shot assignments

7dde2a29652f1c2d3d4ae134eae7251269105298
fix: preserve workspace Character evidence payload compatibility
```

Focused tests:

```text
7c3cf9b30a9573329b48a3fcf127a149cf1815f0
test: lock independent Shot Character assignment

19ceb6e77a3cb455a241d8680fbd8434a51ff22b
test: lock explicit Shot assignment Final Gate contract

9bf1c758292b663bad88a674279a13d6991fab7e
test: lock explicit Shot assignment workspace evidence
```

## CI reality

Inspected backend workflow run for code/test head `9bf1c758292b663bad88a674279a13d6991fab7e`:

```text
Compile V2 backend: PASS
Import FastAPI app 2.4.1: PASS
pytest: 28 failed, 187 passed, 1 skipped
```

The new explicit Shot assignment, Final Gate assignment and workspace assignment tests are not among the failures.

The 28 remaining failures are existing repository-wide legacy/runtime/environment categories: lightweight CI missing `cv2`, missing tracker runtime, FFmpeg assumptions, obsolete V6 semantic assertions and historical workspace expectations.

Frontend CI remains blocked by the pre-existing `vue-tsc` / TypeScript package compatibility issue.

Do not claim whole CI is green.

## Docs synchronized

Current formal entry documents now describe explicit Shot assignment:

```text
AGENTS.md
SKILL.md (version 3.5.0)
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

## Next Windows acceptance

A fresh asset extraction Run is mandatory. Old Runs do not automatically gain `shot_assignment_version` and continue historical behavior.

Procedure:

```text
1. git pull latest main
2. restart backend
3. rerun asset extraction and wait for a fresh Analysis Run
4. confirm global Character count remains correct
5. verify SHOT 0001–0009 against expected visible people
```

If a Shot is still wrong, first inspect:

```text
CharacterCandidate.evidence_json.shot_presence_assignments
```

Check its:

```text
mode
confidence
support_count
support_timestamp_count
face_support_count
winner_margin
```

That is now the direct binding decision. Do not return to Gallery UI work or blindly lower global identity thresholds.

## Release status

Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts the Windows real-video Shot binding result.
