# P7 整集原片理解 Professional Skill 与 Grounding 验收

> 日期：2026-09-09  
> 当前状态：P7 工程实现已具备真实 Provider、项目级模型选择、运行时配置、Professional Skill 与 claim grounding；**P7 仍未最终验收**。  
> 本文补充 `docs/04_阶段人工验收规范.md`，不改变 P8 尚未开始的状态。

---

# 1. 为什么增加 Professional Skill

真实短剧 `货到付款惩治隔壁大妈-第01集.mp4` 使用 Doubao Seed 2.1 Pro 已经能够生成完整的《源作概览分析》，说明整集故事、人物、关系、时间化剧情、Story / Rhythm 的模型能力基本可用。

但第一次真实结果也暴露了 Source Truth 边界问题，例如：

- `world_rules` 出现社会学泛化 / 道德或法律式总结；
- 某些道具 `story_function` 可能把合理推断写成确定因果；
- 人物历史、关系年限、过去行为等事实如果没有明确 Evidence，容易被模型合理补全。

这不是简单的 JSON 格式问题，也不优先通过再增加一次语言模型来解决。

P7 需要正式的专业执行标准：

```text
Root Project Skill
→ source-video-understanding Professional Skill
→ Provider Prompt
→ Grounded Schema
→ Provider / Server Validation
→ SOURCE_BIBLE
```

正式 Skill：

```text
skills/professional/episode-understanding/SKILL.md
skills/professional/episode-understanding/manifest.json
```

Skill ID：

```text
source-video-understanding@1.0.0
```

---

# 2. 固定 Source Truth 层级

```text
完整 Episode / SOURCE_VIDEO
= 最高层原片事实源

CURRENT P6 Source Evidence
= canonical dialogue / OCR 文字事实源

CURRENT Shot Anchors
= 可选时间定位提示
= 不是剧情事实源
= 不是剧情分段边界
```

P7 Provider 必须直接消费完整 Episode。

禁止：

```text
Reference Clip 1 → 猜一段剧情
Reference Clip 2 → 猜一段剧情
...
→ 拼成整集故事
```

---

# 3. Grounding 三档

P7 对容易被合理补全的 claim 统一区分：

```text
FACT
= 原片直接可见，或 CURRENT Source Evidence 明确陈述

INFERENCE
= 根据已知事实可以合理推导，但原片没有直接确认

UNKNOWN
= 无法可靠判断
```

核心原则：

> **宁可 UNKNOWN，也不要合理补全。**

FACT 必须至少提供一种依据：

- CURRENT dialogue evidence ID；
- CURRENT visual text evidence ID；
- 完整 Episode 中明确的 `video_time_ranges`。

不存在的 Evidence ID、越过 Episode duration 的视频依据必须 fail closed。

---

# 4. Schema Grounding 范围

当前 Grounding Contract：

```text
grounded-source-truth-v1
```

P7 Schema 已支持以下 claim grounding：

- `overall_analysis.story_background_grounding`；
- `overall_analysis.world_rule_groundings`；
- `character.identity_grounding`；
- `relationship.grounding`；
- `scene.grounding`；
- `prop.story_function_grounding`；
- `story_event.grounding`。

其中 `world_rules` 保留原字段名用于兼容已有 SOURCE_BIBLE，但语义已经收紧为：

> 只允许本作品内部已经成立、并且对剧情理解有约束作用的 source-internal FACT。

禁止写入：

- “部分老人一般会……”；
- “某类男性通常会……”；
- 社会经验总结；
- 法律结论；
- 道德训诫；
- 与本片无关的世界知识。

没有 source-internal world rule 时应直接输出：

```json
{
  "world_rules": [],
  "world_rule_groundings": []
}
```

---

# 5. Professional Skill 与 Prompt 的关系

Skill 不是 Prompt。

```text
SKILL.md
= 人类可读的专业工作方法 / 决策边界 / 失败策略

manifest.json
= 机器可读取的 Skill 契约和 provider_rules

Provider Prompt
= 当前任务对 Skill 规则的执行表达
```

P7 Provider 不再自己维护一套孤立的业务规则；Doubao / Qwen Provider 都读取：

```text
source-video-understanding@1.0.0
```

的 `provider_rules`，再组合当前 Episode / Evidence / Shot hints / Schema 形成调用 Prompt。

Professional Skill 可通过只读 API 检查：

```text
GET /api/v3/skills/professional
GET /api/v3/skills/professional/source-video-understanding
```

