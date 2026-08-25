# AI Drama Studio — Project State (Reference Video V2 / Character V6)

> 当前开发基线：`main`。
> 产品采用“后台自动能力 + 少量可操作工作区”，人物资产当前正式算法基线为 Character V6。

## 当前基线

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
Character: V6 Global Identity
Project Format: 2.0
App Version: 2.3.x
```

## 正式用户工作区

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

核心原则：

```text
不可修改、无需确认的技术中间结果
→ 后台自动执行
→ 不单独做阶段页面

容易出错，而且用户能够修正的结果
→ 提供编辑 / 修正能力

正常结果
→ 不要求用户逐项确认

异常或用户主动发现问题
→ 再进入人工修正
```

FFprobe、Proxy、Audio WAV、Frame PTS、关键帧缓存、Embedding、MOT、模型内部日志等都不是独立生产页面。

## 01 剧集管理

一个 Project 表示一部短剧；一个 Project 可以包含多个 Episode。

用户负责批量导入、拖动排序、删除 / 替换单集、追加剧集。

`Episode.sort_order` 是所有批量任务的正式处理顺序。

## 02 拉片

正式用户动作：

```text
单集拉片 / 重新自动拉片
顺序批量拉片
必要时打开“修正镜头”
查看 Shot Revision 历史
恢复历史 Revision
```

后台链：

```text
Media Preprocess
→ FFprobe Frame PTS
→ TransNetV2 / Scene evidence
→ Shot Boundaries
→ Reference Clip
→ Thumbnail / Keyframe
→ Safe Current Shot Revision switch
```

批量拉片严格按 `Episode.sort_order` 顺序执行，不并行多个 Episode。

Shot Revision 已实现 AUTO / MANUAL / RESTORE，自动重跑失败不破坏旧 Current。

Current Shot Revision 改变后，当前资产 ContentAnalysisRun 标记为 `STALE`。

## 03 资产

目标：从当前 Shot / Reference Clip 中形成：

```text
人物
场景
关键道具
```

并绑定回 Shot。

### Character V6 正式链

```text
YOLOX Person Observation（约 12fps，长 Shot 有采样上限）
+ YuNet Face
+ SFace Face Embedding Provider
+ YoutuReID Body Evidence
↓
BoT-SORT Mature MOT + CMC
  └ init/runtime failure → 当前 Shot 从头 ByteTrack fallback
↓
CLEAN Track Gallery
+ Face hard-conflict split
↓
Project-level Global Identity Graph
↓
RESOLVED / UNRESOLVED
↓
Final Gate = RESOLVED only
```

Tracking、Identity、Final Character 已彻底分层：

```text
Observation / Track = Evidence
Global Identity = 身份解析
Character = Final Asset
```

Track 数量不能当人物数量。

### 当前自动 Resolve 门槛

为了防止同一演员的侧脸 / 特写 / 遮挡碎片制造“人物020”式虚假人物，当前规则是：

```text
至少 2 条 Face Track
且 Face Evidence 覆盖至少 2 个不同 Shot
→ RESOLVED
```

因此：
- 单 Shot 高清脸仍 `UNRESOLVED`；
- 孤立脸 / 一次误检保留 Evidence；
- 纯 body-only 不能创建 Character；
- body-only 只能在相邻 Shot + 极强 CLEAN ReID 时挂回 Face cluster；
- 同 Shot 时间重叠的人物是永久 cannot-link；
- Face hard conflict 阻断传递合并。

### Final Character Gate

只有明确：

```text
identity_status == RESOLVED
```

才物化 AUTO Final Character。

以下全部只保留 Evidence：
- `UNRESOLVED`；
- 缺失 identity_status；
- 非法 / 损坏状态；
- 未定义为可发布的未来中间状态。

Final Gate 已改为显式 fail-closed allow-list，不再临时修改 `face_visible`，也不再 monkeypatch legacy materializer。

即使 Candidate 标为 RESOLVED，也必须至少存在一条真实 face-visible Track，纯 body-only 不能绕过 Gate。

### MOT 稀疏时间

长 Shot 因采样上限可能低于名义 12fps。V6 会把：

```text
local_time_us / 1_000_000
```

作为真实 timestamp 传入 Mature MOT，避免 Kalman / lost-track 按固定调用间隔误判。

BoT-SORT 若在 Shot 中途失败，本 Shot 的部分结果全部丢弃，从 Shot 开头用 ByteTrack 完整重跑，避免两套 tracker 的 ID / state 混杂。

### Face Provider

当前继续使用 YuNet + SFace。Global Identity 已与 face embedding provider 解耦；以后选定明确可商用或已有授权的 ArcFace 权重后可替换 provider，不改变 Track / Final Asset Contract。

## Evidence / Final Asset / Revision

```text
CharacterCandidate / CharacterTrack / SceneCandidate / PropCandidate
= immutable AI Evidence

