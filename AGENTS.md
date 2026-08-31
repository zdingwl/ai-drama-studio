# AI Drama Studio — Agent Entry Rules

Current architecture: **Reference Video V2 + Breakdown Fast Grounded V2**.  
Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

## 1. Executable CURRENT

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED
Window Context                         = Segment-index v4 / real accepted / production / frozen
Exact-Shot                             = Compact-reconstruction v3 / real accepted / production / frozen
P2-E6 anonymous continuity Fusion     = E6-v2 production / local production regression pending
Replay-v5 continuity                  = real accepted / Scene1=2 / Scene2=2 / conflicts=0
Fresh production performance          = PASS / 14.098 min / <=20min
P2.6 Windows / real-model acceptance  = NOT FINAL PASS / E6-v2 final production confirmation pending
G2 Scene-level text LLM               = BLOCKED / NOT IMPLEMENTED
Scene Timeline result UI              = BLOCKED / NOT IMPLEMENTED
P5 Draft ↔ Character                  = PAUSED
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
```

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
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Context v4
   └─ Exact-Shot compact v3
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6-v2 Episode-context Fusion
   ├─ accepted Scene policy + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth
   └─ replay-v5 compact-safe anonymous continuity
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Production profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

## 4. E6-v2 continuity rules

```text
Stage1 Window hint:
  listed Shot ordinal = candidate location only
  Exact-Shot appearance must positively support the hint

Stages2..4:
  compact aliases are canonicalized for comparison only
  persisted source appearance text is unchanged
  accepted thresholds are unchanged

Hard safety:
  same-Shot observations = hard cannot-link
  explicit male/female contradiction blocks soft union
  explicit long-hair vs short/bald contradiction blocks soft union
  missing attribute is not conflict
```

Accepted policies:

```text
window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
compact appearance   = compact-observation-stable-alias-normalization-v1
```

## 5. Core semantic rules

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

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

## 7. Current real evidence

```text
full production Run performance = 14.098 min
Window v4 = 4/4 READY
Exact-Shot v3 = 6/6 READY
Shot0001 subjects=0; blue roses + glass vase props present
Scenes=2
E6-v1 production continuity regression = Scene1=4 / Scene2=16 / conflicts=0
replay-v5 on same immutable sidecars = Scene1=2 / Scene2=2 / conflicts=0
12 replay continuity tests = user-local PASS
```

Do not claim E6-v2 production regression PASS until the user reports it. Hosted GitHub Actions must
not be used; commits use `[skip ci]`.

## 8. Next safe work

```text
1. run cheap E6-v2 production regression tests
2. if green, execute exactly one final fresh full production Breakdown
3. require Fusion=e6-v2, Window=v4, Exact-Shot=v3
4. require Scenes=2, Scene1 LocalSubjects=2, Scene2 LocalSubjects=2
5. require same_shot_cluster_conflicts=0
6. require Shot0001 subjects=0 and blue roses + glass vase props
7. require whole-run <30min
8. only then review P2.6 final PASS
9. only then begin G2 / Scene Timeline work
```
