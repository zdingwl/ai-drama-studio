# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-30 13:30 +08:00  
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
P2-E4 anonymous continuity Fusion     = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
legacy text-only per-Shot E3          = RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM               = PLANNED / NOT IMPLEMENTED
Scene Timeline result UI              = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

## 2. Real-run status: historical baseline vs current rerun

Historical pre-Fast-Grounded rejection remains the comparison baseline:

```text
30 Shots
21 LocalSubjects total
old Scene04 / 19 Shots -> 14 LocalSubjects
actual visible cast -> mainly one woman + one man
Shot0001 visible truth -> blue roses / glass vase
old result -> leaked neighboring young woman
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute video -> multi-hour runtime class
```

A new Fast Grounded V2 real rerun has already completed. Current user-visible result:

```text
30 Shots
4 Scenes
Scene01 = 5 Shots
Scene02 = 5 Shots
Scene03 = 2 Shots
Scene04 = 18 Shots
```

Confirmed positive G1 gate:

```text
Shot0001 blue roses / glass vase = visually correct
subjects=[]
neighbor woman leakage = fixed in this observed Shot
```

Still pending from the same completed Run:

```text
Scene04 anonymous subject continuity
same-Shot cannot-link real result
whether the current 4 Scenes are true scene changes or duplicate corridor/hallway splits
true whole-run elapsed time
provider ASR/OCR/VLM timings
OCR noise recording only
```

Therefore:

```text
Fast Grounded G1 local-real = PENDING
P2-E4 under grounded input = PENDING
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
→ P2-E4 Episode-context Fusion
   ├─ conservative Scene continuity
   ├─ ASR_SEGMENT dialogue truth/projections
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator/profile:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Production VLM:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_runtime_v1.py
→ engine/app/breakdown_p2_vlm_fast_grounded_v1.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3.py
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
```

Legacy per-Shot text E3 is historical only.

## 5. G1 truth boundaries

Window Context may output only continuity/context:

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

Only Scene fields may conservatively inherit Window Context. Neighbor-only person/action/prop/framing must never become current-Shot truth.

Scene rules:

```text
UNKNOWN / generic / closeup / background-poor -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT↔EXT contradiction -> new Scene
看不出来 != 换场
```

E4 anonymous continuity:

```text
subject_A/B = Shot-local observation labels
LocalSubject = Scene-scoped anonymous cluster
same-Shot observations = hard cannot-link
stable appearance may support continuity
expression/emotion/action/pose/speaking/screen position/framing do not define identity
```

## 6. G1 real-acceptance diagnostics

Read-only modules now exist:

```text
engine/app/breakdown_g1_acceptance_diagnostics_v1.py
engine/app/breakdown_g1_run_selector_v1.py
engine/app/breakdown_g1_acceptance_summary_v1.py
scripts/inspect_breakdown_g1_run.py
```

The selector refuses unfinished/non-Fast-Grounded Runs. `--latest` chooses the newest completed Fast Grounded Run. `--summary` prints the important evidence in one terminal screen while still writing the full JSON artifact.

Recommended command for the already-completed rerun:

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

Important: do **not** rerun the Episode just to inspect acceptance data. Rerun only after a concrete G1 change that requires new inference.

## 7. Acceptance focus

Review in this order:

```text
1. Shot0001 remains blue roses/vase with subject_count=0.
2. Scene04 current 18 Shots: visible cast mainly one woman + one man should converge near two stable LocalSubjects.
3. subject_A/B label swaps must not create new people.
4. same_shot_cluster_conflicts must be empty.
5. Review Scene01..04 boundaries, especially apartment corridor / hallway / living-room naming.
6. Record total Run elapsed from started_at -> completed_at.
7. Record provider ASR/OCR/VLM elapsed separately.
8. Record short OCR noise only; do not prioritize cleanup during G1 unless it corrupts core truth.
```

Machine counters do not auto-PASS G1/P2.6; human review is still required.

## 8. Performance gate

Reference target:

```text
~60 seconds / ~30 Shots / ~4 Scenes
first target: complete Breakdown < 30 minutes
second target: 10..20 minute class
5..6 hours = FAIL
```

Authoritative whole-run elapsed is `BreakdownRun.started_at -> completed_at`, which includes Fusion/validator/IO. `provider_metadata_json.p2_pipeline.timings_seconds` currently contains ASR/OCR/VLM only.

## 9. Character protection

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

Breakdown anonymous continuity can never override Character identity gates or write Final Character/Scene/Prop/Binding truth.

## 10. G2 / Scene Timeline

Only after G1 real acceptance:

```text
Scene
+ exact-Shot grounded visual facts
+ ASR truth
+ OCR truth
+ E4 LocalSubject continuity
+ prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

G2 may organize known evidence but may not invent visual facts or Final identities. Scene Timeline UI is not a substitute for G1 correctness.

## 11. Testing / CI discipline

Hosted GitHub Actions remain intentionally unused. Commits use `[skip ci]`. Repository test presence is not fresh local pytest/Qwen/CUDA PASS.

## 12. Next safe work

```text
A. git pull
B. python scripts/inspect_breakdown_g1_run.py --latest --summary
C. judge Scene04 subject continuity
D. judge current 4 Scene boundaries
E. record whole-run and provider timings
F. record OCR noise only
G. if a core G1 gate fails -> fix only that G1 issue and rerun
H. if G1 is acceptable -> begin G2 Scene-level text LLM
I. P5 remains paused until P2.6 genuinely passes
```
