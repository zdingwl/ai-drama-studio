# 整集原片理解 Professional Skill

> Skill ID：`source-video-understanding`  
> 当前版本：`1.0.0`  
> 适用能力：`EPISODE_UNDERSTANDING`、`STORY_RHYTHM`

## 1. 目标

把完整 Episode 与 CURRENT Source Evidence 转化为可读、可编辑、可版本化的《源作概览分析》 (`SOURCE_BIBLE`)，建立后续逐镜拉片所需的整集故事、人物、关系、场景、关键道具、Story 与 Rhythm 全局知识。

本 Skill 解决的是：

> **整集原片意味着什么。**

它不负责逐 Shot 精细镜头语言，不负责目标版本本土化，也不负责重新识别 canonical 对白 / OCR。

---

## 2. 使用条件

适用于：

- `REPLICA`；
- `REDRAW`；
- 已存在完整、不可变的 `SOURCE_VIDEO`；
- 已存在覆盖当前完整 Episode 的 CURRENT Source Evidence；
- 可选读取 CURRENT `SHOT_ANCHORS` 作为时间定位提示。

不适用于：

- `TRANSLATION` 的纯对白翻译流程；
- P8 逐镜精细拉片；
- 从单个 Reference Clip 猜整集故事；
- 目标版本改编 / 本土化；
- 用多模态模型重新转写并覆盖 P6 ASR/OCR。

---

## 3. Source Truth 与输入优先级

权威顺序：

```text
完整 Episode / SOURCE_VIDEO
= 最高层原片事实源

CURRENT P6 Source Evidence
= canonical 对白 / OCR 文字事实源

CURRENT Shot Anchors
= 可选时间定位提示
= 不是剧情事实源
= 不是语义分段边界
```

硬规则：

1. 模型必须直接读取完整 Episode；
2. 不允许把 Episode 拆成若干 Reference Clip 后分别理解再拼剧情；
3. 对白正文只能来自 CURRENT P6 Evidence；
4. OCR 正文只能来自 CURRENT P6 Evidence；
5. 视频画面可以提供直接视觉事实；
6. Shot Anchors 只能辅助定位，不得被当成剧情段落或重新定义剧情结构。

---

## 4. 三档事实等级

所有容易被模型“合理补全”的事实都必须遵守：

```text
FACT
= 原片直接可见，或 CURRENT Evidence 明确陈述

INFERENCE
= 基于多个已知事实可以合理推导，但原片没有直接确认

UNKNOWN
= 无法可靠判断
```

总原则：

> **宁可 UNKNOWN，也不要合理补全。**

### 4.1 FACT

FACT 必须能追溯到至少一种来源：

- canonical dialogue evidence ID；
- canonical visual text evidence ID；
- 完整 Episode 中明确的时间窗口视觉观察。

例如：

```text
画面身份卡明确写“徐然 / 502业主”
→ FACT

对白明确说“我们结婚八年了”
→ FACT
```

### 4.2 INFERENCE

推断可以用于理解，但不能伪装成 Source Truth。

例如：

```text
人物拎着垃圾袋走出家门
→ 可以确认：人物手里拎着垃圾袋（FACT）

因此推断“她刚才一定是倒垃圾时顺手拿走快递”
→ 原片若未明确确认，只能是 INFERENCE
```

INFERENCE 可以出现在剧情分析、人物动机分析中，但必须保留其推断性质，不得改写为人物历史或客观事实。

### 4.3 UNKNOWN

以下情况应输出 UNKNOWN / 未确认，而不是猜测：

- 人物姓名无法由身份卡、对白或上下文可靠确认；
- 关系类型只能凭年龄或同框猜测；
- 道具剧情作用没有明确依据；
- 行为动机没有原片信息支撑；
- 人物过去经历只存在合理想象，没有原片陈述。

---

## 5. 整体分析方法

### 5.1 故事概述

概述必须覆盖本 Episode 实际发生的核心事件、冲突升级、人物关系变化和结尾状态。

允许叙事性归纳，不允许补写原片不存在的事件。

### 5.2 故事背景

只允许使用：

- 本 Episode 明确陈述的历史；
- 人物身份卡 / OCR 明确提供的信息；
- 从完整 Episode 可直接确认的地点 / 关系 / 情境。

禁止为了让背景“完整”而自动补充人物履历。

### 5.3 世界规则

`world_rules` 只描述**本作品内部已经成立、对理解剧情有约束作用的源作事实**。

允许：

```text
502 是徐然所在住户
503 是王桂香所在住户
某角色明确受某家庭关系约束
```

禁止：

```text
“部分老人通常会……”
“缺乏担当的男性往往会……”
“现实社会中某类人一般……”
法律结论 / 道德训诫 / 社会学泛化
```

如果本集没有真正的世界规则，允许 `world_rules = []`。

---

## 6. 人物与人物关系

### 6.1 人物身份

姓名 / 身份优先依据：

```text
画面身份卡 / OCR
→ canonical 对白明确称呼
→ 完整 Episode 连续上下文
→ 无法确认则使用稳定候选名
```

禁止：

