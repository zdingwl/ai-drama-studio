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
Fast Grounded G1 exact-Shot/E6 quality: FRESH REAL RUN POSITIVE
Window Context contract: SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION
Exact-Shot contract: COMPACT-RECONSTRUCTION V3 / SELECTED-BATCH REAL ACCEPTED / PRODUCTION
P2-E6 Episode-context Fusion: IMPLEMENTED / LOCAL TARGETED TESTS PASS / FRESH REAL RUN POSITIVE
P2-E5 Fusion: PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion: PRESERVED / OLDER ROLLBACK BASELINE
VLM performance instrumentation: IMPLEMENTED / REAL DATA COLLECTED
legacy text-only per-Shot E3: RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM: PLANNED / NOT IMPLEMENTED
Scene Timeline UI: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT FINAL PASS (one fresh production Run pending)
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Fusion, Window-v4 and Exact-Shot-v3 quality tuning are frozen unless new real regression evidence
appears.

## Latest fresh E6 baseline

```text
Run = BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
30 Shots
whole run = 1820.013s = 30.334 min
ASR = 17.951s
OCR = 240.770s
VLM = 1559.171s
```

Quality:

```text
Shot0001 subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 木质桌面
neighbor person leakage=NO
Scenes=2
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts=0
```

This quality baseline predates the final Window-v4 + Exact-Shot-v3 production combination.

## Accepted Window contract

```text
profile = breakdown-p2-vlm-window-context-segment-index-zh-v4
real Window-only result:
  total = 41.920s
  4/4 READY
  tokens = 233..304 / 1600
  0 MAXED
  0 invalid JSON
  0 range errors
```

The model owns Window-local indexes only. Frozen Shot ordinal/revision_item_id are restored by host
code.

## Exact-Shot diagnosis and acceptance

Original selected batches:

```text
batch 1 | 10 frames | 85.693s | 2158/4096 | READY
batch 4 | 10 frames | 97.333s | 2374/4096 | READY
batch 6 | 11 frames | 96.481s | 2277/4096 | READY
```

Compact v2 proved the performance opportunity but failed reconstruction quality because Shot1
visible roses/vase did not enter structured props.

Accepted reconstruction-safe Compact v3:

```text
profile = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
user-local targeted tests = 3/3 PASS

batch 1 | 10 frames | 36.421s |  993/4096 | READY
batch 4 | 10 frames | 58.451s | 1055/4096 | READY
batch 6 | 11 frames | 44.921s | 1061/4096 | READY
```

Representative quality:

```text
Shot1 subjects=0 | props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
Shot3 subjects=2 | props=黑色塑料袋
Shot16 subjects=2 | props=手机
Shot26 subjects=1 | props=花瓶, 书本
Shot27 subjects=2 | props=手机, 玫瑰
Shot30 subjects=2 | props=手机
```

Compact v3 keeps visible facts needed for reconstruction while deterministic host code restores
canonical compatibility fields.

## Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Fast Grounded Qwen3-VL, one model load
   ├─ Window Segment-index v4 Context
   │    24s / 25% overlap / 1 FPS / 262144 px / 1600 max tokens
   │    local indexes -> frozen Shot ordinal/revision_item_id in host
   └─ Exact-Shot Compact-Reconstruction v3
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
        524288 max pixels
        4096 max new tokens
        current-Shot visible description / people / reconstruction props / framing only
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene compatibility + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous continuity Stage1..4 with hard same-Shot cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Top-level profile remains `breakdown-p2-full-v1`; provider order remains `ASR → OCR → VLM`.
Production Fusion remains `breakdown-p2-fusion-episode-context-e6-v1`.

## Production modules

```text
P2 sidecar                       engine/app/breakdown_p2_sidecar_v1.py
ASR                              engine/app/breakdown_p2_asr_v1.py
OCR                              engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded semantic base      engine/app/breakdown_p2_vlm_fast_grounded_v1.py
Timing provider rollback v2      engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
Production timing provider v3    engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
Production continuity wrapper    engine/app/breakdown_p2_vlm_continuity_v1.py
Window production v4             scripts/run_breakdown_vlm_window_segment_index_v4.py
Exact-Shot production v3         scripts/run_breakdown_vlm_exact_shot_compact_v3.py
Timed production entry           scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py
Window diagnostic                scripts/diagnose_breakdown_vlm_windows_v4.py
Exact-Shot baseline diagnostic   scripts/diagnose_breakdown_exact_shot_batches.py
Exact-Shot v3 diagnostic         scripts/diagnose_breakdown_exact_shot_compact_v3.py
VLM performance inspector        scripts/inspect_breakdown_vlm_performance.py
Production E6 Fusion             engine/app/breakdown_p2_fusion_episode_v6.py
Rollback E5 Fusion               engine/app/breakdown_p2_fusion_episode_v5.py
Older rollback E4 Fusion         engine/app/breakdown_p2_fusion_episode_v4.py
Orchestrator                     engine/app/breakdown_p2_pipeline_v1.py
```

## Exact-Shot compact-v3 compatibility semantics

Model emits only compact Shot-local visual facts. Host restores:

```text
revision_item_id = frozen manifest truth
subject_A/B = current-Shot people order only
summary = visible
visual_description = visible
speaking_state = UNKNOWN (ASR owns dialogue truth)
events = [] (Fusion uses summary VISUAL-event fallback)
camera_motion_hint = UNKNOWN for static-frame-only evidence
```

The model never owns Final Character identity or cross-Shot anonymous IDs.

## Core invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Testing / CI discipline

User-local PASS evidence currently includes:

```text
12/12 E6/v3 Fusion targeted tests
3/3 Exact-Shot compact-v3 targeted tests
real Window-v4 diagnostic: 4/4 READY
real Exact-Shot-v3 selected batches: 1,4,6 READY
```

Do not claim assistant-local pytest/Qwen execution. Hosted GitHub Actions remain intentionally unused.

## Next required action

1. Pull current `main`.
2. Run production-routing regression tests for Window v4 + Exact-Shot v3.
3. If green, execute exactly one fresh full production Breakdown on the reference Episode.
4. Inspect G1 quality + VLM performance summaries.
5. Require:
   - Window profile = `...segment-index-zh-v4`
   - Exact-Shot profile = `...compact-reconstruction-zh-v3`
   - Scenes ~= 2 with correct boundaries
   - Scene1/Scene2 anonymous cast remains ~=2 each
   - same_shot_cluster_conflicts=0
   - Shot0001 subjects=0
   - Shot0001 props include blue roses + glass vase
   - whole-run `<30 min`
6. If those gates pass, stop G1 tuning and review P2.6 for final PASS.
7. Only then start G2 / Scene Timeline work.
