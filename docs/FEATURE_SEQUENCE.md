# AI Drama Studio — Approved Production Feature Sequence

> 本文件定义当前已经批准的业务生产开发顺序。
>
> 在正式业务开发开始后，Feature 顺序默认冻结。后续如确需调整，必须先做影响分析并由用户明确确认，不允许 Agent 自行改序。

## 1. 核心开发原则

必须严格按照真实生产流程，一个 Feature 一个 Feature 纵向开发：

```text
Contract
→ 开发
→ 单功能测试
→ 回归测试
→ 真实素材测试
→ READY_FOR_REVIEW
→ 用户人工验收
→ 文档/交接更新
→ STABLE / FROZEN
→ 下一 Feature
```

任何依赖当前 Feature 的下游功能，都不能在当前 Feature 未通过用户验收前正式开发。

AI / Codex / 开发代理只能把 Feature 标记为 `READY_FOR_REVIEW`；只有用户明确确认“验收通过”，才允许进入 `STABLE / FROZEN`。

---

# 2. 完整生产流程

```text
01 创建项目
→ 02 上传原视频
→ 03 视频预处理
→ 04 自动拉片
→ 05 Shot 人工修正
→ 06 自动人物识别
→ 07 人物人工修正
→ 08 ASR 源对白识别
→ 09 Speaker / Character 匹配
→ 10 源对白人工修正
→ 11 Scene 自动识别
→ 12 Scene 人工修正
→ 13 本土演员库
→ 14 AI 本土选角
→ 15 人工选演员
→ 16 Character Bible
→ 17 Scene Bible
→ 18 AI 翻译与本土化对白
→ 19 目标对白人工确认
→ 20 目标对白时长约束
→ 21 Shot Specification
→ 22 Shot Spec 人工确认
→ 23 单 Shot 视频生成
→ 24 Generation 版本管理
→ 25 Auto QC
→ 26 失败 Shot 人工处理
→ 27 批量生成
→ 28 TTS
→ 29 Dialogue Fit
→ 30 Lip Sync
→ 31 最终音频组装与混音
→ 32 最终字幕组装
→ 33 最终合成
→ 34 整集 QC
→ 35 导出
```

---

# 3. Feature 索引

| # | Feature | 核心输入 | 核心输出 | 主要冻结项 |
|---:|---|---|---|---|
| 01 | 创建项目 | 用户输入 | Project + Workspace | Project ID、Project Format Version、目录与 DB 规则 |
| 02 | 上传原视频 | Project + 文件 | Source Video Asset | Source Asset Contract |
| 03 | 视频预处理 | Source Video | Proxy + WAV + Thumbnail + Time Mapping | Preprocess / Timebase Contract |
| 04 | 自动拉片 | Proxy | AI Shot Boundaries | Shot Detection Contract |
| 05 | Shot 人工修正 | AI Shot | Final Shots | Final Shot Contract |
| 06 | 自动人物识别 | Final Shots | Character Clusters | Character Candidate Contract |
| 07 | 人物人工修正 | Character Clusters | Final Characters | Character ID / Final Character |
| 08 | ASR 源对白识别 | Audio | Source Dialogue Segments | ASR Segment Contract |
| 09 | Speaker/Character 匹配 | Dialogue + Tracks | Speaker Mapping Candidates | Mapping Contract |
| 10 | 源对白人工修正 | AI Dialogue | Final Source Dialogues | Source Dialogue Contract |
| 11 | Scene 自动识别 | Final Shots | Scene Candidates | Scene Candidate Contract |
| 12 | Scene 人工修正 | Scene Candidates | Final Scenes | Final Scene Contract |
| 13 | 本土演员库 | 本地演员素材 | Actors | Actor Contract |
| 14 | AI 本土选角 | Character + Dialogue + Actors | Casting Profile + Candidates | Casting Profile / Result Contract |
| 15 | 人工选演员 | Casting Candidates | Character→Actor Mapping | Actor Mapping Contract |
| 16 | Character Bible | Character + Actor + Context | Locked Character Bible | Character Bible Schema |
| 17 | Scene Bible | Final Scene + References | Locked Scene Bible | Scene Bible Schema |
| 18 | AI 翻译与本土化对白 | Source Dialogue + Character Bible + Context | Target Dialogue Draft | Localization Draft Contract |
| 19 | 目标对白人工确认 | Target Dialogue Draft | Approved Target Dialogue | Target Dialogue Contract |
| 20 | 目标对白时长约束 | Target Dialogue + Shot Duration | Timing Constraint / Review Result | Dialogue Timing Contract |
| 21 | Shot Specification | Final Shot + Bibles + Approved Target Dialogue | Draft Shot Spec | Shot Spec Schema |
| 22 | Shot Spec 人工确认 | Draft Shot Spec | Approved Shot Spec | Approved Shot Spec Contract |
| 23 | 单 Shot 视频生成 | Approved Shot Spec | Generation V1 | Generation Request/Result |
| 24 | Generation 版本管理 | Generation[] | Selected Generation | Generation Version Contract |
| 25 | Auto QC | Shot Spec + Generation | PASS/REVIEW/FAIL | QC Result Contract |
| 26 | 失败 Shot 人工处理 | REVIEW/FAIL Generation | Final Generation | Human Decision Contract |
| 27 | 批量生成 | Approved Shots | Episode Generations | Batch Job Contract |
| 28 | TTS | Approved Target Dialogue + Voice Binding | Voice Version | TTS Contract |
| 29 | Dialogue Fit | Voice + Shot Timing Constraint | Final Voice | Voice Timing Contract |
| 30 | Lip Sync | Final Video + Final Voice | Lip Sync Version | Lip Sync Contract |
| 31 | 最终音频组装与混音 | Dialogue + Ambience/SFX/BGM | Final Audio Mix | Audio Mix Contract |
| 32 | 最终字幕组装 | Approved Target Dialogue + Final Timeline | Subtitle Track | Subtitle Contract |
| 33 | 最终合成 | Final Shot Media + Final Audio + Subtitle | Master Candidate | Render Contract |
| 34 | 整集 QC | Master Candidate | Final QC Result | Episode QC Contract |
| 35 | 导出 | Approved Final Master | Deliverables | Export Structure |

