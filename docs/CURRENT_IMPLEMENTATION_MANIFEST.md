# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-31 11:27 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: IMPLEMENTED / FINAL FRESH-RUN ACCEPTANCE PENDING
P2-E6 Episode-context Fusion: IMPLEMENTED / LOCAL TARGETED TESTS PASS / FRESH RUN PENDING
P2-E5 Episode-context Fusion: PRESERVED / ROLLBACK BASELINE
P2-E4 Episode-context Fusion: PRESERVED / OLDER ROLLBACK BASELINE
Fast Grounded VLM timing instrumentation: IMPLEMENTED / LOCAL TEST PENDING
legacy text-only per-Shot E3: RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM: PLANNED / NOT IMPLEMENTED
Scene Timeline UI: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT PASSED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

## Latest real execution truth

Reference real Run:

```text
Run = BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
30 Shots
formal E4 Draft at run time = 4 Scenes
runtime = 33.705 min
ASR = 17.1s
OCR = 265.9s
VLM = 1738.0s
```

Confirmed exact-Shot positive gate:

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage not observed
```

The same immutable ASR/OCR/VLM sidecars were evaluated through read-only replay v3:

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
white long-hair chain:
Shots 2,3,4,5,7,8,9,11,12

gray/white curly-hair + orange floral-shirt chain:
Shots 3,4,5,6,9,10,11
```

Scene2 remains the accepted one-woman + one-man anonymous continuity result.

User-local validation on Windows after E6 promotion:

```text
engine/tests/v2/test_breakdown_g1_fusion_replay_v3.py
engine/tests/v2/test_breakdown_p2_e6_promoted_continuity.py
engine/tests/v2/test_breakdown_g1_fusion_replay_v2_conflict_guard.py
engine/tests/v2/test_breakdown_g1_subject_cluster_bridge_v2.py

12 tests PASS
```

Therefore Fusion quality tuning is now **FROZEN** unless a future real regression provides concrete evidence.
Do not continue changing Scene/anonymous-subject thresholds speculatively.

Overall status:

