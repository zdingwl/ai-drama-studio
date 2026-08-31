# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-31 10:42 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E5 Episode-context Fusion: IMPLEMENTED / FRESH PRODUCTION REAL-RUN PENDING
P2-E4 Episode-context Fusion: PRESERVED / ROLLBACK BASELINE
legacy text-only per-Shot E3: RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM: PLANNED / NOT IMPLEMENTED
Scene Timeline UI: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT PASSED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

## Latest real execution truth

Historical pre-Fast-Grounded failure baseline:

```text
30 Shots
21 LocalSubjects
old Scene04 / 19 Shots -> 14 temporary people
actual visible cast -> mainly one woman + one man
Shot0001 actual -> blue roses / glass vase
old visual result -> neighboring woman leakage
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute Episode -> multi-hour runtime class
```

Latest full Fast Grounded V2 real rerun is completed:

```text
Run = BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
30 Shots
formal E4 Draft at run time = 4 Scenes
5 / 5 / 2 / 18 Shots by Scene
runtime = 33.705 min
ASR = 17.1s
OCR = 265.9s
VLM = 1738.0s
```

Confirmed positive exact-Shot gate:

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage no longer observed
```

The same immutable ASR/OCR/VLM sidecars were then evaluated with G1 read-only replay v2. Accepted
candidate result:

```text
Candidate Scenes = 2
Scene1 = Shots 1-12 / 公寓走廊
Scene2 = Shots 13-30 / 客厅
Scene2 LocalSubjects = 2
accepted_cluster_bridge_count = 4
same_shot_cluster_conflicts = 0
```

The accepted Scene + anonymous-subject policies have now been promoted unchanged into production E5.
This promotion does not rewrite the historical Run. A fresh E5 production run has not yet been executed.

Overall status therefore remains:

```text
G1 focused Scene/Scene2 replay gate = POSITIVE
E5 code promotion = IMPLEMENTED
fresh E5 production real-run = PENDING
performance <30min = FAIL on previous full run
P2.6 = NOT PASSED
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

## Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Fast Grounded Qwen3-VL
   ├─ Window Context: 24s / 25% overlap / 1 FPS / 262144 px
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
        visible people/actions/props/shot prose only from current Shot images
   one subprocess/model load for both stages
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E5 Episode-context Fusion
   ├─ corridor-family Scene compatibility + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ Window hints + stable gap + mutual-best cluster bridge anonymous continuity
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Top-level pipeline profile remains `breakdown-p2-full-v1`; provider order remains `ASR → OCR → VLM`.

## Production modules

```text
P2 sidecar                 engine/app/breakdown_p2_sidecar_v1.py
ASR                        engine/app/breakdown_p2_asr_v1.py
OCR                        engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded provider     engine/app/breakdown_p2_vlm_fast_grounded_v1.py
Fast Grounded runner       scripts/run_breakdown_vlm_fast_grounded_qwen3.py
stable VLM runtime         engine/app/breakdown_p2_vlm_runtime_v1.py
continuity wrapper         engine/app/breakdown_p2_vlm_continuity_v1.py
production E5 Fusion       engine/app/breakdown_p2_fusion_episode_v5.py
rollback E4 Fusion         engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator               engine/app/breakdown_p2_pipeline_v1.py
P2 acceptance              engine/app/breakdown_p2_acceptance_v1.py
G1 diagnostics             engine/app/breakdown_g1_acceptance_diagnostics_v1.py
G1 Run selector            engine/app/breakdown_g1_run_selector_v1.py
G1 compact summary         engine/app/breakdown_g1_acceptance_summary_v1.py
G1 inspection CLI          scripts/inspect_breakdown_g1_run.py
G1 fusion replay v1/v2     engine/app/breakdown_g1_fusion_replay_v1.py / breakdown_g1_fusion_replay_v2.py
G1 completed replay        engine/app/breakdown_g1_fusion_replay_completed_v2.py
cluster bridge policy      engine/app/breakdown_g1_subject_cluster_bridge_v2.py
legacy E2 provider         engine/app/breakdown_p2_vlm_episode_v2.py
historical E3 refiner      engine/app/breakdown_p2_refinement_v1.py
historical E3 runner       scripts/run_breakdown_refinement_qwen3.py
```

Production Fusion profile:

```text
breakdown-p2-fusion-episode-context-e5-v1
```

E4 remains immutable code history / explicit rollback baseline. Legacy E2/E3 modules remain only for
historical comparison/tests and are not production execution truth.

## Fast Grounded G1 behavior

Window Context output:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

Exact-Shot sampling:

```text
<1.2s   -> 1 frame at 50%
1.2..3s -> 2 frames at 25% / 75%
>3s     -> 3 frames at 15% / 50% / 85%
```

Exact-Shot owns:

```text
shot summary / visual_description
shot type / composition
subjects presence / appearance / activity
visible events
visible plot-relevant props
```

