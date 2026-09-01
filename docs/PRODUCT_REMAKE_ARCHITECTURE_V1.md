# AI Drama Studio — Localized Remake Architecture V1

Status: CURRENT PRODUCT DIRECTION  
Date: 2026-09-01

## 1. Product definition

AI Drama Studio is not a generic video-analysis platform and not a simple dubbing tool.

The product receives an existing short drama, understands its story and directing structure, then remakes a new localized drama for the Project target language and target region.

The source drama is used as:

- story reference;
- shot/editing reference;
- acting/action reference;
- blocking/composition/camera reference;
- timing reference;
- Reference Video input for generation.

The target drama changes:

- characters: always localized/replaced;
- dialogue language: always target language;
- voice: target character voice;
- lip movement: synced to final target audio;
- scene: KEEP / LOCALIZE / AUTO according to project policy;
- timeline: may change because target-language speech duration differs from source speech.

Final video generation engine: **local MiniMax H3**.

## 2. Highest product rule

> If the system can complete something automatically with acceptable confidence, do not make it a product page.

> Only uncertain, conflicting, high-risk, or repeatedly failed results enter the human Review Center.

Internal implementation layers may remain complex, but the ordinary user flow must stay simple.

## 3. User-facing workflow

The main UI has only three primary work areas:

1. **Project**
   - project name;
   - source language;
   - target language;
   - target region;
   - scene localization policy;
   - episode import / reorder / delete;
   - one-click automatic processing.

2. **Review Center**
   - only issues that need human judgement;
   - shot boundary correction;
   - character identity merge/split/confirmation;
   - Shot Character/Scene/Prop binding correction;
   - speaker correction;
   - localization ambiguity;
   - dialogue timing conflict;
   - H3 QC failures;
   - lip-sync QC failures.

3. **Output**
   - generation progress;
   - failed/retried segments;
   - selected generations;
   - episode preview;
   - export.

Legacy Stage 01-06 components remain temporarily available as advanced/compatibility tools but no longer define product architecture.

## 4. Automatic pipeline

```text
Project + Episodes
        ↓
Preprocess
        ↓
Shot Detection + Reference Clips
        ↓
Shot QC
        ↓
ASR + OCR + Qwen3-VL
        ↓
Source Drama Snapshot
        ↓
Character / Scene / Prop extraction and binding
        ↓
Target Character / Target Scene localization
        ↓
Target dialogue translation + localization
        ↓
TTS
        ↓
Dialogue Timing Engine
        ↓
Target Remake Timeline
        ↓
H3 Context Compiler
        ↓
MiniMax H3 Local
  Ref2VA main remake
  FL2VA extension / bridge / repair
        ↓
Lip Sync + Audio + Subtitle
        ↓
Automatic QC
        ↓
Episode assembly / export
```

Any stage that cannot decide safely creates a `ReviewIssue` instead of a new product page.

## 5. Existing code that remains authoritative internally

The following existing capabilities remain valuable and should not be removed merely because their old Stage/P/G names are no longer product concepts:

- FFmpeg / FFprobe media handling;
- Source PTS time authority;
- ShotRevision and manual Shot edits;
- current TransVLM/shot detection runtime and cache;
- Reference Clip renderer;
- Faster-Whisper ASR;
- RapidOCR;
- Qwen3-VL Breakdown;
- Window Context + Exact Shot understanding;
- Scene Timeline structured facts;
- Character V10.1 Person Evidence / tracking / ReID;
- Final Character/Scene/Prop and Shot bindings;
- AssetRevision history;
- Localization source immutability and revision safety;
- persistent BackgroundTask / progress infrastructure.

These are implementation modules, not user workflow stages.

## 6. Current new V1 foundation on main

Added on 2026-09-01:

- `ProjectRemakePolicy`
  - `scene_policy = AUTO | KEEP | LOCALIZE`
  - `character_policy = LOCALIZE`
  - `generation_engine = MINIMAX_H3_LOCAL`
- unified `ReviewIssue` queue;
- automatic Shot/Asset/Character issue synchronization;
- one-click `AUTO_REMAKE_PREP_V1` source-analysis task;
- V4 project list and studio shell;
- main UI reduced to Project / Review / Output.

The current one-click task covers:

```text
Preprocess
→ Shot Detection
→ Breakdown (ASR/OCR/Qwen3-VL/Fusion)
→ Character/Scene/Prop extraction
→ ReviewIssue synchronization
```

It does **not yet** mean the full remake pipeline is complete.

## 7. Next backend data model

### 7.1 SourceDramaSnapshot

