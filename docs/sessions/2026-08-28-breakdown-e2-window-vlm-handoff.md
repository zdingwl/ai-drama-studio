# Session handoff — P2-E2 overlapping Episode-window VLM

Date: 2026-08-28
Branch: main

## What changed

P2-E2 continuous-window visual understanding is now implemented and wired through the stable production VLM import.

```text
engine/app/breakdown_p2_vlm_episode_v2.py
  profile = breakdown-p2-vlm-episode-window-e2-v1
  shot-aligned overlapping Episode windows
  default 24s / 25% overlap
  READY preprocess proxy preferred; Episode source fallback
  FFmpeg temporary window materialization
  multi-window Shot candidate ranking
  exact-shot VLM_OUTPUT compatibility
  payload.episode_window provenance

scripts/run_breakdown_vlm_qwen3_episode_windows.py
  isolated Qwen runner
  one model load, sequential windows
  exact Shot boundary manifest
  Chinese Episode-window prompt
  strict optional video reader
  no ASR/OCR transcription
  anonymous semantics only

engine/app/breakdown_p2_vlm_runtime_v1.py
  stable runtime import now re-exports E2 provider

scripts/run_breakdown_p2.py
  adds --vlm-window-seconds / --vlm-window-overlap-ratio

engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
  window planning/coverage
  best-context selection
  exact-shot output contract
  Final Asset field whitelist
  fail-closed missing Episode video
  stable runtime wiring
```

Production pipeline already imported `breakdown_p2_vlm_runtime_v1.Qwen3VLSemanticProvider`, so new BreakdownRuns now use E2 without changing the top-level `breakdown-p2-full-v1` API/Run profile.

P2-E1 production Fusion remains `breakdown-p2-fusion-episode-context-e1-v2`.

## Important Contract decisions

The frozen P2 sidecar schema was intentionally not changed. E2 window inference is a richer visual context stage, but the persisted semantic Evidence consumed by E1 is still:

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen ShotRevisionItem
source_start_us/end_us = exact Shot range
payload.semantic = existing P2.4 semantic shape
```

Selected/supporting window context is stored in `payload.episode_window`. Historical BreakdownRuns/sidecars are not rewritten.

No Final Character/Scene/Prop/Binding IDs are allowed. Character V10.1 remains untouched.

## Acceptance truth

```text
P2-E2 implementation = IMPLEMENTED ON MAIN
unit coverage = ADDED
fresh local pytest execution in this connector session = NOT RUN
real Windows/Qwen short-drama acceptance = PENDING
P2.6 overall real-model acceptance = NOT PASSED
```

Hosted GitHub Actions were not used.

## Real run checks required next

Use a real Episode containing a same-scene wide shot + closeups/inserts/blurred backgrounds, at least one genuine scene change, recurring anonymous people/props, and a dialogue crossing a cut.

Verify:

```text
E2 context prevents false scene fragmentation
scene_basis reflects DIRECT/CONTEXT/MIXED where appropriate
genuine scene changes are not swallowed
anonymous subject/prop descriptions are more stable without identity overreach
E1 full ASR_SEGMENT dialogue projection still works
VLM_OUTPUT stays exact-shot bound
P1 validator/lifecycle stays intact
Final Asset/Character tables remain untouched
```

## Known follow-up

The current generic P2 preflight still primarily checks the established VLM Python/model/runtime basics. It does not by itself prove that E2 FFmpeg window materialization + new window runner + Qwen decode works on the user's Windows machine. A real E2 Episode run is therefore a required gate, not optional evidence.

## Next implementation after E2 runtime check

P2-E3 contextual Shot refinement:

```text
current Scene
+ previous/current/next Shot
+ selected/supporting E2 window context
+ overlapping Episode ASR
+ overlapping OCR
→ refined Shot-level scene/subject/action/prop/shot-language semantics
```

P2-E4 remains planned after E3. P5 Draft ↔ Character stays paused until the Episode-context semantic baseline is locally stable.
