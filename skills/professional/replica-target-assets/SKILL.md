# Replica Target Assets

## 目标

把 CURRENT `TARGET_BIBLE` 中已经确定的 Target Character / Scene / Prop 变成后续分镜与视频生成可以通过稳定 ID 引用的正式视觉身份包。

核心关系：

```text
Target Bible  = semantic truth
Target Assets = visual realization
```

资产设计首先服务跨镜一致性，不以单张图的审美效果作为完成标准。

当前 Professional Skill：

```text
replica-target-assets@1.1.0
P13_PROMPT_VERSION        = p13-replica-target-assets-v3
P13_TARGET_ASSET_CONTRACT = replica-target-visual-identity-v2
```

## 唯一硬输入

```text
CURRENT TARGET_BIBLE
```

P13 不把 `SOURCE_VIDEO_SNAPSHOT`、`ADAPTATION_PLAN`、`TARGET_SCRIPT` 静默加入硬输入。Target Script 的局部对白变化不应无意义地使人物脸型、场景布局或道具视觉身份全部失效。

## 用户审核语言

P13 的视觉实现文本首先是给中国用户理解和审核的，不是最终目标受众文案，也不是已经发给图像/视频模型的执行 prompt。

当前运行合同固定：

```text
review_language = zh-CN
prompt_version  = p13-replica-target-assets-v3
```

因此 Provider 新生成的 review-facing 内容必须以简体中文为主：人物外形/服装/特征/连续性/生成指导/避免项，场景布局/风格/材质/地标/光照/时间基线/连续性，以及道具形态/材质/颜色/尺度/特征/连续性。

允许保留目标地区的专有实体原文，例如：

```text
Lila Xu
Austin
HEB
iPhone
$19.99
```

规则是“解释用中文，实体名按目标地区真实写法保留”。不得因为 `target_language = en-US` 就把整份审核正文写成英文。

当前 `generation_guidance` 仍是**中文可审计的视觉设计指导**，不是最终 image/video prompt。未来真正进入生成阶段时，由独立 Generation Adapter 根据具体模型能力整理成英文或其他模型优化执行 prompt；P13 不提前实现该阶段。

## Asset-local continuity

P13 v2 visual identity contract 明确：

```text
Target*Asset.continuity_constraints
= 当前 asset 的视觉连续性
!= Target Bible preservation locks 的副本
```

Target Bible 中的 global/entity continuity、Story Beat、shot order、dialogue、rhythm、cliffhanger、人物关系等规则继续是上游正式 truth，P13 不得违反；但服务端和 Provider都不得把这些全局叙事规则机械复制到每个人物、场景、道具 packet。

允许的 continuity 示例：

- Character：脸型、发际线、主发型、体型比例、基础服装身份保持稳定；
- Scene：空间拓扑、门窗/电梯/固定地标的相对位置、主材质与稳定光照身份保持稳定；
- Prop：形态、尺寸、材质、颜色和标志性细节保持稳定。

这样既保留 Target Bible lineage，也避免视觉资产变成重复的故事锁文本墙。

## Character

必须围绕同一 `target_character_id` 稳定表达：

- P11 localized identity，不得改变故事身份；
- demographic visual direction；
- face；
- hair；
- body；
- wardrobe baseline；
- signature visual features；
- asset-local continuity constraints；
- generation guidance；
- negative constraints。

`wardrobe_baseline` 只描述人物基础服装身份与风格边界，例如轮廓、色系、材质、正式度、基础饰品。除非 CURRENT TARGET_BIBLE 已明确给出经过确认的 variation，否则禁止 P13 自行生成：

```text
场景 1 穿 A
场景 2 穿 B
闪回穿 C
卧室穿 D
逐 Shot 换装表
```

不得按 Shot 单独重写人物身份。后续 Scene/Shot wardrobe variation 只能由未来正式 production contract 作为 base asset 之上的明确 overlay。

## Scene

必须围绕同一 `target_scene_id` 稳定表达：

