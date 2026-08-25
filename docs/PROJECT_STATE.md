# AI Drama Studio — Project State (Reference Video V2)

> 当前开发基线：`main`。
> 产品已经从“一个技术 Feature 一个页面”切换为“后台自动能力 + 少量可操作工作区”。

## 当前基线

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
Project Format: 2.0
App Version: 2.3.0
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

因此 FFprobe、Proxy、Audio WAV、Frame PTS、关键帧缓存、Embedding、SAM Mask、OCR 原始框、Camera Trajectory、模型内部日志等都不是独立生产页面。

## 01 剧集管理

一个 Project 表示一部短剧；一个 Project 可以包含多个 Episode。

用户负责：

```text
批量导入多个视频
拖动排序
删除 / 后续替换单集
追加剧集
```

`Episode.sort_order` 是所有批量任务的正式处理顺序。

项目名称、原项目语言、目标语言、目标地区属于 Project 设置，不单独占一个生产阶段。

## 02 拉片

正式用户动作：

```text
单集拉片 / 重新自动拉片
顺序批量拉片
必要时打开“修正镜头”
```

拉片 Workflow 内部自动执行：

```text
检查媒体分析资产
↓
如果 preprocess_status != READY
  FFprobe
  → Proxy
  → Audio
  → Media Info
否则
  直接复用已有 Proxy / Audio
↓
FFprobe Frame PTS
↓
TransNetV2
↓
Shot Boundaries
↓
Reference Clip
↓
Thumbnail / Keyframe
↓
Shot Result
```

原来的“视频预处理”仍然是后端基础能力，但已经不再是用户页面。

批量拉片严格按 Episode.sort_order 顺序：

```text
EP01 完整处理完
↓
EP02
↓
EP03
...
```

不并行跑多个 Episode。

### 拉片结果不要求逐镜确认

如果用户没有发现问题，可以直接继续资产阶段。

页面目前用 `< 500ms` 短镜头作为一个简单的“建议检查”提示，但它只是异常提示，不代表 Shot 一定错误，也不会阻塞下游。

### 只有需要时才进入 Shot 修正

V2 已实现真正可写的 Shot 修正：

```text
修改当前 Shot Start 公共边界
修改当前 Shot End 公共边界
在播放器当前播放头拆分 Shot
合并上一镜
合并下一镜
```

硬约束：

```text
Source Domain integer microseconds
相邻 Shot 必须连续
不允许 gap
不允许 overlap
单 Shot 最短 120ms
```

边界修改会同时更新边界两侧的 Shot；拆分保留左 Shot ID 并创建新的右 Shot ID；合并保留左 Shot ID并删除右侧边界。

受影响 Shot 的 Reference Clip / Thumbnail 会重新生成。

一旦 Shot 结构被人工修改：

```text
Episode.status = SHOTS_EDITED
当前资产 ContentAnalysisRun.status = STALE
```

旧资产 Evidence 保留用于对照，但不能继续假装是基于最新 Shot Timeline 的结果。

> 当前 V2 Shot 集合仍是“Current mutable Shot set”；完整 Shot Run / Revision 历史版本模型还未完成，不能把当前实现描述成已经具备完整 R1/R2 历史回退能力。

## 03 资产

目标：从当前 Shot / Reference Clip 中提取：

```text
人物
场景
关键道具
```

并绑定回 Shot。

人物当前策略：

```text
Face / SFace = 身份锚点
Body / Clothing / HOG = 辅助 Evidence
```

body-only Detection 不能单独创建正式人物身份，避免花、衣服、背景纹理被误识别成 Character。

资产页面按：

```text
Episode
→ Shot
→ 当前 Shot 的人物 / 场景 / 道具 Binding
```

组织，不再把几千个 AI Candidate 平铺成卡片墙。

当前资产页已经可以检查 Evidence 和 Shot Binding，但“合并 / 拆分 / 改名 / 添加移除 Binding”的 Final Asset 编辑层尚未完成，因此目前正式名称只叫“资产”，不把只读部分冒充完整“资产审核”。

