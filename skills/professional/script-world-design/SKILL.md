# 剧本生成短剧：目标世界与资产设计 Skill

## 输入与责任

只接收 `SCRIPT_TO_DRAMA` 项目的当前 `SOURCE_TEXT_SNAPSHOT + STORY_SKELETON + RHYTHM_SKELETON`，原剧本是原文事实。输出可审阅的 `TARGET_BIBLE` 和 `TARGET_ASSETS` **定义**，不是已经生成的资产图片。

## 公开资料与转化

- Final Draft 官方的剧本元素介绍：https://kb.finaldraft.com/hc/en-us/articles/27646947570196-What-are-script-elements —— 原剧本的场景标题、动作、人物、对白属于不同信息类型；提取目标世界时不能混淆。
- StudioBinder 官方剧本拆解入门：https://www.studiobinder.com/tutorials/breakdown/intro-to-script-breakdowns/ —— 对场次、角色、服装、道具和 VFX 进行生产要素清点；在本项目转为稳定的实体 registry。
- StudioBinder 剧本拆解项目分类：https://www.studiobinder.com/blog/the-complete-guide-to-mastering-script-breakdown-elements/ —— 区分会影响剧情的道具与普通场景陈设，避免无意义资产爆炸。
- Runway 图片生成视频提示指南：https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide —— 首帧负责人物外观/空间/构图，视频提示主要描述主体与镜头运动；本 Skill 只制作视觉设定，不越权代替下游模型专属 Prompt Skill。

这些公开材料是方法来源；本仓库的证据锁、Artifact 版本和人工确认规则是产品工程约束，不应伪称原资料逐字要求。

## 操作步骤

1. 阅读全剧结构分析与对应原文：逐场列出确实出现的人物、场景、关键道具和人物之间的关系。给每条**原文事实**记录可追溯场次。
2. 建立三类稳定 ID：`CHARACTER_*`、`SCENE_*`、`PROP_*`。同一人物跨集、跨换装仍是同一身份；同一场景不同时间状态记录变体，不复制新 ID。
3. 建立角色视觉卡：外观、年龄段（仅原文明确时）、服饰、体态、可见特点、主要情绪表演、服饰变化和镜头可见区分点；不可用未经证实的出身、种族、心理诊断补足。
4. 建立场景视觉卡：空间分区、光照、时段、布局、稳定布景锚点，以及不同场次的状态变化。
5. 建立剧情道具卡：物体形状与状态，谁持有、何时出现、丢失和变更；普通背景物默认不独立生产。
6. 每个视觉新增细节标记 `VISUAL_INFERENCE`，属于创作性补足，不伪装成已有剧本事实。若某种补足会改变冲突因果、身份或关系，记录 `USER_DECISION_REQUIRED`，停止自动发布。
7. 校验：人物名字和 ID 全文统一；重要道具交接连续；关键场景布局在可连接镜头中不跳变；剧本已有对白不被重写；没有把本阶段产物冒充图片或视频。

## 输出建议字段

`character_registry[] {id, name, source_scene_numbers[], source_facts[], visual_inferences[], visual_description, costumes[]}`；
`scene_registry[] {id, name, source_scene_numbers[], source_facts[], visual_description, variants[]}`；
`prop_registry[] {id, name, source_scene_numbers[], narrative_function, visual_description, state_changes[]}`；
`unresolved_decisions[]`。

发布之前先通过严格 JSON schema，再复核每条引用的场次、实体 ID 唯一性与跨镜一致性。