---

# 4. 各 Feature 详细范围

## 01 创建项目

目标：建立项目容器，不做 AI。

必须：
- 新建/打开项目；
- 项目持久化；
- 自动创建 Workspace；
- 定义稳定 `project_id`；
- 从第一版保存 `project_format_version`；
- 保存应用/Schema 基线信息；
- 重启后可恢复。

`project_format_version` 用于未来识别 Workspace、JSON/Bible/资产目录格式版本，不能仅依赖 Alembic schema revision。

---

## 02 上传原视频

只负责导入 Source Video 与读取媒体元数据，不做预处理和 AI。

原片原则上只读，不允许后续 Feature 覆盖。

---

## 03 视频预处理

输出至少：

```text
proxy.mp4
audio.wav
thumbnail.jpg
media metadata
Source ↔ Proxy / Audio timeline mapping
```

必须遵守 `docs/MEDIA_TIMEBASE_CONTRACT.md`。

---

## 04 自动拉片

输入 Proxy，输出 AI Shot Candidate。

AI 原始边界与人工最终边界必须分离；权威时间使用整数微秒。

---

## 05 Shot 人工修正

支持边界调整、拆分、合并、新增、删除、播放和确认 Final Shot。

确认后，下游只读取 Final Shot。语义修改必须增加 revision，并按 Dependency/Invalidation 规则处理下游 stale。

---

## 06 自动人物识别

流程：抽帧 → Detection → Tracking → Embedding → Clustering。

输出只作为 Character Candidate，不自动成为最终人物。

---

## 07 人物人工修正

支持命名、合并、拆分、删除无关人物、设置角色类型、选择 Cover/Reference。

最终形成稳定 Character ID。

---

## 08 ASR 源对白识别

只解决：原片“什么时候说了什么”。

输出源语言 ASR 文本与 Source Timeline 时间。

---

## 09 Speaker / Character 匹配

结合 Speaker Diarization、人物轨迹、时间重叠、可选 Active Speaker，给出 Character Candidate + Confidence。

低置信度不得强行自动确认。

---

## 10 源对白人工修正

修正源语言：说话角色、文本、起止时间、拆分/合并/新增/删除。

输出 `Final Source Dialogue`。

---

## 11 Scene 自动识别

利用 Shot 关键帧、Embedding、时间连续性等产生 Scene Candidate。

---

## 12 Scene 人工修正

支持 Scene 合并/拆分/命名、Shot 归属修改等，输出 Final Scene。

---

## 13 本土演员库

Actor 至少支持：
- 名称；
- 正脸/侧脸/45°/全身；
- 可选表情参考；
- 参考视频；
- 声音素材；
- Tags / Notes。

---

## 14 AI 本土选角

本 Feature 必须先形成可审计的 `Casting Profile`，再进行候选检索与排序。

Casting Profile 至少考虑：
- 角色定位；
- 年龄表现；
- 外形与气质；
- 性格；
- 情绪范围；
- 动作/表演要求；
- 角色关系；
- 原角色视觉信息；
- 源对白/剧情上下文。

输出：Casting Profile + Top N Candidates + Score + Reason。

AI 只推荐，不能替代 Feature 15 的人工最终选择。

---

## 15 人工选演员

人工确认稳定：

```text
Character → Actor Mapping
```

Mapping 变化属于语义变化，会影响 Character Bible、Shot Spec、Generation/QC 的有效性。

---

## 16 Character Bible

结构化 Schema，允许人工编辑与版本追踪，状态至少：

```text
draft → reviewed → locked
```

只有 locked revision 可进入正式生产。

---

## 17 Scene Bible

结构化描述 Location、Time、Lighting、Architecture、Layout、Furniture、Props、Color/Style、References、Negative Constraints。

只有 locked revision 可进入正式生产。

---

## 18 AI 翻译与本土化对白

