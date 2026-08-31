# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-31 12:27 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1 exact-Shot/E6 quality: FRESH REAL RUN POSITIVE
Window Context contract: SEGMENT V3 IMPLEMENTED / LOCAL WINDOW-ONLY VALIDATION PENDING
P2-E6 Episode-context Fusion: IMPLEMENTED / LOCAL TARGETED TESTS PASS / FRESH REAL RUN POSITIVE
P2-E5 Fusion: PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion: PRESERVED / OLDER ROLLBACK BASELINE
VLM performance instrumentation: IMPLEMENTED / REAL DATA COLLECTED
legacy text-only per-Shot E3: RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM: PLANNED / NOT IMPLEMENTED
Scene Timeline UI: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT PASSED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Fusion quality tuning is frozen unless a future real regression provides new evidence.

## Latest fresh E6 real execution

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

This is the first fresh production E6 quality result and is positive.

## Measured performance

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
Exact-Shot > Window Context >>> model load / FFmpeg preparation
```

First performance gate remains `<30 min`; the fresh Run missed by about 20 seconds.

## Window failure truth

Original timed Window prompt on the fresh Run:

```text
12 Shots -> 1600/1600 MAXED -> invalid JSON
12 Shots -> 1600/1600 MAXED -> invalid JSON
 9 Shots -> 1600/1600 MAXED -> invalid JSON
 7 Shots -> 1442/1600 READY
```

Compact per-Shot v2 follow-up on the same frozen Run:

```text
12 Shots -> 1598/1600 READY
12 Shots -> 1600/1600 MAXED -> invalid JSON
 9 Shots -> 1435/1600 READY
 7 Shots -> 1600/1600 MAXED -> invalid JSON
```

Therefore output truncation is confirmed and per-Shot repeated Scene objects remain structurally too
verbose. Do not solve this by simply increasing the token cap.

## Current Window Segment Contract v3

Profile:

```text
breakdown-p2-vlm-window-context-segment-zh-v3
```

Model output is Scene-segment based rather than one Scene object per Shot:

```text
window_summary
scene_segments[]:
  start_ordinal
  end_ordinal
  boundary_basis = WINDOW_START | DIRECT | CONTEXT | UNCERTAIN
  location_hint
  interior_exterior
  time_of_day
subject_continuity_hints[]
prop_continuity_hints[]
```

Host-side deterministic adapter expands this into canonical `shot_scene_hints[]`:

```text
revision_item_id = copied only from frozen manifest
first Window segment = never hard-cuts
later DIRECT segment start = NEW_SCENE + DIRECT
later CONTEXT/UNCERTAIN start = UNCERTAIN
all other Shots = SAME
segment coverage gap/overlap = fail closed
```

This keeps downstream Exact-Shot grounding and E6 interfaces unchanged while removing repeated model
output. Exact-Shot visible fact remains authoritative.

## Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Fast Grounded Qwen3-VL, one model load
   ├─ Window Segment v3 Context
   │    24s / 25% overlap / 1 FPS / 262144 px
   │    compact Scene segments + anonymous subject/prop continuity
   │    host expands canonical shot_scene_hints
   └─ Exact-Shot frame grounding
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
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
P2 sidecar                    engine/app/breakdown_p2_sidecar_v1.py
ASR                           engine/app/breakdown_p2_asr_v1.py
OCR                           engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded semantic base   engine/app/breakdown_p2_vlm_fast_grounded_v1.py
VLM timing/provider routing   engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
stable VLM runtime            engine/app/breakdown_p2_vlm_runtime_v1.py
Window compact rollback v2    scripts/run_breakdown_vlm_window_compact_v2.py
Window segment production v3  scripts/run_breakdown_vlm_window_segment_v3.py
timed instrumentation v1      scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py
timed production entry v2     scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v2.py
Window-only diagnostic        scripts/diagnose_breakdown_vlm_windows.py
VLM performance inspector     scripts/inspect_breakdown_vlm_performance.py
production E6 Fusion          engine/app/breakdown_p2_fusion_episode_v6.py
rollback E5 Fusion            engine/app/breakdown_p2_fusion_episode_v5.py
older rollback E4 Fusion      engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator                  engine/app/breakdown_p2_pipeline_v1.py
```

## E6 anonymous continuity invariant

```text
subject_A/B = Shot-local labels only
LocalSubject != Character
same-Shot observations = hard cannot-link
explicit male vs female = block soft union
explicit long hair vs short/buzz/bald = block soft union
missing attribute = not a conflict
expression/emotion/action/pose/speaking/screen position/framing = not identity keys
```

E6 metadata records `cluster_bridge_union_count` and `component_bridge_union_count` and fails closed
on same-Shot conflicts, duplicate observation mapping, or incomplete cluster coverage.

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

## Character invariant

Character V10.1 remains protected and unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Testing / CI discipline

Already user-local PASS:

```text
12/12 E6/v3 Fusion targeted tests
```

Segment-v3 adapter/routing tests are now present but require user-local execution. Hosted GitHub
Actions remain intentionally unused.

## Next required action

Do not rerun the full Episode yet.

1. Pull current `main`.
2. Run py_compile for Window segment v3 and timed-v2 entry.
3. Run segment-v3 adapter/routing tests plus existing timing test.
4. Run Window-only diagnostic against `BREAKDOWNRUN_7d27295da479475f92888351bbfb9839`.
5. Require 4/4 Window READY, zero MAXED, and materially lower output token totals.
6. If v3 passes, decide whether one final full production Run is needed for P2.6.
7. Then optimize the measured Exact-Shot 1076s cost center from real generation-token data.
8. G2 / Scene Timeline UI remains blocked until P2.6 final acceptance.
