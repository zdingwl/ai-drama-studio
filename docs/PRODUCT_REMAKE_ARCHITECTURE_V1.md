# AI Drama Studio — Localized Remake Architecture V1

Status: **CURRENT PRODUCT DIRECTION**  
Date: 2026-09-02

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
- one-click automatic preparation.

### Review Center

Only issues needing human judgement:

- shot boundary correction;
- character identity merge/split/confirmation;
- Shot Character/Scene/Prop binding correction;
- speaker correction;
- localization ambiguity;
- dialogue timing conflict;
- H3 QC failures;
- lip-sync target-face ambiguity.

### Output

- final Episode status;
- final Episode preview;
- MP4 download;
- SRT download;
- one-click continue generation/finalization;
- advanced H3/PostProduction diagnostics only when needed.

No top-level GenerationSegment, H3 Context, QC, Lip Sync or evidence pages.

## 4. Automatic pipeline

```text
Project + Episodes
        ↓
Preprocess
        ↓
Shot Detection + Reference Clips
        ↓
ASR + OCR + Qwen3-VL Breakdown
        ↓
Character / Scene / Prop extraction and safe binding
        ↓
SourceDramaSnapshot
        ↓
Target Character / Target Scene localization
        ↓
Target dialogue translation + localization
        ↓
Qwen3-TTS
        ↓
Dialogue Timing Engine
        ↓
RemakeTimeline
        ↓
GenerationSegment
        ↓
H3 Context Compiler
        ↓
MiniMax H3 Local
  Ref2VA main remake
  FL2VA extension / bridge / repair
        ↓
H3 structural + semantic QC
        ↓
automatic retry / GenerationSelection
        ↓
Target-speaker Lip Sync
        ↓
Final target audio + Subtitle
        ↓
EpisodeOutput assembly / export
```

Any stage that cannot decide safely creates a `ReviewIssue` instead of a new product page.

## 5. Source truth boundary

`SourceDramaSnapshot` is the only downstream source-fact interface.

```text
source analysis internals
        ↓
SourceDramaSnapshot
        ↓
target/remake pipeline
```

It exposes current Episode/Scene/Shot hierarchy, source timing, Reference Video anchors, safely resolved source people/assets, action/performance, verbatim source dialogue, speaker keys, OCR, cinematography and a deterministic source fingerprint.

Target-side fields are forbidden from the source contract.

Source ASR/OCR/Shot facts are immutable downstream.

## 6. Target localization truth

Source entities and target entities are separate.

```text
Source Character -> TargetCharacter
Source Scene     -> SceneLocalizationMapping
Source Dialogue  -> TargetDialogue
```

Project scene policy:

```text
AUTO
KEEP
LOCALIZE
```

Characters are always replaced/localized. Source Character rows must never be renamed or repainted into target characters.

## 7. TargetDialogue and target voice

TargetDialogue owns:

- source dialogue anchor/fingerprint;
- translated text;
- localized/final text;
- target Character / Voice;
- generated audio path;
- real speech duration;
- timing status.

Local Qwen3-TTS produces target-character audio. Real `speech_duration_us` drives timing; the source dialogue timing is never overwritten.

## 8. Dialogue timing is first-class

Do not force target speech into source duration.

```text
source dialogue
→ translation/localization
→ TTS
→ real target speech duration
→ compare with Shot/reaction time
→ RemakeTimeline strategy
```

Current strategies include:

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

Never solve timing globally by unnaturally accelerating speech or globally slowing the source video.

## 9. RemakeTimeline

Source timeline is not final timeline.

Each planned Shot keeps its source timing anchor and adds target timing. The complete target Episode duration may differ from the source Episode duration.

Upstream source/target fingerprints are authoritative. Changes invalidate downstream generation plans rather than silently reusing stale media.

## 10. GenerationSegment

Critical rule:

```text
Shot != GenerationSegment
```

Shot is the source directing/editing unit. GenerationSegment is the actual H3 generation unit.

A target Shot may become multiple GenerationSegments when timing or H3 duration constraints require it.

H3 duration rules:

```text
4..15 seconds render window
<4-second target -> render >=4 then exact post-trim
>15-second target -> multiple balanced GenerationSegments
```

## 11. MiniMax H3 integration

Provider boundary:

