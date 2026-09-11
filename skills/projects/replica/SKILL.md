# 复刻短剧 Root Skill

## 目标
把已经验证好看的原短剧换成目标地区的人物、语言和世界重新拍一遍。

## 不可突破的规则
- 故事不乱改，节奏不重做，文化和表达才本土化。
- 必须先完成整集理解，再做逐镜语义拉片。
- P10 `SOURCE_VIDEO_SNAPSHOT` 是 Target 阶段唯一当前 Source 世界版本锚点；Target 不得绕过 Snapshot 自行拼装当前 Source Facts。
- 故事骨架（Story Skeleton）与节奏骨架（Rhythm Skeleton）通过 Snapshot 冻结后，作为目标版本的权威 preservation locks。
- P11 只建立 `ADAPTATION_PLAN + TARGET_BIBLE`；不得提前生成正式 `TARGET_SCRIPT`、Target Storyboard、TTS、Timing 或视频生成参数。
- P12 正式硬输入必须同时是 CURRENT `SOURCE_VIDEO_SNAPSHOT + ADAPTATION_PLAN + TARGET_BIBLE`；P11 已真实人工 PASS 后 P12 才允许执行。
- P12 的 Source Dialogue 只能来自 Snapshot 冻结的 P6 canonical dialogue；不得重新 ASR/OCR/猜词或静默修正 Source 台词。
- P13 正式硬输入只有 CURRENT `TARGET_BIBLE`；不得因为 Source Snapshot、Adaptation Plan 或 Target Script “可能有帮助”就把它们静默升级成硬输入。
- P13 `Target Bible = semantic truth`，`Target Assets = visual realization`；Provider 只能具体化已有 Target Character / Scene / Prop 的视觉表现，不能改变人物故事身份、场景功能、关键道具功能或 Target entity identity。
- P13 asset continuity 必须是 asset-local visual continuity；Target Bible 的 Story Beat / shot order / dialogue / rhythm / cliffhanger 等全局 preservation locks 不复制进每个 Target Asset packet。
- P13 Character wardrobe 只定义 baseline；除非 Target Bible 已明确确认 variation，否则不得自行建立逐 Scene / Shot 换装计划。
- P13 Scene time-of-day 只定义视觉基线；Target Bible 未明确时不得根据 Scene 顺序、闪回或情绪推断剧情时间跳变。
- P13 Provider 结果必须先进入 `NEEDS_REVIEW` candidate；只有用户显式确认后才能发布 CURRENT `TARGET_ASSETS`。
- Target 人物 / 场景 / 道具必须保留 Source lineage，但 Target identity 与 Source identity 严格分离。
- 对白链固定为 `Source Dialogue → Translation → Localization → Final Target Dialogue → Target Speaker/Voice → TTS → Actual Speech Duration → Timing Plan`；P12 只到 Final Target Dialogue。
- 原片事实、目标世界、生产计划严格分层。
- 未经过生成质检与正式选择的尝试不能进入后期。

## 正式顺序
原片 → 证据 → 整集理解 → 故事骨架 / 节奏骨架 → 逐镜拉片与角色 / 场景 / 道具归一 → 原片分析定稿 → **目标设定（ADAPTATION_PLAN + TARGET_BIBLE）** → **目标剧本 / 对白（Translation → Localization → Final Target Dialogue）** → **目标资产（Character / Scene / Prop Visual Identity Packets）** → Target Speaker/Voice → TTS / 真实语音时长 → Timing → 复刻分镜 → 视频生成与选择 → 口型 / 字幕 / 剪辑 → 成片。

## P11 目标设定
P11 读取且只锚定 CURRENT `SOURCE_VIDEO_SNAPSHOT`，确定性锁定：故事主线、Hook、冲突、反转、信息揭示顺序、情绪峰值、Payoff、Cliffhanger、Story Beat timing、Shot rhythm / Scene order / Shot logic / Action rhythm baseline。

允许自动设计：目标地区人物身份 / 姓名 / 外形方向、场景文化环境、关键道具、世界语境、称谓与表达策略、visual style、continuity rules。

外部 Provider 只返回 Target 设计语义；Target ID、preservation locks、Artifact revision / fingerprint / provenance 与 Graph 由服务端控制。

P11 已完成真实人工验收：

```text
LOCALIZATION = AVAILABLE
TARGET_BIBLE = AVAILABLE
```

## P12 目标剧本 / 本土化
P12 已完成真实 Provider、真实项目端到端与用户人工质量验收，用户已明确 `P12 PASS`：

```text
TARGET_SCRIPT = AVAILABLE
```

