# P7 整集原片理解 Professional Skill 与 Grounding 验收

> 日期：2026-09-09  
> 当前状态：P7 工程已接入真实 Provider、项目级模型选择、运行时配置、Professional Skill 与 `grounded-source-truth-v2`；**P7 仍未最终人工验收**。  
> 本文补充 `docs/04_阶段人工验收规范.md`，不改变 P8 尚未开始的状态。

---

# 1. Professional Skill

正式 Professional Skill：

```text
skills/professional/episode-understanding/SKILL.md
skills/professional/episode-understanding/manifest.json
```

当前版本：

```text
source-video-understanding@1.1.0
```

Skill 不是一段 Prompt。正式运行关系：

```text
Root Project Skill
→ source-video-understanding Professional Skill
→ Provider Prompt
→ Grounded Schema
→ Provider Guardrail
→ Service Publication Guardrail
→ SOURCE_BIBLE
```

Doubao / Qwen 三个 P7 Provider 必须执行同一套 Professional Skill，不得各自维护互相冲突的业务判断标准。

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

# 3. Grounding v2

当前 Grounding Contract：

```text
grounded-source-truth-v2
```

Schema：

```text
SOURCE_BIBLE schema 1.1
```

Provider Prompt：

```text
p7-source-bible-v2
```

事实等级仍为：

```text
FACT
= 原片直接可见，或 CURRENT Source Evidence 明确陈述

INFERENCE
= 根据已有 Source Facts 可以合理推导，但原片没有直接确认

UNKNOWN
= 无法可靠判断
```

但 v2 增加最关键的发布语义：

```text
FACT / INFERENCE
→ 必须至少有 CURRENT Evidence ID 或完整 Episode video_time_ranges

UNKNOWN
→ 不得携带 Evidence / video_time_ranges
→ 只能对应省略 / null 的未确认 claim
→ 禁止“确定性正文 + UNKNOWN grounding”
```

核心原则：

> **UNKNOWN 不是绕过 Source Truth 校验的通行证。**

---

# 4. 必须 FACT-grounded 的正式 Source Facts

当前 Provider 输出如果存在以下正式字段，其 grounding 必须为 `FACT`：

```text
overall_analysis.story_background
characters[].identity
relationships[]
scenes[]
story_events[]
key_props[].appearance_state
world_rules[]
```

其中：

- 人物真实姓名无法确认时可以使用稳定“未命名角色A”标签，但该角色在原片中的存在仍需视频依据；
- 夫妻 / 邻居 / 婆媳 / 同事 / 结婚年限 / 赘婿等具体关系没有直接依据时，不得创建正式 relationship；
- 场景与 Story Event 可以使用完整 Episode 的明确视频时间范围作为直接视觉依据；
- `world_rules` 每一条必须和同索引 `world_rule_groundings` 一一对应，且 grounding 必须为 FACT。

没有真正 source-internal world rule 时应直接：

```json
{
  "world_rules": [],
  "world_rule_groundings": []
}
```

禁止写入：

- “部分老人一般会……”；
- “某类男性通常会……”；
- 社会经验总结；
- 法律结论；
- 道德训诫；
- 与本 Episode 无关的世界知识。

---

# 5. 道具 Grounding

v1 暴露出的典型错误是：

```text
画面看到王桂香手持黑色垃圾袋
↓
模型补成
她正准备倒垃圾
↓
进一步补成
她倒垃圾时看到门口花并顺手拿走
```

v2 强制拆开：

```text
appearance_state
= 画面可见状态
= appearance_grounding 必须 FACT

story_function
= 剧情作用
```

`story_function` 规则：

```text
原片直接确认
→ FACT + grounding

只是合理解释
→ INFERENCE + grounding + 推断语气

无法可靠确认
→ story_function = null
→ story_function_grounding = UNKNOWN
```

因此黑色垃圾袋如果原片没有进一步依据，正确结果应类似：

```json
{
  "name": "黑色垃圾袋",
  "appearance_state": "王桂香出场时手里拎着黑色垃圾袋",
  "appearance_grounding": {
    "support_level": "FACT",
    "video_time_ranges": [{"start_us": 3640000, "end_us": 15560000}]
  },
  "story_function": null,
  "story_function_grounding": {
    "support_level": "UNKNOWN",
    "dialogue_evidence_ids": [],
    "visual_text_evidence_ids": [],
    "video_time_ranges": []
  }
}
```

---

# 6. 双层 fail-closed

Grounding v2 不再只依赖 Provider adapter 自己校验。

运行时必须经过：

```text
Provider response
↓
Provider grounding validation
↓
Pydantic parse
↓
Service publication grounding validation
↓
Episode / Evidence / character reference validation
↓
只有全部通过才发布 SOURCE_BIBLE
```

以下任一情况必须失败且不能发布半成品：

- 不存在或不属于 CURRENT Episode 的 Evidence ID；
- FACT / INFERENCE 无任何支持依据；
- UNKNOWN 携带 Evidence / video range；
- 确定性 Source Fact 仍标 UNKNOWN；
- world_rules / groundings 数量不一致；
- 任意 world rule 不是 FACT；
- 道具 appearance 没有 FACT grounding；
- 道具 story_function 为 UNKNOWN 时正文仍非空；
- grounding 视频时间越过 Episode；
- 人物关系引用不存在的人物；
- Provider 输出 Schema 不合法；
- 上游 Source / Evidence / Provider profile 在任务执行期间发生变化。

