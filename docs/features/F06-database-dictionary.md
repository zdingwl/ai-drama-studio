# F06 — Database Dictionary（LEGACY / SUPERSEDED）

> **Status:** LEGACY HISTORY — DO NOT USE FOR CURRENT MIGRATIONS

The former F06 database plan (`character_detection_runs`, old standalone F06 candidate/track schema) belongs to the superseded 35-Feature architecture.

Current Character/asset persistence is part of Reference Video V2 asset analysis and Final Asset workspace.

Current important tables include:

```text
v2_content_analysis_runs
v2_character_candidates
v2_character_tracks
v2_scene_candidates
v2_shot_scene_evidence
v2_prop_candidates
v2_shot_prop_evidence
```

Final Asset / Binding tables are defined by the current asset workspace implementation, including project-level Character and `ShotCharacterBinding` records.

For current database and runtime facts, inspect:

```text
engine/app/content_analysis_v2.py
engine/app/asset_workspace_v3.py
engine/app/asset_final_gate_v10.py
```

and read:

```text
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/F05_CONTENT_ANALYSIS_V2.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

The old detailed F06 schema remains available in Git history only. Do not create its planned migration/tables without a new explicit architecture decision.
