# AI Drama Studio — Fixed Feature Sequence

本文件定义项目唯一推荐的开发顺序。

核心原则：**一个 Feature 一个 Feature 纵向开发、测试、验收、冻结，再进入下一个 Feature。**

任何 Feature 没有通过真实素材验收，不得标记 Stable，也不得开始依赖它的下一个 Feature。

---

## 总流程

```text
01 创建项目
→ 02 上传原视频
→ 03 视频预处理
→ 04 自动拉片
→ 05 Shot 人工修正
→ 06 自动人物识别
→ 07 人物人工修正
→ 08 ASR 对白识别
→ 09 Speaker / Character 匹配
→ 10 对白人工修正
→ 11 Scene 自动识别
→ 12 Scene 人工修正
→ 13 本土演员库
→ 14 AI 本土选角
→ 15 人工选演员
→ 16 Character Bible
→ 17 Scene Bible
→ 18 Shot Specification
→ 19 Shot Spec 人工确认
→ 20 单 Shot 视频生成
→ 21 Generation 版本管理
→ 22 Auto QC
→ 23 失败 Shot 人工处理
→ 24 批量生成
→ 25 TTS
→ 26 Dialogue Fit
→ 27 Lip Sync
→ 28 最终合成
→ 29 整集 QC
→ 30 导出
```

---

## Feature 索引

| # | Feature | 核心输入 | 核心输出 | 验收后主要冻结项 |
|---:|---|---|---|---|
| 01 | 创建项目 | 用户输入 | Project + Workspace | Project ID、目录规则 |
| 02 | 上传原视频 | Project + 文件 | Source Video Asset | Source Asset Contract |
| 03 | 视频预处理 | Source Video | Proxy + WAV + Thumbnail | 媒体预处理输出 |
| 04 | 自动拉片 | Proxy | AI Shot Boundaries | Shot Detection Contract |
| 05 | Shot 人工修正 | AI Shot | Final Shots | Final Shot Contract |
| 06 | 自动人物识别 | Final Shots | Character Clusters | Character Candidate Contract |
| 07 | 人物人工修正 | Character Clusters | Final Characters | Character ID / Final Character |
| 08 | ASR 对白识别 | Audio | Dialogue Segments | ASR Segment Contract |
| 09 | Speaker/Character 匹配 | Dialogue + Tracks | Character Candidate + Confidence | Mapping Candidate Contract |
| 10 | 对白人工修正 | AI Dialogue | Final Dialogues | Final Dialogue Contract |
| 11 | Scene 自动识别 | Final Shots | Scene Candidates | Scene Candidate Contract |
| 12 | Scene 人工修正 | Scene Candidates | Final Scenes | Scene ID / Final Scene |
| 13 | 本土演员库 | 本地素材 | Actors | Actor Contract |
| 14 | AI 本土选角 | Character + Actors | Casting Candidates | Casting Result Contract |
| 15 | 人工选演员 | Candidates | Character→Actor Mapping | Actor Mapping |
| 16 | Character Bible | Character + Actor | Locked Character Bible | Bible Schema |
| 17 | Scene Bible | Final Scene | Locked Scene Bible | Scene Bible Schema |
| 18 | Shot Specification | Shot + Bible + Dialogue | Draft Shot Spec | Shot Spec Schema |
| 19 | Shot Spec 人工确认 | Draft Shot Spec | Approved Shot Spec | Approved Spec Contract |
| 20 | 单 Shot 视频生成 | Approved Shot Spec | Generation V1 | Generation Request/Result |
| 21 | Generation 版本管理 | Generation[] | Selected Generation | Version Contract |
| 22 | Auto QC | Shot Spec + Generation | PASS/REVIEW/FAIL | QC Result Schema |
| 23 | 失败 Shot 人工处理 | Failed Generation | Final Generation | Human Decision Contract |
| 24 | 批量生成 | Approved Shots | Episode Generations | Batch Task Contract |
| 25 | TTS | Final Dialogue | Voice Version | Voice Contract |
| 26 | Dialogue Fit | Voice + Shot Duration | Final Voice | Timing Contract |
| 27 | Lip Sync | Video + Final Voice | Lip Sync Version | Lip Sync Contract |
| 28 | 最终合成 | Final Shot Media | Master Candidate | Render Contract |
| 29 | 整集 QC | Master Candidate | Final QC Result | Final QC Contract |
| 30 | 导出 | Final Master | Deliverables | Export Structure |

