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
Fast Grounded G1: REAL ACCEPTED / PRODUCTION / FROZEN
Window Context: SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion: E6-V2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance: PASS
G2 Scene Timeline Contract: V1 / IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
G2 Deterministic Assembler: V1 / IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
G2 Scene-level text LLM: UNBLOCKED / NOT IMPLEMENTED
Scene Timeline UI: UNBLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Do not tune G1 again without a new real regression. Character V10.1 remains protected.
G2.1/G2.2 implementation is not a PASS claim until user-local tests are run.

## Final real acceptance evidence

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
status = READY
whole run ~= 841.039s = 14.017 min
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
```

```text
Window Context = 84.3492s
Exact-Shot = 455.284273s
Window = 4/4 READY
Exact-Shot = 6/6 READY
generation attempts = 10
MAXED = 0
failed_window_count = 0
failed_grounding_count = 0
missing_shot_semantic_count = 0
```

Quality / continuity:

```text
Fusion = breakdown-p2-fusion-episode-context-e6-v2
scene_segment = 2
local_subject = 4
cluster_count = 4
merged_cluster_count = 4
final_same_shot_conflict_count = 0
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
Shot0001 subjects=0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
```

P2.6 gate:

```text
Fusion=e6-v2                         PASS
Window=v4                            PASS
Exact-Shot=v3                        PASS
Scenes=2                             PASS
2 anonymous people per Scene         PASS
same-Shot conflicts=0                PASS
Shot0001 exact visible truth         PASS
whole-run <30min                     PASS
whole-run <=20min                    PASS
```

## Frozen production chain

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

Production modules:

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
Orchestrator                       engine/app/breakdown_p2_pipeline_v1.py
```

G2 foundation modules:

```text
Scene Timeline Contract v1          engine/app/breakdown_scene_timeline_contract_v1.py
Deterministic Scene assembler v1    engine/app/breakdown_scene_timeline_assembler_v1.py
Contract / assembler tests          engine/tests/v2/test_breakdown_scene_timeline_v1.py
Contract document                   docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

The G2 foundation is read-only. It does not change the frozen G1 production chain.

Continuity semantics:

```text
Stage1 Window hint:
  listed Shot ordinal = candidate location only
  Exact-Shot appearance must positively support the hint

Stages2..4:
  compare canonicalized compact aliases only
  source appearance text stays unchanged
  accepted thresholds stay unchanged

All stages:
  same-Shot observations = hard cannot-link
  explicit gender / long-vs-short hair conflicts stay hard
  LocalSubject != Character
```

Policies:

```text
window_hint_resolution = window-hint-positive-appearance-support-compact-alias-v2
compact_appearance = compact-observation-stable-alias-normalization-v1
subject_continuity = compact-alias-normalized-after-evidence-gated-window-hint-plus-coherent-component-distinctive-attire-hard-same-shot-v3
same_shot_cannot_link = hard
```

## Hard semantic invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 refs != Character identity
G2 Scene Timeline != Final Scene / Final Prop / Final Character truth
ASR-origin DIALOGUE text is copied verbatim by G2
OCR-origin text is copied verbatim by G2
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## G2 foundation behavior

`scene-timeline-v1` is intentionally ordinary-user oriented:

```text
Scene
→ scene info
→ anonymous people (P1/P2 internally, 人物1/人物2 for display)
→ Shots
   → Exact-Shot visual description
   → visible people / grounded performance
   → ASR-only dialogue
   → Shot prop occurrences
   → shot type / Exact-Shot composition / reliable camera motion
   → OCR-only on-screen text
→ existing Scene summary as deterministic story-summary baseline
```

Primary output excludes Evidence IDs, cluster data, confidence, LocalSubject DB IDs and provider/model diagnostics.
The deterministic assembler fails closed on duplicate Scene/Shot ordinals, invalid time ranges or Shot/Scene ownership conflicts.

## Testing / CI discipline

Accepted user-local evidence includes replay continuity regression PASS, real Window/Exact-Shot model
runs, and the final E6-v2 full production Run above. Do not claim assistant-local CUDA/pytest execution.
Hosted GitHub Actions remain unused; commits use `[skip ci]`.

G2.1/G2.2 tests have been added but are **USER-LOCAL ACCEPTANCE PENDING**. Do not mark them PASS before the user runs them.

## Next required action

G1/P2.6 is no longer the blocker. G2.1 Contract and G2.2 deterministic assembly are implemented without touching G1.

Next safe order:

```text
1. user-local run engine/tests/v2/test_breakdown_scene_timeline_v1.py
2. exercise deterministic assembler against final accepted Run BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
3. verify 2 Scenes / 30 Shots / Scene-local anonymous people / Shot0001 no people + blue roses + glass vase / ASR verbatim
4. only after that acceptance, begin G2.3 Scene-level pure-text LLM
5. then G2.4 source/support validator
6. then G2.5 Scene Timeline API
7. finally G2.6 ordinary-user Scene Timeline UI
```

Do not add an LLM, API or UI workaround to hide a deterministic assembler regression. Fix G2 only; do not retune frozen G1 without a new concrete G1 regression.
