# AI Drama Studio — Reference Video V2 Architecture

## 1. 架构目标

本项目最终目标不是产出一份影视分析报告，而是把原短剧拆成可控制的镜头，并用新的语言、人物、声音、场景和关键道具重新制作。

V2 核心：

```text
Reference Video + Structured Control Data
```

原 Shot Reference Video 本身负责保留：
- 人物动作和走位；
- 摄像机运动；
- 景别与构图；
- 大部分空间关系；
- 动作节奏；
- 原镜头的时序结构。

结构化拉片重点保存后续替换、绑定、翻译、配音和生成模型必须明确控制的信息。

## 2. 13 阶段生产链

### F01 项目管理

字段：
- project_name；
- source_language；
- target_language；
- target_region。

目标语言与目标地区分开保存，供后续本地化表达、Voice、Prompt 和文化适配使用。

### F02 剧集导入与排序

一个 Project 对应多个 Episode。

必须支持：
- 多视频导入；
- 拖动排序；
- 单集删除；
- 后续按 `sort_order` 顺序批量处理。

批量不是并行：

```text
EP01 完成 → EP02 完成 → EP03 完成
```

### F03 视频预处理

每集生成：
- Media Info；
- Proxy Video；
- Audio WAV。

Source Video 始终作为原始证据，不被预处理覆盖。

### F04 自动拉片 / Reference Clip

产物：

```text
Shot
├ shot_id
├ episode_id
├ ordinal
├ start_us
├ end_us
├ duration_us
├ reference_clip
├ thumbnail
└ keyframes
```

Reference Clip 从 Original Source 按 Shot 边界重新编码生成并永久保存。

可以重新拉片；新结果替代当前 Shot 集合。V2 不继承旧 Candidate / Final Shot 双层业务模型。

### F05 智能内容识别

F05 是 **AI Evidence 层**，不是人工 Final 数据层。

重点识别：
- Character Identity；
- Character Track；
- Face / Body Evidence；
- Scene Candidate / Scene ID Evidence；
- Source Dialogue / ASR；
- Speaker Diarization；
- Speaker → Character；
- Key Prop Candidate；
- 轻量 Structured Description。

当前 V1 人物视觉链：

```text
YuNet Face Detection
+ SFace Identity Embedding
+ OpenCV HOG Person Detection
+ Body / Clothing Visual Evidence
→ Shot-local Track
→ Conservative Cross-shot Clustering
```

人物不能等同于人脸。没有脸但检测到人体时允许形成 body-only Track；无脸证据只允许保守相邻 Shot 自动连接，避免仅因服装相似造成跨场景误合。

当前 Scene 使用 Shot Thumbnail 视觉聚类；ASR 使用 faster-whisper。

Speaker 是可选本地能力；未配置时必须显式返回 `NOT_CONFIGURED`，不能让其它组件一起失败。

Key Prop 已建立 Evidence 数据结构，但在没有可靠对象 + 交互 + 剧情语义模型时保持 `NOT_CONFIGURED`，禁止把普通环境物体冒充剧情关键道具。

不要求第一版高精度结构化：
- 复杂动作序列；
- 精确空间距离；
- 摄影机轨迹；
- 灯光参数；
- 逐帧动作文字。

详细 Contract：`docs/F05_CONTENT_ANALYSIS_V2.md`。

### F06 拉片审核与人工修正

F06 读取 F05 AI Evidence，不重新跑识别模型。

用户围绕 Reference Video 审核：
- 人物命名 / 增删 / 改绑；
- 人物合并 / 拆分；
- Scene 命名 / 修正 / 合并；
- Key Prop 增删 / 命名 / 合并；
- Speaker 修正；
- Dialogue 文本和类型修正。

最终形成：

```text
Final Character
Final Scene
Final Prop
Final Source Dialogue
Final Speaker → Character
```

AI Evidence 与人工 Final 值保持可区分。

### F07 替换素材与资产绑定

建立 Asset Library：

```text
Character Asset
Scene Asset
Prop Asset
```

支持：
- 上传参考图；
- AI 自动生成 Prompt；
- 手工 Prompt；
- AI 生成图片；
- 资产版本。

资产绑定实体，不绑定单个 Shot。Shot 通过 Character / Scene / Prop ID 自动继承。

### F08 翻译 / 本地化 / Voice / TTS

Dialogue 至少保留：

```text
original_text
translated_text
localized_text
final_text
```

人物级绑定 Voice；每句 Dialogue 可以额外保存 emotion / speaking_style。

Dialogue Type：

```text
dialogue
narration
inner_monologue
```

只有真正画面开口对白才默认需要 Lip Sync。

### F09 重制任务规划

每个 Shot 根据“到底变化了什么”选择成本最低的处理策略：

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

