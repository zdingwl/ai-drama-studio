# 复刻短剧 Root Skill

## 目标
把已经验证好看的原短剧换成目标地区的人物、语言和世界重新拍一遍。

## 不可突破的规则
- 故事不乱改，节奏不重做，文化和表达才本土化。
- 必须先完成整集理解，再做逐镜语义拉片。
- P10 `SOURCE_VIDEO_SNAPSHOT` 是 Target 阶段唯一当前 Source 世界版本锚点；Target 不得绕过 Snapshot 自行拼装当前 Source Facts。
- 故事骨架（Story Skeleton）与节奏骨架（Rhythm Skeleton）通过 Snapshot 冻结后，作为目标版本的权威 preservation locks。
- P11 只建立 `ADAPTATION_PLAN + TARGET_BIBLE`；不得提前生成正式 `TARGET_SCRIPT`、Target Storyboard、TTS、Timing 或视频生成参数。
- Target 人物 / 场景 / 道具必须保留 Source lineage，但 Target identity 与 Source identity 严格分离。
- 目标对白先保证意图、情绪和自然表达，再在后续阶段根据真实 TTS 时长做 Timing；P11 不直接生成正式逐句目标对白。
- 原片事实、目标世界、生产计划严格分层。
- 未经过生成质检与正式选择的尝试不能进入后期。

## 正式顺序
原片 → 证据 → 整集理解 → 故事骨架 / 节奏骨架 → 逐镜拉片与角色 / 场景 / 道具归一 → 原片分析定稿 → **目标设定（ADAPTATION_PLAN + TARGET_BIBLE）** → 目标剧本 / 对白 → 目标资产 → 真实语音时长 → 复刻分镜 → 视频生成与选择 → 口型 / 字幕 / 剪辑 → 成片。

## P11 目标设定
P11 读取且只锚定 CURRENT `SOURCE_VIDEO_SNAPSHOT`，确定性锁定：故事主线、Hook、冲突、反转、信息揭示顺序、情绪峰值、Payoff、Cliffhanger、Story Beat timing、Shot rhythm / Scene order / Shot logic / Action rhythm baseline。

允许自动设计：目标地区人物身份 / 姓名 / 外形方向、场景文化环境、关键道具、世界语境、称谓与表达策略、visual style、continuity rules。

外部 Provider 只返回 Target 设计语义；Target ID、preservation locks、Artifact revision / fingerprint / provenance 与 Graph 由服务端控制。

## 需要用户决策
只有在故事或节奏必须偏离原片、文化替换会改变核心人物关系，或存在多个会显著改变目标世界的合理方向且系统不能安全自动选择时才询问用户。

## 完成标准
原片分析定稿可追溯；Target Bible 与 Source Snapshot lineage 明确；目标人物 / 场景 / 道具属于同一目标世界且使用独立 Target identity；后续目标对白与时间计划成立；复刻分镜保持原故事和节奏；最终成片来自正式 GenerationSelection。
