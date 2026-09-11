# Replica Target Assets

## 目标

把 CURRENT `TARGET_BIBLE` 中已经确定的 Target Character / Scene / Prop 变成后续分镜与视频生成可以通过稳定 ID 引用的正式视觉身份包。

核心关系：

```text
Target Bible  = semantic truth
Target Assets = visual realization
```

资产设计首先服务跨镜一致性，不以单张图的审美效果作为完成标准。

## 唯一硬输入

```text
CURRENT TARGET_BIBLE
```

P13 v1 不把 `SOURCE_VIDEO_SNAPSHOT`、`ADAPTATION_PLAN`、`TARGET_SCRIPT` 静默加入硬输入。Target Script 的局部对白变化不应无意义地使人物脸型、场景布局或道具视觉身份全部失效。

## Character

必须围绕同一 `target_character_id` 稳定表达：

- P11 localized identity，不得改变故事身份；
- demographic visual direction；
- face；
- hair；
- body；
- wardrobe baseline；
- signature visual features；
- continuity constraints；
- generation guidance；
- negative constraints。

不得按 Shot 单独重写人物身份。后续 Shot variation 只能作为 base asset 之上的明确 overlay。

## Scene

必须围绕同一 `target_scene_id` 稳定表达：

- P11 localized setting，不得改变场景功能；
- spatial layout；
- architecture / interior or exterior style；
- materials palette；
- fixed landmarks；
- lighting baseline；
- time-of-day baseline；
- continuity constraints；
- generation guidance；
- negative constraints。

场景资产用于保证空间身份和可识别 landmark 跨镜稳定，不负责重排 Scene order 或 Story Beat timing。

## Prop

必须围绕同一 `target_prop_id` 稳定表达：

- P11 localized form / functional identity，不得改变剧情功能；
- visual form；
- material；
- color；
- scale；
- signature features；
- continuity constraints；
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
Voice / TTS / Timing
Target Storyboard
Video Generation / QC / Post
```

当前仓库只有已接入的 text-only reasoning Provider，因此 v1 不伪造图片 reference media。以后真实图片 Provider 必须沿相同 asset identity 独立接入并验收。

## 服务端确定性职责

服务端负责：

1. 从 CURRENT Target Bible 构造 exact entity manifest；
2. 校验 Provider Character / Scene / Prop 一一完整覆盖；
3. 生成稳定 `target_asset_id`；
4. 注入 Target Bible display name 与 semantic identity；
5. 合并 Target Bible continuity rules，Provider 无权删除；
6. 计算单资产 fingerprint 与 revision；
7. 持久化 `NEEDS_REVIEW` candidate；
8. 用户显式确认后发布正式 `TARGET_ASSETS`；
9. 建立 Artifact Graph、provenance、SUPERSEDES 和 STALE 传播。

## 人工确认

Provider Task succeeded 不等于正式资产 READY。

```text
Provider succeeded
→ candidate NEEDS_REVIEW
→ 用户查看
→ ACCEPT / REJECT
```

只有 ACCEPT 才创建 CURRENT `TARGET_ASSETS`。REJECT 不覆盖旧 CURRENT；重新生成候选也不覆盖旧正式资产。

## 完成标准

P13 工程完成至少要求：

- stable Target Asset ID；
- Character / Scene / Prop typed packet；
- exact Target Bible binding；
- per-asset revision / fingerprint；
- candidate review gate；
- ProviderJob-before-remote；
- GET read-only；
- idempotency / explicit regenerate；
- provenance / Artifact Graph / STALE；
- 用户验收入口；
- 没有创建 P14+ Artifact。

真实人工验收并由用户明确 `P13 PASS` 前，`TARGET_ASSETS` 必须保持 `PLANNED`。