GET 只读取 Skill，不执行模型。

---

# 6. Provider Fingerprint 行为

Provider profile 已包含：

```text
professional_skill_id
professional_skill_version
grounding_contract
```

因此 Professional Skill 版本或 Grounding Contract 改变会进入 P7 task fingerprint。

旧 SOURCE_BIBLE 不会被新 Skill 静默视为相同生成条件。

模型切换 / 模型 profile 改变仍遵守：

```text
旧 SOURCE_BIBLE    → STALE
旧 STORY_SKELETON  → STALE
旧 RHYTHM_SKELETON → STALE
P6 Source Evidence → CURRENT，不修改
```

---

# 7. 同一真实短剧重跑验收

Professional Skill / Grounding 修改完成后，必须使用**与第一次真实 P7 相同的 Episode**重新运行 Doubao Seed 2.1 Pro。

输入保持：

```text
同一完整 Episode
+
同一 CURRENT P6 Source Evidence
+
同一 CURRENT Shot Anchors（如果仍 CURRENT）
```

这样才能判断变化来自 Skill / Prompt / Grounding，而不是素材差异。

## 7.1 必查事实

人工至少抽查：

1. `128 元` 是否与 canonical dialogue 对应；
2. `结婚八年` 如果仍出现，是否有明确 Evidence / 视频依据；
3. `赘婿` 如果仍出现，是否有明确 Evidence / 视频依据；
4. `以前也拿过花 / 经常拿快递` 如果仍出现，是否原片明确交代；
5. 黑色垃圾袋只应确认其画面存在；如果“顺手拿花”的因果没有明确依据，应为 INFERENCE / UNKNOWN，而不是 FACT；
6. 人物姓名、502 / 503 业主等身份是否由 OCR / 视频身份卡或 canonical dialogue 支持。

## 7.2 必查 world_rules

预期：

- 不再出现对“老人”“男性”“现实社会”等群体的泛化；
- 不出现法律定性或道德训诫；
- 每一条保留的 world rule 都是一条本作品内部 FACT；
- 每条 world rule 都有对应 `world_rule_groundings`；
- 没有明确内部规则时为空数组。

## 7.3 必查故事质量没有退化

Grounding 收紧不能把模型变成只会摘抄 Evidence。

仍必须保持：

- 整集故事概述准确；
- 人物不混淆；
- 关系变化准确；
- 6 个左右的语义剧情窗口可以继续跨多个 Shot；
- Hook / Conflict / Escalation / Reveal / Relationship Change / Cliffhanger 与原片一致；
- Story Skeleton 可用于后续改编约束；
- Rhythm Skeleton 能描述完整 Episode 的叙事 / 剪辑节奏。

---

# 8. P7 与 P8 边界

Seko 产品实测已经看到：

```text
源作概览分析
→ 读取节点详情
→ 逐镜拉片分析
→ 分镜表
```

因此 P7 不应该为了接近 Seko 分镜表而提前逐 Shot 输出：

- 景别；
- 构图；
- 运镜；
- 焦距 / 景深；
- 逐镜主体绑定；
- 逐镜对白 / 旁白列；
- 逐镜音效列。

这些仍属于 P8。

P7 的正式职责保持：

```text
完整 Episode
+
Source Evidence
↓
SOURCE_BIBLE《源作概览分析》
+
Story Skeleton
+
Rhythm Skeleton
```

---

# 9. 当前完成状态

当前代码层：

```text
Professional Skill manual / manifest  ✅
Professional Skill machine registry    ✅
Skill read-only API                     ✅
Doubao / Qwen Prompt 读取 Skill rules   ✅
FACT / INFERENCE / UNKNOWN Schema       ✅
Provider claim grounding guardrail      ✅
Provider profile / task fingerprint     ✅
自动测试                                ✅
```

2026-09-09 当前 CI：

```text
Frontend Typecheck / Unit / Build = PASS
Backend install / compile / import / migrate / pytest = PASS
pytest = 81 passed
```

但真实人工状态仍为：

```text
P6 = ✅ 已验收
P7 = 🟡 需要用同一真实短剧按新 Professional Skill / Grounding Contract 重跑并人工确认
P8 = ⏸ 未开始

EPISODE_UNDERSTANDING != AVAILABLE
STORY_RHYTHM != AVAILABLE
```

只有重跑结果通过第 7 节的 Source Truth 与故事质量检查，并由项目使用者明确确认，才允许正式把 P7 标记为完成。