ASR / Speaker / Dialogue 不属于资产提取，后续进入“内容剧本”。

## 04 内容剧本

规划中的后台能力：

```text
Whisper ASR
Speaker Diarization
OCR
Qwen3-VL / 可选云端 VLM
动作 / 情绪 / 景别 / 构图 / 运镜
人物 ↔ Speaker / Dialogue
多模态融合
```

这些不会各自做页面。

用户最终需要修改的是结构化源剧本、人物对白、Scene 内容、重要动作/视觉语义和剧情概括。

## 05 重制设计

后续人工创作工作区：

```text
Character Bible
Scene Bible
本土化对白
Target Character / Scene
Shot Specification
```

这类结果没有唯一正确答案，因此必须可编辑、可重做、可保留 Revision。

## 06 生成 / 导出

后续统一生产工作区：

```text
Video Generation
Voice / TTS
LipSync
QC
Timeline Assembly
Final Export
```

默认采用异常驱动，不要求用户逐项确认所有正常结果。

## 统一后台 Task Progress

所有耗时任务使用持久化 `BackgroundTaskRecord`：

```text
QUEUED
PROCESSING
READY
READY_WITH_WARNINGS
FAILED
CANCELLED
```

任务状态保存在数据库中，因此页面刷新 / 切换工作区不会丢进度；重复点击不会重复创建同作用域活动任务；服务重启后遗留 PROCESSING 会明确标记为中断失败。

第一批已接入：

```text
单集 / 批量视频初始化（兼容/诊断）
单集拉片
顺序批量拉片
资产提取
```

正式 UI 中拉片 Task 已经自动包含必要的视频初始化。

能计算真实数量时显示真实百分比，例如：

```text
EP07 / 16
Reference Clip 18 / 31
```

无法诚实计算模型内部百分比时使用阶段型 indeterminate 进度，不伪造百分比。

Shot 边界/拆分/合并目前只重建 1～2 个 Reference Clip，暂时使用页面局部 busy 状态；如果真实素材上耗时明显，再接入统一 Task Progress。

## 当前 V2 数据模型

基础实体：

```text
Project
Episode
Preprocess
Shot
Character
Scene
Prop
Dialogue
Asset
Voice
Generation
BackgroundTaskRecord
```

AI Evidence 仍然和人工 Final / Revision 分开设计。

当前数据目录：

```text
data_v2/
├ studio_v2.sqlite3
├ models/
└ workspace/
   └ PROJECT_ID/
      └ episodes/
         └ EPISODE_ID/
            ├ source/
            ├ preprocess/
            │  ├ proxy.mp4
            │  └ audio.wav
            └ shots/
               ├ reference/
               └ thumbnails/
```

## 当前开发状态

```text
01 剧集管理: IMPLEMENTED / NEEDS LOCAL REGRESSION
02 拉片: AUTO-PREPROCESS + TASK PROGRESS + MANUAL SHOT EDIT IMPLEMENTED / NEEDS LOCAL REGRESSION
03 资产: IMPLEMENTED AUTO EVIDENCE V1 / FINAL MANUAL BINDING NOT IMPLEMENTED
04 内容剧本: PLANNED
05 重制设计: PLANNED
06 生成 / 导出: PLANNED

Task Progress: IMPLEMENTED V1 / NEEDS LOCAL REGRESSION
Run / Revision / Rerun: GLOBAL CONTRACT CONFIRMED, FULL DATA-MODEL VERSIONING NOT YET COMPLETE
```

## 近期优先级

```text
P0-1 本机验证：拉片自动初始化 + 真实进度 + Shot 边界/拆分/合并
P0-2 完善 Shot Run / Revision 历史版本化
P0-3 完成人物 / 场景 / 道具 Final Asset Binding 人工编辑
P0-4 开发内容剧本（ASR + Speaker + VLM + Structured Script）
```

## 测试入口

```text
python -m pytest engine/tests/v2/test_shot_editor_v2.py -q
python -m pytest engine/tests/v2 -q

cd frontend
npm run typecheck
npm run build
```
