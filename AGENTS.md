# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

Current Breakdown truth:

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

## 1. Current real-run truth

The historical pre-Fast-Grounded run remains the failure baseline:

```text
30 Shots
21 LocalSubjects total
old Scene 04 / 19 Shots -> 14 LocalSubjects
actual visible cast -> mainly one woman + one man
Shot 0001 visible truth -> blue roses / glass vase
old result -> leaked neighboring young woman
legacy E3 -> 30/30 TimeoutExpired fallback
runtime class -> multi-hour for ~1 minute video
```

A new **Fast Grounded V2 real rerun has now been completed**. Current user-visible result:

```text
30 Shots
4 SceneSegmentDrafts visible in UI
Scene01 = 5 Shots
Scene02 = 5 Shots
Scene03 = 2 Shots
Scene04 = 18 Shots
```

One G1 regression gate has been visually confirmed positive:

```text
Shot 0001 = blue roses / glass vase
subjects = []
neighbor woman no longer leaks into the Shot
```

This is **not** overall G1/P2.6 PASS. Still pending from the same completed Run:

```text
Scene04 anonymous continuity -> should converge near the real one-woman + one-man cast
same-Shot hard cannot-link -> must have zero cluster conflicts
4 Scene boundaries -> must be reviewed for real space changes vs duplicate corridor/hallway splitting
whole-run elapsed -> must be recorded from BreakdownRun.started_at -> completed_at
OCR noise -> record only, do not derail G1
```

## 2. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
6. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
7. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
8. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
9. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
10. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
11. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
12. current code/tests
13. latest docs/sessions/*.md handoff
```

Truth priority: `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT`.

Core principles:

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

## 3. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR (faster-whisper)
→ OCR (RapidOCR)
→ G1 Fast Grounded Qwen3-VL, one subprocess/model load
   ├─ Window Context
   │    default 24s / 25% overlap / 1 FPS / ~262k pixels
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s: 1 frame
        1.2..3s: 2 frames
        >3s: 3 frames
        default 5 Shots/batch
        visible people/actions/props/shot prose only from exact frozen Shot frames
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
   ├─ conservative Scene continuity
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator:

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

Legacy `breakdown_p2_refinement_v1.py` / `run_breakdown_refinement_qwen3.py` are historical only.

## 4. Visual truth and anonymous continuity boundaries

Window Context may provide only:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

Exact-Shot owns:

```text
shot.summary visible content
shot.visual_description
shot type/composition
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Only Scene fields may inherit Window Context when exact-Shot frames cannot establish environment. Never import neighboring Shot people/actions/props into the current Shot.

Scene rules:

```text
missing / UNKNOWN / generic / background-poor closeup -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT↔EXT contradiction -> new Scene
看不出来 != 换场
```

Dialogue rules:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE TimelineEvent = projection
```

Anonymous identity rules:

```text
subject_A / subject_B = Shot-local observation labels only
LocalSubject = Scene-scoped anonymous continuity cluster
same-Shot observations = hard cannot-link
expression/emotion/action/pose/speaking/screen position/framing != identity keys
```

Hard semantic boundaries:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
Breakdown Evidence / Draft != Final Asset/Binding truth
```

## 5. Character V10.1 is protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax same-sample cannot-link, face conflict, >=3 independent Shots/images for new identity, ambiguity rules, explicit Shot assignment, or Final Gate because of Breakdown hints.

## 6. G1 real-acceptance diagnostics

Read-only acceptance tooling is now production-adjacent diagnostics only; it never reruns models or mutates Draft/Final assets:

```text
engine/app/breakdown_g1_acceptance_diagnostics_v1.py
engine/app/breakdown_g1_run_selector_v1.py
engine/app/breakdown_g1_acceptance_summary_v1.py
scripts/inspect_breakdown_g1_run.py
```

Recommended local command for the already-completed rerun:

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

Do **not** rerun the Episode again just to inspect it. First inspect the existing completed Fast Grounded Run. Only rerun after a concrete G1 code/prompt/policy fix that requires new model output.

Primary acceptance fields:

```text
Shot 0001 subjects/props/visual truth
Scene count + boundaries + location hints
Scene04 LocalSubject count and source_members
same_shot_cluster_conflicts
runtime.total_elapsed_minutes
runtime.provider_timings_seconds
short OCR noise samples
```

Machine counters never auto-promote G1/P2.6 to PASS; human review remains mandatory.

## 7. Performance gate

Reference clip:

```text
~60 seconds / ~30 Shots / ~4 Scenes
first target: whole Breakdown < 30 minutes
second target: 10..20 minute class
5..6 hours = FAIL
```

Authoritative whole-run time is `BreakdownRun.started_at -> completed_at`. Persisted provider timings currently cover ASR/OCR/VLM only; their sum is not the whole Run.

## 8. G2 and result UI

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

Do not start/accept G2 or Scene Timeline UI as a substitute for G1 correctness. P5 also remains paused until Breakdown passes real acceptance.

## 9. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Repository test files are not proof of fresh local pytest/Qwen/CUDA PASS.

Current targeted coverage includes Fast Grounded grounding, E4 continuity, G1 diagnostics, run selection, and compact summary tests. These repository tests must not be described as locally passed unless actually executed on the local machine.

## 10. Next safe work

```text
A. git pull
B. run: python scripts/inspect_breakdown_g1_run.py --latest --summary
C. inspect Scene04 anonymous continuity (~2 real people expected, not a rigid machine count)
D. require same_shot_cluster_conflicts=[]
E. review current 4 Scene boundaries, especially corridor / hallway / living-room naming
F. record whole-run elapsed and provider timings
G. record OCR noise only
H. if any core G1 gate fails -> fix that G1 issue and rerun
I. only if G1 is acceptable -> begin G2 Scene-level text LLM planning/implementation
J. do not advance P5 until P2.6 is genuinely accepted
```
