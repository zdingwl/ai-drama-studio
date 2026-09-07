# Runtime Model Skills

`engine/skills/` 定义短剧重做生产链里的**运行时模型 Skill 契约**。

它与 `.agents/skills/` 完全不同：

- `.agents/skills/`：约束开发 Agent 如何阅读、修改和验收工程代码。
- `engine/skills/`：约束生产环境里的模型如何理解短剧、改编、生成和质检。

## 当前状态

所有正式 Skill 当前都显式锁定 `Version: 1.0.0`，生命周期分两类：

- `RUNTIME_READY`：已经完成当前版本的 Provider/投影接入、Validator、显式命令入口、revision/fingerprint 和测试契约，可以进入运行门。
- `CONTRACT_ONLY`：只定义契约并可被注册表校验，不允许 live dispatch。

当前只启用原片前半链：`shot_facts -> episode_understanding -> screenplay_reconstruction`。目标国家改编、目标分镜、TTS 和 QC 仍保持 `CONTRACT_ONLY`，不会因为本次接入而误跑到 H3 重做后半链。

## 正式 Skill

| Skill ID | 作用 | 当前状态 |
| --- | --- | --- |
| `shot_facts` | 单镜事实拉片；当前复用已冻结 SourceDramaSnapshot，不重复运行 VLM | RUNTIME_READY |
| `episode_understanding` | 整集剧情结构理解；使用现有本地 Qwen 文本运行时并执行 source-ref 门禁 | RUNTIME_READY |
| `screenplay_reconstruction` | 从已确认原片事实确定性还原正式剧本 | RUNTIME_READY |
| `country_adaptation` | 将锁定原剧本本地化成目标国家版本 | CONTRACT_ONLY |
| `script_to_storyboard` | 将目标剧本转成目标分镜与生成计划 | CONTRACT_ONLY |
| `qwen3_tts` | 锁定角色音色并生成目标对白语音 | CONTRACT_ONLY |
| `video_qc` | 对生成视频做独立语义/结构质检 | CONTRACT_ONLY |

允许的 Skill ID、版本和生命周期以 `engine/skills/registry.py` 为机器可读注册表；各 `SKILL.md` 是详细的人类/模型契约。

## 不做 Skill 的步骤

确定性工程步骤继续由算法、参数和 Validator 管理，不包装成模型 Skill，例如：

- FFmpeg / FFprobe；
- 镜头边界检测本身；
- ASR/OCR 时间轴对齐；
- revision/fingerprint/idempotency/checkpoint；
- LatentSync 执行机制；
- 音频分离、字幕封装、文件拼接。

## 推荐运行链

```text
确定性预处理 / 镜头切分 / ASR / OCR / 人物证据
↓
SourceDramaSnapshot（正式原片事实门）
↓
shot_facts
↓
episode_understanding
↓
screenplay_reconstruction
↓
锁定原剧本
↓
country_adaptation
↓
锁定目标国家剧本
↓
script_to_storyboard
↓
目标人物 / 场景 / 道具准备
↓
qwen3_tts
↓
真实目标语音时长驱动重排
↓
MiniMax H3 Provider
↓
video_qc
↓
LatentSync / 音频 / 字幕 / FFmpeg
↓
目标国家成片
```

当前实现只开放到 `screenplay_reconstruction`。`country_adaptation` 之后仍被注册表运行门拒绝。

`Shot != GenerationSegment`。目标分镜和生成段可以依据目标语言时长与戏剧功能重新组织，不能为了保持原片 Shot 数量而硬塞。

## 当前原片前半链运行规则

1. `shot_facts` 不重新调用 VLM，而是把当前可消费 `SourceDramaSnapshot` 的 Grounded Shot 事实投影成统一 Skill Contract，避免二次推理改漂。
2. `episode_understanding` 只产生 inference layer：Scene Block、Story Beat、Information Flow、Emotion Curve、Shot Function、Remake Invariant。所有输出必须回指当前 source refs；未知 ref、漏 Shot、重复/乱序 Shot 直接拒绝。
3. `screenplay_reconstruction` 不使用生成模型润色事实，只从当前 Shot action/visual facts 和 canonical `SourceDialogueUtterance` 确定性排版；完整对白即使跨多个 Shot，也只能出现一次。
4. 编译结果是 sidecar derived artifact，带 `source_fingerprint/input_fingerprint/output_fingerprint`，本次不新增数据库表，也不把剧情模型结果写回 SourceDramaSnapshot。
5. 运行入口为显式 `POST /api/episodes/{episode_id}/source-screenplay/compile`；没有 GET/page-load 自动推理入口。

## 所有运行时调用最终必须记录

当某个 Skill 升级到 `RUNTIME_READY` 并真正进入生产调用后，每次调用至少记录：

```text
skill_id
skill_version
model
model_version
input_revision
output_revision
```

建议同时记录输入 fingerprint、Provider profile、开始/完成时间和失败类型，便于区分模型变化、Skill 版本变化和输入 revision 变化。

当前 sidecar 编译结果已经记录 Skill ID/version 和 source/input/output fingerprint；持久化运行记录将在后续 command/checkpoint 层接入时统一落库，不在本次改动里另造运行表。

## 全局门禁

所有 Skill 都必须遵守以下规则：

1. `SourceDramaSnapshot` 是正式原片事实入口，Skill 不得绕过正式人物、场景、对白、speaker 和 revision 门禁去消费瞬态证据。
2. 模型推理只能由显式命令启动；GET、页面加载、刷新和普通查询不得触发重模型。
3. 原始检测、Track、Face、ASR/OCR evidence 不是 Final Character / Final Dialogue。
4. Skill 不得把未确认推断写成原片事实；不确定项必须显式输出 uncertainty/review item。
5. 模型离线、显存不足、文件缺失等属于 runtime failure，不得伪装成人工内容审核项。
6. 页面仍以 Project / Review Center / Output 为主，不为自动 Skill 新增普通用户顶层页面。

## 版本规则

- 修改措辞但不改变输入输出语义：patch。
- 增加兼容字段或规则：minor。
- 改变输出结构、核心语义或下游解释方式：major。
- 任何线上调用必须显式锁定版本，禁止用 `latest` 代替正式版本。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
- `docs/04_AI拉片模块业务方案与UI基线.md`
