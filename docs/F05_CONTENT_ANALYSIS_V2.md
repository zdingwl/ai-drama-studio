# F05 — 智能内容识别（Reference Video V2）

## 1. 目标

F05 不负责把原片重新描述成一份“大而全拉片报告”。

它围绕 F04 的 Reference Clip，提取后续重制时必须被程序和人工明确控制的 AI Evidence：

```text
Character Candidate / Track
Scene Candidate
Key Prop Candidate
Source Dialogue
Speaker Segment
Speaker → Character Candidate
Short Structured Description
```

原动作、人物走位、摄影机运动、构图和大部分空间关系继续由 Reference Video 本身提供。

## 2. Run 范围

F05 采用 Project 级 Run：

```text
Project
→ Episode 01
→ Episode 02
→ Episode 03
→ ...
```

分析顺序读取 `Episode.sort_order`。

这样人物候选可以跨集聚类，不会每一集重新生成一套男主/女主 ID。

每次重新分析创建新的：

```text
v2_content_analysis_runs
```

历史 Run 保留；完整成功后才切换 `is_current=true`。

## 3. AI Evidence 与 Final 数据分离

F05 写：

```text
v2_character_candidates
v2_character_tracks
v2_scene_candidates
v2_shot_scene_evidence
v2_prop_candidates
v2_shot_prop_evidence
v2_speaker_segments
v2_analysis_dialogues
```

F06 以后写人工确认后的：

```text
v2_characters
v2_scenes
v2_props
v2_dialogues
```

禁止人工修改覆盖 F05 原始自动证据。

## 4. Character V1

当前本地视觉链：

```text
Reference Clip
↓
3 个时间采样点
↓
YuNet Face Detection
+ OpenCV HOG Person Detection
↓
SFace Identity Embedding
+ Body / Clothing HSV Histogram
↓
Shot-local Track
↓
Cross-shot Conservative Clustering
↓
Character Candidate
```

### 为什么不是“只做人脸识别”

- 有脸：SFace 是主要身份依据，身体/服装作为辅助；
- 人脸属于某个 Person Box 时，Track 使用人体区域作为位置和 body evidence；
- 没露脸但 HOG 能检测到身体时，仍产生 `face_visible=false` 的 body-only Track；
- body-only Track 不跨远距离镜头激进合并，只允许相邻 Shot 且身体特征极高相似度时自动连接；
- F06 后续允许人工合并、拆分、改绑。

这不是最终 Body ReID 模型。以后可以把 HOG/Histogram 替换为专门 ReID embedding，而不改变 F05 数据 Contract。

## 5. Scene V1

当前使用 Shot Thumbnail 的 HSV histogram 做保守聚类。

输出：

```text
Scene Candidate
↕
Shot Scene Evidence
```

Scene Candidate 只是自动候选，不等于最终“办公室 / 医院 / 家”等人工语义名称。

## 6. ASR V1

依赖：

```text
faster-whisper==1.2.1
```

默认：

```text
AI_DRAMA_WHISPER_MODEL=small
AI_DRAMA_WHISPER_DEVICE=auto
```

可以通过环境变量覆盖：

```text
AI_DRAMA_WHISPER_MODEL
AI_DRAMA_WHISPER_DEVICE
AI_DRAMA_WHISPER_COMPUTE_TYPE
```

ASR 对每个 Episode 的 F03 `audio.wav` 运行一次，然后根据时间重叠绑定到 Shot。

保存 Source Timeline 和 Shot-local Time 两套时间：

```text
source_start_us
source_end_us
shot_start_us
shot_end_us
```

F05 自动文本字段是：

```text
ai_text
```

F06 人工确认后再产生 Final Source Dialogue。

## 7. Speaker

Speaker Diarization 当前不是强制默认依赖。

原因：正式 pyannote Community 模型需要单独准备模型文件/许可条件，不能在用户不知情时静默联网下载。

如果配置：

```text
AI_DRAMA_DIARIZATION_MODEL_PATH=<本地 pyannote pipeline 路径>
```

且 Python 环境已经安装兼容的 `pyannote.audio`，F05 会输出：

```text
Speaker Segment
speaker_label
```

未配置时：

```text
speaker = NOT_CONFIGURED
```

不是任务失败。

## 8. Speaker → Character

只有 Speaker 和 Character Evidence 同时存在时才自动映射。

规则保守：

1. 统计同一 Speaker 在多个 Shot 中与哪些 Character Candidate 共现；
2. 至少有两段支持，且第一候选明显高于其它候选时才自动绑定；
3. 单 Shot 只有一个可见人物时允许低置信候选绑定；
4. 多人物且证据不足时保持未绑定，交给 F06。

不允许为了“结果完整”强制绑定错误人物。

## 9. Key Prop

当前已经建立正式 AI Evidence 表：

```text
v2_prop_candidates
v2_shot_prop_evidence
```

但 V1 没有默认对象模型，因此：

```text
props = NOT_CONFIGURED
```

这是有意设计。

普通桌椅、垃圾桶、水杯等环境物体不能因为通用 Object Detection 检测到了就自动升级为“剧情关键道具”。后续 Prop 模块应结合：

```text
Object Detection
+ 人物交互
+ 多 Shot 重复出现
+ Dialogue / Plot Context
```

再判断是否进入核心 Prop Library。

## 10. Short Description

当前只写结构化摘要，例如：

```text
2 个人物候选；已归入场景候选；1 段源对白
```

不重复生成：

```text
人物站左边
人物走两步
镜头缓慢推进
...
```

这些信息由 Reference Clip 直接保留。

## 11. API

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare

POST /api/projects/{project_id}/content-analysis
GET  /api/projects/{project_id}/content-analysis/current
GET  /api/content-analysis/{run_id}

GET /api/content-analysis/characters/{candidate_id}/cover
GET /api/content-analysis/scenes/{candidate_id}/cover
```

## 12. 当前验收重点

Windows 真实短剧素材必须检查：

- 背影是否能形成 body-only Track；
- 同一个人物跨镜头是否过拆/误合；
- 两个同时出现的人物是否被错误合并；
- Scene 聚类是否过度合并；
- Whisper 中文时间和文本准确度；
- Dialogue → Shot 时间绑定；
- Project 多集顺序分析；
- 重新分析后旧 current 是否正确切换；
- 缺少人物模型时 Scene/ASR 是否仍可完成；
- Speaker 未配置时是否明确显示而非失败。

## 13. 下一阶段 F06

F06 不再重新跑识别算法。

它读取 F05 AI Evidence，提供：

```text
人物命名 / 合并 / 拆分 / Shot 改绑
Scene 命名 / 合并 / Shot 改绑
Prop 增删 / 合并 / 命名
Dialogue 文本修正
Dialogue Type 修正
Speaker → Character 修正
```

最后形成可供 F07/F08 使用的 Final 实体。
