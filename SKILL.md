---
name: ai-drama-studio-reference-video-v2
version: 3.2.0
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

F05 当前实现见 `docs/F05_CONTENT_ANALYSIS_V2.md`。

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

F05 额外维护 AI Evidence：

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

AI Evidence 与 F06 以后人工 Final 实体必须分离。

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

## Character 规则

人物不能等同于人脸。

F05 V1 最低基线：

```text
YuNet Face Detection
+ SFace Identity Embedding
+ OpenCV HOG Person Detection
+ Body / Clothing Visual Evidence
+ Shot-local Track
+ Conservative Cross-shot Clustering
```

有脸时 SFace 主导身份；没有脸但检测到人体时允许形成 body-only Track。body-only 不允许跨远距离 Shot 激进合并，只允许相邻 Shot 且极高身体相似度时自动连接。

以后可以把 HOG/HSV 换成专门 Body ReID / Segmentation 模型，但不得改变 Character/Track 的业务语义。

## F05 各子组件必须独立失败

F05 不是一个黑盒模型。

```text
Characters
Scenes
Props
ASR
Speaker
Speaker → Character
Description
```

每个组件必须有独立状态。某一组件模型缺失或失败时，不应无条件摧毁其它已经可计算的结果。

例如 Speaker 未配置时：

```text
speaker = NOT_CONFIGURED
```

Scene / ASR / Character 仍可完成。

Key Prop 没有可靠对象/剧情模型时保持 `NOT_CONFIGURED`，禁止用普通 Object Detection 结果冒充剧情关键道具。

## F05 ASR / Speaker

源对白使用 faster-whisper。

默认配置：

```text
AI_DRAMA_WHISPER_MODEL=small
AI_DRAMA_WHISPER_DEVICE=auto
```

Speaker Diarization 是可选本地能力，通过：

```text
AI_DRAMA_DIARIZATION_MODEL_PATH
```

接入本机 pyannote Pipeline。

低置信 Speaker → Character 不能强行绑定；未解析是合法状态，F06 人工处理。

## 批量执行

Episode 按 `sort_order` 排序。

```text
EP01 完成
→ EP02 完成
→ EP03 完成
```

默认不并行多个视频，后续 GPU 重任务同样默认 concurrency = 1。

F05 使用 Project 级 Run 按这个顺序读取所有 Episode，使人物候选可以跨集聚类。

## 时间规则

Source Shot / F05 Dialogue 使用原片 integer microseconds。

Dialogue 同时保存：

```text
source_start_us / source_end_us
shot_start_us / shot_end_us
```

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

```text
F01-F02 = IMPLEMENTED
F03-F04 = IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO TEST
F05 = IMPLEMENTED V1 / NEEDS REAL-SAMPLE TEST
F06-F13 = NOT IMPLEMENTED
```

V2 主代码：
- `engine/app/studio_v2.py`
- `engine/app/media_v2.py`
- `engine/app/content_models_v2.py`
- `engine/app/character_visual_v2.py`
- `engine/app/content_analysis_v2.py`
- `engine/app/main.py`
- `frontend/src/views/ProjectList.vue`
- `frontend/src/views/ProjectStudio.vue`

## Git 工作方式

用户当前明确要求直接在默认分支开发：

```text
Default Branch: main
Development Branch: main
```

后续默认：
- 直接提交 `main`；
- 不新建 feature/rebuild 分支；
- 不主动创建 PR；
- 历史 `rebuild/reference-video-v2` 分支只保留为历史记录，不再作为开发入口。

除非用户以后明确改变这一规则，否则必须一直遵守。

## Legacy 规则

仓库中旧 35 Feature、旧 Frozen Snapshot、旧 Workflow Versioning 文档和旧业务模块均属于历史资料。用户已明确授权 V2 不做旧数据/旧 API 兼容，因此它们不能限制 V2 设计。

如复用旧算法，仅把算法代码当参考，不继承旧业务 Contract。

## 测试

默认：

```bash
pytest
```

只验证 `engine/tests/v2`。

F03-F05 还必须在 Windows 本机验证真实媒体链。F05 特别检查：
- 正脸/侧脸/背影 Track；
- 同人物跨 Shot 过拆和误合；
- 同 Shot 多人物不能自动合并；
- Scene 聚类；
- Faster Whisper 文本和 Shot 时间绑定；
- Project 多 Episode 顺序分析；
- 重跑后 Current Run 切换；
- 缺少可选模型时组件状态是否明确。
