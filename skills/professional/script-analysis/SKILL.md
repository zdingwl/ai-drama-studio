# 剧本结构化理解 Professional Skill

## 目标

把剧本文本变成后续本土化和生成都能稳定消费的 Source Truth。这个 Skill **只理解，不改写**。

正式输出：

```text
SOURCE_TEXT
→ SOURCE_TEXT_SNAPSHOT
→ STORY_SKELETON
→ RHYTHM_SKELETON
```

## 研究依据

本手册综合以下公开资料的稳定原则：

- Final Draft《Screenplay Formatting and Elements》：剧本至少需要正确区分 Scene Heading、Action、Character、Dialogue、Parenthetical、Transition 等元素。
- Final Draft《How to Format a Screenplay》：Scene Heading 应表达 INT/EXT、Location、Time of Day；Action 描述观众可见内容；Character Cue 明确对白归属。
- Netflix Timed Text Style Guide：跨语言处理时剧情相关对白优先，角色语气、register、class、formality 与创作意图需要保持一致。
- Microsoft Globalization / Localization 指南：本地化需要显式处理文化引用、习语、日期、时间、货币、度量衡、书写系统和市场惯例，并建立术语与 style guide。

这些来源用于建立分析维度，不复制其文本。

## 硬规则

1. **SOURCE_TEXT 是唯一原文事实。**
2. 不修词、不润色、不自动补场景、不补人物动机。
3. 格式异常时保留原文并标记 `UNRESOLVED`。
4. 人物、场景、机构、专名必须跨全文归一，不按分块重复创造身份。
5. 主线、因果、信息揭示顺序、反转顺序必须保持原文。
6. 任何“这是为什么”的解释若不能从文本证明，属于 `STRUCTURAL_INFERENCE`，不能写成 Source Fact。

## 分析顺序

### 1. 剧本元素

优先识别：

- Scene Heading：内/外景、地点、时间；
- Action：画面中实际发生的动作；
- Character Cue；
- Dialogue；
- Parenthetical；
- V.O. / O.S. / 旁白；
- Transition；
- 明确出现的重要道具和屏幕文字。

### 2. 故事骨架

必须提取：

- premise / logline；
- protagonist / antagonist / supporting roles；
- character goal / obstacle / stakes；
- Story Beat；
- 因果链；
- setup / escalation / reversal / payoff；
- episode/act cliffhanger（若原文存在）。

### 3. 节奏骨架

每个关键节奏点记录：

- narrative function；
- intensity 1~5；
- 发生顺序；
- 参与人物；
- 是否属于 Hook / Conflict / Escalation / Reversal / Peak / Payoff / Cliffhanger。

### 4. 本土化准备信息

只记录，不替换：

- 人名与称谓；
- 地点；
- 学校/公司/医院/警察/法院等制度；
- 金额、货币、日期、度量衡；
- 饮食、节日、宗教、家庭关系；
- 俚语、脏话、双关、网络梗；
- 社交平台、支付方式、交通方式；
- 品牌和可能涉及商标的实体；
- 阶层、礼貌等级、权力距离、称呼体系。

每条文化元素都需要说明：

```text
原始元素
剧情功能
如果直译会出现的问题
是否允许后续替换
```

## 长文本

不得静默截断。

长剧本：

```text
稳定段落切块
→ 每块结构化分析
→ 全局合并
→ 人物/场景/术语去重
→ 全局 Story / Rhythm 校验
```

分块边界只是工程手段，不是故事边界。

## 完成条件

输出必须让后续本土化模型知道三件事：

1. **什么绝对不能改；**
2. **什么是文化包装，可以改；**
3. **什么目前无法确定，必须保留为 unresolved。**
