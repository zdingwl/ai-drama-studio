# Session Handoff — 2026-08-28 18:12 +08:00 — P2 Episode-context Fusion E1

## 1. 本次开发目标

用户在真实拉片结果中指出两个结构性问题：

1. 对白跨过 Shot 切镜点后被拆成残句；
2. 同一场景包含人物特写、虚化背景、插入镜头时，因为单 Shot 环境信息不足被错误拆成多个 Scene。

用户确认新的产品原则：

> **拉片应当是整集上下文拉片；Shot 是结果展示/编辑单位，不是 AI 理解边界。**

本次先执行迁移第一阶段 P2-E1：在不破坏 P1 schema、immutable sidecar、Character V10.1、P4 Final Evidence gates 的前提下，修正 Fusion 的 Scene continuity 与 cross-Shot dialogue semantics。

## 2. 开始前仓库事实

```text
Architecture: Reference Video V2
Character: V10.1
P1/P2 implementation: CONDITIONAL PASS
P2.6 real-model acceptance: NOT PASSED
P3 UI: acceptance in progress
P4 Draft-guided Scene/Prop: implemented / local acceptance pending
```

旧 P2 行为：

```text
ASR = Episode audio
VLM = one Reference Clip / Shot
Scene Fusion = missing/different scene signature can create new segment
Dialogue Fusion = ASR segment split at exact Shot boundaries, often using word timestamps
```

## 3. 本次实际完成

### 3.1 新增 P2-E1 production Fusion

新增：

```text
engine/app/breakdown_p2_fusion_episode_v2.py
```

Profile：

```text
breakdown-p2-fusion-episode-context-e1-v2
```

行为：

```text
Scene:
UNKNOWN / missing / generic hint → inherit current Scene
compatible specificity → same Scene
strong location contradiction / explicit INT↔EXT → new Scene

Dialogue:
ASR_SEGMENT = dialogue text truth
Shot DIALOGUE event = projection
cross-Shot sentence keeps full text in every projection
shared dialogue_group_id = asr_segment_id
```

ASR_WORD raw Evidence 保持 immutable，并作为 SUPPORT provenance 重新连接到相交 projection。

### 3.2 Production pipeline 已接入 E1

修改：

```text
engine/app/breakdown_p2_pipeline_v1.py
```

从：

```text
breakdown_p2_fusion_v1
```

切换到：

```text
breakdown_p2_fusion_episode_v2
```

顶层 `breakdown-p2-full-v1` pipeline profile 保持不变，避免无意义破坏已有 API / Run Contract；Fusion 子 profile 记录在 provenance。

### 3.3 测试覆盖已新增

