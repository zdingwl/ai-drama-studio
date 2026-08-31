# AI Drama Studio — Agent Entry Rules

Current architecture: **Reference Video V2 + Breakdown Fast Grounded V2**.  
Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

## 1. Executable CURRENT

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED
Window Context                         = Segment-index v4 / real accepted / production / frozen
Exact-Shot                             = Compact-reconstruction v3 / selected-batch real accepted / production
P2-E6 anonymous continuity Fusion     = production / fresh quality positive / frozen
P2-E5 Fusion                          = rollback baseline
P2-E4 Fusion                          = older rollback baseline
G2 Scene-level text LLM               = NOT IMPLEMENTED
Scene Timeline result UI              = NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT FINAL PASS (one fresh final production Run pending)
P5 Draft ↔ Character                  = PAUSED
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
```

`AGENTS.md` / `SKILL.md` summarize entry rules; if historical notes conflict with executable CURRENT,
follow executable CURRENT.

## 2. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
6. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
7. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
8. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
9. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
10. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
11. Character docs when relevant
12. current code/tests
13. latest docs/sessions/*.md handoff
```

## 3. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR (faster-whisper)
→ OCR (RapidOCR)
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Context v4
   │    24s / 25% overlap / 1 FPS / 262144 px
   │    local indexes only
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot compact v3
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        524288 px / 4096 max tokens / 5 Shots per batch
        current-Shot visible description / people / reconstruction-relevant props / framing
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ corridor-family Scene compatibility + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous continuity Stage1..4 with hard same-Shot cannot-link
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Production profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v1
Pipeline = breakdown-p2-full-v1
```

## 4. Core semantic rules

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

```text
Window Context -> Scene + anonymous continuity only
Exact-Shot -> current Shot people/actions/props/framing/visual prose
ASR -> dialogue text truth
OCR -> visible text evidence
```

Never import neighboring Shot people/actions/props into current-Shot visible truth.

Hard boundaries:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
subject_A/B = Shot-local labels only
same-Shot person observations = hard cannot-link
```

Dynamic expression/emotion/action/pose/speaking/screen position/framing are not identity keys.

## 5. Exact-Shot compact-v3 semantics

The model emits compact Shot-local facts. Host code restores canonical compatibility fields:

```text
revision_item_id = frozen manifest truth
subject_A/B = current-Shot people order
summary = visible
visual_description = visible
speaking_state = UNKNOWN
camera_motion_hint = UNKNOWN for static sampled frames
events = [] with Fusion summary->VISUAL fallback
```

Reconstruction rule:

```text
salient independently visible objects required to reconstruct the Shot must enter props,
even when no person interacts with them.
```

## 6. Character V10.1 is protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax same-sample cannot-link, face conflict, >=3 independent evidence rule, ambiguity rules,
explicit Shot assignment or Final Gate because of Breakdown hints.

## 7. Current acceptance evidence

User-local / real diagnostic evidence already reported:

```text
12/12 E6/v3 Fusion targeted tests PASS
3/3 Exact-Shot compact-v3 targeted tests PASS
Window v4 real diagnostic = 4/4 READY, 233..304 tokens, 41.920s
Exact-Shot v3 selected batches 1/4/6 = READY, ~993..1061 tokens
Shot1 v3 = subjects=0; blue roses + glass vase present in props
```

Do not claim assistant-local pytest/CUDA execution. Hosted GitHub Actions must not be used; commits
use `[skip ci]`.

## 8. Next safe work

```text
1. run cheap production-routing regression tests
2. if green, execute exactly one fresh full production Breakdown on the reference Episode
3. inspect quality + timings
4. require Window v4 + Exact-Shot v3 + E6 profiles
5. require Scenes ~=2, each real cast ~=2, same-Shot conflicts=0
6. require Shot0001 subjects=0 and blue roses + glass vase reconstruction props
7. require whole-run <30min
8. if all pass, stop G1 tuning and review P2.6 for final PASS
9. only then begin G2 / Scene Timeline work
```
