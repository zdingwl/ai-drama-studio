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
G1 Window Context + Exact-Shot Ground = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E6 anonymous continuity Fusion     = IMPLEMENTED / FRESH PRODUCTION REAL-RUN PENDING
P2-E5 Fusion                          = PRESERVED / ROLLBACK BASELINE
P2-E4 Fusion                          = PRESERVED / OLDER ROLLBACK BASELINE
legacy text-only per-Shot E3          = RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM               = PLANNED / NOT IMPLEMENTED
Scene Timeline result UI              = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

## 2. Latest real-run and replay truth

Historical pre-Fast-Grounded rejection baseline:

```text
30 Shots
21 LocalSubjects
old Scene04 / 19 Shots -> 14 temporary people
actual visible cast -> mainly one woman + one man
Shot0001 visible truth -> blue roses / glass vase
old result -> neighboring woman leakage
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute Episode -> multi-hour runtime class
```

Latest full Fast Grounded V2 execution:

```text
Run = BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
30 Shots
formal E4 Draft at execution time = 4 Scenes
5 / 5 / 2 / 18 Shots
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

The immutable sidecars from that Run were then evaluated read-only. Latest accepted Replay v3:

```text
Candidate Scenes = 2
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts = 0
providers_executed = []
mutates_breakdown_run = false
mutates_final_assets = false
```

Scene1 anonymous chains are supported by the real exact-Shot evidence:

```text
white long-hair person:
2,3,4,5,7,8,9,11,12

gray/white curly-hair + orange floral-shirt person:
3,4,5,6,9,10,11
```

Scene2 remains the accepted one-woman + one-man anonymous result.

The replay-v3 policy has been promoted into versioned production E6. Historical Runs remain immutable.
A fresh E6 production full run has not yet been executed.

Therefore:

```text
G1 exact-Shot focused gate = POSITIVE
G1 Scene replay gate = POSITIVE
G1 Scene1 continuity replay gate = POSITIVE
G1 Scene2 continuity replay gate = POSITIVE
G1 same-Shot hard safety replay gate = POSITIVE
fresh E6 production execution = PENDING
performance first target <30 min = FAIL on previous run
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

Rollback baselines:

```text
engine/app/breakdown_p2_fusion_episode_v5.py
engine/app/breakdown_p2_fusion_episode_v4.py
```

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

Only Scene fields may conservatively inherit Window Context. Neighbor-only person/action/prop/framing
must never become current-Shot truth.

Scene rules:

```text
UNKNOWN / generic / closeup / background-poor -> inherit current Scene
compatible specificity -> same Scene
corridor qualifier drift alone -> same Scene
DIRECT Window NEW_SCENE -> force cut
strong incompatible location or INT↔EXT contradiction -> cut
看不出来 != 换场
```

Anonymous continuity:

```text
subject_A/B = Shot-local observation labels
LocalSubject = Scene-scoped anonymous cluster
same-Shot observations = hard cannot-link
explicit male/female or long-hair/short-hair contradiction blocks soft union
stable appearance may support continuity
co-star structure / distinctive attire may support Stage4 coherent components
expression/emotion/action/pose/speaking/screen position/framing do not define identity
```

## 6. Testing and real acceptance

User-local targeted E4/E5/replay-v2 suite before v3/E6 promotion:

```text
21 tests PASS
```

Replay v3 then produced the 2-Scene / 2-person-per-Scene result above with zero hard conflicts.
New v3/E6 targeted tests are present in the repository but still require a fresh local run after pull.
Hosted GitHub Actions remain intentionally unused.

## 7. Performance gate

Reference target:

```text
~60 seconds / ~30 Shots / ~2 current candidate Scenes
first target: complete Breakdown < 30 minutes
second target: 10..20 minute class
5..6 hours = FAIL
```

Authoritative whole-run elapsed is `BreakdownRun.started_at -> completed_at`.

Previous full execution:

```text
33.705 min total
VLM 1738.0s dominant
OCR 265.9s
ASR 17.1s
```

Before another expensive full run, add detailed VLM instrumentation:

```text
model load
Window Context total/per-window
Exact-Shot total/per-batch
frame/batch counts
```

Then execute one fresh E6 production run and review quality + timing together.

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

Do not use anonymous Breakdown continuity as Final Character identity truth.

## 9. Next required action

```text
1. git pull
2. run targeted replay-v3 + E6 tests
3. if green, freeze Fusion quality tuning
4. add VLM detailed timing instrumentation
5. execute one fresh E6 full real run
6. only then decide G1/P2.6 PASS
7. G2 / Scene Timeline UI stays blocked until that decision
```
