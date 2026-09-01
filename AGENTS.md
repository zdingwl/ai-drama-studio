# AI Drama Studio — Agent Entry Rules

Current product architecture: **Localized Remake V1 + local MiniMax H3 target runtime**.

Rollback snapshot:

```text
branch: backup/pre-h3-remake-restructure-2026-09-01
commit: 37944c693a08c6ff292b08e1f73b1249812cabae
```

## 1. Highest product definition

AI Drama Studio receives an existing short drama, understands its content/directing structure, and remakes a localized short drama for the Project target language and target region.

Source drama provides:

```text
story
shot/edit structure
actions/performance
blocking/composition/camera
Reference Video
dialogue relationships
```

Target drama changes:

```text
characters -> localized Target Characters (required)
scene -> KEEP / LOCALIZE / AUTO
language -> target language
voice -> Target Character voice
lip movement -> final target audio
timeline -> may extend/trim/reflow for target speech duration
video generation -> local MiniMax H3
```

**Product rule:** automatic work is background work, not a page. Only uncertain/conflicting/high-risk/repeatedly failed items enter Review Center.

Detailed architecture: `docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md`.

## 2. Current ordinary-user UI

Formal UI:

```text
ProjectListV4
ProjectStudioV4
```

Primary work areas:

```text
Project
Review Center
Output
```

Legacy Stage 01-06 / P/G UIs are compatibility/advanced tools only.

## 3. Current automatic workflow

One-click task:

```text
AUTO_REMAKE_PREP_V1
```

Current executable scope:

```text
Project/Episodes
→ automatic preprocess when needed
→ Current Shot detection / Reference Clips when needed
→ Breakdown ASR + OCR + Qwen3-VL + Fusion
→ Character V10.1 / Scene / Prop extraction
→ Final Asset application under existing safety rules
→ Shot / Character / Asset ReviewIssue sync
→ project SourceDramaSnapshot
→ Speaker ReviewIssue sync
```

Current ReviewIssue producers:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
```

Future producers:

```text
LOCALIZATION
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

## 4. SourceDramaSnapshot is now the downstream source boundary

R2 is implemented on `main`.

Future remake modules must consume:

```text
SourceDramaSnapshot
```

instead of directly depending on G2/P5/P6/P7 product naming.

APIs:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

The Snapshot is a deterministic current read facade, not a duplicate truth database. Downstream persisted models must anchor its `source_fingerprint`.

It contains source-only facts. Target dialogue, TargetCharacter, target scene, TTS, target timing and H3 output are forbidden from this Contract.

Read `docs/SOURCE_DRAMA_SNAPSHOT_V1.md` before changing downstream remake models.

## 5. Existing accepted internals remain usable

Do not delete or weaken accepted internals merely because their old names are no longer product concepts.

Still valuable:

```text
FFmpeg / FFprobe
Source PTS authority
ShotRevision + manual Shot edits
TransVLM/current shot runtime + cache
frame-exact Reference Clip rendering
Faster-Whisper ASR
RapidOCR
Qwen3-VL Breakdown
Window Context / Exact Shot
Scene Timeline structured facts
Character V10.1 Person Evidence / tracking / ReID
Final Character/Scene/Prop + Shot bindings
AssetRevision
P5/P6 compatibility layers while SourceDramaSnapshot still consumes them
Localization revision safety where legacy code still depends on it
BackgroundTask / progress
```

Previously accepted G1/G2/P5 behavior stays fail-closed unless a concrete regression or deliberate migration requires change.

## 6. Semantic safety rules

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence != Final binding truth
same-Shot person observations = hard cannot-link
ASR source text = immutable source truth
OCR source text = immutable source truth
SourceDramaSnapshot target-side fields = forbidden
```

Character V10.1 identity safety must not be relaxed to reduce ReviewIssues. Ambiguity belongs in Review Center.

## 7. Current product data foundations

### ProjectRemakePolicy

```text
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

### ReviewIssue

Unified attention queue; not a second source of domain truth.

### SourceDramaSnapshot

Single downstream source-read boundary with stable source keys and `source_fingerprint`.

## 8. Next development frontier

Do **not** continue the old Stage 05 plan.

Current order:

```text
R2 SourceDramaSnapshot                  = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R4 TargetCharacter + SceneLocalizationMapping = NEXT
R5 automatic target dialogue + TTS
R6 Dialogue Timing Engine + RemakeTimeline
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 automatic generation QC / retry
R10 Lip Sync + audio/subtitle/episode assembly
R11 legacy cleanup after dependencies are migrated
```

`Shot != GenerationSegment` must be preserved.

## 9. Git workflow

```text
Documentation-only change -> main directly
Code/behavior change -> main directly by default
Only create/use another branch or PR when the user explicitly asks
All commits -> [skip ci]
Hosted GitHub Actions -> not acceptance evidence
```

The backup branch is rollback-only.

## 10. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
4. docs/PROJECT_STATE.md
5. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
6. docs/SOURCE_DRAMA_SNAPSHOT_V1.md when working downstream
7. relevant current code/tests
8. old P/G docs only when maintaining those internals
```
