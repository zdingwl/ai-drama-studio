# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-29 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2-E1 Scene/Dialogue continuity: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement: IMPLEMENTED / LOCAL-REAL QUALITY NOT ACCEPTED
P2-E4 final Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / real-model acceptance: NOT PASSED
P3 02 拉片 UI: IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Latest pre-E4 real run was rejected: 30 Shots produced 21 LocalSubjects; the 19-Shot living-room Scene produced 14 temporary people although the visible cast remained one woman + one man. E3 timed out and fell back to E2 for the complete run.

Core semantic rule:

```text
Shot = smallest review/render unit
Shot != maximum semantic context
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
→ P2-E2 overlapping Episode-window Qwen3-VL
→ continuity-preserving VLM wrapper keeps subject/prop window hints
→ P2-E3 contextual Shot refinement
   └─ E3-only failure -> FALLBACK_E2
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Production modules:

```text
P2 sidecar           engine/app/breakdown_p2_sidecar_v1.py
ASR                  engine/app/breakdown_p2_asr_v1.py
OCR                  engine/app/breakdown_p2_ocr_runtime_v1.py
E2 provider          engine/app/breakdown_p2_vlm_episode_v2.py
E2 runner            scripts/run_breakdown_vlm_qwen3_episode_windows.py
E3 refiner           engine/app/breakdown_p2_refinement_v1.py
E3 runner            scripts/run_breakdown_refinement_qwen3.py
E2+E3 runtime        engine/app/breakdown_p2_vlm_runtime_v1.py
E4 continuity VLM    engine/app/breakdown_p2_vlm_continuity_v1.py
legacy Fusion        engine/app/breakdown_p2_fusion_v1.py
E1 Fusion            engine/app/breakdown_p2_fusion_episode_v2.py
production E4 Fusion engine/app/breakdown_p2_fusion_episode_v4.py
orchestrator         engine/app/breakdown_p2_pipeline_v1.py
acceptance           engine/app/breakdown_p2_acceptance_v1.py
```

Top-level pipeline profile remains `breakdown-p2-full-v1`; Provider order remains `ASR → OCR → VLM`.

Production Fusion profile:

```text
breakdown-p2-fusion-episode-context-e4-v1
base = breakdown-p2-fusion-episode-context-e1-v2
```

## E1 behavior retained by E4

Scene continuity:

```text
missing/UNKNOWN/generic -> inherit current Scene
compatible specificity -> same Scene
strong location or INT/EXT contradiction -> new Scene
```

Dialogue continuity:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE = projection
```

Cross-Shot projections share dialogue-group/continuation metadata. UI continuation projections are deduped for normal display.

## E2 / continuity preservation

Default visual context remains shot-aligned overlapping Episode windows: 24s target, 20..40s allowed, 25% overlap, 10..50% allowed, sequential inference, proxy-first/source-fallback.

The Qwen runner already emits `subject_continuity_hints` and `prop_continuity_hints`. The old normalizer discarded them. Production now uses `breakdown_p2_vlm_continuity_v1.py` to preserve normalized hints inside `ProviderResult.metadata.window_summaries`. Frozen per-Shot sidecar shape does not change.

## E3 behavior

E3 remains text-only and current-Shot grounded. It consumes Scene + neighbor E2 Shot semantics + window context + ASR/OCR. It may refine Scene/narrative wording but cannot invent current-Shot people/objects or Final IDs.

E3-only runtime/model/subprocess/timeout failure now degrades to explicit `FALLBACK_E2`; E2 visual failure still fails closed. The latest real run had E3 timeout for all Shots, so E3 quality remains unaccepted.

## E4 anonymous subject continuity

Old LocalSubject linking used exact normalized `appearance_summary`, causing expression/pose/action wording to create false new people.

E4 now builds a Scene-scoped anonymous Subject Continuity Graph:

```text
node = one Shot-local subject_* observation
primary positive edge = E2 window subject_continuity_hint
fallback positive edge = strong stable-appearance similarity across nearby Shots
hard negative = any two observations in the same Shot
cluster = LocalSubject Draft continuity
```

Shot-local `subject_A/B` labels have no global meaning and may swap between Shots.

Stable appearance fallback excludes dynamic state:

```text
exclude expression/emotion/action/pose/speaking/screen-position/camera-framing
prefer gender-presentation/age-band/hair/clothing/persistent accessories
```

Union-find checks same-Shot overlap before every merge, so cannot-link also blocks transitive over-merges. Ambiguous evidence remains unresolved/separate.

E4 provenance is stored in LocalSubject `appearance_json` and Run/Fusion metadata: observation count, cluster count, hint count, explicit/fallback union count and cannot-link rejection count.

## APIs / execution discipline

Formal APIs are unchanged:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch remains sequential by Episode sort order; heavy jobs remain globally serialized.

## P1 / media / Character invariants

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy/audio
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
Reference Clip / thumbnail / keyframes
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

Historical Runs/sidecars are immutable. E4 does not modify the P1 schema.

Character V10.1 remains protected: YOLOX → MOT → YoutuReID → RESOLVED/UNRESOLVED → explicit Shot Assignment → Final Gate. E4 anonymous continuity cannot override Character cannot-link, face conflicts, evidence thresholds or final bindings.

## P3 current UI

`02 拉片` remains `镜头管理 + 拉片结果`. The dialogue UI uses projection metadata to hide repeated continuation text and show “承接上一镜对白”. Technical provenance remains backend truth, not the primary normal-user display.

## Acceptance / CI truth

```text
P2-E4 local-real acceptance = PENDING
P2.6 = NOT PASSED
latest real pre-E4 run = REJECTED
GitHub hosted Actions = intentionally not used
```

Unit coverage added:

```text
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

Code presence is not a fresh local pytest/Qwen/CUDA PASS.

Next required run: re-run the same Episode after `git pull`; verify the 19-Shot living-room sequence collapses to the actual anonymous cast without merging two people visible in one Shot. Then inspect E3 timeout separately.