这是正式新增的独立生产步骤。

输入：Final Source Dialogue + 角色/关系/场景上下文 + 目标语言/市场。

必须区分：

```text
source_text
literal_translation（可选）
localized_draft
```

目标不是机械直译，而是在不改变剧情事实的前提下，使目标语言自然、符合角色身份和目标市场表达习惯。

AI 输出不能直接用于正式 TTS，必须经过 Feature 19 人工确认。

---

## 19 目标对白人工确认

人工确认：
- 目标语言文本；
- 语气；
- 角色归属；
- 是否保留专有名词；
- 必要的文化本土化；
- 是否需要缩短/改写。

输出 `Approved Target Dialogue`。

后续 Shot Spec、TTS、字幕都依赖该结果，而不是直接依赖源对白。

---

## 20 目标对白时长约束

在生成 Shot 之前，先验证目标对白是否能在镜头可用时间内自然说完。

至少保存：

```text
available_duration_us
estimated_speech_duration_us
recommended_rate
status: pass / review
```

V1 可使用语言/字符/词数估算，后续可使用预览 TTS；但该 Feature 不产生最终正式 TTS。

如果目标对白明显过长，应优先回到 Feature 19 缩短/改写，而不是等视频生成完再强行加速。

---

## 21 Shot Specification

必须读取：Final Shot、Final Character、Locked Bibles、Final Scene、Approved Target Dialogue、Timing Constraint。

Shot Spec 是模型无关的结构化镜头要求。

---

## 22 Shot Spec 人工确认

人工可修改景别、机位、运镜、动作、情绪、时长、服装、Scene、References 等。

只有 Approved Shot Spec 才能生成视频。

---

## 23 单 Shot 视频生成

只先跑通一个镜头：

```text
Approved Shot Spec
→ Prompt Compiler
→ Provider Adapter
→ Provider Job
→ Generation V1
```

必须遵守 Provider Job Safety，网络 timeout 不得无脑重提付费任务。

---

## 24 Generation 版本管理

所有结果版本化，历史不覆盖。支持查看、对比、重新生成、切模型、设置 Selected Generation。

---

## 25 Auto QC

至少三级：技术质量、一致性、语义符合度。

统一输出 `PASS / REVIEW / FAIL`，并绑定具体 Generation Version。

---

## 26 失败 Shot 人工处理

允许修改 Prompt/Reference/允许编辑的 Shot 参数、换模型、重新生成、上传手工替换、人工 override。

一个 Shot 出错不能触发整集重跑。

---

## 27 批量生成

只负责批量调度已经 Stable 的单 Shot 生成闭环，不复制第二套生成逻辑。

---

## 28 TTS

输入必须是 `Approved Target Dialogue`，不是源对白。

Voice 与 Character 建立稳定绑定；TTS 结果必须版本化。

---

## 29 Dialogue Fit

使用真实 TTS 时长与 Shot 可用时长进行最终适配。

允许合理语速/停顿调整；严重超时应回退目标对白文本，不允许无限拉伸造成失真。

---

## 30 Lip Sync

输入 Selected/Final Generation + Final Voice，输出版本化 Lip Sync Result。

---

## 31 最终音频组装与混音

必须明确最终音频床来源。

V1 允许组合：
- Final Dialogue/TTS；
- 原片分离/导入的环境声、SFX、BGM；
- 视频模型原生音频；
- 人工导入音频资产。

本 Feature 负责选择、对齐、音量/峰值处理和混合，不要求 V1 自研 AI SFX/BGM 生成器。

输出 `Final Audio Mix`。

---

## 32 最终字幕组装

根据 `Approved Target Dialogue` 和最终生产时间轴生成目标语言字幕。

字幕时间必须映射到最终成片 Shot 顺序/时长，不能简单复制原片 ASR 时间。

输出至少：Subtitle Cue List，可进一步导出 SRT/VTT。

---

## 33 最终合成

FFmpeg 读取：
- 所有 Selected/Final Shot Media；
- Final Audio Mix；
- Subtitle Track（外挂或可选烧录）。

输出 Master Candidate。

---

## 34 整集 QC

检测 Shot 缺失/顺序、黑帧、音频缺失、字幕缺失、静音、峰值、时长异常、输出损坏等。

---

## 35 导出

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

# 5. Stable Gate

任何 Feature 只有同时满足以下条件，且用户明确确认验收通过，才允许进入 STABLE/FROZEN：

```text
Contract 已定义
+ Scope 未偷做下游功能
+ 功能完成
+ 错误处理完成
+ 当前 Feature 自动测试通过
+ 受影响 Stable Feature 回归测试通过
+ 真实素材测试完成
+ P0 Review 完成
+ 代码/数据库注释 Review 完成
+ Feature 文档更新
+ Session Handoff 更新
+ PROJECT_STATE 更新
+ 用户明确验收通过
```

Agent 自己测试通过时只能标记：

```text
READY_FOR_REVIEW
```

不得自行宣布 STABLE/FROZEN 或擅自进入下一依赖 Feature。
