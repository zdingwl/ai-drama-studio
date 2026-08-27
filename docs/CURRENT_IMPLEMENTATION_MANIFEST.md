# AI Drama Studio — Current Implementation Manifest

> Purpose: give a new conversation one compact, code-aligned manifest before it reads historical Feature documents.
>
> Last synchronized: **2026-08-27 12:12 +08:00**

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
→ persist CharacterCandidate / CharacterTrack
→ asset_final_gate_v10.apply_analysis_to_assets
→ Character / ShotCharacterBinding
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
engine/app/character_gallery_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_v3.py
```

Do not infer formal algorithm version from individual filenames.

## Current validation state

```text
Character V10.1 implementation: implemented
Risky-view identity creation: implemented
Known-identity Track recovery: implemented
V10/V10.1 Final Gate: implemented
Real Windows short-drama validation after latest binding change: pending
Whole repository CI: not green
```

Known CI categories include missing full `cv2`/MOT/media runtime, legacy V6 expectations, FFmpeg assumptions, and frontend vue-tsc/TypeScript compatibility.

## New-conversation guardrail

Before proposing or coding a character change, verify these three facts from code:

```text
character_visual_v2.py points to the expected runtime/resolver
character_runtime_v6.runtime_status()["profile"] matches this manifest
asset_final_gate_v10.py includes the active resolver in the formal allow-list
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
