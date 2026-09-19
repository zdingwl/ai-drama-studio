# 剧本本土化 Skill：公开资料核查与规则映射

> 日期：2026-09-19。此文是技能规则来源审计，不表示模型质量已经真实验收。

## 已核查的一手资料

| 资料 | 链接 | 对应本项目规则 |
|---|---|---|
| Final Draft, Screenplay Formatting and Elements | https://www.finaldraft.com/learn/screenplay-formatting-elements/ | 场景标题、动作、人物、对白与括注等元素必须区别解析；目标输出应保持剧本结构。 |
| Final Draft, What are script elements? | https://kb.finaldraft.com/hc/en-us/articles/27646947570196-What-are-script-elements | 剧本段落有各自的类型和格式；不把剧本扁平化成小说散文。 |
| Microsoft, How to perform localization testing | https://learn.microsoft.com/en-us/globalization/testing/how-to-perform-localization-testing | 评估准确度、语境、风格手册、术语、一致性和文化适配；人工审阅必须基于完整上下文。 |
| Microsoft, Localize your product | https://learn.microsoft.com/en-us/globalization/localization/localization-overview | 建立目标语言风格指南、术语词表，跨版本保留一致性；本项目的文化映射表借鉴此工程思想。 |
| Netflix, English USA Timed Text Style Guide | https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide | 保持角色原有 tone、register、class、formality；译写脏话时保持强度与意图；剧情相关对白优先。 |
| Netflix, Timed Text Style Guide: Subtitle Templates | https://partnerhelp.netflixstudios.com/hc/en-us/articles/219375728-Timed-Text-Style-Guide-Subtitle-Templates | 需要上下文标注文化典故、俚语、双关、人物关系、正式程度与意图。本项目转成分析阶段文化锚点。 |

## 适用性边界

- Final Draft 是剧本格式参考，不定义本产品的 Agent、Artifact 或版本管理方法。
- Microsoft 是通用软件本地化质量参考，不能假称其规定短剧必须采用某个故事结构。
- Netflix 文献规范字幕与模板，不应把字幕字数/阅读速度等限制生搬硬套到正式可读剧本；只借用对白意义、人物语气及上下文一致性原则。
- 「锁定故事因果与信息揭示顺序」「跨场次人物注册表」「SOURCE_TEXT 不可反写」「分块完整覆盖与不允许静默截断」为平台自己的产品与工程约束，并非以上机构给出的行业强制标准。

## Skill → 实现映射

- `script-analysis`：固定 SourceText 和结构化 JSON；人物/场景/节奏/文化锚点分层输出；不确定项进入 `unresolved_questions`。
- `script-localization`：计划阶段输出人物、地点、机构、术语和称谓一致性映射；核心剧情冲突写入 `unresolved_decisions` 交人工判断；生成阶段保留目标地区自然对白和 `changes`。
- Validator：使用严格 typed JSON、Artifact lineage、来源版本/fingerprint、目标语言地区校验；这些校验能保证结构与可追踪性，**不能代替真实本土化质量与人工逐场阅读验收**。

## 当前产品边界

目前文本模型一次分析上限 24000 字符；超过限制时明确失败，不会截断冒充全文分析。大体量剧本的场景分块、全剧映射全局合并和人工验收仍需后续扩展。`SCRIPT_ANALYSIS`、`EXPORT_SCRIPT` 在真实 Provider/人工完整验收前不得因工程测试通过就标记 AVAILABLE。
