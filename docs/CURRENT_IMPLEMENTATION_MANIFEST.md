# AI Drama Studio — Current Implementation Manifest

> Purpose: give a new conversation one compact, code-aligned manifest before it reads historical Feature documents.
>
> Last synchronized: **2026-08-27 12:49 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
```

## Formal Character baseline

```text
Character version: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Primary identity model: YoutuReID Person Re-identification
Face role: optional support / high-quality conflict signal
Final Gate: confirmed formal RESOLVED identity only
```

## Executable wiring

```text
content_analysis_v2
→ character_visual_v2.analyze_characters
→ character_runtime_v6.analyze_characters   # filename is compatibility-only
→ character_observation_v10.detect_observations
→ character_tracking_v10.build_tracks
→ character_identity_v101.resolve_global_identities
→ character_shot_binding_v101.recover_unresolved_tracks
→ character_evidence_store_v10.update_person_evidence_classification
→ character_persistence_v6.persist_results_v6
   └ persist per-Track identity_recovery provenance
→ asset_final_gate_v10.apply_analysis_to_assets
   └ recovered-only Shot uses Track recovery score as Shot-presence confidence
→ Character / ShotCharacterBinding
→ asset_routes_v3 workspace response
→ asset_workspace_character_v101 decorator
   ├ RESOLVED → evidence_by_shot.characters
   └ UNRESOLVED → evidence_by_shot.character_diagnostics
```

## Identity confirmation

Formal V10/V10.1 identity creation requires at least:

```text
3 independent Shots
3 model-usable Person Images
stable cross-Shot Person-ReID class
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong contaminated/substantial partial crops can seed only with stricter confirmation. Weak partial crops are evidence/attach-only.

## Shot binding recovery

V10.1 contains a second pass for a known Character that is visible in a Shot but whose individual crops remained ambiguous:

```text
UNRESOLVED Track
→ compare repeated observations to all RESOLVED identity galleries
→ >=3 usable observations
→ >=2 supporting observations
→ unique winner + margin
→ fail closed on cannot-link / Face conflict
→ attach whole Track to existing identity
```

This pass never creates a new Character.

Recovered Track persistence:

```text
CharacterTrack.evidence_json.identity_recovery = {
  source,
  target_candidate_id,
  shot_id,
  score,
  observation_count,
  policy
}
```

Formal recovery source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

## Identity confidence vs Shot presence

These are different values and are no longer treated as identical:

```text
normal/direct Track in Shot
→ ShotCharacterBinding.confidence = candidate identity confidence fallback

recovered-only Track(s) in Shot
→ ShotCharacterBinding.confidence = strongest validated Track recovery score
```

Multiple Track fragments of the same Character in one Shot still produce only one Final binding.

No DB schema migration was needed.

## Final Character materialization

Formal V10/V10.1 gate requires:

```text
identity_status == RESOLVED
formal resolver allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required for formal V10/V10.1 identities.

## Asset Workspace Character evidence

Formal API responses no longer inherit the historical face-visible-only diagnostic behavior.

```text
evidence_by_shot.characters
= RESOLVED Character evidence only
= may come from front / side / back / body-visible / recovered Track

evidence_by_shot.character_diagnostics
= UNRESOLVED diagnostics only
= no final_asset_id
= no Final-binding confidence
```

This prevents `待解析人物` fragments from replacing/contaminating the Final Character suggestion while still retaining diagnostic evidence.

## Fixed model package

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

V10.1 reuses the V10 model package. Therefore `content_models_v2.model_status()` can still expose a V10 model-package profile while the formal runtime/resolver is V10.1.

## Current key modules

```text
engine/app/main.py
engine/app/content_analysis_v2.py
engine/app/content_models_v2.py
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_observation_v10.py
engine/app/character_person_evidence_v10.py
engine/app/character_person_features_v9.py
engine/app/character_tracking_v10.py
engine/app/character_identity_v10.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_persistence_v6.py
engine/app/character_gallery_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_v3.py
engine/app/asset_workspace_character_v101.py
engine/app/asset_routes_v3.py
frontend/src/types/studio.ts
```

Do not infer formal algorithm version from individual filenames.

## Current validation state

```text
Character V10.1 implementation: implemented
Risky-view identity creation: implemented
Known-identity Track recovery: implemented
Per-Track recovery provenance: implemented
Shot-presence confidence separation: implemented
Face-optional workspace Character evidence: implemented
RESOLVED/UNRESOLVED workspace evidence separation: implemented
V10/V10.1 Final Gate: implemented
Real Windows short-drama validation after latest binding change: pending
Whole repository CI: not green
```

Recent CI still shows backend compile and FastAPI import passing before the existing full-pytest failure. Frontend build remains blocked by the existing vue-tsc/TypeScript compatibility issue. Known backend failure categories include missing full `cv2`/MOT/media runtime, legacy assertions, and FFmpeg/runtime assumptions.

## New-conversation guardrail

Before proposing or coding a Character change, verify these facts from code:

```text
character_visual_v2.py points to the expected runtime/resolver
character_runtime_v6.runtime_status()["profile"] matches this manifest
character_persistence_v6.py preserves formal V10/V10.1 profile + identity_recovery
asset_final_gate_v10.py includes the active resolver in the formal allow-list
asset_routes_v3.py decorates workspace Character evidence through asset_workspace_character_v101
```

If any one differs, update this manifest and `PROJECT_STATE.md` before continuing.

## Documents that describe the current Character implementation

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

Older V1–V10 planning/implementation notes are historical unless explicitly referenced by these current documents.
