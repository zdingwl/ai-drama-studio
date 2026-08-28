# Session Handoff — Breakdown P2.6 Production + Local Acceptance

> Date: 2026-08-28  
> Repository: `zdingwl/ai-drama-studio`  
> Work branch during implementation: `feature/p2-6-complete`  
> Intended final branch: `main`  
> Hosted CI: **not run / not checked per user instruction**

## 1. Result

P2 backend implementation is now functionally complete:

```text
P2.1 Provider/raw Evidence sidecar       COMPLETE
P2.2 ASR                                 COMPLETE
P2.3 OCR                                 COMPLETE / frozen baseline
P2.4 VLM                                 COMPLETE
P2.5 deterministic Fusion                COMPLETE
P2.6 production orchestrator             COMPLETE
P2.6 single/batch background API         COMPLETE
P2.6 runtime preflight                   COMPLETE
P2.6 Windows local runner                COMPLETE
P2.6 acceptance report/scoring/compare  COMPLETE
```

Important status distinction:

```text
P2 IMPLEMENTATION CODE = COMPLETE
P2 REAL-VIDEO ACCEPTANCE EXECUTION = PENDING
```

The repository does not contain a real short-drama video sample, and this development environment is not the user's Windows GPU machine. Therefore this session did not pretend to produce a real-video quality PASS.

## 2. New production orchestrator

New module:

```text
engine/app/breakdown_p2_pipeline_v1.py
```

Formal profile:

```text
breakdown-p2-full-v1
```

Formal execution order:

```text
create frozen BreakdownRun
→ ASR
→ OCR
→ VLM
→ P2.5 Fusion
→ P1 validator/publish
```

Continuation rules:

```text
ASR READY / NO_EVIDENCE / NOT_AVAILABLE allowed
OCR READY / NO_EVIDENCE / NOT_AVAILABLE allowed
VLM READY required
FAILED / NOT_CONFIGURED fail closed
```

Each Provider still passes through P2.1 validate → immutable sidecar → component provenance. Fusion still consumes sidecars and never reruns providers implicitly.

Pipeline failure only fails a still-PROCESSING Run. STALE/terminal states are preserved. Immutable Run failure provenance stores only a safe exception type, not arbitrary Provider exception text.

## 3. New production APIs

`engine/app/breakdown_routes_v1.py` now exposes:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Existing P1 read endpoints remain:

```text
GET /api/episodes/{episode_id}/breakdown-runs
GET /api/episodes/{episode_id}/breakdown-current
GET /api/breakdown-runs/{run_id}
```

The new write endpoints reuse the existing persistent BackgroundTask infrastructure rather than introducing a second job system.

### Batch rule

Batch Breakdown strictly follows:

```text
Episode.sort_order
concurrency = 1
```

A failed Episode is recorded and the batch continues. Any failure/warning produces aggregate `READY_WITH_WARNINGS`.

## 4. P2.6 Acceptance module

New module:

```text
engine/app/breakdown_p2_acceptance_v1.py
schema = breakdown-p2-acceptance-v1
```

Runtime preflight checks:

```text
main Python
faster-whisper
RapidOCR
OpenCV
FFmpeg / FFprobe
isolated VLM Python / runner / model path
isolated torch / transformers / qwen_vl_utils imports
CUDA when required
nvidia-smi GPU / VRAM / driver metadata
```

Preflight does not download models, run video inference or modify a BreakdownRun.

Structural acceptance checks:

```text
Run READY / READY_WITH_WARNINGS
ASR/OCR/VLM sidecars registered
fingerprint provenance present
VLM READY
FUSION READY / READY_WITH_WARNINGS
Draft Shot count == frozen source ShotRevisionItem count
```

Human review keys, 0–5:

```text
asr_dialogue
asr_timing
ocr_text
vlm_scene
vlm_subjects
vlm_actions
vlm_props
fusion_completeness
fusion_timing
fusion_conflict_handling
```

States:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

PASS requires every required score >=4.0 and no blocking issue. OCR may be explicitly N/A only when source material genuinely has no reviewable text.

