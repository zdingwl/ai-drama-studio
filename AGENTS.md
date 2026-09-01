# AI Drama Studio — Agent Entry Rules

Current product architecture: **Localized Remake V1 + local MiniMax H3 target runtime**.

The pre-restructure repository state is frozen at:

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

**Product rule:** if a result can be completed automatically with acceptable confidence, do not make it a separate user page. Only uncertain/conflicting/high-risk/repeatedly failed items enter the Review Center.

Detailed architecture: `docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md`.

## 2. Current ordinary-user UI

The formal main UI is V4:

```text
ProjectListV4
ProjectStudioV4
```

Only three primary work areas:

```text
Project
Review Center
Output
```

Legacy Stage 01-06 / P/G UIs remain compatibility/advanced tools only. Do not treat them as the current product workflow.

## 3. Current automatic workflow on main

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
→ ReviewIssue synchronization
```

Current ReviewIssue producers include:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
```

Future producers will include:

```text
SPEAKER
LOCALIZATION
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

## 4. Existing accepted internals remain usable

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
Localization immutable-source / revision safety
BackgroundTask / progress
```

Previously accepted G1/G2/P5 behavior should stay fail-closed unless a concrete regression or the new remake contract requires a deliberate migration.

## 5. Semantic safety rules that remain valid

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence != Final binding truth
same-Shot person observations = hard cannot-link
ASR source text = immutable source truth
OCR source text = immutable source truth
```

Dynamic expression/emotion/action/pose/speaking/screen position/framing are not identity keys.

Character V10.1 identity safety must not be relaxed simply to reduce ReviewIssues. The product solution for uncertainty is **human confirmation in Review Center**, not unsafe auto-merging.

## 6. New current product data foundations

### ProjectRemakePolicy

```text
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

### ReviewIssue

Unified attention queue. It is not a second source of domain truth.

Domain correction remains in Shot / Asset / Dialogue / Generation APIs; ReviewIssue records why attention is needed and whether it was resolved.

## 7. Next development frontier

Do **not** continue the old Stage 05 plan.

Next order:

```text
R2 SourceDramaSnapshot facade
R4 TargetCharacter + SceneLocalizationMapping
R5 automatic target dialogue + TTS
R6 Dialogue Timing Engine + RemakeTimeline
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 automatic generation QC / retry
R10 Lip Sync + audio/subtitle/episode assembly
R11 legacy cleanup after dependencies are migrated
```

`Shot != GenerationSegment` must be preserved: Shot is source directing/editing structure; GenerationSegment is the actual H3 execution unit.

## 8. Git workflow

```text
Documentation-only change:
  -> edit main directly

Code/behavior change:
  -> edit main directly by default

Only create/use another branch or PR when the user explicitly asks.

All commits:
  -> include [skip ci]
  -> hosted GitHub Actions are not acceptance evidence
```

Current requested backup branch must remain untouched unless the user explicitly asks to change it.

## 9. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
4. docs/PROJECT_STATE.md
5. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
6. relevant current code/tests
7. old P/G docs only when maintaining those internals
```

When old docs conflict with this file on **product workflow**, this file + `PRODUCT_REMAKE_ARCHITECTURE_V1.md` are authoritative.
