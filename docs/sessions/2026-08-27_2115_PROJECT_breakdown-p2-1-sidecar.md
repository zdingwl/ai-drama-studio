# Breakdown P2.1 — Provider / Raw Evidence Sidecar Handoff

> Date: 2026-08-27  
> Repository: `zdingwl/ai-drama-studio`  
> Feature branch: `feat/breakdown-p2-1-evidence-sidecar`  
> PR: #9 `feat: start Breakdown P2 evidence sidecar`  
> Base main at start: `248ed1427a2ce93425a067b135c25c112cd720e0`  
> Phase: **P2 IN PROGRESS / P2.1 COMPLETE / P2.2 NEXT**

## 1. What P2.1 completed

P2.1 establishes the provider/raw-Evidence sidecar underneath the already-closed P1 anonymous Draft runtime.

Formal module:

```text
engine/app/breakdown_p2_sidecar_v1.py
```

Formal contract:

```text
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
schema = breakdown-p2-evidence-v1
```

A Provider no longer guesses Current Shots. It consumes one exact `PROCESSING BreakdownRun` source snapshot:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ Reference Clip / thumbnail / keyframes
+ Episode preprocess audio_path
+ Project source_language
```

## 2. Unified Provider boundary

P2.1 defines one synchronous-local Adapter Contract for:

```text
ASR
OCR
VLM
```

Standardized result:

```text
component
provider
model
status
evidence[]
metadata
warnings
```

Raw Evidence source types:

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

This layer is intentionally model-brand independent. P2.2/P2.3/P2.4 should implement adapters against this boundary rather than leaking SDK-specific objects into business/Fusion code.

External asynchronous/paid providers are not allowed to pretend to be synchronous; they must first use the persistent Job rules in `docs/PROVIDER_JOB_RULES.md`.

## 3. Evidence persistence

Raw Provider Evidence is physically separated from future fused Draft rows:

```text
workspace/<project_id>/episodes/<episode_id>/breakdown/<run_id>/evidence/
  asr/<sha256-fingerprint>.json
  ocr/<sha256-fingerprint>.json
  vlm/<sha256-fingerprint>.json
```

Properties:

```text
stable normalized JSON
content SHA-256 fingerprint
same result = same artifact path
changed result = new artifact
no overwrite of historical evidence
atomic .tmp → os.replace
```

`BreakdownRun.component_status_json` and `provider_metadata_json` only keep compact component/artifact provenance; they are not copies of the raw model result.

## 4. Fail-closed boundaries

P2.1 rejects:

```text
non-PROCESSING Run
STALE Run
source ShotRevision no longer Current
unknown component/status/source type
invalid source time pair
shot-bound evidence outside its exact ShotRevisionItem
confidence outside 0..1
READY result with no Evidence
non-READY result carrying consumable Evidence
```

The anonymous boundary recursively rejects business Final IDs such as:

```text
character_id
scene_id
prop_id
asset_revision_id
speaker_character_id
shot_character_binding_id
shot_scene_binding_id
shot_prop_binding_id
```

This prevents VLM/ASR metadata from silently bypassing later identity/asset resolution.

## 5. ShotRevision race protection

Provider work may be long-running, so P2.1 checks source revision at multiple points:

```text
before provider work
before raw artifact persistence
after artifact persistence before Run provenance update
```

If ShotRevision changed meanwhile, old results cannot become active evidence for the new Current revision.

P1.6 still owns automatic Run → STALE when ShotRevision changes.

## 6. `BreakdownEvidenceLink` rule

P2.1 does **not** fabricate a Run-level `BreakdownEvidenceLink` because P1 owner types are Draft entities, not Run.

P2.5 Fusion will create links only when an actual Draft owner consumes raw Evidence:

```text
SHOT_DRAFT
LOCAL_SUBJECT
TIMELINE_EVENT
SCENE_SEGMENT
PROP_HINT
```

This keeps provenance truthful.

## 7. Tests / CI

New focused file:

```text
engine/tests/v2/test_breakdown_p2_sidecar_v1.py
```

Five tests cover:

```text
exact ShotRevisionItem provider context
Episode audio/source-language/reference/keyframe input
idempotent fingerprinted raw Evidence persistence
Run component/provenance metadata
no Character/Scene/Prop materialization
Final Asset ID leakage fail-closed
STALE Run rejection after ShotRevision change
shot-bound evidence timing validation
Windows Chinese/space workspace paths
```

A separate durable Windows job was added:

```text
job: breakdown-p2-windows
```

Acceptance on PR head before docs-only synchronization:

```text
Windows Breakdown P2 suite: 18/18 PASS
Windows Breakdown P1 regression gate: PASS
Ubuntu compile: PASS
FastAPI import/version: PASS (2.4.1)
Ubuntu full pytest: 28 failed, 224 passed, 1 skipped
Frontend: existing vue-tsc/TypeScript build failure
```

The five extra Ubuntu passes are exactly the five new P2.1 tests. The same 28 historical backend failures remain; P2.1 introduced no new failure category.

## 8. Explicit non-goals preserved

P2.1 did not implement:

```text
real ASR inference
OCR inference
VLM semantic inference
speaker → LocalSubject fusion
ASR/OCR/VLM Fusion
SceneSegmentDraft/ShotSemanticDraft/TimelineEvent generation
Breakdown publish orchestration
P3 UI
```

It did not write or change:

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
AssetRevision
Character V10.1 identity thresholds/gates
```

No database table/schema was added in P2.1.

## 9. Historical helper warning

`engine/app/content_analysis_v2.py` still has historical helper code including:

```text
_run_asr()
_run_diarization()
_attach_speakers()
_map_speaker_to_character()
```

Do not promote the old `ASR → AnalysisDialogue → CharacterCandidate` chain to P2.

P2 speaker information must stay anonymous. A speaker label may help build `LocalSubject` later, but cannot directly become a Character identity.

## 10. Next safe step — P2.2 only

P2.2 should implement the formal ASR Adapter against `BreakdownP2Provider` and preserve raw timing Evidence:

```text
Episode audio
→ ASR segment timing
→ word timing
→ P2EvidenceRecord(ASR_SEGMENT)
→ P2EvidenceRecord(ASR_WORD)
→ P2 sidecar artifact
```

Do not fuse to Character or Final assets in P2.2.

Before choosing/locking the ASR model configuration, compare the current viable local candidates for short-drama Chinese/multilingual accuracy, word timing, Windows/CUDA support, performance, model license and offline deployment. The existing `faster-whisper` dependency is a useful baseline candidate, not automatically the final winner.

## 11. Recovery order for next conversation

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ this handoff
→ current P2 code/tests
```

Always verify `main` SHA first. Repository `main` after PR #9 merge is the authority, not the pre-merge branch SHA recorded here.