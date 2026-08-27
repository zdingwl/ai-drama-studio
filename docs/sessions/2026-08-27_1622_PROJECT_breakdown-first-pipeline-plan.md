# Session Handoff — Breakdown-first 拉片先行资产识别总体规划

> Date: 2026-08-27 16:22 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Status: TARGET PLAN ACCEPTED / DOCUMENTATION SYNCHRONIZED / NO BUSINESS CODE CHANGED

## 1. User goal

用户重新明确了产品里“拉片”的含义：

```text
拉片 != 只做镜头切分
```

目标拉片应该先像人工拉片师一样看懂视频，并输出带时间轴的场景化视听脚本，例如：

```text
场景1 · 内 · 走廊 · 00:00-00:22
人物：人物A、人物B
道具：蓝玫瑰

[00:00] 蓝玫瑰插在玻璃花瓶中，特写。
[00:01] 人物A拦住人物B，面露不悦。
人物A（质问）：……
人物B（辩解）：……
```

然后再根据这份第一版拉片中的人物/场景/道具/对白/动作上下文去定向寻找真实资产，最后把真实 Character / Scene / Prop 回填到拉片。

用户同时明确要求：

- 先规划，不修改业务代码；
- 必须把规划同步到仓库文档；
- 未来新对话不能因为聊天丢失规划；
- 当前代码事实和未来规划不能混写，避免后续乱改已有功能。

## 2. Accepted target principle

```text
先看懂，再识别，再回填
```

Target flow：

```text
Original Video
→ Preprocess
→ Shot Detection
→ Shot + Reference Clip
→ ASR / OCR / Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence extraction
→ Global Asset Resolution + Final Shot Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

第一遍必须使用：

```text
人物A / 人物B
subject_A / subject_B
```

等匿名 `LocalSubject`，不能让 VLM 在没有项目级身份 Evidence 时直接写正式 Character ID。

## 3. Critical semantic rules

```text
Semantic Draft
= soft prior / search hint

Visual / Audio / OCR Evidence
= measurable facts

Final Asset / Final Binding
= validated + editable product truth
```

因此：

- Draft 可以告诉系统“重点找黑衣年轻女性、合同、医院”等；
- Draft 不能直接创建 Character / Scene / Prop；
- Draft 不能直接写 `ShotCharacterBinding`；
- reliable cannot-link / Face conflict 等硬证据优先于剧情猜测；
- Scene Segment（剧情段）与 Scene Asset（项目级视觉环境）必须分开；
- Final Breakdown 前端可以是漂亮剧本文案，但后台必须保存结构化时间/实体/事件引用。

## 4. Current repository facts verified before planning

### Current V2 media/Shot path

Current FastAPI `main.py` wires:

```text
media_v2.preprocess_episode
media_v2.detect_episode_shots
studio_v2.Shot
```

Current `media_v2.detect_episode_shots()` already does:

```text
FFprobe authoritative timing
+ TransNetV2 Shot boundary detection
+ Reference Clip rendering
+ thumbnail/keyframe
+ safe Shot revision switch
```

Current Shot has:

```text
start_us / end_us / duration_us
reference_clip_path
thumbnail_path
keyframes_json
short_description
shot_type
camera_motion
```

But it does **not** currently have the accepted full anonymous semantic breakdown pipeline.

### Historical F04/F05 naming caveat

`shot_detection.py` docstring calls itself F04 “自动拉片”, but its real responsibility is Shot Candidate boundary detection.

`shot_workbench.py` calls itself F05 “镜头人工修正/拉片工作台”, and explicitly says it does **not** do Character / ASR / Scene / Qwen3-VL.

Do not let those historical Feature labels redefine the new product meaning of “拉片”.

### Current Character baseline

Formal current Character is V10.1:

```text
Person Evidence
→ Track
→ Global Identity
→ Independent Shot × known-Character Assignment
→ Final Character / ShotCharacterBinding
```

Current Shot assignment source/version:

```text
v10.1-shot-character-assignment-1
V10_1_SHOT_CHARACTER_ASSIGNMENT
```

Final current V10.1 binding uses explicit `shot_presence_assignments`, not Candidate Track ownership.

### Current Scene / Prop reality

`content_analysis_v2.py` has established Candidate/Evidence data boundaries.

Current Scene candidate is still lightweight (thumbnail visual descriptor + Episode-contiguous grouping), not the target semantic Scene identity resolver.

Current Prop boundary exists, but when no reliable configured model exists the runtime may return `NOT_CONFIGURED`; do not fabricate Prop.

### Current Qwen/TransVLM caveat

`transvlm_runtime_v51.py` uses `TransVLM-Qwen3-VL-4B-Instruct` for transition-segment detection/caching. This is **not** the target semantic breakdown engine and must never be documented as if first-pass content understanding is already implemented.

## 5. Accepted target data concepts

Planning-only concepts, not current DB tables:

```text
LocalSubject
ShotSemanticDraft
TimelineEvent
SceneSegmentDraft
DraftResolution
```

Meaning:

```text
LocalSubject
= anonymous person inside Draft scope