Create one stable downstream read model that hides P5/P6/P7 naming and exposes only information needed to remake the drama:

- episode / scene / shot;
- source timing;
- Reference Video;
- source characters;
- final source Character/Scene/Prop binding where known;
- action/performance;
- source dialogue and speaker;
- OCR;
- cinematography.

P5/P6/P7 may continue implementing this internally until migration is complete.

### 7.2 TargetCharacter

Source Character and localized Target Character must be separate entities.

```text
Source Character
      ↓ mapping
Target Character
```

TargetCharacter owns:

- localized name/identity;
- target-region appearance design;
- reference images/video;
- target voice;
- stable generation identity.

### 7.3 SceneLocalizationMapping

```text
source_scene_id
policy = KEEP | LOCALIZE
target_scene_id / target scene references
```

AUTO policy resolves to KEEP or LOCALIZE and creates ReviewIssue only when ambiguous/high-risk.

### 7.4 TargetDialogue

Target dialogue must not be treated as a text-only translation field.

It needs:

- source dialogue anchor;
- translated text;
- localized/final text;
- character/speaker;
- voice;
- generated audio path;
- speech duration;
- timing quality status.

### 7.5 RemakeTimeline

Source timeline is not final timeline.

Each shot/segment needs:

- `source_duration_us`;
- `target_speech_duration_us`;
- `planned_duration_us`;
- `timing_strategy`.

Timing strategies include:

- KEEP;
- REWRITE_SHORTER;
- TRIM;
- EXTEND;
- CARRY_OVER_REACTION;
- REGENERATE_EXTENSION;
- HUMAN_REVIEW.

### 7.6 GenerationSegment

`Shot != GenerationSegment`.

Shot is the source directing/editing unit. GenerationSegment is the actual H3 generation unit and may contain one or more short Shots or a generated extension around a Shot.

GenerationSegment needs:

- source Shot references;
- Reference Video(s);
- target character references;
- target scene references;
- target audio;
- target duration;
- H3 mode;
- prompt/context package;
- generation versions;
- QC state;
- selected output.

## 8. MiniMax H3 integration target

Create internal modules rather than product pages:

### H3RuntimeManager

- local model status;
- model paths;
- GPU/runtime capability;
- start/stop/load state;
- Ref2VA execution;
- FL2VA execution;
- local queue and failure handling.

### H3ContextCompiler

Compile AI Drama Studio structured remake data into H3 inputs:

```text
Reference Video
+ Target Character references
+ Target Scene references when localized
+ Target Dialogue audio
+ actions/performance
+ camera/composition constraints
+ target duration
```

### H3GenerationService

- versioned generations;
- retry policy;
- QC;
- selected output;
- later high-resolution regeneration path when available.

## 9. Dialogue timing is a first-class subsystem

Do not force target dialogue into the original duration.

Required flow:

```text
source dialogue
→ translation/localization
→ TTS
→ real target speech duration
→ compare with available shot/reaction time
→ automatically choose timing strategy
```

Do not solve long dialogue by globally slowing video or unnaturally accelerating speech.

Preferred strategy order:

1. wording optimization without semantic loss;
2. use existing pauses/available shot time;
3. carry audio across reaction shots when editorially valid;
4. extend/regenerate shot naturally;
5. human ReviewIssue when no safe automatic strategy exists.

## 10. ReviewIssue contract

All future uncertain stages publish to one queue.

Core fields:

```text
project_id
episode_id
shot_id
source_key
issue_type
severity
status
reason
ai_suggestion
editable_payload
resolution
```

Issue types will grow to include:

- SHOT_BOUNDARY;
- CHARACTER_IDENTITY;
- ASSET_BINDING;
- SPEAKER;
- LOCALIZATION;
- DIALOGUE_TIMING;
- H3_QC;
- LIP_SYNC_QC.

Domain-specific correction APIs remain authoritative. ReviewIssue records attention and resolution state; it must not become a second copy of Character/Shot/Dialogue truth.

## 11. Removal policy

Do not mass-delete legacy code yet.

Safe cleanup order:

1. new V4 user workflow becomes stable;
2. new downstream models stop depending on legacy user-facing Stage contracts;
3. global import/API/test search confirms a legacy component is no longer required;
4. remove legacy UI;
5. then remove compatibility backend layers only after dependencies are migrated.

The backup branch created before this restructuring is:

`backup/pre-h3-remake-restructure-2026-09-01`

It points to pre-restructure main commit:

`37944c693a08c6ff292b08e1f73b1249812cabae`
