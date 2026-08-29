# Session Handoff — P2-E4 Anonymous Subject Continuity

Date: 2026-08-29 +08:00

## Trigger

Real short-drama acceptance rejected the current Breakdown result:

```text
30 Shots
21 LocalSubjects
Scene 04 / 客厅 / 19 Shots -> 14 LocalSubjects
actual visible cast -> same one woman + one man
E3 -> TimeoutExpired -> FALLBACK_E2 for the run
```

Diagnosis: legacy Fusion used exact normalized `appearance_summary` as the cross-Shot LocalSubject key. Dynamic wording such as expression, pose and action therefore fragmented one person. Shot-local `subject_A/B` also swapped people across Shots and could not be used as identity.

A second gap was confirmed: E2 Prompt already produced `subject_continuity_hints / prop_continuity_hints`, but the E2 normalizer discarded them before Fusion.

## Implemented

### 1. Preserve E2 window continuity evidence

New:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
profile = breakdown-p2-vlm-window-continuity-preservation-e4-v1
```

The wrapper subclasses the existing composite E2+E3 runtime and preserves normalized window:

```text
subject_continuity_hints
prop_continuity_hints
```

inside `ProviderResult.metadata.window_summaries` without changing the frozen exact-Shot VLM sidecar schema.

### 2. P2-E4 Subject Continuity Graph

New:

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
base = breakdown-p2-fusion-episode-context-e1-v2
```

Graph semantics:

```text
node = (ShotRevisionItem, Shot-local subject label)
primary positive edge = E2 subject_continuity_hint
fallback positive edge = strong stable appearance similarity across nearby Shots
hard negative = same-Shot cannot-link
cluster = Scene-scoped LocalSubject
```

Shot-local `subject_A/B` labels are not treated as global identity.

Stable appearance fallback excludes expression/emotion/action/pose/speaking/screen-position/camera-framing. It uses conservative stable cues such as hair, clothing and persistent accessories. Ambiguous evidence remains separate.

Union-find enforces same-Shot cannot-link transitively, so a bad hint cannot indirectly merge two people visible in the same Shot.

E4 reuses the mature P1 writer and E1 Scene/Dialogue rewrites through a short-lived patched LocalSubject key function under the existing Fusion lock. P1 schema, immutable Evidence sidecars, Final Asset tables and Character V10.1 are unchanged.

### 3. Production wiring

Updated:

```text
engine/app/breakdown_p2_pipeline_v1.py
```

Production now imports:

```text
VLM = breakdown_p2_vlm_continuity_v1.Qwen3VLSemanticProvider
Fusion = breakdown_p2_fusion_episode_v4
```

Formal provider order stays `ASR → OCR → VLM`; APIs stay unchanged.

### 4. Tests added

```text
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

Coverage targets:

```text
E2 window continuity hint preservation
subject label swap across Shots
expression/action/pose changes do not create new LocalSubject clusters
hard same-Shot cannot-link blocks malformed/transitive hint overmerge
stable-appearance fallback across adjacent Shots
```

## Documentation synchronized

Updated:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

Current truth is now:

```text
P2-E4 = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 = NOT PASSED
latest pre-E4 real run = REJECTED
```

## Commits

```text
97158f6f  preserve E2 continuity hints
a4d8506b  add E4 anonymous subject continuity fusion
dac5e579  wire E4 + continuity VLM into production
71a2175c  add E4 subject continuity tests
05474295  sync PROJECT_STATE
e676f65a  sync CURRENT_IMPLEMENTATION_MANIFEST
baf10a19  sync AGENTS
a03b3b04  sync SKILL
51018826  sync Episode-context plan
0b9889ce  sync local acceptance
```

## Verification truth

Hosted GitHub Actions were not used. This connector environment cannot execute the user's Windows/Qwen/CUDA project runtime. Therefore:

```text
fresh local pytest = NOT CLAIMED
fresh Qwen/CUDA run = NOT CLAIMED
E4 real quality = PENDING
P2.6 PASS = NO
```

## Next action

User should `git pull` and re-run the exact rejected Episode. First inspect only:

```text
Scene 04 / 19 Shots
actual visible cast = one woman + one man
LocalSubject result should collapse from 14 fragments to roughly two stable anonymous subjects
```

Also verify same-Shot people are never merged and Shot-local subject label swaps do not create new people. If E4 continuity is acceptable, diagnose/optimize the independent E3 TimeoutExpired issue next. P5 stays paused.
