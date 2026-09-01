---
name: ai-drama-studio-reference-video-v2
version: 3.20.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1/P2.6、G2.1-G2.5、P5 已真实验收并冻结，G2.6 与 P4 仍待对应用户本机验收。
---

# AI Drama Studio — Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ relevant Breakdown plans/contracts
→ Character docs when relevant
→ current code/tests
→ latest docs/sessions/*.md handoff
```

Executable CURRENT = `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests`.

### Git workflow

```text
文档同步 / 状态文档修正：直接修改 main，不为纯文档单独创建分支或 PR。
代码/行为修改：默认 feature branch + Draft PR。
用户明确要求直接 main/merge 时按明确指令执行。
所有提交使用 [skip ci]；Hosted GitHub Actions 不作为本项目验收手段。
```

## 1. Current baseline

```text
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: REAL ACCEPTED / PRODUCTION / FROZEN
Window Context: Segment-index v4 / REAL ACCEPTED / FROZEN
Exact-Shot: Compact-reconstruction v3 / REAL ACCEPTED / FROZEN
P2-E6 Fusion: E6-v2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance: PASS
G2 Scene Timeline Contract: v1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler: v1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core: v1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime: REAL ACCEPTED / FROZEN BASELINE
G2 Source/Support Validator: v1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance: PASS
G2.5 Scene Timeline API: v1 / FINAL PASS / FROZEN
G2.5 Windows/CUDA local acceptance: PASS
G2.6 ordinary-user Scene Timeline UI: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: v1 / FINAL PASS / FROZEN
```

Do not reopen frozen layers without a concrete regression.

## 2. Frozen production flow

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
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Accepted production reference:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
Scenes = 2
LocalSubjects = 4
same_shot_cluster_conflicts = 0
```

## 3. Core semantic boundaries

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text = verbatim truth
OCR-origin visible text = verbatim truth
```

## 4. Character V10.1 protected baseline

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

## 5. Frozen G2 baseline

G2.1 through G2.5 are frozen. Accepted evidence includes:

```text
G2.1/G2.2 = 4 passed
G2.3/G2.4 = 15 passed + real local Qwen acceptance
G2.5 = 12 passed + 2 accepted titles + 2 summaries + 0 warnings
```

G2.3 LLM authority remains narrow:

```text
MAY: readable_title, story_summary
MUST NOT: timestamps, boundaries, people identity/count, Shot facts,
          ASR/OCR truth, props, cinematography, Final Assets
```

G2.6 is implemented on `main` and uses G2.5 directly, but remains user-local acceptance pending.

## 6. P5 frozen Character bridge

P5 merge commit:

```text
ab4b11716f5c1c5ead7367119d1b2d787defe8f9
```

Frozen implementation:

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
docs/P5_BREAKDOWN_CHARACTER_BRIDGE_V1.md
```

Authority direction:

```text
Final ShotCharacterBinding
→ Scene-local deterministic exact presence-signature reconciliation
→ resolve anonymous Breakdown person only when uniquely safe
```

P5 MUST NOT use dialogue names, ASR speaker labels, relationship terms, role hints, appearance prose or P1/P2 labels as identity authority. Ambiguous/partial people remain `UNRESOLVED`.

User-local acceptance:

```text
unit contract = 7 passed
real Episode runner = READY
scene_count = 2
person_count = 4
resolved_count = 1
unresolved_count = 3
warnings = []
Scene1 P2 -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

Unique match support:

```text
Scene1 P2 = Shots 3,4,5,6,9,10,11
Final 人物 001 projected signature = Shots 3,4,5,6,9,10,11
```

Other three people correctly remain unresolved. Therefore **P5 = FINAL PASS / FROZEN**.

## 7. Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. User-local evidence is acceptance truth. Hosted GitHub Actions must not be used; commits use `[skip ci]`.

## 8. Immediate safe work

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. finish G2.6 user-local acceptance when needed
3. P4 Scene/Prop local acceptance remains pending
4. next code frontier = P6 Final identity/asset fill-back + final Breakdown read model/renderers
```

P6 must compose frozen G2 + frozen P5 without mutating either. Only P5 `RESOLVED` people may render Final Character names/assets; `UNRESOLVED` people remain anonymous. ASR/OCR and frozen Shot factual objects remain unchanged.
