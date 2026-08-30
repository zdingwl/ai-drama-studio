# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-30 +08:00**

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

Latest real run before Fast Grounded V2 was rejected for both anonymous-subject fragmentation and
exact-Shot visual leakage. It also took multi-hour class for a ~1-minute Episode. This is not PASS.

Core semantic rules:

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
        1..3 frames per frozen Shot
        default 5 Shots/batch
        visible people/actions/props/shot prose only from current Shot images
   one subprocess/model load for both stages
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Top-level pipeline profile remains `breakdown-p2-full-v1`; Provider order remains `ASR → OCR → VLM`.

## Production modules

```text
P2 sidecar              engine/app/breakdown_p2_sidecar_v1.py
ASR                     engine/app/breakdown_p2_asr_v1.py
OCR                     engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded provider  engine/app/breakdown_p2_vlm_fast_grounded_v1.py
Fast Grounded runner    scripts/run_breakdown_vlm_fast_grounded_qwen3.py
stable VLM runtime      engine/app/breakdown_p2_vlm_runtime_v1.py
continuity wrapper      engine/app/breakdown_p2_vlm_continuity_v1.py
legacy E2 provider      engine/app/breakdown_p2_vlm_episode_v2.py
legacy E2 runner        scripts/run_breakdown_vlm_qwen3_episode_windows.py
historical E3 refiner   engine/app/breakdown_p2_refinement_v1.py
historical E3 runner    scripts/run_breakdown_refinement_qwen3.py
legacy Fusion           engine/app/breakdown_p2_fusion_v1.py
E1 Fusion               engine/app/breakdown_p2_fusion_episode_v2.py
production E4 Fusion    engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator            engine/app/breakdown_p2_pipeline_v1.py
acceptance              engine/app/breakdown_p2_acceptance_v1.py
```

Production Fusion profile:

```text
breakdown-p2-fusion-episode-context-e4-v1
```

## Fast Grounded G1 behavior

Window Context output is intentionally small:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

It does not own final current-Shot visual facts.

Exact-Shot sampling:

```text
<1.2s   -> 1 frame at 50%
1.2..3s -> 2 frames at 25% / 75%
>3s     -> 3 frames at 15% / 50% / 85%
```

Exact-Shot owns:

```text
shot summary/visual_description
shot type/composition
subjects presence/appearance/activity
visible events
visible plot-relevant props
```

Only Scene fields may conservatively inherit Window Context. Neighbor-only people/actions/props are forbidden.

Frozen sidecar compatibility remains:

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

Scene continuity remains conservative: missing/generic/background-poor visual evidence inherits the
current Scene; strong location or INT/EXT contradiction creates a new Scene.

`ASR_SEGMENT` is Episode-time dialogue truth; Shot dialogue rows are projections. Cross-Shot full
sentence text and continuation metadata remain, while normal UI hides duplicate continuation rows.

E4 builds Scene-scoped anonymous Subject Continuity Graphs. `subject_A/B` labels are Shot-local only.
Primary positive edges are Window Context subject hints; fallback uses stable appearance. Expression,
emotion, action, pose, speaking, screen position and framing are excluded. Same-Shot observations
have a transitive hard cannot-link.

## Legacy E3

Text-only per-Shot E3 no longer executes in production. Historical modules/tests remain importable
for old Run comparison. Its product responsibility is split into:

```text
G1 Exact-Shot visual grounding
+
G2 Scene-level pure-text LLM (planned)
```

## G2 / Scene Timeline target

Planned input:

```text
Scene + grounded Shot visual facts + ASR + OCR + E4 LocalSubjects + prop continuity
```

Planned output: readable Scene Timeline Breakdown, one text-model call per Scene rather than per Shot.
The text LLM may organize known evidence but may not invent visual facts or Final identities.

## APIs / execution discipline

Formal APIs remain unchanged:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch stays sequential by Episode sort order; heavy jobs remain globally serialized.

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

Historical Runs/sidecars are immutable.

Character V10.1 remains protected: YOLOX → MOT → YoutuReID → RESOLVED/UNRESOLVED → explicit Shot
Assignment → Final Gate. Breakdown continuity cannot override Character identity safety.

## Performance / acceptance truth

Reference target:

```text
60 seconds / ~30 Shots / ~4 Scenes
first target: <30 minutes total
later target: 10..20 minute class
5..6 hours: FAIL
```

Current truth:

```text
Fast Grounded G1 local-real = PENDING
P2-E4 under grounded input = PENDING
P2.6 = NOT PASSED
latest real run = REJECTED (pre Fast Grounded)
GitHub hosted Actions = intentionally not used
```

Coverage added:

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

Code presence is not fresh local pytest/Qwen/CUDA PASS.

Next required run: `git pull`, rerun the same Episode, first verify Shot 0001 remains the blue-rose
insert with `subjects=[]`, then verify Scene 04 anonymous cast continuity and record actual elapsed
time. Fix G1 regressions before G2 Scene LLM / Scene Timeline UI.