```text
remake business code
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

Business services do not call SGLang directly.

### H3 Context Compiler

The compiler materializes deterministic generation context from:

```text
source Reference Video
+ TargetCharacter references
+ TargetScene reference/description when localized
+ exact target-dialogue audio timeline
+ actions/performance
+ camera/composition constraints
+ target duration
```

For Ref2VA, the source Reference Video derivative is visual-only. Source-language soundtrack is never passed as H3 reference audio.

## 12. GenerationAttempt and H3 QC

```text
GenerationSegment
→ GenerationAttempt
→ structural QC
→ Qwen3-VL semantic QC
→ retry / review / GenerationSelection
```

`GenerationAttempt(SUCCEEDED)` is execution history, not final usable truth.

Structural QC checks real video stream, duration, dimensions/fps and full ffmpeg decode.

Semantic QC checks at minimum:

```text
visual integrity
source actor leakage
target character consistency
scene consistency
Ref2VA action/camera consistency
FL2VA continuity consistency
```

Only `GenerationSelection` may enter downstream postproduction.

`H3_QC` cannot be generically ignored/resolved. Human fallback must either select a structurally valid version or retry generation.

## 13. R10 PostProduction

R10 consumes **Selected Output** and final target audio.

```text
GenerationSelection
→ PostProductionSegment
→ EpisodeOutput
```

### Lip-sync policy

```text
off-screen target dialogue
  -> keep target audio, skip mouth edit

single visible target speaker
  -> LatentSync full segment

multiple visible faces
  -> resolve target speaker identity first
  -> crop/ROI LatentSync only on the target face
```

Multi-face identity resolution is executed as background work, not in a GET/read API.

If the face locator/model is unavailable, the system waits; it does not create a fake human content problem.

If target identity remains ambiguous, create `LIP_SYNC_QC`.

`LIP_SYNC_QC` is domain-edited. Generic Ignore/Resolve is forbidden. A retry must re-run real localization/postproduction.

### Dialogue audio

One target sentence may span multiple GenerationSegments. Later segments trim the already-played part of the TargetDialogue audio rather than replaying the sentence from the beginning.

### Subtitle

SRT uses target RemakeTimeline timing, UTF-8 encoding and deduplicates a TargetDialogue spanning multiple GenerationSegments.

### Episode assembly

Only `SUCCEEDED` PostProductionSegments enter EpisodeOutput. Media is normalized before concat to prevent silent failure from differing frame size/fps/audio presence.

EpisodeOutput is the normal user-facing final video authority.

## 14. Audio mix boundary

Current R10 guarantees final target dialogue audio, but it does not yet own a complete ambience/BGM/SFX mix layer.

R10.1 must follow these rules:

```text
never reintroduce source-language dialogue
preserve source ambience/music only when it can be separated safely
otherwise reconstruct/replace non-dialogue audio explicitly
mix around target dialogue rather than competing with it
apply deterministic loudness/peak control
keep postproduction reruns idempotent
```

Do not hide source dialogue leakage under a lower volume mix.

## 15. ReviewIssue contract

ReviewIssue is an attention queue, not a second truth database.

Current families:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

Infrastructure-only states such as H3/TTS/Qwen/LatentSync service offline do not become human ReviewIssues.

## 16. Existing internals to preserve

Keep accepted capabilities that already work:

- FFmpeg / FFprobe media handling;
- Source PTS time authority;
- ShotRevision and manual Shot edits;
- Reference Clips;
- Faster-Whisper ASR;
- RapidOCR;
- Qwen3-VL Breakdown;
- Scene Timeline structured facts;
- Character V10.1 tracking/ReID;
- Final Character/Scene/Prop and bindings;
- AssetRevision history;
- SourceDramaSnapshot;
- BackgroundTask / progress;
- Target localization / dialogue / TTS;
- RemakeTimeline;
- GenerationSegment;
- GenerationAttempt / QC / Selection;
- PostProductionSegment;
- EpisodeOutput.

Do not weaken accepted Character identity gates merely to reduce ReviewIssues.

## 17. Removal policy

Do not mass-delete legacy code until the current full remake workflow passes real-project local acceptance.

Safe order:

1. V4 workflow remains stable;
2. current remake code depends on formal source/target authorities rather than legacy page contracts;
3. local H3/Qwen/LatentSync real-project acceptance passes;
4. global import/API/test search confirms legacy code is no longer required;
5. remove legacy UI and compatibility backend layers incrementally.

## 18. Current development state

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED
R4 TargetCharacter + SceneMapping             = IMPLEMENTED
R5 TargetDialogue + local Qwen3-TTS           = IMPLEMENTED
R6 Dialogue Timing + RemakeTimeline            = IMPLEMENTED
R7 GenerationSegment + H3 Runtime/Provider     = IMPLEMENTED
R8 H3 ContextCompiler + GenerationAttempt      = IMPLEMENTED / ISOLATED CI PASS
R9 automatic QC / retry / GenerationSelection = IMPLEMENTED / ISOLATED CI PASS
R10 Lip Sync + subtitle + assembly/export      = IMPLEMENTED / ISOLATED CI PASS
R10.1 ambience / BGM / SFX mix layer          = NEXT
R11 legacy cleanup                            = LATER
```

Local real-project H3/Qwen/LatentSync acceptance remains pending and must not be confused with repository CI acceptance.
