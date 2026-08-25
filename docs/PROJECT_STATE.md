# AI Drama Studio — Project State (Reference Video V2)

> 当前开发基线：`main`。
> 产品已经从“一个技术 Feature 一个页面”切换为“后台自动能力 + 少量人工审核工作区”。

## 当前基线

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
Project Format: 2.0
App Version: 2.1.0
```

## 正式用户工作区

左侧主导航只保留真正需要用户管理、审核或创作的工作区：

```text
01 剧集管理
02 拉片审核
03 资产审核
04 内容剧本
05 重制设计
06 生成 / 导出
```

核心原则：

```text
不可修改、无需确认的技术中间结果
→ 后台自动执行
→ 不单独做生产阶段页面

容易出错、影响下游、用户可以修正的结果
→ 做审核工作区
```

因此下列能力不再单独占导航：

```text
FFprobe / Media Info
Proxy
Audio WAV
Frame PTS
关键帧缓存
Face / Body Embedding
SAM Mask / Track
OCR 原始框
Camera Trajectory
模型内部日志
```

需要排错时通过详情 / Evidence 查看。

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

项目级属性：

```text
项目名称
原项目语言
目标语言
目标地区
```

属于 Project 设置，不再占一个生产阶段。

## 02 拉片审核

正式用户动作只有：

```text
单集拉片 / 重新拉片
顺序批量拉片
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

也就是说，原来的“F03 视频预处理”仍然是后端基础能力，但已经不再是用户页面。

批量拉片严格：

```text
EP01 完整处理完
↓
EP02
↓
EP03
...
```

不并行跑多个 Episode。

拉片结果属于高风险结果，因此保留审核工作台：Shot 边界、拆分、合并、重新执行等人工能力继续在这里完成。

## 03 资产审核

目标：从 Final Shot / Reference Clip 中提取并审核：

```text
人物
场景
关键道具
```

全部绑定回 Shot。

人物当前策略：

```text
Face / SFace = 身份锚点
Body / Clothing / HOG = 辅助 Evidence
```

body-only Detection 不能单独创建正式人物身份，避免花、衣服、背景纹理被误识别成 Character。

资产页面默认按：

```text
Episode
→ Shot
→ 当前 Shot 的人物 / 场景 / 道具 Binding
```

组织，不再把几千个 AI Candidate 平铺成卡片墙。

ASR / Speaker / Dialogue 不再属于资产提取，后续进入“内容剧本”。

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

用户最终审核：

```text
结构化源剧本
人物对白
Scene 内容
动作 / 重要视觉语义
剧情概括
```

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

默认采用异常驱动审核，不要求用户逐项确认所有正常结果。

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

任务状态保存在数据库中，因此：

```text
页面刷新不会丢进度
切换工作区不会丢进度
重复点击不会重复创建同作用域活动任务
服务重启后遗留 PROCESSING 会明确标记为中断失败
```

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

AI Evidence 仍然和人工 Final / Revision 分开保存。

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
02 拉片审核: IMPLEMENTED V1 / AUTO-PREPROCESS INTEGRATED / NEEDS LOCAL REGRESSION
03 资产审核: IMPLEMENTED V1 / ALGORITHM + UI STILL UNDER REAL-VIDEO REVIEW
04 内容剧本: PLANNED
05 重制设计: PLANNED
06 生成 / 导出: PLANNED

Task Progress: IMPLEMENTED V1 / NEEDS LOCAL REGRESSION
Run / Revision / Rerun: GLOBAL CONTRACT CONFIRMED, NEEDS FURTHER DATA-MODEL IMPLEMENTATION
```

## 近期优先级

```text
P0-1 本机验证：拉片自动预处理 + 全局真实进度
P0-2 完善拉片人工 Revision / 重跑版本化
P0-3 完善人物 / 场景 / 道具资产算法与 Final Binding
P0-4 开发内容剧本（ASR + Speaker + VLM + Structured Script）
```

## 测试入口

```text
python -m pytest engine/tests/v2 -q

cd frontend
npm run typecheck
npm run build
```