```text
G1 exact-Shot focused grounding gate = POSITIVE
G1 Scene boundary replay gate = POSITIVE
G1 Scene1 anonymous continuity replay gate = POSITIVE
G1 Scene2 anonymous continuity replay gate = POSITIVE
same-Shot hard safety replay gate = POSITIVE
E6 code promotion = IMPLEMENTED
E6 targeted local regression = PASS (12/12)
fresh E6 production real-run = PENDING
performance <30min = FAIL on previous full run
VLM detailed timing instrumentation = IMPLEMENTED / LOCAL TEST PENDING
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
   ├─ Host preparation timing
   │    Window clip materialization
   │    Exact-Shot FFmpeg frame extraction
   ├─ Window Context: 24s / 25% overlap / 1 FPS / 262144 px
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
        visible people/actions/props/shot prose only from current Shot images
   one subprocess/model load for both stages
   timing metadata persists:
        model load
        Window total + per-window
        Exact-Shot total + per-top-level-batch
        batch shot/frame counts
        subprocess wall
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene compatibility + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous continuity:
        Stage1 Window hints with exact-Shot conflict guard
        Stage2 conservative stable-appearance gap fallback with conflict guard
        Stage3 mutual-best cluster bridge
        Stage4 coherent-component bridge using co-star structure/distinctive attire
        every union preserves hard same-Shot cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Top-level pipeline profile remains `breakdown-p2-full-v1`; provider order remains `ASR → OCR → VLM`.

## Production modules

```text
P2 sidecar                   engine/app/breakdown_p2_sidecar_v1.py
ASR                          engine/app/breakdown_p2_asr_v1.py
OCR                          engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded semantic base  engine/app/breakdown_p2_vlm_fast_grounded_v1.py
VLM timing provider          engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
Timed isolated runner        scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py
stable VLM runtime           engine/app/breakdown_p2_vlm_runtime_v1.py
continuity wrapper           engine/app/breakdown_p2_vlm_continuity_v1.py
production E6 Fusion         engine/app/breakdown_p2_fusion_episode_v6.py
rollback E5 Fusion           engine/app/breakdown_p2_fusion_episode_v5.py
older rollback E4 Fusion     engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator                 engine/app/breakdown_p2_pipeline_v1.py
VLM performance inspector    scripts/inspect_breakdown_vlm_performance.py
G1 inspection CLI            scripts/inspect_breakdown_g1_run.py
G1 replay v3                 engine/app/breakdown_g1_fusion_replay_v3.py
completed replay v3          engine/app/breakdown_g1_fusion_replay_completed_v3.py
v2 cluster bridge            engine/app/breakdown_g1_subject_cluster_bridge_v2.py
v3 component bridge          engine/app/breakdown_g1_subject_component_bridge_v3.py
```

Production Fusion profile:

```text
breakdown-p2-fusion-episode-context-e6-v1
```

VLM performance profile:

```text
breakdown-p2-vlm-performance-timing-v1
```

## E6 Scene / anonymous continuity policy

Scene policy:

```text
corridor-family-qualifier-drift-with-direct-new-scene-v1
```

Anonymous subject policy:

```text
coherent-component-distinctive-attire-hard-same-shot-v3
base = cluster-visual-plus-common-costar-mutual-best-hard-same-shot-v2
```

Hard rules:

```text
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
explicit male vs female = block soft union
explicit long hair vs short/buzz/bald = block soft union
missing attribute = not a conflict
expression/emotion/action/pose/speaking/screen position/framing = not identity keys
```

E6 fails closed if final clusters contain same-Shot conflicts, one observation maps to multiple
clusters, or cluster coverage does not exactly cover Scene observations.

E6 metadata records both:

```text
cluster_bridge_union_count
component_bridge_union_count
```

## Performance instrumentation contract

The instrumented production VLM adds only metadata; it does not change semantic prompts, sampling,
resolution, token limits, window planning, batch size or Exact-Shot truth rules.

Persisted VLM metadata contains:

```text
performance.profile
performance.provider_runner_wall_seconds
performance.host.window_materialization_total_seconds
performance.host.window_materialization[]
performance.host.grounding_frame_materialization_total_seconds
performance.host.shot_frame_materialization[]
performance.host.subprocess_wall_seconds
performance.host.grounding_frame_count
performance.model_runner.model_load_seconds
performance.model_runner.window_context_total_seconds
performance.model_runner.window_timings[]
performance.model_runner.exact_shot_total_seconds
performance.model_runner.grounding_batch_timings[]
performance.model_runner.grounding_batch_count
performance.model_runner.grounding_frame_count
performance.model_runner.runner_total_seconds
```

CUDA timing uses synchronization around measured inference stages when CUDA is available so model
stage timings are not misleadingly short due to asynchronous kernel launch.

Read-only summary after a newly completed instrumented Run:

```powershell
python scripts/inspect_breakdown_vlm_performance.py --run-id <NEW_RUN_ID>
```

## Performance / acceptance truth

Reference target:

```text
~60 seconds / ~30 Shots
first target: <30 minutes total
later target: 10..20 minute class
5..6 hours: FAIL
```

Previous full Fast Grounded Run:

```text
33.705 min total -> FAIL first <30min target
VLM 1738.0s -> dominant cost
OCR 265.9s
ASR 17.1s
```

Do not optimize blindly. The next full run must use the new timing profile and be used to decide
which cost center to change.

## G2 / Scene Timeline target

Do not begin G2 or Scene Timeline UI before fresh E6 + performance acceptance.

Later target:

```text
Scene + grounded Shot visual facts + ASR + OCR + E6 LocalSubjects + prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

## Character invariant

Character V10.1 remains protected and was not changed by E6 or VLM instrumentation:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Testing / CI discipline

Already user-local PASS:

```text
12/12 E6/v3 targeted Fusion tests
```

New instrumentation tests still require user-local execution after `git pull`:

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_vlm_performance_instrumentation_v1.py
```

Hosted GitHub Actions remain intentionally unused.

## Next required action

1. Pull current main.
2. Run the cheap instrumentation tests and Python compile checks.
3. If green, do not change Fusion further.
4. Execute exactly one fresh full E6 production Breakdown Run with timing enabled.
5. Run `scripts/inspect_breakdown_vlm_performance.py` on that new Run.
6. Optimize the measured dominant cost center, then decide G1/P2.6 acceptance.
