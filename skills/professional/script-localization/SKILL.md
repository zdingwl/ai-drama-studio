# 剧本跨文化本土化 Professional Skill

## 目标

把一个已经成立的剧本迁移到目标语言和目标地区，让目标观众读起来像“原本就发生在这里”，同时不偷偷改掉故事。

核心公式：

```text
Source Story Truth
+ Target Culture / Language
+ Character Voice
+ Consistency Registry
= Localized Target Script
```

## 研究依据

本手册综合：

- American Translators Association 对 transcreation 的定义：目标文本不仅翻译字面，还要为目标受众重建信息、风格、情绪和文化背景。
- Microsoft Localization 指南：Localization 不只是翻译，还涉及文化引用、习语、货币、日期、度量衡、图像/市场惯例；应建立目标语言 style guide、术语表与一致性资产。
- Netflix Timed Text Style Guides：翻译应保留剧情相关信息，保持原作 tone、register、class、formality；脏话强度和意图应等价；专名、品牌和文化元素需要一致处理。
- Final Draft screenplay guidance：目标输出仍应保持 Scene Heading、Action、Character、Dialogue 等剧本元素，而不是改写成小说。

Netflix 的字幕规则并不直接等同于“剧本本土化”；本 Skill 只吸收其中关于**意义、语气、人物声音和一致性**的原则。本项目允许在 preservation locks 之外做更强的文化迁移。

## 三层决策

### A. 必须锁定

默认不得改变：

- 故事主线；
- 因果关系；
- 人物剧情功能；
- 核心人物关系；
- 关键秘密与信息揭示顺序；
- 冲突与反转顺序；
- 情绪峰值；
- Payoff；
- Cliffhanger；
- 原剧本明确依赖的关键道具功能。

### B. 可以本土化

在不破坏 A 的前提下可以替换：

- 人名与昵称；
- 地名；
- 学校、公司、医院、警局、法院等机构表达；
- 工作岗位和社会身份的当地等价物；
- 金额、货币、日期、时间、单位；
- 饮食、交通、支付、通信、社交平台；
- 节日、家庭称谓、礼貌体系；
- 俚语、脏话、网络语言；
- 双关、笑点、梗；
- 视觉上只属于文化包装的道具。

### C. 不能自动决定

若替换会改变：

- 核心冲突成立条件；
- 人物价值观；
- 法律/伦理后果；
- 婚姻、宗教、族群等敏感关系；
- 关键身份造成的剧情机制；

则输出 `unresolved_decision`，不得自行“让它合理”。

## 本土化计划

正式改写前必须先建立全剧一致 Registry：

```text
character_map
location_map
institution_map
terminology
honorific/register rules
money/unit/date rules
brand treatment
dialogue style guide
preservation locks
```

后续每个文本块都使用同一个 Registry。

## 对白规则

目标对白优先级：

1. 剧情意义；
2. 人物意图；
3. 情绪强度；
4. 人物声音；
5. 关系与权力距离；
6. 目标地区自然度；
7. 字面对齐。

禁止：

- 所有人说成同一种 AI 腔；
- 把粗鲁角色自动礼貌化；
- 把正式角色自动口语化；
- 直译双关导致笑点消失却不处理；
- 为“更顺”删掉 plot-pertinent 信息；
- 因文化不熟悉就随意替换品牌、名人或机构。

## 格式规则

目标输出继续是剧本：

- Scene Heading 保持场景边界；
- Action 写观众可见/可听内容；
- Character Cue 明确对白归属；
- Parenthetical 只在表演意图确有必要时保留；
- V.O. / O.S. / 旁白语义不丢失；
- 不把整个剧本改成连续散文。

## Change Log

所有实质变更至少记录：

```text
category
source
target
reason
```

典型 category：

```text
CHARACTER_NAME
LOCATION
INSTITUTION
MONEY
UNIT
DATE_TIME
HONORIFIC
SLANG
PROFANITY
CULTURAL_REFERENCE
JOKE_WORDPLAY
BRAND
SOCIAL_CUSTOM
DIALOGUE_REGISTER
```

## 最终校验

发布前检查：

- 人物名称是否一对一稳定；
- 同一地点是否出现多种译名；
- 同一称谓是否随场景漂移；
- 货币/单位是否前后矛盾；
- 角色说话风格是否突然改变；
- Story Beat 顺序是否被移动；
- 是否增加了原文没有的新秘密、动机或关系；
- 是否删除了 plot-pertinent 信息；
- 是否存在本应让用户决定但被模型静默处理的文化冲突。

通过后才能发布 TARGET_SCRIPT。
