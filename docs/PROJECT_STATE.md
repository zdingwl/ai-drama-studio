# AI Drama Studio — Project State (Reference Video V2)

> 2026-08-24：用户明确决定不再受旧程序和旧 Contract 限制，项目按 Reference Video 驱动重制架构重新建立。

## 当前状态

```text
Repository: zdingwl/ai-drama-studio
Official Release Baseline: main
Current Rebuild Branch: rebuild/reference-video-v2
Architecture: Reference Video V2
Project Format: 2.0

F01 项目管理: IMPLEMENTED
F02 多剧集导入与排序: IMPLEMENTED
F03 视频预处理: IMPLEMENTED / NEEDS LOCAL REAL-VIDEO TEST
F04 自动拉片 + Reference Clip: IMPLEMENTED / NEEDS LOCAL REAL-VIDEO TEST
F05-F13: PLANNED / ENTITY BOUNDARIES RESERVED
```

未创建 PR，未合并 main。

## 产品主线

```text
F01 项目管理
↓
F02 剧集导入与排序
↓
F03 视频预处理
↓
F04 自动拉片 / Reference Clip
↓
F05 人物 / 场景 / 道具 / 台词智能识别
↓
F06 拉片审核与人工修正
↓
F07 替换素材与资产绑定
↓
F08 翻译 / 本地化 / Voice / TTS
↓
F09 重制任务规划
↓
F10 Reference Video 视频重制
↓
F11 弹性时间轴 / 整集合成
↓
F12 QC
↓
F13 导出
```

详细见 `docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md`。

## 当前 V2 数据模型

已建立：

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
```

正式数据库使用 `v2_*` 表，与旧数据库结构隔离。

当前默认本地数据目录：

```text
data_v2/
├ studio_v2.sqlite3
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

可通过 `AI_DRAMA_STUDIO_HOME` 改变本地数据根目录。

## 当前 F01-F04 用户流程

### F01

新建项目填写：
- 项目名称；
- 原项目语言；
- 目标语言；
- 目标地区。

### F02

一个 Project 可以导入多个视频。

前端支持：
- 多文件导入；
- 拖动排序；
- 删除 Episode。

数据库以 `sort_order` 作为后续批处理顺序。

### F03

每个 Episode 独立：
- FFprobe 媒体信息；
- 标准化 Proxy；
- 独立 WAV；
- 状态记录。

单集可处理，也可以项目级顺序批处理。

### F04

每个 Episode：

```text
proxy.mp4
→ FFprobe Frame PTS
→ TransNetV2
→ Shot Boundaries
→ 从 original source 生成每个 Shot 的 Reference Clip
→ 生成 Thumbnail
→ 保存 Shot
```

支持：
- 单集拉片；
- 单集重新拉片；
- 项目级顺序批量拉片。

Reference Clip 是正式 Shot 资产。

## F05 以后必须遵守的核心方向

F05 不做“大而全影视分析”。

重点顺序：

```text
★★★★★ Character Identity
★★★★★ Character Track
★★★★★ Dialogue / ASR
★★★★★ Speaker → Character
★★★★☆ Character Mask
★★★★☆ Scene ID
★★★★☆ Key Prop ID
★★★☆☆ Dialogue Emotion / Speaking Style
★★★☆☆ Short Description
★★☆☆☆ Shot Type / Camera Motion
```

复杂动作、机位、空间关系和镜头运动优先由 Reference Video 直接提供给后续视频模型。

## 重制原则

F09 以后每个 Shot 先选择处理策略，而不是全部 Full Regen：

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

目标语言造成的音频时长变化允许改变最终 Shot 时长。F11 重算 Production Timeline。

## 测试状态

已完成代码级 Smoke 验证：
- V2 Python 模块可编译；
- V2 DB 初始化可执行；
- Project 创建/读取可执行；
- FastAPI V2 应用可导入。

默认 pytest 已切换到：

```text
engine/tests/v2
```

仍需要用户 Windows 本机做真实素材验证：
- FFmpeg/FFprobe；
- TransNetV2 权重和推理；
- 多 Episode 顺序批处理；
- Reference Clip 边界与画面准确性；
- Vue build / 浏览器交互。

## Legacy 状态

旧代码、旧测试、旧 Feature 文档可能仍保留在仓库中作为历史参考，但：

```text
Legacy != V2 Contract
Legacy != 当前产品入口
Legacy != 默认测试 Gate
```

V2 `engine/app/main.py` 和 V2 Router 不允许重新依赖旧业务流程，除非用户明确决定复用某个算法。

## 下一开发目标

本机验收 F01-F04 后进入 F05：

```text
Character Detection
+ Face / Body ReID
+ Character Track
+ Mask
+ Scene Clustering
+ Key Prop Detection
+ ASR
+ Speaker Diarization
+ Speaker ↔ Character
+ Dialogue Type
+ Emotion / Speaking Style
```

全部结果绑定现有 Shot / Reference Clip。