P12 同时读取 CURRENT Snapshot、Adaptation Plan、Target Bible，从 Snapshot 中确定性提取 canonical dialogue manifest。Provider 只能针对已有 `utterance_id` 输出 `translation_text / localization_text / final_target_dialogue`，不得改变 Source text、时间或 utterance 集合。

若 Source Speaker → Source Character → Target Character lineage 可证明，服务端可绑定 `target_character_id`；否则保持未绑定，不能让模型猜。Target Voice / TTS / Duration / Timing 属于后续阶段。

普通产品页面加载只读；只有 P11 Target Bible 当前有效且用户显式点击“生成目标剧本 / 重新生成目标剧本”时才启动 P12。

P12 最终验收记录见 `docs/27_P12最终验收与后续阶段准入评估.md`。

## P13 目标资产
P13 基础合同见 `docs/28_P13TargetAssetsProfessionalSkill与数据契约.md`，审核语言见 `docs/29_P13中文审核语言与生成执行语言分层.md`，真实项目整改基线见 `docs/30_P13真实项目验收_资产作用域与时序约束整改.md`，最终验收状态见 `docs/31_P13最终验收与P14准入评估.md`。

当前 Professional Skill / runtime contract：

```text
replica-target-assets@1.1.0
p13-replica-target-assets-v3
replica-target-visual-identity-v2
```

P13 只读取 CURRENT `TARGET_BIBLE`，把已有 Target Character / Scene / Prop 转成可被后续分镜和视频生成稳定引用的 typed visual identity packet。

资产设计要求：

```text
Character
= identity / demographic / face / hair / body / wardrobe baseline
+ signature visual features
+ asset-local visual continuity / generation guidance / negative constraints

Scene
= spatial identity / layout / architecture / material palette / fixed landmarks
+ lighting / time-of-day visual baseline
+ asset-local visual continuity / generation guidance / negative constraints

Prop
= functional identity / form / material / color / scale / signature features
+ asset-local visual continuity / generation guidance / negative constraints
```

稳定 `target_asset_id`、Target Bible entity binding、单资产 fingerprint/revision、Artifact Graph 和 stale propagation 都由服务端确定性控制。Target Bible 的全局故事 / 镜头 preservation locks 继续通过 lineage 保持权威，但不机械复制进每个 asset packet。

当前仓库没有已接入并验收的图片生成 Provider，因此 P13 不伪造图片 URI / hash / 尺寸；正式资产先以 typed visual identity packet 成立，并为未来真实 reference media 保留受控槽位。

Provider 成功不等于正式资产可用：

```text
Provider succeeded
→ NEEDS_REVIEW candidate
→ 用户显式 ACCEPT / REJECT
→ ACCEPT 才发布 CURRENT TARGET_ASSETS
```

v3 / visual-identity-v2 已完成真实 Provider、真实项目重跑与用户人工质量复验，用户已明确 `P13 PASS`。正式能力状态为：

```text
TARGET_ASSETS = AVAILABLE
```

旧 `replica-target-visual-identity-v1` 正式 revision 继续只作为历史保留；当前可用基线以 v3 / visual-identity-v2 为准。

P13 自身不创建 Target Voice / TTS / Timing / Target Storyboard / Generation / QC / Lip Sync / Post Artifact。P13 PASS 也不自动准入这些后续能力；它们继续 `PLANNED`，必须先建立下一阶段正式合同，再分别完成工程与真实人工验收。

## 下一阶段边界
Root Skill 的长期顺序在 `target_assets` 后是 `voice_timing`，但当前只表示依赖顺序，不等于 P14 已实现或已准入。P14 正式合同尚未建立；在新的编号合同明确 Target Voice / TTS / Timing 的硬输入、typed output、Provider、时长权威来源、Artifact Graph 与验收规则前，不进入 P14 实现。

## 需要用户决策
只有在故事或节奏必须偏离原片、文化替换会改变核心人物关系，或存在多个会显著改变目标世界的合理方向且系统不能安全自动选择时才询问用户。P13 的视觉身份候选属于正式人工确认边界，必须由用户显式接受或拒绝。

## 完成标准
原片分析定稿可追溯；Target Bible 与 Source Snapshot lineage 明确；Target Script 保留 canonical Source Dialogue 与三层目标对白的可审计 lineage；目标人物 / 场景 / 道具属于同一目标世界且使用独立 Target identity；P13 资产必须保持 Target Bible semantic truth、稳定 Target Asset ID 与 per-asset revision，保持 asset-local visual scope，并经过显式人工确认；后续目标语音与时间计划成立；复刻分镜保持原故事和节奏；最终成片来自正式 GenerationSelection。
