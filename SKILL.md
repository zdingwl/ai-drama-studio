---
name: ai-drama-studio-reference-video-v2
version: 3.16.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；Window v4 与 Exact-Shot compact v3 已冻结，replay-v5 连续性真实通过并升入生产 E6-v2，等待最后生产确认。
---

# AI Drama Studio — Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ Breakdown plans/contracts
→ Character docs when relevant
→ current code/tests
→ latest docs/sessions/*.md handoff
```

Executable CURRENT = `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests`.

## 1. Current baseline

```text
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Window Context: Segment-index v4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: Compact-reconstruction v3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion: E6-v2 / PRODUCTION / LOCAL PRODUCTION REGRESSION PENDING
Replay-v5 continuity: REAL ACCEPTED / 2 Scenes / 2+2 anonymous cast / conflicts=0
Fresh production performance: 14.098 min / <=20min PASS
P2.6: NOT FINAL PASS — one E6-v2 fresh production confirmation pending
G2 Scene-level pure-text LLM: BLOCKED / NOT IMPLEMENTED
Scene Timeline UI: BLOCKED / NOT IMPLEMENTED
P5 Draft ↔ Character: PAUSED
```

## 2. Current production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + frozen ShotRevision
→ PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-reconstruction v3
→ immutable exact-Shot VLM_OUTPUT
→ P2-E6-v2 Episode-context Fusion
   ├─ accepted Scene policy
   ├─ ASR_SEGMENT dialogue truth
   └─ replay-v5 compact-safe anonymous continuity
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

## 3. Core semantic boundaries

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
```

Window Context only provides Scene/anonymous continuity. Exact-Shot owns current-Shot visible truth.
ASR owns dialogue text truth. OCR owns visible text evidence.

## 4. Window v4 + Exact-Shot v3 frozen truth

Window v4 real production evidence:

```text
4/4 READY
0 MAXED
output tokens = 233..304 /1600
```

Exact-Shot compact v3 real production evidence:

```text
6/6 READY
output tokens = 763..1088 /4096
attempts=1 each
Shot0001 subjects=0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
```

Do not tune VLM performance further unless a new real regression appears.

## 5. E6-v2 anonymous continuity

The E6-v1 full production Run reached 14.098 min and correct Scene/Shot truth but fragmented anonymous
people to Scene1=4 / Scene2=16. Provider-free diagnostics proved the root cause was continuity, not
VLM performance.

Replay-v5 accepted fix:

```text
Stage1:
  Window-listed ordinal = candidate presence only
  Exact-Shot stable appearance must positively support the hint

Stages2..4:
  canonicalize compact aliases for matching only
  preserve source appearance text
  preserve accepted thresholds

Hard guards:
  same-Shot cannot-link
  explicit gender conflict
  explicit long-hair vs short/bald conflict
```

Policies:

```text
window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
compact appearance   = compact-observation-stable-alias-normalization-v1
```

User-local accepted replay-v5 result:

```text
12 targeted tests PASS
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
```

Production E6-v2 now uses this replay-v5 subject policy. Do not claim final P2.6 PASS until a fresh
production Run confirms it.

## 6. Character V10.1 protected baseline

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never weaken Character identity safety because of Breakdown anonymous hints.

## 7. Testing / CI discipline

User-reported local evidence includes:

```text
12 replay-v2/v3/v4/v5 continuity tests PASS
3 Exact-Shot compact-v3 targeted tests PASS
Window v4 real READY
Exact-Shot v3 real READY
full production performance = 14.098 min
replay-v5 real completed-run continuity = 2 / 2 / conflicts=0
```

Do not claim E6-v2 production tests PASS until user output confirms them. Do not consume hosted
GitHub Actions quota. Use `[skip ci]`.

## 8. Immediate safe work

```text
git pull
→ run E6-v2 production regression tests
→ if green, run exactly one fresh full production Breakdown
→ inspect G1 quality + VLM performance
→ require Fusion=e6-v2, Window=v4, Exact-Shot=v3
→ require Scenes=2 and anonymous cast=2 per Scene
→ require same_shot_cluster_conflicts=0
→ require Shot0001 subjects=0 and roses/vase props
→ require whole-run <30min
→ if all pass, review P2.6 final PASS
→ only then begin G2 / Scene Timeline
```
