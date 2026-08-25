---
name: ai-drama-studio-reference-video-v2
version: 3.3.0
description: AI Drama Studio Reference Video 驱动的本地短剧本地化重制工作台开发规则；人物资产当前基线 Character V6。
---

# AI Drama Studio — Reference Video V2 / Character V6

## 产品目标

把多集原短剧拆成可控制的 Shot，并把每个原 Shot 保存为 Reference Video。后续通过人物、场景、关键道具、目标语言 Dialogue、Voice 和替换资产控制重制，而不是把原镜头完全翻译成文字后从零猜测动作与摄影。

## 正式用户工作区

```text
01 剧集管理
→ 02 拉片
→ 03 资产
→ 04 内容剧本
→ 05 重制设计
→ 06 生成 / 导出
```

技术中间步骤默认在后台运行，不为 FFprobe、MOT、Embedding、ASR 等内部能力单独制造生产页面。

## 核心实体

```text
Project
Episode
Shot
Character
Scene
Prop
Dialogue
Asset
Voice
Generation
```

Shot 是核心生产单元，Reference Clip 是 Shot 一级正式资产。

AI Evidence 额外维护：

```text
ContentAnalysisRun
CharacterCandidate
CharacterTrack
SceneCandidate
ShotSceneEvidence
PropCandidate
ShotPropEvidence
SpeakerSegment
AnalysisDialogue
```

AI Evidence 与 Final Asset / Binding / Revision 必须分离。

## Character V6：正式人物链

```text
YOLOX Person Observation（约 12fps；长 Shot 有上限）
+ YuNet Face
+ SFace Face Embedding Provider
+ YoutuReID Body Evidence
↓
BoT-SORT Mature MOT + CMC
  └ init/runtime failure: 当前 Shot 从头 ByteTrack fallback
↓
CLEAN Track Gallery
+ Face hard-conflict split
↓
Project-level Global Identity Graph
↓
RESOLVED / UNRESOLVED
↓
Final Character Gate = RESOLVED only
```

### 三层业务语义不可混淆

```text
Detection / Observation = 视觉观测
Track = Shot 内连续轨迹
Global Identity = 跨 Shot 人物身份
Final Character = 可编辑项目级人物资产
```

Track 数量永远不能直接当人物数量。

### Identity 规则

当前自动 RESOLVED 门槛：

```text
至少 2 条 Face Track
且至少覆盖 2 个不同 Shot
```

因此：
- 单 Shot 高清脸仍先 `UNRESOLVED`；
- 孤立脸 / 一次误检 / 侧脸碎片 `UNRESOLVED`；
- body-only 不能自行创建人物；
- body-only 只允许在相邻 Shot + 极强 CLEAN ReID 时挂回 Face cluster；
- 同 Shot 时间重叠的人物 Track 是永久 cannot-link；
- 明确 Face 冲突阻断图传递合并。

### Final Gate

只有 Candidate Evidence 明确：

```text
identity_status == RESOLVED
```

才允许自动物化 Final Character。

以下全部 fail closed，只保留 Evidence：
- `UNRESOLVED`；
- 缺失 identity_status；
- 非法 / 损坏 JSON；
- 未来新增但尚未定义为可发布的中间状态。

即使 Candidate 标成 RESOLVED，仍必须至少有一条真实 `face_visible` Track；纯 body-only 不得创建 Final Character。

Final Gate 禁止临时修改 Candidate / Track Evidence，也禁止 monkeypatch 旧 materializer。

## Face Provider 授权边界

当前使用 YuNet + SFace，provider 与 Global Identity Graph 解耦。

不要静默打包仅限非商业研究用途的预训练 ArcFace / InsightFace 权重。后续只有选择明确可商用或已有授权的 ArcFace 权重后才替换 provider；不得因此改变 Track / Identity / Final Asset Contract。

## Mature MOT 时间规则

V6 采样存在上限，长 Shot 的实际 observation 间隔可能低于名义 12fps。因此必须把 Reference Clip 的真实采样时间：

```text
timestamp = local_time_us / 1_000_000
```

传给 `tracker.update()`。