Only Scene fields may conservatively inherit Window Context. Neighbor-only people/actions/props/framing are forbidden.

Frozen sidecar compatibility:

```text
one frozen ShotRevisionItem -> one VLM_OUTPUT
source time = exact Shot range
payload.semantic = grounded semantic consumed by Fusion
payload.exact_shot_semantic = exact image result before Scene inheritance
payload.episode_window = selected Scene context provenance
payload.exact_shot_grounding = frame/truth policy provenance
metadata.window_summaries = E5 continuity context input
```

## Scene / Dialogue / E5 continuity

Scene policy promoted from accepted replay:

```text
corridor-family-qualifier-drift-with-direct-new-scene-v1
```

Rules:

```text
missing/generic/background-poor visual evidence -> inherit current Scene
compatible specificity -> same Scene
corridor qualifier drift alone -> same Scene
DIRECT Window NEW_SCENE -> force Scene cut
real incompatible location -> cut
INT/EXT contradiction -> cut
```

`ASR_SEGMENT` remains Episode-time dialogue truth; Shot dialogue rows are projections.

E5 anonymous continuity policy:

```text
cluster-visual-plus-common-costar-mutual-best-hard-same-shot-v2
```

Order:

```text
subject_A/B = Shot-local observation labels only
primary edges = Window Context continuity hints
second stage = conservative stable-appearance observation gap bridge
third stage = mutual-best cluster bridge using stable visual consensus and shared co-star cannot-link
same-Shot observations = hard cannot-link for every union
expression/emotion/action/pose/speaking/screen position/framing excluded as identity keys
```

E5 fails closed if final clusters contain a same-Shot conflict, one observation maps twice, or cluster
coverage does not exactly cover the Scene observations.

## G1 acceptance tooling

Existing real-run inspection:

```powershell
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

Accepted Fusion replay for a completed Run:

```powershell
python scripts/replay_breakdown_g1_fusion.py --run-id BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
```

The completed-run replay reads immutable sidecars only. It does not rerun providers, mutate Draft rows,
touch Character V10.1 or create Final assets.

The acceptance snapshot includes:

```text
whole-run elapsed
ASR/OCR/VLM timings
Shot0001 final grounded Draft
all Scene boundaries
per-Scene LocalSubjects
focused subject continuity
source_members + source subject_A/B labels
same_shot_cluster_conflicts
short OCR noise samples
```

## Performance / acceptance truth

Reference target:

```text
~60 seconds / ~30 Shots
first target: <30 minutes total
later target: 10..20 minute class
5..6 hours: FAIL
```

Authoritative total elapsed is `BreakdownRun.started_at -> completed_at`.

Previous full Fast Grounded run:

```text
33.705 min total -> FAIL first <30min target
VLM 1738.0s -> dominant cost
OCR 265.9s
ASR 17.1s
```

Current truth:

```text
Fast Grounded exact-Shot visual grounding = POSITIVE focused gate
G1 read-only E5 candidate Scene/Scene2 continuity = POSITIVE focused gate
E5 production routing = IMPLEMENTED
fresh E5 production execution = PENDING
runtime optimization/acceptance = PENDING
P2.6 = NOT PASSED
GitHub hosted Actions = intentionally not used
```

## G2 / Scene Timeline target

Only after fresh E5 + performance acceptance:

```text
Scene + grounded Shot visual facts + ASR + OCR + E5 LocalSubjects + prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

The text LLM may organize known evidence but may not invent visual facts or Final identities. Scene Timeline UI is not a substitute for G1 correctness.

## Media / Character invariants

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy/audio/frame extraction
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
Reference Clip / thumbnail / keyframes
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

Historical Runs/sidecars remain immutable. Character V10.1 remains protected:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Testing / CI discipline

Targeted repository coverage now includes:

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
engine/tests/v2/test_breakdown_p2_e5_promoted_continuity.py
engine/tests/v2/test_breakdown_g1_fusion_replay_v1.py
engine/tests/v2/test_breakdown_g1_subject_cluster_bridge_v2.py
engine/tests/v2/test_breakdown_g1_acceptance_diagnostics_v1.py
engine/tests/v2/test_breakdown_g1_run_selector_v1.py
engine/tests/v2/test_breakdown_g1_acceptance_summary_v1.py
```

Code/test presence is not fresh local pytest/Qwen/CUDA PASS. Hosted GitHub Actions remain unused.

## Next required action

Do not start G2 and do not immediately spend another ~33 minute inference run.

First run targeted local tests for E5/replay. Then add detailed Fast Grounded timing instrumentation for:

```text
model load
Window Context total/per-window
Exact-Shot total/per-batch
frame/batch counts
```

After instrumentation, execute one fresh full production E5 run and review:

```text
Scene count/boundaries
Scene2 anonymous continuity
same-Shot conflicts
Shot0001 grounding regression
whole-run / ASR / OCR / VLM detailed timing
```

Only then decide G1/P2.6 PASS and whether to begin G2.
