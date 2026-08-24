# AI Drama Studio — Project State (Reference Video V2)

> 2026-08-24：用户明确决定不再受旧程序和旧 Contract 限制，项目按 Reference Video 驱动重制架构重新建立。
> 同日用户进一步明确：后续开发直接在默认分支 `main` 进行，不再新建开发分支。

## 当前状态

```text
Repository: zdingwl/ai-drama-studio
Default / Development Branch: main
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

当前 V2/F05 代码已快进进入 `main`。不需要 PR，也不再使用 `rebuild/reference-video-v2` 作为开发入口。

## Git 工作方式

```text
所有后续开发 → main
默认不创建 feature/rebuild 分支
默认不创建 PR
```

历史 `rebuild/reference-video-v2` 分支可以保留作历史记录，但不得作为当前开发基线。

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

F05 自动证据与 F06 以后人工 Final 实体分开保存。正式数据库使用 `v2_*` 表，与旧数据库结构隔离。

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

F01 新建项目填写项目名称、原项目语言、目标语言和目标地区。

F02 一个 Project 可导入多个视频，前端支持多文件导入、拖动排序和删除 Episode；`sort_order` 是所有批处理顺序依据。

F03 每个 Episode 独立生成 FFprobe 媒体信息、标准化 Proxy、独立 WAV 和状态记录，支持单集或项目级顺序批处理。

F04：

```text
proxy.mp4
→ FFprobe Frame PTS
→ TransNetV2
→ Shot Boundaries
→ 从 original source 生成每个 Shot 的 Reference Clip
→ Thumbnail
→ Shot
```

Reference Clip 是正式 Shot 资产。

## F05 当前实现

F05 是 Project 级 Run，按照 `Episode.sort_order` 顺序读取全部 Shot，从而跨集建立统一人物候选。

### Character

```text
Reference Clip 采样
→ YuNet Face Detection
+ OpenCV HOG Person Detection
→ SFace Identity Embedding
+ Body / Clothing Visual Evidence
→ Shot-local Track
→ Conservative Cross-shot Clustering
→ Character Candidate
```

人物不是只靠人脸：未露脸但检测到身体时会形成 `face_visible=false` 的 body-only Track；body-only 只允许相邻 Shot 极高相似度保守合并。同一 Shot 多人物禁止因服装相似自动合并。

### Scene

Shot Thumbnail 视觉聚类形成 Scene Candidate。它只是 AI Evidence，F06 再命名、合并和改绑。

### ASR

使用 `faster-whisper==1.2.1`。默认 small 模型，可通过：

```text
AI_DRAMA_WHISPER_MODEL
AI_DRAMA_WHISPER_DEVICE
AI_DRAMA_WHISPER_COMPUTE_TYPE
```

覆盖。ASR 每个 Episode 跑一次，再按 Source Timeline overlap 绑定到 Shot，并同时保存 Shot-local Time。

### Speaker

当前为可选能力。设置 `AI_DRAMA_DIARIZATION_MODEL_PATH` 并安装兼容 `pyannote.audio` 后启用；未配置返回 `NOT_CONFIGURED`，不阻塞其他 F05 组件。

### Speaker → Character

采用保守映射；证据不足保持未绑定，交给 F06。

### Key Prop

已经建立 Prop Candidate / Shot Prop Evidence 表结构，但 V1 不用普通 Object Detection 冒充剧情关键道具识别；当前 `props = NOT_CONFIGURED`。

## F05 API

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare
POST /api/projects/{project_id}/content-analysis
GET  /api/projects/{project_id}/content-analysis/current
GET  /api/content-analysis/{run_id}
GET  /api/content-analysis/characters/{candidate_id}/cover
GET  /api/content-analysis/scenes/{candidate_id}/cover
```

## F05 前端

F05 已是实际工作台，可以看到人物模型状态、开始/重新识别、Characters / Scenes / Dialogues / Props、各子组件独立状态、人物候选封面和 Track 数、Scene 候选以及 ASR/Speaker 信息。

## 测试状态

默认 pytest：

```text
engine/tests/v2
```

GitHub Actions `Reference Video V2 CI` 已改为监听 `main` push，并验证：
- V2 backend compile/import/tests；
- frontend npm ci/build。

仍必须在用户 Windows 本机用真实短剧素材验证：
- F03 FFmpeg/FFprobe；
- F04 TransNetV2；
- F05 YuNet/SFace/HOG 人物结果；
- 背影 body-only Track；
- 人物跨镜头误合/过拆；
- Scene 聚类；
- Faster Whisper 中文 ASR；
- 多 Episode F05 顺序分析；
- 浏览器真实交互。

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
