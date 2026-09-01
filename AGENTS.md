# AI Drama Studio — Agent Entry Rules

Current product architecture: **Localized Remake V1 + local MiniMax H3**.

Rollback snapshot:

```text
branch: backup/pre-h3-remake-restructure-2026-09-01
commit: 37944c693a08c6ff292b08e1f73b1249812cabae
```

## 1. Highest product definition

Input an existing short drama, understand its story/directing structure, then remake a localized drama for the Project target language/region.

```text
source story / shots / actions / camera / Reference Video
→ localized characters
→ KEEP / LOCALIZE target scenes
→ target-language dialogue / voice / lip
→ timing-adjusted remake timeline
→ local MiniMax H3
→ final episode
```

Characters must be replaced. Scene policy is AUTO / KEEP / LOCALIZE. Target speech must not be forced into source timing with unnatural speed/slow-motion.

**UX rule:** automatic work is background work, not a page. Only uncertainty/conflict/high-risk/repeated failure enters Review Center.

## 2. User surface

```text
Project
Review Center
Output
```

Formal UI:

```text
ProjectListV4
ProjectStudioV4
```

Old Stage/P/G screens are compatibility/advanced only.

## 3. Current automatic workflow

```text
AUTO_REMAKE_PREP_V1

Project/Episodes
→ preprocess
→ Shot / Reference Clip
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset
→ source ReviewIssues
→ SourceDramaSnapshot
→ Speaker ReviewIssues
→ TargetCharacter / SceneLocalizationMapping
→ target ReviewIssues
```

Current ReviewIssue producers:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
```

Future producers:

```text
LOCALIZATION
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

## 4. SourceDramaSnapshot boundary

R2 is implemented.

All new downstream remake modules must consume SourceDramaSnapshot, not direct G2/P5/P6/P7 product names.

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

It is deterministic source-only current read truth with `source_fingerprint`, not another source DB.

Spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 5. Target localization boundary

R4 is implemented.

Target-side persistent models:

```text
TargetCharacter
SceneLocalizationMapping
```

Source and target assets are strictly separate.

### TargetCharacter

```text
one source Character in one Project
→ one TargetCharacter
```

Stores target-region name, stable appearance profile, generation prompt, future reference assets and confidence/review state.

### SceneLocalizationMapping

Same Final Scene across episodes must share one target scene decision:

```text
Final Scene SCENE_X
→ canonical key ASSET:SCENE_X
→ one KEEP / LOCALIZE mapping
```

Anonymous source scenes remain occurrence-local.

Project policy rules:

```text
KEEP     -> automatic KEEP
LOCALIZE -> target description required
AUTO     -> AI KEEP/LOCALIZE; low confidence -> REVIEW
```

R4 reuses the configured local Qwen3-VL OpenAI-compatible endpoint. Do not create another model server for the same planning work without a concrete need.

Spec: `docs/TARGET_LOCALIZATION_V1.md`.

## 6. Freshness rules

Downstream target data must fail closed when stale.

```text
SourceDramaSnapshot fingerprint change
local source Character signature change
canonical source Scene signature change
Project scene policy change
Project target language/region change
```

Manual target decisions survive ordinary reruns only while their relevant local source signature remains unchanged.

## 7. Existing internals to preserve

```text
FFmpeg / FFprobe
Source PTS
ShotRevision + manual Shot edits
TransVLM shot runtime/cache
Reference Clip
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Window / Exact Shot
Scene Timeline
Character V10.1
Final Character/Scene/Prop + Shot bindings
AssetRevision
P5/P6 compatibility while required by SourceDramaSnapshot
BackgroundTask / progress
```

Do not weaken accepted Character identity gates to reduce ReviewIssues.

## 8. Semantic invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
Source Character != TargetCharacter
Source Scene != Target Scene decision
same-Shot observations = hard cannot-link
ASR source text = immutable
OCR source text = immutable
SourceDramaSnapshot contains no target truth
ReviewIssue is attention state, not domain truth
```

## 9. Development frontier

Do not resume old Stage 05 planning.

```text
R2 SourceDramaSnapshot                       = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R5 TargetDialogue + TTS/Voice                = NEXT
R6 Dialogue Timing Engine + RemakeTimeline
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 H3 QC / retry
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

`Shot != GenerationSegment` remains mandatory.

## 10. Recovery order

```text
1. AGENTS.md
2. SKILL.md
3. docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
4. docs/PROJECT_STATE.md
5. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
6. docs/SOURCE_DRAMA_SNAPSHOT_V1.md
7. docs/TARGET_LOCALIZATION_V1.md
8. relevant current code/tests
9. old P/G docs only for internal maintenance
```

## 11. Git discipline

```text
main = active development
backup branch = rollback-only
code/docs -> main directly unless user explicitly asks otherwise
all commits -> [skip ci]
hosted GitHub Actions != acceptance evidence
```
