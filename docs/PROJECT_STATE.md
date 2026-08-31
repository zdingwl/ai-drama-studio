# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-31 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2 + Breakdown Fast Grounded V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED
G1 Exact-Shot + E6 quality            = FRESH REAL RUN POSITIVE
Window Context production contract    = SEGMENT-INDEX V4 / REAL ACCEPTED / FROZEN
Exact-Shot production contract        = COMPACT-RECONSTRUCTION V3 / SELECTED-BATCH REAL ACCEPTED
P2-E6 anonymous continuity Fusion     = IMPLEMENTED / TARGETED LOCAL TEST PASS / FRESH REAL RUN POSITIVE
P2-E5 Fusion                          = PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion                          = PRESERVED / OLDER ROLLBACK BASELINE
Fast Grounded VLM timing              = IMPLEMENTED / REAL DATA COLLECTED
legacy text-only per-Shot E3          = RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM               = PLANNED / NOT IMPLEMENTED
Scene Timeline result UI              = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT FINAL PASS (one fresh production Run still required)
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Fusion quality, Window-v4 and Exact-Shot-v3 tuning are now **FROZEN** unless a future real production
regression provides new evidence. Character V10.1 remains protected.

## 2. Latest fresh E6 production quality baseline

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
Scene1 = 00:00.000–00:22.800 | Shots 1-12 | 公寓走廊 | LocalSubjects=2
Scene2 = 00:22.800–01:06.360 | Shots 13-30 | 客厅 | LocalSubjects=2
same_shot_cluster_conflicts=0
```

This fresh E6 quality baseline is positive. It predates the final Window-v4 + Exact-Shot-v3
production combination, so one final fresh production Run is still required before P2.6 PASS.

## 3. Window Context v4 — accepted and frozen

Profile:

```text
breakdown-p2-vlm-window-context-segment-index-zh-v4
```

Real Window-only acceptance on the frozen completed Run:

```text
Window Context total = 41.920s
window-0001 | 12 Shots | READY | 276/1600
window-0002 | 12 Shots | READY | 304/1600
window-0003 |  9 Shots | READY | 237/1600
window-0004 |  7 Shots | READY | 233/1600
4/4 READY
0 MAXED
0 invalid JSON
0 range errors
```

The model emits Window-local 1-based indexes; frozen Episode Shot ordinal/revision_item_id are
restored by Python. Window context may help Scene and anonymous continuity only.

## 4. Exact-Shot performance diagnosis

Original production Exact-Shot selected batches:

```text
batch 1 | Shots 1-5   | 10 frames | 85.693s | 2158/4096 | READY
batch 4 | Shots 16-20 | 10 frames | 97.333s | 2374/4096 | READY
batch 6 | Shots 26-30 | 11 frames | 96.481s | 2277/4096 | READY
```

This proved the dominant cost was verbose generated semantic JSON, not model load, FFmpeg,
4096-token exhaustion or adaptive retry.

## 5. Exact-Shot compact v2 history

Compact v2 reduced selected Exact-Shot total from ~279.6s to ~108.3s and output to 851..1097 tokens,
but real review exposed a reconstruction regression:

```text
Shot1 summary correctly saw blue roses + glass vase
Shot1 subjects=0
Shot1 props=[]   <- unacceptable for reconstruction
```

Therefore v2 remains historical/candidate-only and was not promoted.

## 6. Exact-Shot reconstruction-safe compact v3 — accepted and production

Profile:

```text
breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
```

Semantic rule added over v2:

```text
salient independently visible objects needed to reconstruct the Shot must be represented in props,
even when no person interacts with them.
```

User-local targeted tests:

```text
3/3 PASS
```

Real selected-batch acceptance:

```text
batch 1 | Shots 1-5   | 10 frames | 36.421s |  993/4096 | READY
batch 4 | Shots 16-20 | 10 frames | 58.451s | 1055/4096 | READY
batch 6 | Shots 26-30 | 11 frames | 44.921s | 1061/4096 | READY
```

Quality examples:

```text
Shot1  subjects=0 | props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
Shot3  subjects=2 | props=黑色塑料袋
Shot16 subjects=2 | props=手机
Shot26 subjects=1 | props=花瓶, 书本
Shot27 subjects=2 | props=手机, 玫瑰
Shot30 subjects=2 | props=手机
```

The accepted compact contract keeps:

```text
visible Shot description
minimal Scene check
shot type + composition
visible people appearance/activity/position/visibility
reconstruction-relevant visible props + person association
```

Host compatibility restores:

```text
revision_item_id from frozen manifest
subject_A/B from current-Shot person order
summary + visual_description from visible
speaking_state=UNKNOWN (ASR owns dialogue truth)
events=[] (Fusion summary fallback creates VISUAL event when needed)
camera_motion_hint=UNKNOWN for static-frame-only evidence
```

No frame ratios, image resolution, max token cap or top-level batch size were changed.

## 7. Current production VLM path

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py
   ├─ scripts/run_breakdown_vlm_window_segment_index_v4.py
   └─ scripts/run_breakdown_vlm_exact_shot_compact_v3.py
```

Production visual contracts:

```text
Window prompt profile    = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot prompt profile = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
```

Stable inference parameters remain:

```text
Window: 24s / 25% overlap / 1 FPS / 262144 px / 1600 max new tokens
Exact-Shot:
  <1.2s -> 1 frame at 50%
  1.2..3s -> 2 frames at 25/75%
  >3s -> 3 frames at 15/50/85%
  524288 max pixels
  4096 max new tokens
  5 Shots / top-level batch
```

## 8. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL
   ├─ accepted Window Segment-index v4
   └─ accepted Exact-Shot reconstruction-safe compact v3
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene compatibility + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous continuity Stage1..4 with hard same-Shot cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Top-level pipeline profile remains `breakdown-p2-full-v1`; provider order remains `ASR → OCR → VLM`.
Production Fusion remains `breakdown-p2-fusion-episode-context-e6-v1`.

## 9. Core invariants

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
YOLOX -> capture-first Person Evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## 10. Next required action

Run cheap production-routing regression tests first. If green, execute exactly one fresh full
production Breakdown on the reference Episode.

Final P2.6 acceptance requires the new Run to preserve:

```text
Window profile = ...segment-index-zh-v4
Exact-Shot profile = ...compact-reconstruction-zh-v3
Scenes ~= 2 with correct boundaries
Scene1 LocalSubjects ~= 2
Scene2 LocalSubjects ~= 2
same_shot_cluster_conflicts=0
Shot0001 subjects=0
Shot0001 reconstruction props include blue roses + glass vase
whole-run <30 min
```

Do not continue tuning G1 if those gates pass. Then P2.6 can be reviewed for final PASS and G2 /
Scene Timeline planning may begin. Hosted GitHub Actions remain intentionally unused.
