# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-30 13:30 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
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
old Scene04 / 19 Shots -> 14 LocalSubjects
actual visible cast -> mainly one woman + one man
Shot0001 actual -> blue roses / glass vase
old visual result -> neighboring woman leakage
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute Episode -> multi-hour runtime class
```

Latest Fast Grounded V2 real rerun is already completed. Current UI result:

```text
30 Shots
4 Scenes
5 / 5 / 2 / 18 Shots by Scene
```

Confirmed positive gate:

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage no longer observed
```

Still pending:

```text
Scene04 anonymous continuity
same-Shot cannot-link real result
Scene boundary correctness
whole-run elapsed
ASR/OCR/VLM elapsed
OCR noise record-only review
```

Overall status therefore remains G1/P2-E4 pending and P2.6 NOT PASSED.

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
→ P2-E4 Episode-context Fusion
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
production E4 Fusion       engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator               engine/app/breakdown_p2_pipeline_v1.py
P2 acceptance              engine/app/breakdown_p2_acceptance_v1.py
G1 diagnostics             engine/app/breakdown_g1_acceptance_diagnostics_v1.py
G1 Run selector            engine/app/breakdown_g1_run_selector_v1.py
G1 compact summary         engine/app/breakdown_g1_acceptance_summary_v1.py
G1 inspection CLI          scripts/inspect_breakdown_g1_run.py
legacy E2 provider         engine/app/breakdown_p2_vlm_episode_v2.py
historical E3 refiner      engine/app/breakdown_p2_refinement_v1.py
historical E3 runner       scripts/run_breakdown_refinement_qwen3.py
```

Production Fusion profile:

```text
breakdown-p2-fusion-episode-context-e4-v1
```

Legacy E2/E3 modules remain only for historical comparison/tests and are not production execution truth.

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
metadata.window_summaries = E4 continuity context
```

## Scene / Dialogue / E4 continuity

Scene continuity remains conservative:

```text
missing/generic/background-poor visual evidence -> inherit current Scene
compatible specificity -> same Scene
strong location or INT/EXT contradiction -> new Scene
```

`ASR_SEGMENT` is Episode-time dialogue truth; Shot dialogue rows are projections.

E4 builds Scene-scoped anonymous Subject Continuity Graphs:

```text
subject_A/B = Shot-local observation labels only
primary edges = Window Context continuity hints
fallback = conservative stable appearance
same-Shot observations = hard cannot-link
expression/emotion/action/pose/speaking/screen position/framing excluded as identity keys
```

## G1 acceptance tooling

Recommended command for the already-completed real rerun:

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

`--latest` auto-selects the newest completed Run whose VLM metadata contains:

```text
production_vlm_profile = breakdown-p2-vlm-fast-grounded-v1
```

`--summary` prints the compact terminal review and still writes the full JSON acceptance artifact. Explicit `--run-id` refuses unfinished or non-Fast-Grounded Runs.

The snapshot includes:

```text
whole-run elapsed
ASR/OCR/VLM timings
Shot0001 final grounded Draft
all Scene boundaries
per-Scene LocalSubjects
Scene04 focused subject continuity
source_members + source subject_A/B labels
same_shot_cluster_conflicts
short OCR noise samples
```

This tooling is read-only and never reruns providers, mutates Draft rows, touches Character V10.1, or creates Final assets.

## Performance / acceptance truth

Reference target:

```text
~60 seconds / ~30 Shots / ~4 Scenes
first target: <30 minutes total
later target: 10..20 minute class
5..6 hours: FAIL
```

Authoritative total elapsed is `BreakdownRun.started_at -> completed_at`. Persisted pipeline provider timings are ASR/OCR/VLM only.

Current truth:

```text
Fast Grounded real rerun = COMPLETED / PARTIAL HUMAN REVIEW
Shot0001 visual grounding = POSITIVE GATE CONFIRMED
Scene04 continuity = PENDING
Scene boundary review = PENDING
runtime review = PENDING
Fast Grounded G1 local-real = PENDING
P2-E4 under grounded input = PENDING
P2.6 = NOT PASSED
GitHub hosted Actions = intentionally not used
```

## G2 / Scene Timeline target

Only after G1 real acceptance:

```text
Scene + grounded Shot visual facts + ASR + OCR + E4 LocalSubjects + prop continuity
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

Historical Runs/sidecars remain immutable. Character V10.1 remains protected: YOLOX → MOT → YoutuReID → RESOLVED/UNRESOLVED → explicit Shot Assignment → Final Gate.

## Testing / CI discipline

Targeted repository coverage now includes:

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
engine/tests/v2/test_breakdown_g1_acceptance_diagnostics_v1.py
engine/tests/v2/test_breakdown_g1_run_selector_v1.py
engine/tests/v2/test_breakdown_g1_acceptance_summary_v1.py
```

Code/test presence is not fresh local pytest/Qwen/CUDA PASS. Hosted GitHub Actions remain unused.

## Next required action

Do not rerun the model just to inspect the existing result. Run:

```powershell
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

Then decide:

```text
G1 failure -> fix only the failing G1 layer and rerun
G1 acceptable -> begin G2 Scene-level text LLM
```
