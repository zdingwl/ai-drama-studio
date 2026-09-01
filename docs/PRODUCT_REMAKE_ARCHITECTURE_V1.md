# AI Drama Studio — Localized Remake Architecture V1

Status: **CURRENT PRODUCT DIRECTION**  
Date: 2026-09-01

## 1. Product definition

AI Drama Studio is a localized short-drama remake system, not a generic video-analysis platform and not a simple dubbing tool.

The product receives an existing short drama, understands its story/directing structure, then remakes a new localized drama for the Project target language and target region.

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
- scene: KEEP / LOCALIZE / AUTO according to Project policy;
- timeline: may change because target-language speech duration differs from source speech.

Final video generation engine: **local MiniMax H3**.

## 2. Highest product rule

> If the system can complete something automatically with acceptable confidence, do not make it a product page.

> Only uncertain, conflicting, high-risk, or repeatedly failed results enter the human Review Center.

Internal implementation layers may stay complex, but the ordinary-user flow must stay simple.

## 3. User-facing workflow

The main UI has only three primary work areas:

### Project

- project name;
- source language;
- target language;
- target region;
- scene localization policy;
- Episode import / reorder / delete;
- one-click automatic processing.

### Review Center

Only issues needing human judgement:

- shot boundary correction;
- character identity merge/split/confirmation;
- Shot Character/Scene/Prop binding correction;
- speaker correction;
- localization ambiguity;
- dialogue timing conflict;
- H3 QC failures;
- lip-sync QC failures.

### Output

- generation progress;
- failed/retried segments;
- selected generations;
- Episode preview;
- export.

Legacy Stage 01-06 components remain compatibility/advanced tools while migration is incomplete.

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
Character / Scene / Prop extraction and safe binding
        ↓
SourceDramaSnapshot
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

Keep the accepted capabilities that already work:

- FFmpeg / FFprobe media handling;
- Source PTS time authority;
- ShotRevision and manual Shot edits;
- current TransVLM/shot detection runtime and cache;
- frame-exact Reference Clip renderer;
- Faster-Whisper ASR;
- RapidOCR;
- Qwen3-VL Breakdown;
- Window Context + Exact Shot understanding;
- Scene Timeline structured facts;
- Character V10.1 Person Evidence / tracking / ReID;
- Final Character/Scene/Prop and Shot bindings;
- AssetRevision history;
- existing P5/P6 safety/read layers while the migration facade still consumes them;
- persistent BackgroundTask / progress infrastructure.

These are implementation modules, not product workflow stages.

## 6. Current implemented remake foundation

### ProjectRemakePolicy

```text
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

### Unified ReviewIssue

Current automatic source-side issue types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
```

### One-click source understanding

```text
AUTO_REMAKE_PREP_V1
```

Current chain:

```text
Preprocess
→ Shot Detection
→ Breakdown ASR/OCR/Qwen3-VL/Fusion
→ Character/Scene/Prop extraction
→ Final Asset application
→ source-side ReviewIssue sync
→ SourceDramaSnapshot
```

### Formal V4 UI

```text
Project
Review Center
Output
```

## 7. SourceDramaSnapshot V1 — IMPLEMENTED

R2 is implemented on `main`; local/real-material acceptance is still pending.

The Snapshot is the single product-facing source read model:

```text
G2 / P5 / P6 / Final Asset internals
                ↓
      SourceDramaSnapshot V1
                ↓
all future remake models
```

It is a deterministic current read facade, **not** another duplicate business-truth database.

Episode endpoint:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
```

Project endpoint:

```text
GET /api/projects/{project_id}/source-drama-snapshot
```

It exposes:

- Episode / Scene / Shot hierarchy;
- source timing;
- ShotRevision and Reference Video anchors;
- source people and safely resolved Final Character identity;
- Final Scene/Prop overlays when current bindings support them;
- action/performance;
- verbatim source dialogue;
- speaker person keys;
- OCR;
- cinematography;
- deterministic `source_fingerprint`.

Target-side fields are forbidden from the Contract.

Downstream persisted models must store the source fingerprint and become stale when the current source fingerprint changes.

Detailed contract: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 8. Next model: TargetCharacter

Source Character and localized Target Character must be separate entities.

```text
Source Character
      ↓ mapping