ShotSemanticDraft
= structured first-pass Shot understanding

TimelineEvent
= VISUAL / ACTION / DIALOGUE / OCR / AUDIO_EVENT with real timing

SceneSegmentDraft
= narrative scene segment grouping multiple Shots

DraftResolution
= subject_A → Character001, scene_hint → Scene003, prop_hint → Prop005
```

## 6. Protected current functionality

Do not damage/rewrite these just to implement the new plan:

```text
Project / Episode / sort_order
source hash / media management
FFmpeg / FFprobe preprocess
integer microseconds
TransNetV2 boundary detection
Shot revision
stable shot_id
Reference Clip / thumbnail / keyframes
Character V10.1 Person Evidence
YoutuReID Global Identity
same-sample cannot-link
explicit Shot Character Assignment
Final Character Gate
Final Asset / Binding / Revision separation
MANUAL / RESTORE protection
old Run compatibility
sequential heavy processing / concurrency=1
```

Database evolution for the new flow starts ADD-only; no destructive cleanup before the new path is accepted.

## 7. Frozen implementation order

```text
P0 docs / contract only
P1 Draft data contract ADD-only
P2 ASR / OCR / VLM anonymous Draft read-only sidecar
P3 02 拉片 structured Draft UI
P4 Draft-guided Scene / Prop evidence
P5 Draft ↔ Character safe integration, only after current V10.1 real-video baseline acceptance
P6 Final fill-back + standard/international renderers
P7 downstream remake integration
```

Do not skip straight to P5 and start changing Character thresholds because the new product concept exists.

## 8. Documentation synchronized in this planning session

Created:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

Updated:

```text
AGENTS.md
SKILL.md              # 3.5.0 → 3.6.0, documentation/target-contract change only
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

The entry docs now explicitly require reading the Target Plan while keeping CURRENT and TARGET separate.

Main documentation commits from this session:

```text
8ad62bc67c81768d0edf744d944c5b9a4e3bc65b  docs: define breakdown-first asset pipeline target plan
5bf705cc7976176eaa56168dfe4a0a2e77b48c91  docs: add accepted breakdown-first target plan guardrail
2d50f454885ec8fb353ca9e75f2318b8c479ca6e  docs: register breakdown-first target workflow contract
0bf476a925a3d04a679db0b7f1823bda75eec591  docs: record accepted breakdown-first plan without changing current state
f9cf99d726af00dcf7fb51b5918a79f1411c6fbe  docs: separate current wiring from breakdown-first target plan
b73499a82e5ba0115889d50f2ee00ca141e6f5b6  docs: guard Character V10.1 against premature breakdown-context changes
```

## 9. Code / DB change status

```text
Business code changed: NO
Database schema changed: NO
Runtime profile changed: NO
Character algorithm changed: NO
Shot algorithm changed: NO
Frontend behavior changed: NO
```

Only planning/documentation files were changed.

## 10. Next development starting point

Do not immediately implement the entire Target Plan.

Next coding step, only when the user explicitly asks to start development, should be:

```text
Phase P1 — freeze Draft data/API contract
```

Before writing P1 code:

```text
1. read AGENTS.md
2. read SKILL.md
3. read PROJECT_STATE.md
4. read CURRENT_IMPLEMENTATION_MANIFEST.md
5. read BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
6. inspect current studio_v2/media_v2/shot revision/content analysis code + tests
7. design ADD-only schema and backward compatibility
8. do not touch Character V10.1 thresholds/binding path in P1
```

The goal of P1 is only to create a safe place for structured anonymous Draft data. It should not yet run VLM or change Final Asset results.

## 11. Anti-drift rule for future sessions

Whenever implementation advances one Phase:

```text
code + focused tests + real acceptance
↓
update CURRENT Project State / Manifest
↓
update Target Plan Phase status
↓
update affected specialist doc
↓
create new session handoff
```

Never do the reverse by marking future Target work as CURRENT before code exists.
