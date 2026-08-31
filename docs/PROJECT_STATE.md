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
Window Context production contract    = SEGMENT-INDEX V4 / REAL WINDOW-ONLY ACCEPTANCE POSITIVE
P2-E6 anonymous continuity Fusion     = IMPLEMENTED / TARGETED LOCAL TEST PASS / FRESH REAL RUN POSITIVE
P2-E5 Fusion                          = PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion                          = PRESERVED / OLDER ROLLBACK BASELINE
Fast Grounded VLM timing              = IMPLEMENTED / REAL DATA COLLECTED
Exact-Shot performance optimization   = DIAGNOSTIC PHASE
legacy text-only per-Shot E3          = RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM               = PLANNED / NOT IMPLEMENTED
Scene Timeline result UI              = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT FINAL PASS (fresh v4 full-run timing still required)
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Fusion Scene/anonymous-subject quality tuning is **FROZEN** unless a future real regression provides
new evidence. Character V10.1 remains protected.

## 2. Latest fresh E6 real Run quality

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
Shot0001:
subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 木质桌面
no neighboring-person leakage

Scenes=2
Scene1 = 00:00.000–00:22.800 | Shots 1-12 | 公寓走廊 | LocalSubjects=2
Scene2 = 00:22.800–01:06.360 | Shots 13-30 | 客厅 | LocalSubjects=2
same_shot_cluster_conflicts=0
```

Therefore E6 Scene/anonymous-continuity and Exact-Shot visible-truth quality gates are positive.

## 3. Measured performance before Window v4

Fresh instrumented Run:

```text
Host Window materialization = 4.842s
Host Exact-Shot frame extraction = 6.161s
Grounding frames = 58
Qwen model load = 4.723s
Window Context = 465.062s
Exact-Shot = 1076.135s
runner total = 1547.107s
```

Dominant cost is Exact-Shot. Model load and FFmpeg preparation are negligible in comparison.

The first whole-run target is `<30 min`; the fresh Run missed it by about 20 seconds.

## 4. Window Context evolution and real acceptance

### Original prose-heavy Window

```text
12 Shots -> FAILED -> 1600/1600 MAXED
12 Shots -> FAILED -> 1600/1600 MAXED
 9 Shots -> FAILED -> 1600/1600 MAXED
 7 Shots -> READY  -> 1442/1600
```

### Compact per-Shot v2

Still repeated one Scene object per Shot and remained unreliable:

```text
READY 1598/1600
FAILED 1600/1600 MAXED
READY 1435/1600
FAILED 1600/1600 MAXED
```

### Segment v3

Token problem was solved but the model-generated Episode ordinal contract was invalid:

```text
Window total = 107.664s
tokens = 296..366
0 MAXED
4/4 failed segment ordinal validation
```

### Segment-index v4 — ACCEPTED

The model now emits only Window-local 1-based indexes. Frozen Episode ordinal and
`revision_item_id` are deterministically restored by the host adapter.

Real Window-only acceptance on the same completed frozen Run:

```text
profile = breakdown-p2-vlm-window-context-segment-index-zh-v4
Host window materialization = 4.735s
Model load = 5.882s
Window Context total = 41.920s
Runner total = 48.900s

window-0001 | 12 Shots | READY | 276/1600
window-0002 | 12 Shots | READY | 304/1600
window-0003 |  9 Shots | READY | 237/1600
window-0004 |  7 Shots | READY | 233/1600

4/4 READY
0 MAXED
0 JSON truncation
0 segment range error
```

Window Context is now considered **FROZEN / ACCEPTED** unless a future real regression appears.

## 5. Current production VLM path

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_runtime_v1.py
→ engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v3.py
→ scripts/run_breakdown_vlm_window_segment_index_v4.py
```

Production Window profile:

```text
breakdown-p2-vlm-window-context-segment-index-zh-v4
```

Window v3/v2 files remain available as historical/rollback implementations.

Exact-Shot visible-truth path is unchanged:

```text
<1.2s -> 1 frame
1.2..3s -> 2 frames
>3s -> 3 frames
default 5 Shots/batch
max pixels = 524288
max new tokens = 4096
```

Window Context may help Scene and anonymous continuity only. Exact-Shot remains authoritative for
current-Shot people/actions/props/framing/visual prose.

## 6. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ G1 Fast Grounded Qwen3-VL, one model load
   ├─ Window Segment-index v4 Context
   │    24s / 25% overlap / 1 FPS / 262144 px
   │    Scene segments + anonymous subject/prop continuity only
   │    local window indexes -> frozen Shot ordinal/revision_item_id in host
   └─ Exact-Shot frame grounding
        1..3 frames per frozen Shot
        default 5 Shots/batch
        visible facts only from exact frozen Shot frames
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene continuity + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth/projections
   └─ anonymous Subject Continuity
        Stage1 Window hints + exact-Shot explicit conflict guard
        Stage2 stable-appearance gap fallback + conflict guard
        Stage3 mutual-best cluster bridge
        Stage4 coherent-component bridge
        all unions preserve same-Shot hard cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator remains `breakdown-p2-full-v1`; provider order remains `ASR → OCR → VLM`.
Production Fusion profile remains `breakdown-p2-fusion-episode-context-e6-v1`.

## 7. Exact-Shot performance diagnostic

Do not change `4096`, image resolution, frame ratios or batch size speculatively.

A read-only selected-batch diagnostic is available:

```powershell
python scripts/diagnose_breakdown_exact_shot_batches.py `
  --run-id BREAKDOWNRUN_7d27295da479475f92888351bbfb9839 `
  --batches 1,4,6
```

It runs accepted Window v4 once and only the selected Exact-Shot top-level batches, with no DB,
sidecar, Draft or Final writes. It reports:

```text
real output token count / 4096
MAXED or not
adaptive generation attempt count
batch elapsed time
Shot ordinals
frame count
```

Use those measurements to decide whether the Exact-Shot bottleneck is mostly output generation,
image/vision input cost, oversized schema, or retry/split behavior.

## 8. Core truth boundaries

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

Anonymous continuity:

```text
subject_A/B = Shot-local observation labels
same-Shot observations = hard cannot-link
explicit male/female contradiction blocks soft union
explicit long-hair/short-hair contradiction blocks soft union
missing attributes are not contradictions
expression/emotion/action/pose/speaking/screen position/framing do not define identity
```

## 9. Character V10.1 protection

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Anonymous Breakdown continuity must never be treated as Final Character identity truth.

## 10. Next required action

Do not run another full Episode yet.

```text
1. git pull
2. run v4 production routing + Exact-Shot diagnostic unit tests
3. run selected Exact-Shot batches 1,4,6 on the completed frozen Run
4. inspect actual output tokens / retries / elapsed time
5. optimize only the measured Exact-Shot bottleneck
6. run one final fresh full E6 + Window-v4 production Breakdown
7. require quality gates remain positive and whole-run <30min
8. then decide final G1/P2.6 PASS
9. G2 / Scene Timeline UI stays blocked until that decision
```

Hosted GitHub Actions remain intentionally unused.
