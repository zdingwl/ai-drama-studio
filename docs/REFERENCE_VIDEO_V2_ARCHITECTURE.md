# AI Drama Studio — Reference Video V2 Architecture

> **Current architecture document.**  
> Last synchronized: 2026-08-27.  
> Character baseline: **V10.1**.

## 1. Architecture goal

The project is not primarily a film-analysis-report generator. It is a local short-drama remake/localization workstation.

Core model:

```text
Reference Video + Structured Control Data
```

Each original Shot keeps a Reference Clip that already preserves:

- character action and blocking;
- camera motion;
- shot scale and framing;
- most spatial relationships;
- motion rhythm;
- original temporal structure.

Structured data should focus on what later localization/replacement/generation must explicitly know and control.

## 2. Current six user workspaces

The old 13-stage / 35-Feature numbering is legacy history. The current product UI/workflow is:

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Technical stages are background capabilities, not separate user pages.

## 3. 01 剧集管理

A Project represents one drama and can contain multiple Episodes.

Project localization fields include:

```text
name
source_language
target_language
target_region
```

Episode operations include import, delete/replace, append and drag reorder.

Formal batch order:

```text
Episode.sort_order
```

Heavy batch work is sequential by default:

```text
EP01 complete
→ EP02 complete
→ EP03 complete
```

## 4. 02 拉片

The output is a production Shot, not a temporary “candidate shot”.

Each current Shot owns:

```text
shot_id
episode_id
ordinal
start_us
end_us
duration_us
reference_clip
thumbnail
revision history
```

Reference Clip is a formal project asset.

Shot/Reference behavior is versioned through safe revisions. A failed rerun must not destroy the previously current valid Shot set.

All formal media time uses integer microseconds.

## 5. 03 资产

Current asset scope:

```text
Character
Scene
Key Prop
```

The asset workflow separates immutable AI Evidence from project Final Assets/Bindings.

### 5.1 Character V10.1

Formal identifiers:

```text
runtime profile:
character-v10.1-capture-first-model-classification

asset profile:
f05-assets-v10.1-person-evidence-model-classification

resolver:
person-evidence-model-classifier-v10.1
```

Formal pipeline:

```text
Shot / Reference Clip
↓
YOLOX Person Detection
↓
explicit isolated Person Instance crops
↓
Capture-first Person Evidence
  YoutuReID = primary identity model signal
  clothing/body = support
  YuNet/SFace Face = optional support / conflict
↓
Mature MOT = Shot-local temporal organization
↓
Project-level model identity classification
↓
RESOLVED / UNRESOLVED
↓
V10.1 known-identity Track recovery
↓
Final Gate
↓
Character + ShotCharacterBinding
```

Business layers:

```text
Observation / Person Evidence / Track = AI evidence
Identity Class = cross-Shot person identity
Character = project-level Final Asset
```

Track/crop/Face count must never become Character count.

### 5.2 Identity confirmation

A formal new identity requires at least:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID class
unique winner
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Face is optional.

Strong contaminated/substantial partial crops may seed only with stricter confirmation. Weak/tiny partial evidence is save/classify/attach-only.

### 5.3 Shot-level known identity recovery

After global identity resolution, one unresolved Track may attach to an already-confirmed identity only when repeated Track observations create one unique winner.

Current recovery requires repeated usable evidence and fails closed on cannot-link/Face conflict.

It never creates a new Character.

This pass exists so Character identity and Shot binding use the same resolved Track membership.

### 5.4 Final Gate

Formal V10/V10.1 Candidate materialization requires:

```text
identity_status == RESOLVED
formal resolver
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required for formal V10/V10.1 identities.

### 5.5 Scene

Scene extraction is a lighter AI Evidence layer. Current implementation prefers contiguous Episode context rather than globally grouping unrelated Shots only because their color histograms look similar.

Scene Candidate is not automatically a human semantic location name.

### 5.6 Key Prop

Prop tables/contracts exist, but the system must not fabricate “key props” when no reliable object+interaction+story-context model is configured.

Generic detected environment objects are not automatically story-critical props.

## 6. 04 内容剧本

This workspace is where source narrative/dialogue structure should converge.

Planned/partial capabilities include:

```text
ASR
Speaker Diarization
Active Speaker / Speaker → Character
OCR / VLM support
Source Dialogue
Dialogue Type
Emotion / Speaking Style
structured source script
```

Historical ASR/Speaker helpers may still exist in `content_analysis_v2.py` for compatibility, but their presence does not make them the current 03 资产 contract.

Dialogue types must be able to distinguish at least:

```text
dialogue
narration
inner_monologue
unknown
```

## 7. 05 重制设计

This is the editable production design layer.

Expected project-level controls include:

```text
Character Bible / target character assets
Scene Bible / target scene assets
Prop replacement assets
localized/final Dialogue
Voice
Shot Specification / remake strategy
```

AI suggestions can exist, but user-editable production data needs revisions and must remain separate from raw AI Evidence.

## 8. 06 生成 / 导出

Per Shot, choose the lowest-cost strategy that satisfies the requested change:

```text
REUSE_REFERENCE
AUDIO_ONLY
LIPSYNC_ONLY
CHARACTER_REPLACE
SCENE_REPLACE
PROP_REPLACE
PARTIAL_EDIT
FULL_VIDEO_REGEN
```

Typical generation inputs:

```text
Reference Clip
+ Character assets
+ Scene asset
+ Prop assets
+ Target Dialogue audio
+ Minimal generation instructions
```

Reference Video should carry original motion/framing whenever possible instead of recreating all movement from text.

Production output also needs:

```text
Voice/TTS
LipSync
QC
Timeline assembly
Final export
```

## 9. Time model

Source evidence and target production timelines are different domains.

Do not assume:

```text
original_duration_us == target_audio_duration_us == generated_duration_us == final_duration_us
```

Source Shot/Dialogue time is integer microseconds. Final production can rebuild timing after localization/generation.

## 10. Core entity relationship

```text
Project
├ Episode
│  └ Shot
│     ├ Character bindings
│     ├ Scene binding
│     ├ Prop bindings
│     ├ Dialogue / script links
│     └ Generation versions
├ Character
├ Scene
├ Prop
├ Asset
├ Voice
└ Production outputs
```

## 11. AI Evidence vs Final Data

Current asset evidence includes:

```text
ContentAnalysisRun
CharacterCandidate
CharacterTrack
Person Evidence manifest/gallery
SceneCandidate
ShotSceneEvidence
PropCandidate
ShotPropEvidence
```

Final production entities include:

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
Dialogue
```

AI Evidence should remain traceable. Human/manual revisions must not silently overwrite it.

A new AI Run must not silently overwrite a protected MANUAL/RESTORE Final Asset revision.

## 12. Current formal code map for Character

```text
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

Some filenames retain old version numbers for compatibility. Do not infer the active algorithm from filenames alone.

## 13. Current implementation status

```text
01 剧集管理: IMPLEMENTED
02 拉片: IMPLEMENTED / real Windows-video release regression remains
03 资产: Character V10.1 implemented / latest Shot Binding fix needs real-video regression
04 内容剧本: planned / partial low-level compatibility exists
05 重制设计: planned
06 生成 / 导出: planned
```

Current whole-repository CI is not globally green; do not treat legacy/environment CI failures as proof that the Character V10.1 binding change is wrong, and do not claim all tests pass.

## 14. Documentation authority

For current implementation facts read:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
current code
```

Old F01-F13/F01-F35 Feature plans and Frozen snapshots remain historical references unless one of the current documents explicitly points to them.
