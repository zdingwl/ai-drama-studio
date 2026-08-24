---
name: ai-drama-studio-reference-video-v2
version: 3.0.0
description: AI Drama Studio Reference Video 驱动的本地短剧本地化重制工作台开发规则。
---

# AI Drama Studio — Reference Video V2

## 产品目标

把多集原短剧拆成可控制的 Shot，并把每个原 Shot 保存为 Reference Video。后续通过人物、场景、关键道具、目标语言 Dialogue、Voice 和替换资产控制重制，而不是把原镜头完全翻译成文字后从零猜测动作与摄影。

## 正式流程

```text
F01 项目管理
→ F02 剧集导入与排序
→ F03 视频预处理
→ F04 自动拉片 / Reference Clip
→ F05 智能内容识别
→ F06 人工审核修正
→ F07 替换素材
→ F08 本地化与声音
→ F09 重制任务规划
→ F10 Reference Video 重制
→ F11 弹性时间轴
→ F12 QC
→ F13 导出
```

详细定义见 `docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md`。

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

其中 Shot 是核心生产单元，Reference Clip 是 Shot 一级正式资产。

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

不优先结构化：复杂动作序列、精确人物空间距离、复杂摄影轨迹、详细灯光参数、逐帧动作文字化。Reference Video 已经包含这些信息时，不重复高成本重建。

## 批量执行

Episode 按 `sort_order` 排序。

```text
EP01 完成
→ EP02 完成
→ EP03 完成
```

默认不并行多个视频，后续 GPU 重任务同样默认 concurrency = 1。

## 时间规则

Source Shot 使用原片 integer microseconds。

目标语言允许改变 Shot 时长：

```text
original_duration_us
!= target_audio_duration_us
!= generated_duration_us
!= final_duration_us
```

F11 重新建立 Production Timeline；最终字幕和音频以 Production Timeline 为准，不复制 Source ASR 全局时间。

## 重制策略

F09 必须允许按 Shot 选择：

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

## 当前代码状态

V2 当前真正实现：F01-F04。

主代码：
- `engine/app/studio_v2.py`
- `engine/app/media_v2.py`
- `engine/app/main.py`
- `frontend/src/views/ProjectList.vue`
- `frontend/src/views/ProjectStudio.vue`

F05-F13 的实体边界已经在 V2 Schema 中预留，但必须逐步实现后才能标记为可用。

## Legacy 规则

仓库中旧 35 Feature、旧 Frozen Snapshot、旧 Workflow Versioning 文档和旧业务模块均属于历史资料。用户已明确授权 V2 不做旧数据/旧 API 兼容，因此它们不能限制 V2 设计。

如复用旧算法，仅把算法代码当参考，不继承旧业务 Contract。

## 测试

默认：

```bash
pytest
```

只验证 `engine/tests/v2`。

F03/F04 还必须在 Windows 本机验证 FFmpeg、TransNetV2 和真实视频输出。测试重点是 Reference Clip 是否准确、批量是否按顺序、失败是否明确可恢复。
