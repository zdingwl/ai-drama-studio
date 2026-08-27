# F06 — Function Contracts（LEGACY / SUPERSEDED）

> **Status:** LEGACY HISTORY — NOT CURRENT EXECUTABLE CONTRACT  
> The old F06 function/API plan has been retired by the Reference Video V2 asset workflow and Character V10.1 implementation.

Do not implement or restore the old planned functions such as:

```text
get_character_detection()
run_character_detection()
rerun_character_detection()
_build_sample_plan(...)
_detect_and_embed_faces(...)
_cluster_tracks(...)
```

or the old `/character-detection` API family merely because they are documented in Git history.

## Current formal function flow

```text
content_analysis_v2
→ character_visual_v2.analyze_characters
→ character_runtime_v6.analyze_characters
→ character_observation_v10.detect_observations
→ character_tracking_v10.build_tracks
→ character_identity_v101.resolve_global_identities
→ character_shot_binding_v101.recover_unresolved_tracks
→ character_evidence_store_v10.update_person_evidence_classification
→ persist CharacterCandidate / CharacterTrack
→ asset_final_gate_v10.apply_analysis_to_assets
→ Character / ShotCharacterBinding
```

`character_runtime_v6.py` is a compatibility filename; its formal runtime is Character V10.1.

## Current public compatibility/model endpoints

Current asset analysis/model APIs are documented in:

```text
docs/F05_CONTENT_ANALYSIS_V2.md
```

and include the current `/api/models/f05/*` and `/api/projects/{project_id}/content-analysis*` compatibility routes plus task-based asset routes used by the UI.

## Current authority

Read in this order:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
current code
```

The previous detailed F06 function contract remains available in Git history only.