BoT-SORT 若在一个 Shot 中途失败，不能保留前半段 BoT-SORT ID 再接 ByteTrack；必须丢弃当前 Shot 的部分 MOT 结果，从 Shot 开头用 ByteTrack 完整重跑。

## Run / Revision

新分析 Run 必须完整成功后才能切 Current：

```text
Track / Global Identity
→ RESOLVED / UNRESOLVED
→ Candidate / Track / Scene Evidence
→ counts
→ Current Run
→ commit
```

任何一步失败，旧 Current 不动。

Final Asset 使用独立 Revision；MANUAL / RESTORE 默认受保护，新 AI Run 不静默覆盖人工版本。

## 拉片数据优先级

第一优先级：
- Shot 边界与 Reference Clip；
- Character Identity；
- Character Track；
- Dialogue；
- Speaker → Character。

第二优先级：
- Scene ID；
- Key Prop ID；
- Character Mask；
- Dialogue Type / Emotion / Speaking Style。

第三优先级：
- Short Description；
- Shot Type；
- Camera Motion；
- Prop Track / Mask。

不优先把 Reference Video 已天然包含的复杂动作、精确人物空间关系、摄影轨迹、详细灯光参数逐帧文字化。

## 批量执行

Episode 按 `sort_order` 顺序处理：

```text
EP01 完成
→ EP02 完成
→ EP03 完成
```

默认不并行多个视频，GPU 重任务同样默认 concurrency = 1。

人物分析是 Project 级 Run，先完成全部 Shot Track，再统一做 Global Identity Graph。

## 时间规则

Source Shot / Dialogue 使用原片 integer microseconds。

目标语言允许：

```text
original_duration_us
!= target_audio_duration_us
!= generated_duration_us
!= final_duration_us
```

最终由 Production Timeline 重新建立时间轴。

## 重制策略

后续按 Shot 允许：

```text
REUSE_REFERENCE
AUDIO_ONLY
LIPSYNC_ONLY
CHARACTER_REPLACE
SCENE_REPLACE
PROP_REPLACE
PARTIAL_EDIT
FULL_VIDEO_REGEN
```

不是所有 Shot 都调用最昂贵的视频生成模型。

## 当前主代码

```text
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/content_models_v2.py
engine/app/content_analysis_v2.py
engine/app/character_observation_v6.py
engine/app/character_tracking_v6.py
engine/app/character_identity_v6.py
engine/app/character_runtime_v6.py
engine/app/asset_final_gate_v6.py
engine/app/asset_workspace_v3.py
engine/app/asset_routes_v3.py
engine/app/main.py
frontend/src/views/ProjectList.vue
frontend/src/views/ProjectStudio.vue
```

旧 `character_visual_v5.py` 等模块可被 V6 复用数据类和低层工具，但 V5 身份决策逻辑不是正式入口。

## 测试

默认：

```bash
pytest
```

正式基线是 `engine/tests/v2`。

Character V6 重点回归：
- 多 Track 碎片不会膨胀人物数；
- 三个演员保持三个 Identity；
- 同框 cannot-link 不被图传递绕过；
- 单 Shot Face 不自动发布；
- 两 Shot Face 确认可 RESOLVED；
- body-only 不创造人物；
- UNRESOLVED 不进 Final；
- identity_status 缺失时 Final Gate fail closed；
- tracker 输出按 IoU 映射回 Observation；
- 稀疏采样使用真实 timestamp；
- BoT-SORT runtime failure 整 Shot ByteTrack 重跑。

真实短剧仍必须在用户 Windows 本机验证 GPU Runtime、人物交叉遮挡、长 Shot、跨 Shot Identity 与 Final Character 数量。

## Git 工作方式

```text
Default Branch: main
Development Branch: main
```

默认直接提交 `main`，不新建 feature 分支，不主动创建 PR。只有用户明确改变要求时才修改这一工作方式。

## Legacy

旧 35 Feature、旧 Frozen Snapshot、旧 Workflow Versioning、Character V1-V5.1 都是历史资料。

如复用旧算法，只复用低层实现，不继承旧业务 Contract。任何“检测到一张脸就创建 Character”或“Track 数≈人物数”的旧逻辑都禁止重新接回正式链路。