Target Character
```

TargetCharacter should own:

- `source_character_id`;
- source snapshot fingerprint anchor;
- localized character name/identity;
- target-region appearance design;
- stable reference images/video;
- target voice identity;
- generation identity/status.

Source Character rows must never be renamed/repainted into target characters.

High-confidence automatic design can proceed without a page. Main cast identity/design ambiguity creates ReviewIssue.

## 9. SceneLocalizationMapping

Scene policy is Project-level:

```text
AUTO
KEEP
LOCALIZE
```

Per source Scene the system resolves:

```text
source_scene_key
source_final_scene_id when available
requested_policy
resolved_policy = KEEP | LOCALIZE
source_fingerprint
localized scene design/references when needed
```

`AUTO` should normally resolve automatically from visible regional/cultural evidence. Only ambiguous/high-risk decisions enter Review Center.

## 10. TargetDialogue

Target dialogue is not just a translation string.

It needs:

- source `dialogue_key`;
- source fingerprint;
- translated text;
- localized/final text;
- target Character / Voice;
- generated audio path;
- real speech duration;
- timing quality/status.

The source text in SourceDramaSnapshot is immutable.

## 11. Dialogue timing is first-class

Do not force target speech into source duration.

```text
source dialogue
→ translation/localization
→ TTS
→ real target speech duration
→ compare with Shot/reaction time
→ choose timing strategy
```

Timing strategies:

```text
KEEP
REWRITE_SHORTER
TRIM
EXTEND
CARRY_OVER_REACTION
REGENERATE_EXTENSION
HUMAN_REVIEW
```

Preferred order:

1. wording optimization without semantic loss;
2. use existing pauses/available time;
3. carry audio across reaction shots when editorially valid;
4. naturally extend/regenerate the visual;
5. ReviewIssue when no safe automatic strategy exists.

Never solve this by globally slowing video or unnaturally accelerating speech.

## 12. RemakeTimeline

Source timeline is not final timeline.

Each planned Shot needs:

```text
source_shot_key
source_duration_us
target_speech_duration_us
planned_duration_us
timing_strategy
```

The complete target Episode duration may differ from the source Episode duration.

## 13. GenerationSegment

Critical rule:

```text
Shot != GenerationSegment
```

Shot is the source directing/editing unit. GenerationSegment is the actual H3 generation unit and may cover one Shot, multiple short Shots, or an extension/repair around a Shot.

GenerationSegment needs:

- source Shot references;
- Reference Video(s);
- Target Character references;
- Target Scene references when localized;
- target audio;
- target duration;
- H3 mode;
- compiled generation context;
- generation versions;
- QC state;
- selected output.

## 14. MiniMax H3 integration target

### H3RuntimeManager

- local model paths/status;
- GPU/runtime capability;
- load/start/stop state;
- local task queue;
- Ref2VA execution;
- FL2VA execution;
- failure handling.

### H3ContextCompiler

Compile structured remake data into:

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
- future high-resolution regeneration path.

## 15. ReviewIssue contract

ReviewIssue is an attention queue, not a second truth database.

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

Current and planned types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
LOCALIZATION
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

Domain correction APIs remain authoritative.

## 16. Removal policy

Do not mass-delete legacy code yet.

Safe order:

1. V4 workflow stays stable;
2. downstream remake models depend on SourceDramaSnapshot instead of legacy user-facing Stage contracts;
3. global import/API/test search confirms a legacy layer is no longer required;
4. remove legacy UI;
5. remove compatibility backend layers only after dependencies are migrated.

Backup branch:

```text
backup/pre-h3-remake-restructure-2026-09-01
```

Pre-restructure commit:

```text
37944c693a08c6ff292b08e1f73b1249812cabae
```

## 17. Current development order

```text
R2 SourceDramaSnapshot                  = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R4 TargetCharacter + SceneMapping       = NEXT
R5 target dialogue + TTS                = NOT STARTED
R6 Dialogue Timing + RemakeTimeline     = NOT STARTED
R7 local MiniMax H3 RuntimeManager      = NOT STARTED
R8 H3 ContextCompiler + Generation      = NOT STARTED
R9 automatic QC / retry                 = NOT STARTED
R10 Lip Sync + assembly / export        = NOT STARTED
R11 legacy cleanup                      = LATER
```