例如只是翻译配音的镜头不需要 Full Regen；无变化镜头直接复用 Reference。

### F10 Reference Video 视频重制

典型输入：

```text
Reference Clip
+ Character Reference Assets
+ Scene Reference Asset
+ Prop Reference Assets
+ Target Dialogue Audio
+ Minimal Generation Prompt
```

Prompt 主要强调“保持原运动/构图/摄影”，而不是重新用文字重建原视频动作。

### F11 弹性时间轴

语言变化允许 Shot 时长变化。

必须区分：

```text
original_duration_us
target_audio_duration_us
generated_duration_us
final_duration_us
```

根据最终 Shot 时长重新生成 Production Timeline、字幕时间和音频对齐。

### F12 QC

自动检查至少覆盖：
- Missing Shot；
- Failed Generation；
- Black Frame；
- Missing Audio；
- Missing Dialogue；
- Missing Asset / Voice；
- Lip Sync Failure；
- Duration Outlier；
- Subtitle Timing Error。

允许单 Shot 重试，不要求整集重跑。

### F13 导出

支持：
- 单集 MP4；
- 批量 MP4；
- SRT / ASS；
- Dialogue JSON；
- Shot JSON；
- Project JSON；
- 可选音频输出。

## 3. 核心实体关系

```text
Project
├ Episode
│  └ Shot
│     ├ Character links
│     ├ Scene link
│     ├ Prop links
│     ├ Dialogue
│     └ Generation versions
├ Character
├ Scene
├ Prop
├ Asset
└ Voice
```

### Project

业务范围和本地化目标。

### Episode

原始视频的剧集容器；所有批量任务按 `sort_order`。

### Shot

最小可独立处理和重制的生产单元。

### Character / Scene / Prop

跨 Shot 复用的语义实体。

### Dialogue

绑定 Shot 和 Speaker；源文本与目标文本分层保存。

### Asset / Voice

重制所需替换素材与声音实体。

### Generation

保存每次 Shot 重制策略、版本、目标时长与输出。

## 4. F05 AI Evidence 与 Final 分层

F05 写：

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

F06 写人工 Final：

```text
Character
Scene
Prop
Dialogue
```

F05 重跑不能覆盖旧 Evidence；新 Run 成功后切换 current。F06 人工修正不得覆盖原始 AI Evidence。

## 5. Shot 数据优先级

### 必须高准确率

```text
Shot Boundaries
Reference Clip
Character Identity
Character Track
Dialogue
Speaker → Character
```

### 高价值

```text
Character Mask
Scene ID
Key Prop ID
Dialogue Type
Emotion / Speaking Style
```

### 辅助

```text
Short Description
Shot Type
Camera Motion
Prop Track / Mask
```

Character Mask 仍属于高价值后续增强；当前 F05 V1 先稳定 Track / BBox，不用低质量伪 Mask 冒充正式分割结果。

## 6. Reference Clip 存储原则

建议工作区：

```text
PROJECT_ID/
└ episodes/
   └ EPISODE_ID/
      ├ source/
      ├ preprocess/
      └ shots/
         ├ reference/
         │  ├ shot_0001.mp4
         │  ├ shot_0002.mp4
         │  └ ...
         └ thumbnails/
```

Reference Clip 以后可作为：
- Video-to-Video 输入；
- Character Replacement 输入；
- Inpainting 输入；
- Lip Sync 输入；
- 生成结果对比证据。

## 7. 时间模型

所有数据库正式时间单位使用：

```text
integer microseconds
```

Source Timeline 只描述原视频证据。
Production Timeline 描述目标语言重制成片。

F05 Dialogue 同时保存 Source Time 与 Shot-local Time。

禁止假设：

```text
Production Shot duration == Source Shot duration
```

## 8. 当前实现范围

```text
F01-F02 = IMPLEMENTED
F03-F04 = IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO TEST
F05 = IMPLEMENTED V1 / NEEDS REAL-SAMPLE TEST
F06-F13 = NOT IMPLEMENTED
```

F04 当前本地方案继续使用 TransNetV2 + FFprobe PTS；后续如果更换切镜算法，只替换 detector，不改变 Shot / Reference Clip Contract。

F05 当前算法也采用能力分层：Character Visual、Scene、ASR、Speaker、Prop 可以分别替换，不允许再次做成一个不可拆的黑盒。

## 9. 与 Legacy 的关系

V2 不要求：
- 旧数据库迁移兼容；
- 旧 API 兼容；
- 旧页面兼容；
- 旧 Frozen Feature 顺序兼容。

历史代码可以作为算法参考，但新实现必须以本文件、`docs/PROJECT_STATE.md`、当前 Feature Contract 和用户最新决策为准。
