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
Window Context contract: SEGMENT-INDEX V4 / REAL WINDOW-ONLY ACCEPTANCE POSITIVE / PRODUCTION
P2-E6 Episode-context Fusion: IMPLEMENTED / LOCAL TARGETED TESTS PASS / FRESH REAL RUN POSITIVE
P2-E5 Fusion: PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion: PRESERVED / OLDER ROLLBACK BASELINE
VLM performance instrumentation: IMPLEMENTED / REAL DATA COLLECTED
Exact-Shot optimization: DIAGNOSTIC PHASE
legacy text-only per-Shot E3: RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM: PLANNED / NOT IMPLEMENTED
Scene Timeline UI: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT FINAL PASS (fresh v4 full-run timing pending)
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Fusion and Window-v4 policy tuning are frozen unless a future real regression provides new evidence.

## Latest fresh E6 production quality

```text
Run = BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
30 Shots
whole run = 1820.013s = 30.334 min
ASR = 17.951s
OCR = 240.770s
VLM = 1559.171s
```

```text
Shot0001 subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 木质桌面
neighbor person leakage=NO

Scenes=2
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts=0
```

The fresh E6 quality result is positive. The only remaining P2.6 work is performance optimization and
one final production timing confirmation with the accepted Window-v4 path.

## Performance truth

Fresh instrumented production Run before Window-v4 promotion:

```text
Host Window materialization = 4.842s
Host Exact-Shot extraction = 6.161s
Qwen model load = 4.723s
Qwen Window Context = 465.062s
Qwen Exact-Shot = 1076.135s
Qwen runner total = 1547.107s
Grounding frames = 58
```

Measured priority:

```text
Exact-Shot > old Window Context >>> model load / FFmpeg preparation
```

The first whole-run target remains `<30 min`.

## Window Context acceptance history

Original prose-heavy Window:

```text
3/4 windows hit 1600/1600 and returned truncated JSON
```

Compact per-Shot v2:

```text
2/4 still hit 1600/1600; repeated Scene object per Shot remained structurally too verbose
```

Segment v3:

```text
Window total = 107.664s
tokens = 296..366
0 MAXED
4/4 failed because model-produced Episode ordinals were not reliable
```

Segment-index v4 real read-only acceptance:

```text
profile = breakdown-p2-vlm-window-context-segment-index-zh-v4
Host materialization = 4.735s
Model load = 5.882s
Window Context total = 41.920s
Runner total = 48.900s

window-0001 | 12 Shots | READY | 276/1600
window-0002 | 12 Shots | READY | 304/1600
window-0003 |  9 Shots | READY | 237/1600
window-0004 |  7 Shots | READY | 233/1600

4/4 READY
0 MAXED
0 invalid JSON
0 segment range error
```

v4 uses Window-local 1-based indexes. The host maps those indexes back to frozen Episode Shot ordinal
and `revision_item_id`, so the model no longer owns identifier alignment.

## Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Fast Grounded Qwen3-VL, one model load
   ├─ Window Segment-index v4 Context
   │    24s / 25% overlap / 1 FPS / 262144 px
   │    Scene segments + anonymous subject/prop continuity
   │    local indexes -> frozen Shot ordinal/revision_item_id in host
   └─ Exact-Shot frame grounding
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
        524288 max pixels
        4096 max new tokens
        visible facts only from exact frozen Shot frames
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene compatibility + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous continuity
        Stage1 Window hints + exact-Shot conflict guard
        Stage2 stable-appearance gap fallback + conflict guard
        Stage3 mutual-best cluster bridge
        Stage4 coherent-component bridge
        every union preserves hard same-Shot cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Top-level pipeline profile remains `breakdown-p2-full-v1`; provider order remains `ASR → OCR → VLM`.
Production Fusion remains `breakdown-p2-fusion-episode-context-e6-v1`.

## Production modules

```text
P2 sidecar                     engine/app/breakdown_p2_sidecar_v1.py
ASR                            engine/app/breakdown_p2_asr_v1.py
OCR                            engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded semantic base    engine/app/breakdown_p2_vlm_fast_grounded_v1.py
VLM timing/provider routing    engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
stable VLM runtime             engine/app/breakdown_p2_vlm_runtime_v1.py
Window segment production v4   scripts/run_breakdown_vlm_window_segment_index_v4.py
Window segment rollback v3     scripts/run_breakdown_vlm_window_segment_v3.py
Window compact rollback v2     scripts/run_breakdown_vlm_window_compact_v2.py
timed instrumentation base     scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py
timed v4 production entry      scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v3.py
Window v4 diagnostic           scripts/diagnose_breakdown_vlm_windows_v4.py
Exact-Shot batch diagnostic    scripts/diagnose_breakdown_exact_shot_batches.py
VLM performance inspector      scripts/inspect_breakdown_vlm_performance.py
production E6 Fusion           engine/app/breakdown_p2_fusion_episode_v6.py
rollback E5 Fusion             engine/app/breakdown_p2_fusion_episode_v5.py
older rollback E4 Fusion       engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator                   engine/app/breakdown_p2_pipeline_v1.py
```

## E6 / Character invariants

```text
subject_A/B = Shot-local labels only
LocalSubject != Character
same-Shot observations = hard cannot-link
explicit male vs female = block soft union
explicit long hair vs short/buzz/bald = block soft union
missing attribute = not a conflict
expression/emotion/action/pose/speaking/screen position/framing = not identity keys
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Core semantic rules

```text
Shot = smallest visual evidence/location unit
Shot != maximum semantic context
Scene Timeline = primary user-readable Breakdown unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
```

## Testing / CI discipline

Already user-local PASS:

```text
12/12 E6/v3 Fusion targeted tests
```

Window-v4 real model acceptance is confirmed by the read-only diagnostic output above. Production
routing and Exact-Shot diagnostic unit tests are present but should be described as local PASS only
after the user runs them. Hosted GitHub Actions remain intentionally unused.

## Next required action

Do not rerun the whole Episode yet.

1. Pull current `main`.
2. Run production Window-v4 routing and Exact-Shot diagnostic unit tests.
3. Run selected Exact-Shot batches `1,4,6` against the frozen completed Run.
4. Inspect real output token counts, adaptive attempts and elapsed time.
5. Change only the measured Exact-Shot bottleneck.
6. Run one final fresh E6 + Window-v4 production Breakdown.
7. Require quality gates remain positive and whole-run `<30 min`.
8. Then decide final G1/P2.6 PASS and only then proceed to G2 / Scene Timeline UI.