Character / Scene / Prop
= Project Final Asset

ShotCharacterBinding / ShotSceneBinding / ShotPropBinding
= Final Binding
```

人物 RESOLVED Identity 可以自动形成 AUTO Final Character；UNRESOLVED 永远不会增加 Final Character 数量。

Asset Revision 继续保护 MANUAL / RESTORE：新 AI Run 默认不能静默覆盖人工版本。

## Character V6 Run 原子性

新 Run 完整成功才切 Current：

```text
Track / Global Identity
→ RESOLVED / UNRESOLVED 标记
→ Candidate / Track / Scene Evidence
→ counts
→ Current Run 切换
→ commit
```

任何一步失败，旧 Current 不动。

## 04 内容剧本

规划 / 后续能力：Whisper ASR、Speaker Diarization、OCR、VLM、人物 ↔ Speaker / Dialogue、多模态融合、结构化源剧本。

这些不会各自做页面。用户最终修改的是结构化剧情与可生产数据。

## 05 重制设计

后续人工创作工作区：

```text
Character Bible
Scene Bible
本土化对白
Target Character / Scene
Shot Specification
```

必须可编辑、可重做、可保留 Revision。

## 06 生成 / 导出

统一生产工作区：

```text
Video Generation
Voice / TTS
LipSync
QC
Timeline Assembly
Final Export
```

默认异常驱动，不要求用户逐项确认所有正常结果。

## 统一后台 Task Progress

耗时任务使用持久化 `BackgroundTaskRecord`：

```text
QUEUED
PROCESSING
READY
READY_WITH_WARNINGS
FAILED
CANCELLED
```

页面刷新 / 切换工作区不会丢进度；重复点击不重复创建同作用域活动任务；服务重启后遗留 PROCESSING 明确标记为中断失败。

## 当前开发状态

```text
01 剧集管理:
  IMPLEMENTED / NEEDS LOCAL REGRESSION

02 拉片:
  AUTO-PREPROCESS + TASK PROGRESS + MANUAL EDIT + SHOT REVISION + SAFE RERUN
  IMPLEMENTED / NEEDS LOCAL REAL-VIDEO REGRESSION

03 资产:
  Character V6 Mature MOT + Global Identity + RESOLVED-only Final Gate
  IMPLEMENTED / NEEDS WINDOWS REAL-SAMPLE REGRESSION
  Scene / Prop 继续沿用当前 Evidence / Semantic 链

04 内容剧本:
  PLANNED / PARTIAL LOW-LEVEL CAPABILITIES EXIST

05 重制设计:
  PLANNED

06 生成 / 导出:
  PLANNED
```

## Character V6 已锁行为测试

```text
15 Track 碎片 / 3 人 → 3 RESOLVED Identity
同框两人不能经 bridge Track 传递合并
孤立 Face → UNRESOLVED
单 Shot 高清 Face → UNRESOLVED
同身份两 Shot Face → RESOLVED
body-only → 不能创建 Character
body-only 可挂回 Face cluster 但不能晋级单 Shot Face
UNRESOLVED face_visible Evidence → 不物化 Final Character
缺失 identity_status → Final Gate fail closed
MOT tracker rows → 按 IoU 映射 Observation
稀疏采样 → 真实 timestamp
BoT-SORT runtime failure → 整 Shot ByteTrack 重跑
未确认 observation → 仍保留 Evidence
```

## 近期优先级

```text
P0-1 Windows 本机安装/确认 trackers 2.6 + supervision + ONNX Runtime GPU Runtime
P0-2 用真实短剧重新跑资产，验收 Final Character 数量而不是 Track 数量
P0-3 重点检查人物进入 / 遮挡 / 交叉 / 离开、长 Shot、侧脸和同框 cannot-link
P0-4 核对 RESOLVED / UNRESOLVED Evidence 页面与 Final Asset 数量
P0-5 继续内容剧本（ASR + Speaker + VLM + Structured Script）
```

## 测试入口

```text
python -m pytest engine/tests/v2/test_character_identity_v6.py -q
python -m pytest engine/tests/v2/test_character_tracking_v6.py -q
python -m pytest engine/tests/v2/test_asset_final_gate_v6.py -q
python -m pytest engine/tests/v2 -q

cd frontend
npm run typecheck
npm run build
```

真实媒体 Release Gate 仍必须在用户 Windows 本机完成；仓库单元测试不能替代 GPU / FFmpeg / Reference Clip / 人物真实素材验收。
