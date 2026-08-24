# AI Drama Studio — Project State (Reference Video V2)

> 2026-08-24：用户明确决定不再受旧程序和旧 Contract 限制，项目按 Reference Video 驱动重制架构重新建立。

## 当前状态

```text
Repository: zdingwl/ai-drama-studio
Official Release Baseline: main
Current Rebuild Branch: rebuild/reference-video-v2
Architecture: Reference Video V2
Project Format: 2.0
App Version: 2.1.0

F01 项目管理: IMPLEMENTED
F02 多剧集导入与排序: IMPLEMENTED
F03 视频预处理: IMPLEMENTED / NEEDS LOCAL REAL-VIDEO TEST
F04 自动拉片 + Reference Clip: IMPLEMENTED / NEEDS LOCAL REAL-VIDEO TEST
F05 智能内容识别: IMPLEMENTED V1 / NEEDS LOCAL REAL-VIDEO TEST
F06-F13: PLANNED / ENTITY BOUNDARIES RESERVED
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

详细见：

```text
docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md
docs/F05_CONTENT_ANALYSIS_V2.md
```

## 当前 V2 数据模型

基础生产实体：

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

F05 AI Evidence：

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

F05 自动证据与 F06 以后人工 Final 实体分开保存。

正式数据库使用 `v2_*` 表，与旧数据库结构隔离。

当前默认本地数据目录：

```text
data_v2/
├ studio_v2.sqlite3
├ models/
│  └ f05/
└ workspace/
   ├ analysis/
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

## F01-F04 当前流程

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

每个 Episode 独立生成：
- FFprobe 媒体信息；
- 标准化 Proxy；
- 独立 WAV；
- 状态记录。

单集可处理，也可以项目级顺序批处理。

### F04

```text
proxy.mp4
→ FFprobe Frame PTS
→ TransNetV2
→ Shot Boundaries
→ 从 original source 生成每个 Shot 的 Reference Clip
→ Thumbnail
→ Shot
```

支持单集重跑和项目级顺序批量拉片。

Reference Clip 是正式 Shot 资产。

## F05 当前实现

F05 是 Project 级 Run，按照 Episode.sort_order 顺序读取全部 Shot，从而跨集建立统一人物候选。

### Character

```text
Reference Clip 3 点采样
→ YuNet Face Detection
+ OpenCV HOG Person Detection
→ SFace Identity Embedding
+ Body / Clothing HSV Evidence
→ Shot-local Track
→ Conservative Cross-shot Clustering
→ Character Candidate
```

人物不是只靠人脸：未露脸但检测到身体时会形成 `face_visible=false` 的 body-only Track；body-only 只允许相邻 Shot 极高相似度保守合并。

### Scene

Shot Thumbnail HSV Visual Clustering。

Scene Candidate 只是 AI Evidence，F06 再命名/合并/改绑。

### ASR

固定依赖：

```text
faster-whisper==1.2.1
```

默认 `small` 模型，可通过：

```text
AI_DRAMA_WHISPER_MODEL
AI_DRAMA_WHISPER_DEVICE
AI_DRAMA_WHISPER_COMPUTE_TYPE
```

覆盖。

ASR 每个 Episode 跑一次，再按 Source Timeline overlap 绑定到 Shot，并同时保存 Shot-local Time。

### Speaker

当前为可选能力。

设置：

```text
AI_DRAMA_DIARIZATION_MODEL_PATH=<本地 pyannote pipeline>
```

且本机安装兼容 `pyannote.audio` 后启用。

未配置时返回：

```text
NOT_CONFIGURED
```

不会让整个 F05 失败。

### Speaker → Character

采用保守跨 Shot 共现规则；证据不足保持未绑定，交给 F06。

### Key Prop

F05 已有 Prop Candidate / Shot Prop Evidence 正式表结构，但 V1 不在没有对象模型时伪造结果。

当前：

```text
props = NOT_CONFIGURED
```

后续必须结合 Object Detection + 人物交互 + 多 Shot 重复 + Dialogue/剧情上下文判断“关键道具”。

### Short Description

只生成结构化摘要，例如：

```text
2 个人物候选；已归入场景候选；1 段源对白
```

不重复描述 Reference Video 已经保留的动作/摄影信息。

## F05 API

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare

POST /api/projects/{project_id}/content-analysis
GET  /api/projects/{project_id}/content-analysis/current
GET  /api/content-analysis/{run_id}

GET /api/content-analysis/characters/{candidate_id}/cover
GET /api/content-analysis/scenes/{candidate_id}/cover
```

## F05 前端

F05 已从“待开发占位页”升级为实际工作台：
- 人物模型状态；
- 开始 / 重新识别；
- Characters / Scenes / Dialogues / Props 四类结果；
- 每个子能力独立显示状态；
- Character Candidate 封面、Shot 数、Track 数；
- Scene Candidate 封面与 Shot 数；
- ASR 文本、Source 时间、Speaker 状态。

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

默认 pytest 入口：

```text
engine/tests/v2
```

已新增 F05 数据层测试：
- F05 AI Evidence 表与 Final 表分离；
- Project Analysis Current Run；
- Scene / Dialogue 持久化；
- Speaker → Character 保守映射。

仍必须在用户 Windows 本机使用真实短剧素材验证：
- F03 FFmpeg/FFprobe；
- F04 TransNetV2；
- F05 YuNet/SFace/HOG 人物结果；
- 背影 body-only Track；
- 人物跨镜头误合/过拆；
- Scene 聚类；
- Faster Whisper 中文 ASR；
- 多 Episode F05 顺序分析；
- Vue build / 浏览器交互。

## Legacy 状态

旧代码、旧测试、旧 Feature 文档可以作为历史算法参考，但：

```text
Legacy != V2 Contract
Legacy != 当前产品入口
Legacy != 默认测试 Gate
```

V2 不为旧数据库/API/页面兼容性牺牲当前架构。

## 下一开发目标

下一正式阶段：

```text
F06 拉片审核与人工修正
```

它读取 F05 AI Evidence，不重新执行识别模型，形成：

```text
Final Character
Final Scene
Final Prop
Final Source Dialogue
Final Speaker → Character
```

并支持人物合并/拆分/命名、Scene 合并/改绑、Prop 修正、Dialogue 文本/类型/Speaker 修正。