- P11 localized setting，不得改变场景功能；
- spatial layout；
- architecture / interior or exterior style；
- materials palette；
- fixed landmarks；
- lighting baseline；
- time-of-day baseline；
- asset-local continuity constraints；
- generation guidance；
- negative constraints。

场景资产用于保证空间身份和可识别 landmark 跨镜稳定，不负责重排 Scene order 或 Story Beat timing。

`time_of_day_baseline` 是视觉基线，不是剧情时间轴。若 CURRENT TARGET_BIBLE 没有明确给出故事时段，P13 不得仅凭 Scene 顺序、闪回或情绪自行推断“深夜 / 次日上午 / 数小时后”等新剧情事实。此时应描述不依赖虚构剧情时间的稳定采光/人工光基线，并把具体 Shot 昼夜变化留给后续 Storyboard / Shot context。

## Prop

必须围绕同一 `target_prop_id` 稳定表达：

- P11 localized form / functional identity，不得改变剧情功能；
- visual form；
- material；
- color；
- scale；
- signature features；
- asset-local continuity constraints；
- generation guidance；
- negative constraints。

## Provider 权限

Provider 只输出视觉实现语义。

Provider 不得输出或修改：

```text
Target Bible semantic identity
Target Asset ID
Artifact ID
revision / fingerprint / CURRENT / STALE
Source facts
Target Script
Story Beat / shot order / dialogue / rhythm / cliffhanger preservation locks
逐 Scene / Shot wardrobe plan
未经 Target Bible 明确支持的剧情时间变化
Voice / TTS / Timing
Target Storyboard
Video Generation / QC / Post
```

当前仓库只有已接入的 text-only reasoning Provider，因此 v1 reference-media capability 不伪造图片 reference media。以后真实图片 Provider 必须沿相同 asset identity 独立接入并验收。

## 服务端确定性职责

服务端负责：

1. 从 CURRENT Target Bible 构造 exact entity manifest；
2. 校验 Provider Character / Scene / Prop 一一完整覆盖；
3. 生成稳定 `target_asset_id`；
4. 注入 Target Bible display name 与 semantic identity；
5. 保留 Target Bible 作为上游 semantic truth / lineage，但**不把 global/entity narrative continuity rules 复制进 asset-local continuity 字段**；
6. 计算单资产 fingerprint 与 revision；
7. 持久化 `NEEDS_REVIEW` candidate；
8. 用户显式确认后发布正式 `TARGET_ASSETS`；
9. 建立 Artifact Graph、provenance、SUPERSEDES 和 STALE 传播。

Provider 响应在进入 composition 前还必须通过中文审核语言门禁；明显以英文为主的候选应 fail closed，不得进入人工审核区。composition 也不得在门禁之后重新注入英文 review-facing 叙事规则。

## 人工确认

Provider Task succeeded 不等于正式资产 READY。

```text
Provider succeeded
→ candidate NEEDS_REVIEW
→ 用户查看
→ ACCEPT / REJECT
```

只有 ACCEPT 才创建 CURRENT `TARGET_ASSETS`。REJECT 不覆盖旧 CURRENT；重新生成候选也不覆盖旧正式资产。

旧 visual-identity-v1 正式资产不由数据库迁移静默改写；真实验收发现其内容不满足 v2 最终质量合同后，必须由用户显式 regenerate → review → accept 产生新 revision。

## 完成标准

P13 工程完成至少要求：

- stable Target Asset ID；
- Character / Scene / Prop typed packet；
- exact Target Bible binding；
- per-asset revision / fingerprint；
- 中文审核语言与目标受众/模型执行语言分层；
- asset-local visual continuity，不复制全局故事/镜头 preservation locks；
- wardrobe baseline 不越权变成逐场景换装计划；
- time-of-day baseline 不发明剧情时序；
- candidate review gate；
- ProviderJob-before-remote；
- GET read-only；
- idempotency / explicit regenerate；
- provenance / Artifact Graph / STALE；
- 用户验收入口；
- 没有创建 P14+ Artifact。

真实人工验收并由用户明确 `P13 PASS` 前，`TARGET_ASSETS` 必须保持 `PLANNED`。
