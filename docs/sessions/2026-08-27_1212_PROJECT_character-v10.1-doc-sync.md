# Session Handoff — Character V10.1 documentation sync

Date: 2026-08-27 12:12 +08:00  
Scope: PROJECT / 03 资产 / Character V10.1  
Branch: `main`

## 1. Goal

Synchronize the repository's authoritative documentation with the actual Character V10.1 code after the shot-level known-identity Track recovery fix, so a future conversation does not restart from stale Character V6 / old F06 documentation.

## 2. State before this session

The code already contained Character V10.1 behavior:

```text
capture-first Person Evidence
→ V10.1 identity classification
→ recover_unresolved_tracks()
→ persistence
→ V10/V10.1 Final Gate
→ ShotCharacterBinding
```

Relevant code commits already on `main` included:

```text
a7849f6  shot-level known identity recovery implementation
1c88ece  runtime integration
4bab131  recovery regression coverage
a776b37  fail-closed recovery hardening
```

However major entry documents still described Character V6, face-track 2-Shot confirmation, old F05 Character V1, or a planned standalone F06 YuNet/SFace pipeline.

That created a real cross-conversation risk: a new Agent could follow documented history instead of current executable wiring.

## 3. Completed in this session

Updated the authoritative entry chain to Character V10.1:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
```

Added a compact implementation manifest:

```text
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
```

Expanded the current Character implementation document:

```text
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

Updated the cross-conversation protocol so future sessions must verify current wiring/profile/resolver before trusting historical Feature documents:

```text
docs/CONTINUATION_PROTOCOL.md
```

Updated user/architecture entry docs:

```text
README.md
docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md
docs/F05_CONTENT_ANALYSIS_V2.md
```

Retired the obsolete standalone F06 character plan as explicit Legacy/Superseded history:

```text
docs/features/F06-auto-character-detection.md
docs/features/F06-function-contracts.md
docs/features/F06-database-dictionary.md
docs/features/F06-p0-checklist.md
docs/features/README.md
```

## 4. Current documented Character contract

```text
Formal runtime profile:
character-v10.1-capture-first-model-classification

Formal asset profile:
f05-assets-v10.1-person-evidence-model-classification

Resolver:
person-evidence-model-classifier-v10.1
```

Current identity creation minimum:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID class
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Face is optional support, not a mandatory identity definition.

Strong contaminated/substantial partial evidence may seed with stricter confirmation; weak/tiny partial evidence is attach-only.

## 5. Current documented Shot Binding recovery

Formal post-confirmation flow:

```text
UNRESOLVED Track
→ compare repeated observations against all RESOLVED identity galleries
→ >=3 usable observations
→ >=2 supporting observations
→ unique winner + margin
→ cannot-link / Face conflict fail closed
→ attach whole Track to already-confirmed identity
```

This pass never creates a new Character.

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

Call order is documented as:

```text
resolve_global_identities()
→ recover_unresolved_tracks()
→ update_person_evidence_classification()
→ persist Candidate / Track
→ Final Gate
→ ShotCharacterBinding
```

## 6. API / DB / file changes

This documentation session changed **no runtime API, DB schema, or algorithm logic**.

A new documentation file was added:

```text
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
```

This Session Handoff file was also added.

## 7. Technical decisions recorded

1. Old Feature/Frozen documents no longer outrank a later explicitly adopted Reference Video V2 implementation merely because they were once marked user-confirmed.
2. New conversations must verify executable wiring before acting on versioned historical documentation.
3. Compatibility filenames (`character_runtime_v6.py`, `character_person_features_v9.py`) must not be used to infer the active Character version.
4. `content_models_v2.model_status()` may still show a V10 **model package** profile because V10.1 reuses the same model weights; runtime/resolver remains V10.1.
5. Whole-repository CI is currently not green and documentation must not claim otherwise.
6. Real Windows short-drama validation is still required after the latest Shot Binding change.

## 8. Testing / CI status

No new code logic was introduced in this documentation-only session, so no new test run was required solely for the docs edits.

Known current CI state from the latest run before this documentation sync:

```text
backend compile/import: passes after CI dependency/version fixes
full pytest: not green
frontend build: not green
```

Failure categories include:

```text
missing cv2/full media runtime in lightweight CI
missing external trackers runtime
legacy Character V6 assertions
FFmpeg assumptions
legacy workspace expectations
vue-tsc / TypeScript package compatibility
```

Do not state “all tests pass”.

## 9. Current risk / unresolved work

The latest Character V10.1 Shot Binding recovery has not yet been accepted on the user's real Windows short-drama sample after a fresh asset rerun.

Old ContentAnalysisRun / CharacterTrack / ShotCharacterBinding data will not automatically change after code updates.

## 10. Contract change status

Documentation contract changed from stale Character V6/old F06 descriptions to the already-implemented Character V10.1 runtime contract.

Runtime behavior itself did not change in this session.

## 11. Documentation commits

```text
6018a87  docs: sync project state to Character V10.1
81d52a7  docs: make Character V10.1 the agent baseline
87a078f  docs: update project skill to Character V10.1
87d2c02  docs: document V10.1 shot binding recovery
e1fcc9f  docs: add current implementation manifest
5ed722e  docs: require code-doc reconciliation on new sessions
d1480b3  docs: refresh README current asset baseline
eb5cba5  docs: sync F05 asset analysis to Character V10.1
38d08ab  docs: retire legacy F06 character plan
85f991e  docs: retire legacy F06 function contracts
9cb620e  docs: retire legacy F06 database dictionary
0e73b04  docs: retire legacy F06 P0 checklist
8223b4f  docs: clarify legacy feature documents
1449ae8  docs: align V2 architecture with current workspaces
```

## 12. Next action

On the user's Windows environment:

```text
1. pull latest main
2. verify F05 models + MOT runtime
3. rerun asset extraction on the same real sample
4. verify Final Character count
5. verify previously wrong ShotCharacterBinding rows/UI
6. if still wrong, inspect person_evidence and track_recovery_* metadata
7. only then tune recovery/identity thresholds
```

## 13. New conversation must read first

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
docs/sessions/2026-08-27_1212_PROJECT_character-v10.1-doc-sync.md
```

Then inspect current code wiring before proposing changes.