新增：

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
```

覆盖：

```text
weak/UNKNOWN scene inheritance
strong location change splits scene
compatible location specificity stays same scene
ASR raw evidence remains unchanged when building projection view
cross-Shot dialogue projection keeps full sentence + group metadata + word provenance
```

本 Session 未在用户本地项目环境执行 pytest，也未使用 hosted GitHub Actions，因此不能声称测试 PASS。

### 3.4 文档同步

新增：

```text
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
```

更新：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

所有文档明确：

```text
P2-E1 = implemented, local-real acceptance pending
P2-E2 continuous-window VLM = NOT IMPLEMENTED
P2.6 = NOT PASSED
P5 = paused until Episode-context semantic baseline is stable
```

## 4. 关键实现细节

### Scene continuity

E1 使用 conservative planner：

```text
current anchor = strong meaningful Scene hint
weak current Shot = no new segment
compatible more-specific hint = upgrade anchor
strong contradiction = segment break
```

示例：

```text
客厅大全景
→ 人物特写 UNKNOWN
→ 手机插入 “室内”
→ 家中客厅
= one Scene Segment
```

```text
客厅
→ closeup UNKNOWN
→ 医院走廊
= two Scene Segments
```

### Dialogue continuity

P1 `TimelineEvent` 仍要求一个 `shot_draft_id`，所以 E1 不做 destructive DB migration。

跨镜对白通过 projection metadata 表达：

```text
dialogue_group_id
asr_segment_id
dialogue_source_start_us / dialogue_source_end_us
projection_start_us / projection_end_us
projection_index / projection_count
continues_from_previous_shot
continues_to_next_shot
```

历史 raw ASR sidecar 不改写。

## 5. 当前已知工程风险

### Risk 1 — E1 暂时复用 legacy writer

为了避免复制 1000+ 行成熟 P1 writer，E1 在一个 process lock 内短暂替换 legacy `_segment_plans`，调用 legacy `_write_fused_draft`，然后立即恢复。

```text
_FUSION_PATCH_LOCK
+ current heavy P2 jobs globally serialized
```

当前生产模型下可控，但这属于迁移实现。P2-E4 或后续 refactor 应把 segment planner 变成显式 dependency，而不是长期 monkeypatch private function。

### Risk 2 — current Qwen is still Shot-local

E1 只能解决 Fusion 对“不确定”的错误解释，不能让一个完全没有环境信息的 Shot 自己获得真实 Episode visual context。

真正视觉上下文将在 P2-E2：

```text
overlapping 20–40s Episode video windows
+ Shot boundaries
```

### Risk 3 — UI continuation presentation not yet optimized

E1 backend 会让跨镜 projections 保存完整句。如果 P3 直接逐 Shot 无差别显示，可能看到重复完整句。

后续 UI 应读取：

```text
dialogue_group_id
continues_from_previous_shot
continues_to_next_shot
```

显示为“对白开始 / 对白继续”，而不是把两个 projection 当两句不同对白。

## 6. 数据 / Contract 变化

### DB schema

```text
NO CHANGE
```

### P1 Draft Contract

```text
NO BREAKING CHANGE
```

### P2 raw sidecar Contract

```text
NO CHANGE
raw Evidence remains immutable
```

### API

```text
NO CHANGE
```

### Derived Fusion semantics

```text
CHANGED FOR NEW BreakdownRuns
```

旧 BreakdownRun 历史不可变；必须重新运行 AI 拉片才能得到 E1 结果。

## 7. Character / Final Asset 边界

未修改：

```text
Character V10.1 resolver
MOT / ReID
same-sample cannot-link
Face hard conflicts
explicit Shot Character Assignment
Final Character Gate
P4 Scene/Prop visual verification gates
```

E1 不创建 Final Character/Scene/Prop，也不写 Final Shot bindings。

## 8. 本次 commits

```text
5ff083f8 feat: add episode-context fusion E1
bfb67987 fix: keep E1 fusion provenance counts exact
efca93f7 feat: wire episode-context fusion E1
5305fbf8 test: cover episode-context fusion E1
360ae06a docs: define episode-context breakdown migration
41cd0231 docs: sync current episode-context E1 wiring
b9dec749 docs: move project state to episode-context E1
461aea08 docs: update agent entry for episode-context E1
53f50862 docs: sync project skill with episode-context breakdown
79e931c9 docs: add E1 checks to P2 local acceptance
0e06a082 docs: revise breakdown-first plan for episode context
```

All current development/documentation commits use `[skip ci]`; no hosted Actions quota was intentionally consumed.

## 9. 当前验收状态

```text
P2-E1 code implementation       = IMPLEMENTED
P2-E1 unit tests in repo        = ADDED / NOT EXECUTED IN THIS SESSION
P2-E1 local real-video behavior = PENDING
P2.6 real-model acceptance      = NOT PASSED
P3 UI acceptance                = IN PROGRESS
P4 local acceptance             = PENDING
```

## 10. 下一步唯一推荐动作

在用户本地环境使用最新 `main`，对一集真实短剧 **重新执行 AI 拉片**，重点验收：

```text
A. 找一条跨切镜对白
   → 两个 Shot 不得出现残句
   → full sentence + same dialogue_group_id

B. 找一个同场景：大全景 → 特写/虚化 → 插入 → 特写
   → 不应因为背景不足拆 Scene

C. 找一个明确换场
   → 必须仍能拆 Scene
```

如果 E1 行为通过，下一开发阶段是：

```text
P2-E2 overlapping continuous-window Qwen3-VL
```

不要先推进 P5。

## 11. 给下一位 Agent 的一句话

> 生产 pipeline 已切到 Episode-context E1 Fusion；先用真实短剧确认跨镜对白与同场景连续性，再做 P2-E2 连续窗口 VLM。不要把 E1 描述成“整集连续 VLM 已完成”，也不要改变 Character V10.1 / Final Asset hard gates。
