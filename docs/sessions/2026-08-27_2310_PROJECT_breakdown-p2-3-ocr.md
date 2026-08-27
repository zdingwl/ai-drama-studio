# Session Handoff — Breakdown P2.3 OCR Observation Provider

> Date: 2026-08-27 23:10 +09:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch during implementation: `feat/breakdown-p2-3-ocr-provider`  
> PR: #11  
> Scope: **P2.3 only**

## 1. Current phase state

```text
P0  planning/contracts                         COMPLETE
P1  Draft data/runtime/history/compatibility   COMPLETE
P2  ASR/OCR/VLM anonymous Evidence/Draft       IN PROGRESS
  P2.1 Provider/raw Evidence sidecar            COMPLETE
  P2.2 ASR Provider                            COMPLETE
  P2.3 OCR Observation Provider                COMPLETE
  P2.4 VLM anonymous Shot semantics            NEXT
  P2.5 Fusion → complete P1 Draft              PLANNED
  P2.6 real-video benchmark/closure            PLANNED
```

P2.3 completion means a formal local OCR raw-Evidence producer exists. It does **not** mean TimelineEvent generation, complete anonymous Draft, OCR temporal dedupe, VLM, asset resolution or final Breakdown are complete.

## 2. Files introduced/changed by P2.3

Production:

```text
engine/app/breakdown_p2_ocr_v1.py
engine/requirements.txt
```

Tests/CI:

```text
engine/tests/v2/test_breakdown_p2_ocr_v1.py
.github/workflows/v2-ci.yml
```

Synchronized docs:

```text
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
docs/sessions/2026-08-27_2310_PROJECT_breakdown-p2-3-ocr.md
```

## 3. Formal OCR baseline

```text
Provider class: RapidOCROCRProvider
component: OCR
provider: rapidocr
package: rapidocr==3.9.2
OCR version: PP-OCRv6
model type: small
engine: ONNX Runtime
default device: cpu
```

Config:

```text
AI_DRAMA_P2_OCR_MODEL_TYPE          # small / medium
AI_DRAMA_P2_OCR_DEVICE              # cpu / auto / cuda
AI_DRAMA_P2_OCR_SAMPLE_INTERVAL_US
AI_DRAMA_P2_OCR_MAX_FRAMES_PER_SHOT
AI_DRAMA_P2_OCR_TEXT_SCORE
AI_DRAMA_P2_OCR_MODEL_CACHE
```

Default CPU is deliberate stability-first behavior. `auto` may select CUDA when available; only auto-selected CUDA may visibly fall back to CPU on engine-load failure. Explicit `cuda` remains fail-closed.

## 4. Input contract

P2.3 consumes the exact historical source frozen by the `PROCESSING BreakdownRun`:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ each ShotRevisionItem.reference_clip_path
```

It does not rediscover historical input from Current `v2_shots`.

Each Reference Clip is sampled at multiple deterministic positions across the Shot. P2.3 intentionally does **not** rely on one middle thumbnail, because subtitles/phone screens/signage can be transient.

## 5. Output contract

P2.3 emits only anonymous raw:

```text
OCR_OBSERVATION
```

Each observation preserves:

```text
exact shot_revision_item_id
Episode source_start_us/source_end_us
text
project source language
provider confidence when valid
polygon_px
bbox_px
polygon_norm
frame width/height
frame sample index
frame-relative requested microseconds
recognition-language profile
```

OCR frame observations use a 1µs point interval at the sampled source position. A sampled frame is not represented as a subtitle duration.

Repeated text across sampled frames remains repeated raw Evidence. P2.3 does not dedupe or infer persistence/duration. Cross-frame stitching belongs to P2.5 Fusion.

## 6. Language behavior

Project source-language values are mapped to RapidOCR PP-OCRv6 recognition profiles inside the adapter. Common routes include Simplified/Traditional Chinese, English, Japanese, Korean, Arabic-family, Cyrillic, Devanagari and Latin profiles.

The Evidence language itself remains the project source language; provider-specific recognition-language naming stays in payload/metadata.

## 7. Status/failure behavior

```text
all historical Reference Clips missing → NOT_AVAILABLE
usable frames but no recognized text      → NO_EVIDENCE
no sampled frame can be analyzed          → FAILED
explicit CUDA unavailable/load failure    → FAILED
auto CUDA load failure                    → visible CPU fallback allowed
```

The provider is lazy-loaded and reuses P2.1 immutable fingerprinted sidecar persistence plus BreakdownRun component provenance.

## 8. Protected boundaries

P2.3 does **not** write:

```text
TimelineEvent
complete ShotSemanticDraft / SceneSegmentDraft
studio_v2.Dialogue
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

It does not alter Character V10.1 thresholds, cannot-link, Face hard conflict, explicit Shot assignment or Final Gate behavior.

## 9. Focused acceptance

Seven P2.3 OCR focused tests cover the provider/contract behaviors, including deterministic multi-frame sampling, exact historical ShotRevisionItem anchoring, source microsecond timing/geometry, raw repeated observations, missing/no-evidence behavior and CUDA policy.

Latest implementation-head acceptance before final docs-only commits:

```text
Windows breakdown-p2-windows: PASS
  combined P2 provider suite: 31/31 PASS
Windows breakdown-p1-windows: PASS
Ubuntu backend compile: PASS
FastAPI import/version: PASS (2.4.1)
Ubuntu full pytest: 28 failed, 237 passed, 1 skipped
Frontend build: existing vue-tsc / TypeScript failure
```

The seven pass-count increase over P2.2 matches the seven new OCR tests. No new backend failure category was introduced. The repository as a whole is still **not globally green** because the known historical/backend-environment failures and frontend build failure remain.

Focused CI uses injected fake OCR engine/frame sampler and does not download OCR weights or claim real-video OCR quality.

## 10. P2.6 benchmark debt intentionally preserved

Do not treat PP-OCRv6 small or the current sampling interval as proven optimal yet. P2.6 must compare real short-drama material for:

```text
subtitle recall/precision
small text / phone screen / signage behavior
Chinese + target multilingual behavior
sampling interval vs transient-text recall
PP-OCRv6 small vs medium
CPU vs GPU speed/memory
Windows real-machine behavior
model cache/offline readiness
```

## 11. Next safe subphase

Only after PR #11 is merged and `main` SHA is re-verified, proceed to:

```text
P2.4 — VLM anonymous Shot semantics Provider
```

Before P2.4 coding, read current `main`, `PROJECT_STATE`, `CURRENT_IMPLEMENTATION_MANIFEST`, `BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN`, `BREAKDOWN_DRAFT_DATA_CONTRACT`, `BREAKDOWN_P2_SIDECAR_CONTRACT`, this handoff, and the actual P2.1/P2.2/P2.3 provider code/tests.

P2.4 must consume exact ShotRevisionItem/Reference Clip history, emit anonymous `VLM_OUTPUT`/support Evidence through the P2.1 contract, and must not jump ahead into P2.5 Fusion or Final Asset writes.