---

# 01 创建项目

目标：建立 Project 和本地 Workspace，不做任何 AI。

必须支持：
- 新建项目
- 打开项目
- 项目持久化
- Workspace 自动创建
- 关闭软件后再次打开仍可恢复

验收：创建真实项目、重启应用、再次进入，数据与目录全部正常。

---

# 02 上传原视频

只负责原片导入，不做拉片、人物或对白。

必须读取：
- 文件名
- 文件大小
- Duration
- Width / Height
- FPS
- Video Codec
- Audio Codec
- Audio Track

必须支持基本播放。

原片进入系统后原则上只读。

---

# 03 视频预处理

输入：Source Video。

输出：
```text
proxy.mp4
audio.wav
thumbnail.jpg
media metadata
```

必须保证 Proxy 与原片时间轴一致，避免后续 Shot、Dialogue 时间码漂移。

---

# 04 自动拉片 / Shot Detection

输入：Proxy Video。

开发期推荐主路线：TransNetV2；PySceneDetect 可作兜底。

输出必须保留 AI 原始结果：
```text
detected_start
detected_end
final_start
final_end
```

此阶段不做人物、对白、Scene。

---

# 05 Shot 人工修正

支持：
- 调整开始时间
- 调整结束时间
- 拆分 Shot
- 合并相邻 Shot
- 删除 Shot
- 新增 Shot
- 播放当前 Shot
- 确认 Final Shot

完成以后，下游只能读取 Final Shot，不直接依赖算法原始边界。

---

# 06 自动人物识别

输入：Final Shots。

流程：
```text
抽帧
→ Face Detection
→ Tracking
→ Face Embedding
→ Clustering
→ Character Candidate
```

输出只是候选 Cluster，不直接认为是最终 Character。

---

# 07 人物人工修正

必须支持：
- 命名
- 合并错误 Cluster
- 拆分错误 Cluster
- 删除无关人物/路人
- 设置主角、配角
- 修改 Cover / Reference

完成以后生成稳定 Character ID，下游只引用该 ID。

---

# 08 ASR 对白识别

目标只解决“说了什么、什么时候说”。

输入：audio.wav。

推荐：Whisper / WhisperX。

输出：Dialogue Segment + timestamps。

此 Feature 不强行完成 Character Mapping。

---

# 09 Speaker / Character 匹配

输入：
- Dialogue Segments
- Speaker Diarization
- Character Tracks
- 时间重叠信息
- 可选 Active Speaker 信息

输出：
```text
character_candidate
confidence
```

低置信度必须允许人工处理。

---

# 10 对白人工修正

支持：
- 修改说话角色
- 修改文本
- 修改开始/结束时间
- 删除
- 新增
- 拆分
- 合并

完成后生成 Final Dialogue。

---

# 11 Scene 自动识别

输入：Final Shots。

推荐：Shot 关键帧 + DINOv2 Embedding + 时间连续性 + 聚类。

输出 Scene Candidates。

---

# 12 Scene 人工修正

支持：
- Shot 移动 Scene
- Scene 合并
- Scene 拆分
- 新增 Scene
- 删除 Scene
- Scene 命名

完成后生成 Final Scene。

---

# 13 本土演员库

只建立 Actor Library，不做 AI 选角。

Actor 至少包含：
- 名称
- 正脸/侧脸/45°/全身参考图
- 可选表情参考
- 参考视频
- 声音素材
- Tags
- Notes

---

# 14 AI 本土选角

输入：Final Character + Actor Library。

AI 只负责候选和排序，不负责最终决定。

输出：Top N Candidates + Score + Reason。

---

# 15 人工选演员

人工确定：
```text
Character → Actor Mapping
```

后续 Character Bible 与视频生成只能读取已确认 Mapping。

---

# 16 Character Bible

前置条件：Character 与 Actor Mapping 已确认。

AI 输出必须是结构化 Schema，而不是只生成一段自然语言。

至少包含：
- Identity
- Face / Hair / Body
- Wardrobe Looks
- Accessories
- Expressions
- Behavior
- Voice
- Relationships
- Reference Images/Videos
- Negative Constraints