HTTP acceptance report is always written into that Run's workspace. The API no longer accepts arbitrary server output paths. CLI may specify a local output path intentionally.

## 5. CLI / Windows

New files:

```text
scripts/run_breakdown_p2.py
scripts/run_breakdown_p2_windows.ps1
scripts/p2_acceptance_review_template.json
```

Examples:

```text
python scripts/run_breakdown_p2.py preflight --strict
python scripts/run_breakdown_p2.py run --episode-id <EPISODE_ID> --acceptance
python scripts/run_breakdown_p2.py report --run-id <RUN_ID>
python scripts/run_breakdown_p2.py compare report-a.json report-b.json
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_breakdown_p2_windows.ps1 -EpisodeId <EPISODE_ID>
```

The Windows script runs strict preflight first by default.

## 6. Provider candidate comparison

The CLI accepts ASR/OCR/VLM parameter overrides so real-video candidates can be run as separate Breakdown Runs.

Supported override categories:

```text
ASR model / device / compute type
OCR model type / device / sampling interval / max frames / score threshold
VLM model / model path / device / fps / max tokens / max pixels
```

Comparison reads existing acceptance reports only; it does not rerun models implicitly.

Successful candidate Runs follow normal P1 Current publish semantics, so model sweeps should use a dedicated test project/episode or intentionally accept Current Breakdown changes.

## 7. Dependency check

`engine/requirements.txt` already includes:

```text
faster-whisper==1.2.1
rapidocr==3.9.2
opencv-python==4.11.0.86
onnxruntime-gpu[cuda,cudnn]==1.21.1
```

No OCR dependency rewrite was needed.

VLM remains isolated and uses the existing P2.4 setup/runtime boundary.

## 8. New focused tests

Added:

```text
engine/tests/v2/test_breakdown_p2_pipeline_v1.py
engine/tests/v2/test_breakdown_p2_acceptance_v1.py
```

Pipeline test coverage:

```text
fixed ASR → OCR → VLM → Fusion order
ASR NO_EVIDENCE degradation
OCR NOT_AVAILABLE degradation
VLM non-READY fail closed
Provider exception failure closure
formal run profile creation
```

Acceptance test coverage:

```text
structural success still requires human review
required scores >=4 PASS
OCR N/A handling
low score/blocking issue → NEEDS_TUNING
structural failure cannot be overridden
invalid score fails closed
report comparison ordering
```

New Python files/tests were syntax-compiled locally during development. No fresh full-repo pytest result is claimed because this execution environment has no full repository checkout.

## 9. No hosted CI

The user explicitly said GitHub CI quota is unavailable. Therefore:

```text
no GitHub Actions run triggered intentionally
no workflow run checked
no CI result used as P2.6 completion evidence
```

Development commits use `[skip ci]`.

## 10. Protected P2/Character boundaries

Still forbidden throughout P2:

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

No changes were made to Character V10.1 thresholds, same-sample cannot-link, Face hard conflicts, explicit Shot Character Assignment or Final Character Gate.

OCR Provider was not redesigned/reworked.

## 11. P2.5 same-Shot subject cannot-link remains

Current Fusion policy:

```text
same normalized appearance
+ >=2 simultaneous subjects in one Shot
→ appearance becomes ambiguous for the segment
→ never use that appearance as cross-Shot merge key
→ shot-local anonymous fallback
```

This is only anonymous Draft grouping, not Character identity resolution.

## 12. Docs synchronized

Updated/added:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
this session handoff
```

`docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md` remains the frozen P1 contract. Its historical P1-era status wording should not override the current P2 status documented above.

## 13. Next safe code phase

Next implementation phase:

```text
P3 — 02 拉片 structured Draft UI
```

P3 should consume:

```text
P2 single/batch task APIs
BackgroundTask progress
Breakdown current/history read APIs
Reference Clips
anonymous Scene/Shot/Subject/Timeline/Prop Draft rows
Evidence provenance
```

Do not build a second ASR/OCR/VLM/Fusion path in the frontend.

Before P3, a user Windows real-video acceptance run is valuable for model tuning, but the P3 UI can be implemented against the now-stable backend contract without waiting for a fake CI gate.
