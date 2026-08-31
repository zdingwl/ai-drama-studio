# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-31 11:27 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2 + Breakdown Fast Grounded V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED
G1 Window Context + Exact-Shot Ground = IMPLEMENTED / FINAL FRESH-RUN ACCEPTANCE PENDING
P2-E6 anonymous continuity Fusion     = IMPLEMENTED / TARGETED LOCAL TEST PASS / FRESH RUN PENDING
P2-E5 Fusion                          = PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion                          = PRESERVED / OLDER ROLLBACK BASELINE
Fast Grounded VLM timing              = IMPLEMENTED / LOCAL TEST PENDING
legacy text-only per-Shot E3          = RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM               = PLANNED / NOT IMPLEMENTED
Scene Timeline result UI              = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

## 2. Latest real-run and replay truth

Reference full Fast Grounded execution:

```text
Run = BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
30 Shots
formal E4 Draft at execution time = 4 Scenes
whole run = 33.705 min
ASR = 17.1s
OCR = 265.9s
VLM = 1738.0s
```

Exact-Shot positive gate:

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor person leakage not observed
```

Latest accepted read-only Replay v3 over the immutable sidecars:

```text
Candidate Scenes = 2
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts = 0
providers_executed = []
mutates_breakdown_run = false
mutates_final_assets = false
```

Scene1 real anonymous chains:

```text
white long-hair person:
2,3,4,5,7,8,9,11,12

gray/white curly-hair + orange floral-shirt person:
3,4,5,6,9,10,11
```

Scene2 remains the accepted one-woman + one-man anonymous result.

The replay-v3 policy is now production E6. Historical Runs remain immutable.

User-local E6/v3 targeted validation:

```text
12 tests PASS
```

Therefore **Fusion Scene/anonymous-subject quality tuning is frozen**. Do not keep changing thresholds
without a concrete future real regression.

Current acceptance state:

```text
G1 exact-Shot focused gate = POSITIVE
G1 Scene replay gate = POSITIVE
G1 Scene1 continuity replay gate = POSITIVE
G1 Scene2 continuity replay gate = POSITIVE
G1 same-Shot hard safety replay gate = POSITIVE
E6 targeted local tests = PASS
fresh E6 production execution = PENDING
previous performance <30 min target = FAIL
P2.6 = NOT PASSED
```

## 3. Product principles

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

Hard boundaries:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

## 4. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ G1 Fast Grounded Qwen3-VL
   ├─ Host preparation
   │    Window clip materialization
   │    Exact-Shot FFmpeg frame extraction
   ├─ Window Context
   │    default 24s / 25% overlap / 1 FPS / 262144 max pixels
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s: 1 frame
        1.2..3s: 2 frames
        >3s: 3 frames
        default 5 Shots/batch
        visible facts only from exact frozen Shot frames
   one subprocess/model load for both stages
   structured timing persisted in VLM metadata
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene continuity + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth/projections
   └─ anonymous Subject Continuity
        Stage1 Window hints + explicit exact-Shot conflict guard
        Stage2 stable-appearance gap fallback + conflict guard
        Stage3 mutual-best cluster bridge
        Stage4 coherent-component bridge
        all unions preserve same-Shot hard cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator/profile:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v6.py
profile = breakdown-p2-fusion-episode-context-e6-v1
```

Production VLM timing path:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_runtime_v1.py
→ engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py
```

Semantic base remains:

```text
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
```

The timing layer changes metadata only; prompts, frame ratios, resolutions, token limits, window
planning, batch size and exact-Shot truth rules remain unchanged.

## 5. G1 truth boundaries

Window Context may output continuity/context only:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

Exact-Shot owns current-Shot visible truth:

```text
shot summary / visual_description
shot type / composition
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Anonymous continuity hard rules:

```text
subject_A/B = Shot-local observation labels
LocalSubject = Scene-scoped anonymous cluster
same-Shot observations = hard cannot-link
explicit male/female contradiction blocks soft union
explicit long-hair/short-hair contradiction blocks soft union
missing attributes are not contradictions
stable appearance / co-star structure / distinctive attire may support anonymous continuity
expression/emotion/action/pose/speaking/screen position/framing do not define identity
```

## 6. Performance instrumentation

Persisted VLM performance profile:

```text
breakdown-p2-vlm-performance-timing-v1
```

Measured fields include:

```text
Host:
- Window materialization total/per-window
- Exact-Shot frame extraction total/per-shot
- total grounding frame count
- subprocess wall time

Qwen runner:
- model load
- Window Context total/per-window
- Exact-Shot total/per-top-level-batch
- batch shot count
- batch frame count
- runner total
```

CUDA is synchronized around measured model stages when CUDA is available.

Read-only summary after a new completed Run:

```powershell
python scripts/inspect_breakdown_vlm_performance.py --run-id <NEW_RUN_ID>
```

## 7. Performance gate

Reference target:

```text
~60 seconds / ~30 Shots / ~2 candidate Scenes
first target: complete Breakdown < 30 minutes
second target: 10..20 minute class
5..6 hours = FAIL
```

Previous execution:

```text
33.705 min total
VLM 1738.0s dominant
OCR 265.9s
ASR 17.1s
```

Do not optimize blindly. The next full production Run is specifically for detailed measurement plus
E6 fresh-run quality acceptance.

## 8. Character protection

Character V10.1 remains protected:

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

## 9. Next required action

```text
1. git pull
2. run cheap VLM instrumentation unit tests + py_compile
3. if green, keep Fusion frozen
4. execute one fresh E6 full production Breakdown Run
5. inspect detailed timing with scripts/inspect_breakdown_vlm_performance.py
6. optimize only the measured dominant cost center
7. then decide G1/P2.6 PASS
8. G2 / Scene Timeline UI stays blocked until that decision
```