必须允许人工编辑，并支持状态：draft → reviewed → locked。

只有 locked Bible 可用于正式生成。

---

# 17 Scene Bible

输入：Final Scene + Scene References。

至少包含：
- Location
- Time
- Weather
- Lighting
- Architecture
- Layout
- Furniture
- Props
- Color / Style
- References
- Negative Constraints

必须支持人工编辑和 lock。

---

# 18 Shot Specification

输入：
- Final Shot
- Final Character
- Final Dialogue
- Character Bible
- Final Scene
- Scene Bible

输出结构化 Shot Spec，至少包含：
- Duration
- Characters
- Framing
- Camera Angle
- Camera Movement
- Main Subject
- Action
- Emotion
- Dialogue
- Wardrobe Look
- Scene
- Continuity
- References

---

# 19 Shot Spec 人工确认

必须允许人工修改：
- 景别
- 机位
- 运镜
- 人物
- 动作
- 情绪
- 对白
- 时长
- 服装
- Scene
- References

只有 Approved Shot Spec 才能进入视频生成。

---

# 20 单 Shot 视频生成

只实现单镜头闭环，暂不实现一键整集。

流程：
```text
Approved Shot Spec
→ Prompt Compiler
→ Provider Adapter
→ Video API
→ Generation V1
```

业务层禁止绑定具体 Provider。

---

# 21 Generation 版本管理

任何生成不得覆盖旧结果。

示例：
```text
SHOT_023
├ V001
├ V002
├ V003
└ V004
```

必须支持：查看、对比、删除非选中版本、切换模型重新生成、设置 selected_generation_id。

---

# 22 Auto QC

建议三级：

1. 技术 QC：损坏、时长、分辨率、FPS、黑屏、静帧、模糊等。
2. 一致性 QC：Character / Scene / Visual Embedding。
3. 语义 QC：VLM 判断人物、动作、场景、情绪、构图是否符合 Shot Spec。

统一输出：
```text
PASS
REVIEW
FAIL
```

并保留各维度分数和失败原因。

---

# 23 失败 Shot 人工处理

人工必须可以：
- 修改 Prompt
- 修改允许编辑的 Shot 参数
- 换 Provider / Model
- 换 Reference
- 重新生成
- 上传手工替换视频
- 人工通过

一个 Shot 失败不得触发整集重跑。

---

# 24 批量生成

只有单 Shot 完整闭环 Stable 后才能开发。

本质上批量层只负责调用已经冻结的单 Shot 生成流程，并增加：
- pending
- running
- completed
- failed
- pause
- resume

不得复制一套新的生成逻辑。

---

# 25 TTS

输入 Final Dialogue。

Voice 与 Character 建立稳定绑定。

所有 TTS 结果版本化。

---

# 26 Dialogue Fit

目标：让最终 Voice Duration 适配 Shot 可用时长。

输入：Shot Duration + Voice Duration。

允许：语速调整、重新 TTS、停顿调整。

超出合理阈值进入人工处理，不强行拉伸到明显失真。

---

# 27 Lip Sync

输入：Final Generation + Final Voice。

输出版本化 Lip Sync Result。

必须允许重新生成和人工选择最终版本。

---

# 28 最终合成

输入只读取所有已选中的 Final Shot Media。

FFmpeg 根据 Shot 顺序合成，不重新理解 AI。

---

# 29 整集 QC

重点检测：
- Shot 缺失
- 顺序错误
- 黑帧
- 音频缺失
- 字幕缺失
- 静音
- 音量峰值
- 总时长异常
- 输出文件损坏

---

# 30 导出

第一版至少输出：
```text
final_master.mp4
clean_video.mp4
subtitle.srt
subtitle.vtt
final_audio.wav
project metadata
```

后续需要时再增加 Premiere XML、DaVinci XML、EDL。

---

## Gate 规则

任何 Feature 只有同时满足以下条件才能标记 Stable：

```text
Contract 已定义
+ 功能完成
+ 异常处理完成
+ 自动测试完成
+ 真实素材测试完成
+ 人工验收通过
+ Freeze 清单完成
```

未通过 Gate，不进入下一依赖 Feature。
