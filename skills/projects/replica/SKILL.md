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
- Target 人物 / 场景 / 道具必须保留 Source lineage，但 Target identity 与 Source identity 严格分离。
- 对白链固定为 `Source Dialogue → Translation → Localization → Final Target Dialogue → Target Speaker/Voice → TTS → Actual Speech Duration → Timing Plan`；P12 只到 Final Target Dialogue。
- 原片事实、目标世界、生产计划严格分层。
- 未经过生成质检与正式选择的尝试不能进入后期。

## 正式顺序
原片 → 证据 → 整集理解 → 故事骨架 / 节奏骨架 → 逐镜拉片与角色 / 场景 / 道具归一 → 原片分析定稿 → **目标设定（ADAPTATION_PLAN + TARGET_BIBLE）** → **目标剧本 / 对白（Translation → Localization → Final Target Dialogue）** → 目标资产 → Target Speaker/Voice → TTS / 真实语音时长 → Timing → 复刻分镜 → 视频生成与选择 → 口型 / 字幕 / 剪辑 → 成片。

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

P12 最终验收记录见 `docs/27_P12最终验收与后续阶段准入评估.md`。P12 PASS 不自动准入或实现 `TARGET_ASSETS / TTS / TIMING / STORYBOARD / VIDEO_GENERATION / QC_SELECTION / LIP_SYNC / POST_PRODUCTION`；下一工程阶段必须先有正式契约。

## 需要用户决策
只有在故事或节奏必须偏离原片、文化替换会改变核心人物关系，或存在多个会显著改变目标世界的合理方向且系统不能安全自动选择时才询问用户。

## 完成标准
原片分析定稿可追溯；Target Bible 与 Source Snapshot lineage 明确；Target Script 保留 canonical Source Dialogue 与三层目标对白的可审计 lineage；目标人物 / 场景 / 道具属于同一目标世界且使用独立 Target identity；后续目标语音与时间计划成立；复刻分镜保持原故事和节奏；最终成片来自正式 GenerationSelection。
