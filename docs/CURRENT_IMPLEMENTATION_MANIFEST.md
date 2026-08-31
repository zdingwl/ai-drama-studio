# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-31 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Window Context: SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion: E6-V2 PRODUCTION PROMOTED / LOCAL PRODUCTION REGRESSION PENDING
Replay-v5 continuity: REAL ACCEPTED / Scene1=2 / Scene2=2 / conflicts=0
Fresh full-run performance: PASS / 14.098 min / <=20min YES
Fresh Shot/Scene truth: POSITIVE
Previous E6-v1 anonymous continuity: REGRESSION / Scene1=4 / Scene2=16
same-Shot hard safety: PASS / conflicts=0
P2.6 Windows / real-model acceptance: NOT FINAL PASS (E6-v2 fresh confirmation pending)
G2 Scene-level text LLM: BLOCKED / NOT IMPLEMENTED
Scene Timeline UI: BLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Performance tuning, Window-v4 and Exact-Shot-v3 are frozen. Character V10.1 is protected.

## Latest full production evidence

```text
Run = BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
whole run = 845.898s = 14.098 min
ASR = 15.884s
OCR = 264.235s
VLM = 564.050s
```

```text
Window = 4/4 READY | tokens 276,304,237,233 /1600
Exact-Shot = 6/6 READY | tokens 763..1088 /4096 | attempts=1 each
MAXED=0
Shot0001 subjects=0
Shot0001 props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
Scenes=2
same_shot_cluster_conflicts=0
```

This Run passed performance and Shot/Scene truth but E6-v1 produced:

```text
Scene1 LocalSubjects=4
Scene2 LocalSubjects=16
```

## Continuity diagnosis

Provider-free Stage diagnostics showed the main fault was Stage1 Window hint resolution. The old
resolver treated a Window-listed ordinal as guaranteed presence and auto-bound the only visible
person even when appearance disagreed.

Examples from the real Run included:

```text
white off-shoulder woman hint -> gray-hoodie man Shot
male gray-hoodie hint        -> white-clothed woman Shot
```

Replay-v4 replaced only Stage1 with an evidence-gated resolver and restored Scene1=2, Scene2=3.
The remaining Scene2 singleton was compact wording drift (`灰卫衣` vs `灰色连帽衫`). Replay-v5
canonicalizes compact aliases only in the comparison view used by Stages2..4; source evidence text,
thresholds and hard guards remain unchanged.

User-local replay-v5 acceptance:

```text
12 tests PASS
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
Candidate Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
```

Policies:

```text
window_hint_resolution = window-hint-positive-appearance-support-compact-alias-v2
compact_appearance     = compact-observation-stable-alias-normalization-v1
```

## Current production chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ Qwen3-VL one model load
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-Reconstruction v3
→ immutable VLM_OUTPUT sidecar
→ P2-E6-v2 Fusion
   ├─ accepted corridor-family Scene policy + DIRECT boundary safeguard
   ├─ ASR_SEGMENT dialogue truth
   └─ replay-v5 compact-safe anonymous continuity
→ P1 validator
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

## Production modules

```text
P2 sidecar                         engine/app/breakdown_p2_sidecar_v1.py
ASR                                engine/app/breakdown_p2_asr_v1.py
OCR                                engine/app/breakdown_p2_ocr_runtime_v1.py
Production VLM provider            engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
Production continuity wrapper      engine/app/breakdown_p2_vlm_continuity_v1.py
Window production v4               scripts/run_breakdown_vlm_window_segment_index_v4.py
Exact-Shot production v3           scripts/run_breakdown_vlm_exact_shot_compact_v3.py
Timed production entry             scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py
Production E6-v2 Fusion            engine/app/breakdown_p2_fusion_episode_v6.py
Accepted replay-v5                 engine/app/breakdown_g1_fusion_replay_v5.py
Hint resolver                      engine/app/breakdown_g1_subject_hint_resolver_v2.py
Compact appearance normalizer      engine/app/breakdown_g1_compact_appearance_normalizer_v1.py
E6-v2 production regression        engine/tests/v2/test_breakdown_p2_e6_v2_compact_continuity.py
Orchestrator                       engine/app/breakdown_p2_pipeline_v1.py
```

## E6-v2 continuity semantics

```text
Stage1 Window hint:
  listed Shot ordinal = candidate location only
  Exact-Shot appearance must positively support the hint

Stages2..4:
  compare canonicalized compact aliases
  preserve accepted thresholds
  preserve explicit gender / long-vs-short-hair conflict guards

All stages:
  same-Shot observations = hard cannot-link
  LocalSubject != Character
```

Production provenance persists:

```text
fusion_profile = breakdown-p2-fusion-episode-context-e6-v2
window_hint_resolution_policy
compact_appearance_policy
subject_continuity_policy
same_shot_cannot_link=hard
promotion_source=g1-read-only-replay-v5-real-accepted
```

## Hard invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Testing / CI discipline

User-local evidence currently includes:

```text
12 replay-v2/v3/v4/v5 continuity tests PASS
3 Exact-Shot compact-v3 targeted tests PASS
Window-v4 real diagnostic 4/4 READY
Exact-Shot-v3 selected real batches READY
full production performance 14.098 min
replay-v5 real completed-run result = 2 / 2 / conflicts=0
```

Do not claim E6-v2 production tests PASS until user-local output confirms them. Hosted GitHub Actions
remain unused; commits use `[skip ci]`.

## Next required action

1. Pull current `main`.
2. Run E6-v2 production regression tests.
3. If green, execute exactly one final fresh production Breakdown on the reference Episode.
4. Require:
   - Fusion profile `...e6-v2`
   - Window profile `...segment-index-zh-v4`
   - Exact-Shot profile `...compact-reconstruction-zh-v3`
   - Scenes=2
   - Scene1 LocalSubjects=2
   - Scene2 LocalSubjects=2
   - same_shot_cluster_conflicts=0
   - Shot0001 subjects=0
   - Shot0001 props include blue roses + glass vase
   - whole-run `<30 min`
5. Only then review P2.6 for final PASS and start G2 / Scene Timeline work.