- 因为“一张脸”直接确定最终身份；
- 因年龄、服装、性别刻板印象补全职业 / 亲属关系；
- 把剧情功能描述写成人物真实历史。

### 6.2 人物关系

“夫妻、母子、婆媳、邻居、同事、结婚年限、赘婿”等具体关系事实必须有来源。

关系变化可以做剧情分析，但必须与本集可观察行为一致。

---

## 7. 场景与关键道具

### 7.1 场景

场景可以记录：

- 名称；
- 时间范围；
- 空间关系；
- 可观察环境细节。

不得把视觉装修风格推断成未经证实的社会身份或经济背景事实。

### 7.2 道具

区分：

```text
appearance_state
= 画面可见状态

story_function
= 该道具在剧情中的作用
```

`appearance_state` 可以由画面直接确认。

`story_function` 没有明确依据时允许写“未确认明确剧情功能”，不得因为道具出现就硬编因果。

---

## 8. 时间化原作剧情

`timed_script` 是**语义 / 剧情时间窗口**，不是 Shot 表。

允许：

- 一个剧情段跨多个 Shot；
- 相邻语义窗口轻微重叠；
- 依据故事事件、人物状态和冲突阶段划分。

必须：

- 时间都在完整 Episode 范围内；
- dialogue evidence ID 只引用 CURRENT P6 对白；
- visual text evidence ID 只引用 CURRENT P6 OCR；
- 不根据视频音轨重新写对白；
- 不把 Shot Anchors 伪装成剧情段。

---

## 9. Story Skeleton

Story Skeleton 描述整集的叙事骨架，而不是逐镜细节。

可使用：

- `HOOK`；
- `CONFLICT`；
- `ESCALATION`；
- `REVEAL`；
- `REVERSAL`；
- `EMOTIONAL_PEAK`；
- `RELATIONSHIP_CHANGE`；
- `PAYOFF`；
- `CLIFFHANGER`。

Beat 必须在原片真实时间范围内，并且不能为了凑结构强行创造并不存在的反转 / 爽点。

---

## 10. Rhythm Skeleton

Rhythm Skeleton 描述：

- 整体节奏快慢；
- 场景内部节奏；
- 对白—反应节奏；
- 剪辑节奏趋势；
- 关键 Story Beat 周围的时间组织。

P7 只建立整集节奏骨架。

以下内容留给 P8：

- 每个 Shot 的景别；
- 构图；
- 镜头角度；
- 运镜；
- 焦距 / 景深；
- 每个 Shot 的主体绑定；
- 逐镜音效。

---

## 11. 执行步骤

```text
1. 校验完整 Episode 与 CURRENT Evidence
2. 读取完整 Episode
3. 建立时间化剧情语义段
4. 归纳人物与关系
5. 归纳场景与关键道具
6. 建立事件 / 情绪时间线
7. 建立 Story Skeleton
8. 建立 Rhythm Skeleton
9. 对容易被补全的事实做 FACT / INFERENCE / UNKNOWN 检查
10. 校验 Evidence ID / 时间范围 / 引用完整性
11. 只有全部通过才发布 SOURCE_BIBLE
```

---

## 12. 用户决策策略

默认自动完成，不因为普通歧义频繁打断用户。

只有以下情况需要用户决定：

- 关键人物身份存在互相冲突的强证据；
- 核心关系存在结构性冲突，无法安全归一；
- 原片本身存在无法判断的版本 / 剪辑缺失，直接影响 Story Skeleton；
- 用户明确要求偏离原片事实做创作解释。

普通不确定性优先标记 UNKNOWN，而不是询问或猜测。

---

## 13. 输出契约

正式输出：

```text
SOURCE_BIBLE《源作概览分析》
+
STORY_SKELETON
+
RHYTHM_SKELETON
```

必须满足：

- 用户可读；
- 用户可编辑；
- revision 明确；
- input fingerprint 明确；
- 完整 Episode 与 Source Evidence provenance 可追溯；
- canonical Evidence 保持原文；
- 重要事实与推断边界明确；
- 不能提前产出 P8 分镜表。

---

## 14. Fail-closed

以下情况禁止发布 SOURCE_BIBLE：

- 引用不存在的 dialogue / OCR evidence ID；
- FACT 没有任何 Evidence / 视频时间依据；
- 时间范围超出 Episode；
- 人物关系引用不存在的人物；
- Provider 输出结构不合法；
- 把社会泛化 / 法律判断写成 source world rule；
- P7 Task 创建后上游 Source / Evidence / Provider profile 已变化。

失败只能让 Task FAILED，不能用半成品覆盖旧 CURRENT SOURCE_BIBLE。

---

## 15. 完成标准

本 Skill 只有在以下全部成立时才算完成一次有效执行：

- 完整 Episode 被直接消费；
- CURRENT Source Evidence 未被改写；
- SOURCE_BIBLE 结构合法；
- 时间 / Evidence / 人物引用合法；
- 关键 source facts 有可追溯依据；
- Story / Rhythm 与整集剧情一致；
- 不包含明显片外补全和社会泛化；
- 输出可以作为 P8 的全局上下文。