P6 Source Evidence 在任何上述失败中都不能被改写。

---

# 7. Provenance 可审计性

新的 SOURCE_BIBLE provenance 必须直接显示：

```text
prompt_version = p7-source-bible-v2
schema_version = 1.1
professional_skill_id = source-video-understanding
professional_skill_version = 1.1.0
grounding_contract = grounded-source-truth-v2
```

此外继续保留：

- exact SOURCE_VIDEO Artifact ID / fingerprint；
- exact SOURCE_DIALOGUE Artifact ID / fingerprint；
- 可选 Shot Anchors ID / fingerprint；
- Episode Evidence Set ID / fingerprint；
- ProviderJob ID；
- provider / model；
- remote response ID；
- generated Task ID。

这些字段也进入 Provider profile / task fingerprint；Professional Skill、Prompt、Schema 或 Grounding Contract 改变后不得复用旧任务结果。

---

# 8. v1 → v2 STALE 行为

`grounded-source-truth-v1` 已经通过真实短剧暴露出：

```text
确定性正文
+
UNKNOWN grounding
```

的逃逸路径。

因此 Alembic `0010_p7_grounding_contract_v2` 部署时必须自动使旧 P7 链失效：

```text
旧 SOURCE_BIBLE       → STALE
旧 STORY_SKELETON     → STALE
旧 RHYTHM_SKELETON    → STALE
P6 Source Evidence    → CURRENT，完全不动
```

迁移不可逆地避免旧 v1 SOURCE_BIBLE 在 downgrade 后被静默恢复为 CURRENT。

---

# 9. 同一真实短剧第三次重跑验收

必须继续使用用户已经用于前两轮验收的同一 Episode：

```text
货到付款惩治隔壁大妈-第01集.mp4
约 66 秒
```

输入保持：

```text
同一完整 Episode
+
同一 CURRENT P6 Source Evidence
+
同一 CURRENT Shot Anchors（如果仍 CURRENT）
```

这样变化才能归因于 Skill / Prompt / Grounding Contract，而不是素材变化。

## 9.1 必查 Source Truth

人工至少抽查：

1. `128 元` 是否与 canonical dialogue 一致；
2. `结婚八年` 如果出现，关系 grounding 是否明确支持；
3. `赘婿` 如果出现，是否有 Evidence / 视频直接支持；
4. `以前也拿过花 / 经常拿快递` 如果出现，是否原片明确交代；
5. 黑色垃圾袋如果没有明确剧情功能，`story_function` 是否为 null / UNKNOWN，而不是继续写“顺手拿花”；
6. 人物姓名、502 / 503 业主等身份是否为 FACT grounding；
7. 所有 scene / story_event 是否不再整体使用 UNKNOWN 逃逸。

## 9.2 必查 world_rules

预期只有两种合法状态：

```text
A. [] / []
```

或者：

```text
B. 每条都是本作品内部 FACT
   且 world_rules 与 groundings 1:1
```

任何社会泛化 / 法律结论直接判本轮失败。

## 9.3 必查故事质量没有退化

Grounding 收紧不能把模型变成只会摘抄 Evidence。

仍必须保持：

- 整集故事概述准确；
- 人物不混淆；
- 关系变化准确；
- 约 6 个语义剧情窗口可以继续跨多个 Shot；
- Hook / Conflict / Escalation / Reveal / Relationship Change / Cliffhanger 与原片一致；
- Story Skeleton 可作为后续复刻 / 重绘约束；
- Rhythm Skeleton 能描述完整 Episode 的叙事 / 剪辑节奏。

## 9.4 必查 provenance

导出的结果必须能直接看到：

```text
schema_version: 1.1
prompt_version: p7-source-bible-v2
professional_skill_id: source-video-understanding
professional_skill_version: 1.1.0
grounding_contract: grounded-source-truth-v2
```

缺任一项均视为审计能力未收口。

---

# 10. P7 与 P8 边界

Seko 产品实测观察到：

```text
源作概览分析
→ 读取节点详情
→ 逐镜拉片分析
→ 分镜表
```

因此 P7 仍不能提前逐 Shot 输出：

- 景别；
- 构图；
- 运镜；
- 焦距 / 景深；
- 逐镜主体绑定；
- 逐镜对白 / 旁白列；
- 逐镜音效列。

这些仍属于 P8。

P7 正式职责保持：

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

# 11. 当前完成状态

代码层目标：

```text
Professional Skill 1.1.0                  ✅
grounded-source-truth-v2                  ✅
Prompt p7-source-bible-v2                 ✅
SOURCE_BIBLE schema 1.1                   ✅
UNKNOWN 非通行证                          ✅
Provider grounding guardrail              ✅
Service publication grounding guardrail   ✅
Provenance 直接记录 Skill / contract       ✅
v1 CURRENT 迁移为 STALE                    ✅
自动测试                                  待最终 CI 确认
```

真实人工状态继续保持：

```text
P6 = ✅ 已验收
P7 = 🟡 等待同一真实短剧按 v2 第三次重跑并由项目使用者确认
P8 = ⏸ 未开始

EPISODE_UNDERSTANDING != AVAILABLE
STORY_RHYTHM != AVAILABLE
```

只有第三次真实 Doubao 结果通过第 9 节，并由项目使用者明确确认，才允许正式把 P7 标记为完成。