---
name: ai-drama-studio-development
version: 1.0.0
description: AI Drama Studio 本地自用 AI 短剧重制工作台的开发技能手册。严格按照真实生产流程逐 Feature 开发、真实素材测试、人工验收、Contract 冻结后再进入下一功能，避免跨模块反复返工。
---

# AI Drama Studio Development Skill

## 1. Skill 的作用

本 Skill 用于指导 **AI Drama Studio** 的产品设计、技术设计、编码、测试、验收、重构和后续迭代。

任何开发人员、AI Coding Agent、Codex 或自动化开发工具在修改本项目之前，都应先阅读本文件。

本 Skill 的优先目标不是让代码看起来“先进”，而是保证：

1. 真实短剧工作流完整跑通。
2. 每个功能可以单独验证。
3. 已经验收的上游功能不被下游反复破坏。
4. AI 结果始终可人工修正。
5. 单个 Shot 可以独立重试和替换。
6. 模型与供应商可以替换。
7. RTX 4060 Ti 16GB 能完成开发阶段验证。
8. 系统保持本地自用所需要的简单度。

---

# 2. 项目定位

AI Drama Studio 是一个：

> **本地自用的 AI 短剧重制生产工作台。**

系统输入一部已有短剧，通过自动分析 + 人工校正，将其转换为结构化的 Character / Scene / Shot / Dialogue 数据；随后完成本土选角、Character Bible、Scene Bible、Shot Specification、逐镜头 AI 重生成、自动 QC、失败镜头人工修正、TTS、Lip Sync 和整集合成。

它不是：

- 通用 AIGC SaaS
- 多租户平台
- 在线商城
- 视频模型训练平台
- Premiere / DaVinci 的完整替代品
- 面向大量并发用户的云服务

第一版只服务一个目标：

> **让本地操作者按照短剧生产流程，从原片一直走到可导出的 AI 重制成片。**

---

# 3. 最终业务流程

流程固定为：

```text
上传短剧
→ 视频预处理
→ 自动拉片
→ 人工修正 Shot
→ 自动识别人
→ 人工修正人物
→ 自动识别对白
→ Speaker / Character 匹配
→ 人工修正对白
→ 自动识别 Scene
→ 人工修正 Scene
→ 本土演员库
→ AI 本土选角
→ 人工选演员
→ AI 建 Character Bible
→ 人工确认 / Lock
→ AI 建 Scene Bible
→ 人工确认 / Lock
→ AI 分析 Shot Specification
→ 人工确认
→ 单 Shot 视频生成
→ Generation 版本管理
→ Auto QC
→ 失败 / 低质量 Shot 推人工
→ 修改 / 重新生成 / 手工替换
→ 批量生成
→ TTS
→ Dialogue Fit
→ Lip Sync
→ 最终合成
→ 整集 QC
→ 导出
```

任何产品或代码设计都应服务于这条流程。

---

# 4. 最高优先级规则：必须逐 Feature 开发

## 4.1 禁止“大阶段一起开发”

禁止：

```text
先一起开发
拉片 + 人物 + 对白 + Scene + Bible
→ 最后统一测试
→ 发现 Shot 数据结构有问题
→ 全部跟着返工
```

必须：

```text
Feature 01
→ 开发
→ 单功能测试
→ 真实短剧测试
→ 人工验收
→ 修复
→ 再测试
→ Freeze

Feature 02
→ ...
```

一次只推进 **一个当前 Feature**。

---

## 4.2 Feature Gate

一个 Feature 只有满足下面条件才能进入 Stable：

```text
Contract 已定义
+ 功能实现完成
+ 异常处理完成
+ 自动测试完成
+ 真实素材测试完成
+ 人工验收通过
+ Freeze 清单完成
```

如果没有人工验收通过：

> 不得主动开发下一个依赖它的 Feature。

---

## 4.3 每个 Feature 开发前必须建立规格

复制：

```text
templates/FEATURE_SPEC_TEMPLATE.md
```

至少写清：

1. 功能目标
2. 明确不做什么
3. 前置 Stable Feature
4. 用户操作流程
5. Input Contract
6. Output Contract
7. 读取的数据
8. 允许修改的数据
9. 禁止修改的数据
10. DB Migration
11. 文件输入输出
12. API
13. 模型 / Provider
14. GPU 策略
15. 异常处理
16. 测试
17. 真实素材验收
18. Definition of Done
19. Freeze

没有 Contract，不开始编码。

---

# 5. Stable Feature 冻结原则

Feature 被标记 Stable 后，默认冻结：

- Input Contract
- Output Contract
- API Contract
- 核心 DB fields
- ID 规则
- 文件目录 / 命名规则
- 状态枚举
- 错误码

后续 Feature 禁止为了方便：

- 重写 Stable 上游模块
- 改变已有字段语义
- 绕过上游 Final 数据
- 在下游复制上游算法
- 直接删除 Stable 字段

确实需要修改时优先：

```text
新增字段
→ Adapter
→ V2 Contract
```

而不是破坏 V1。

---

# 6. AI Result 与 Final Result 必须分离

只要 AI 结果允许人工修改，就必须保留原始结果。

## Shot

```text
detected_start
detected_end

final_start
final_end
```

## Character

```text
ai_cluster_id
final_character_id
```

## Dialogue

```text
asr_text
final_text
speaker_candidate
final_character_id
```

## QC

```text
ai_qc_scores
ai_qc_status
human_decision
human_reason
```

禁止人工编辑直接覆盖 AI 原始结果。

这样做的原因：

- 可追溯
- 可重新跑模型
- 可比较算法准确率
- 可积累真实训练 / 优化数据
- 可恢复人工误操作

---

# 7. Shot 是系统核心生产单元

整个系统必须围绕 Shot 独立性设计。

每个 Shot 必须能够独立：

- 播放
- 修正时间边界
- 重新人物分析
- 修改 Dialogue
- 修改 Scene
- 修改 Shot Specification
- 更换 Reference
- 更换 Provider
- 更换 Model
- 重新生成 Video
- 单独 QC
- 重新 TTS
- 重新 Lip Sync
- 上传手工替换视频
- 选择最终版本

一个 Shot 出错：

> 不得要求整集重跑。

---

# 8. Generation / TTS / Lip Sync 必须版本化

禁止覆盖历史媒体结果。

## Video Generation

```text
SHOT_023
├── V001
├── V002
├── V003
└── V004
```

Shot 保存：

```text
selected_generation_id
```

每个 Generation 至少记录：

- generation_id
- shot_id
- version
- provider
- model
- provider_task_id
- prompt
- references
- duration
- resolution
- seed（如有）
- output_path
- status
- cost（能获取时）
- created_at
- metadata
- QC result

TTS 和 Lip Sync 使用相同原则。

---

# 9. 模型必须可替换

业务代码禁止绑定具体供应商。

错误：

```python
generate_with_minimax()
generate_with_runway()
generate_with_seedance()
```

正确：

```python
video_generation.generate(request)
```

Provider Adapter 再负责：

```text
Provider A
Provider B
Provider C
```

业务层认识的是：

- Character Bible
- Scene Bible
- Shot Specification
- Generation Request
- Generation Result
- QC Result
- Voice Request
- LipSync Request

而不是某一个模型品牌。

---

# 10. Prompt Compiler 与 Shot Specification 必须分离

Shot Specification 是模型无关的镜头需求。

它描述：

- 哪些人物
- 哪个 Scene
- 时长
- 景别
- 机位
- 运镜
- 动作
- 情绪
- 对白
- 服装
- Continuity
- Reference

模型专属 Prompt：

```text
Shot Specification
       ↓
Prompt Compiler
       ├ Model A Prompt
       ├ Model B Prompt
       └ Model C Prompt
```

禁止把模型 A 的特殊 Prompt 规则污染 Shot Specification。

---

# 11. 当前技术栈

## Frontend

```text
Vue 3
TypeScript
Vite
Pinia
```

## Backend / AI Engine

```text
Python 3.11
FastAPI
PyTorch
CUDA
OpenCV
FFmpeg
FFprobe
```

## Data

```text
SQLite
SQLAlchemy
Alembic
Local Filesystem
```

## Desktop

```text
Electron
```

但 Electron **后置**。

开发阶段优先：

```text
Vue localhost:5173
FastAPI localhost:8000
```

完整工作流稳定后再打包桌面应用。

---

# 12. 当前硬件约束

当前开发机：

```text
NVIDIA RTX 4060 Ti 16GB
```

开发阶段：

- 不追求速度
- 不追求并发
- 不以 GPU 性能阻塞功能开发

GPU 默认：

```text
concurrency = 1
```

策略：

```text
任务需要模型
→ load
→ execute
→ unload
→ release VRAM
```

不要求 Whisper、DINO、Face、LipSync 等全部常驻显存。

---

# 13. 本地模型 / API 分工

## 本地优先

- FFmpeg / FFprobe
- OpenCV
- Shot Detection
- Scene Embedding
- Face Detection / Tracking / Embedding
- Whisper / WhisperX
- Speaker Diarization
- Embedding
- Technical QC
- Basic Consistency QC
- Final Render

## API 优先

- 强 VLM
- Character Bible 语义生成
- Scene Bible 语义生成
- Shot Understanding
- Prompt 辅助
- Video Generation
- Premium TTS
- Premium Lip Sync
- Semantic QC

## 不在开发阶段自研基础模型

不投入时间训练：

- Video Foundation Model
- Large VLM
- ASR Foundation Model
- TTS Foundation Model

项目核心是 **Short Drama Production Engine**。

---

# 14. 数据核心关系

推荐核心对象：

```text
Project
└── Episode
    ├── Character
    │   ├── Actor Mapping
    │   └── Character Bible
    │
    ├── Scene
    │   ├── Scene Bible
    │   └── Shot
    │       ├── Character Relations
    │       ├── Dialogue
    │       ├── Shot Specification
    │       ├── Generation[]
    │       │   └── QC Result
    │       └── Selected Generation
    │
    └── Render / Export
```

推荐稳定 ID：

```text
PROJECT_*
EPISODE_*
SCENE_*
SHOT_*
CHARACTER_*
ACTOR_*
DIALOGUE_*
GENERATION_*
QC_*
VOICE_*
LIPSYNC_*
RENDER_*
```

ID 不因文件名、Provider 或重新生成而变化。

---

# 15. 本地文件规则

视频、图片、音频禁止直接写 SQLite Blob。

SQLite 保存：

- IDs
- metadata
- state
- relationship
- structured JSON
- relative path

媒体保存：

```text
workspace/
└── project_001/
    ├── source/
    ├── proxy/
    ├── audio/
    ├── frames/
    ├── shots/
    ├── characters/
    ├── actors/
    ├── scenes/
    ├── generations/
    ├── voice/
    ├── lipsync/
    ├── cache/
    └── exports/
```

Source Video 原则上只读。

数据库优先保存相对路径。

---

# 16. UI 原则

本项目不是传统后台管理系统。

核心 UI 应接近“AI 视频工作台”：

```text
┌────────────┬──────────────────────┬──────────────┐
│ 资源 / 对象 │      视频播放器       │ Inspector    │
│ Character  │                      │ Shot         │
│ Scene      │                      │ Character    │
│ Shot       │                      │ Scene        │
│ Actor      │                      │ Dialogue     │
│            │                      │ Prompt / QC  │
├────────────┴──────────────────────┴──────────────┤
│ Shot Timeline / Scene Timeline                  │
└─────────────────────────────────────────────────┘
```

优先：

- 同一个工作区完成大量操作
- 少跳页面
- Shot 点击即查看详情
- AI 结果旁边直接人工修正
- 失败原因清楚可见

第一版 Timeline 不做成 Premiere。

只做当前业务必要的：

- 点击
- 播放
- 调整 Shot 边界
- 拆分
- 合并
- 排序 / Scene 归属
- 显示状态

---

# 17. 长任务规范

AI / 视频处理任务统一状态：

```text
pending
running
completed
failed
cancelled
```

UI 必须显示：

- 当前任务名称
- 当前步骤
- 进度
- 错误原因
- 是否可重试

WebSocket 可用于实时进度。

禁止 UI 长时间只有 Loading 且不知道在干什么。

---

# 18. 错误恢复原则

每个 Feature 必须支持当前步骤重跑。

例如：

```text
Character Detection Failed
→ 只重跑 Character Detection
```

```text
SHOT_023 Video Generation Failed
→ 只重跑 SHOT_023
```

外部 API 错误至少区分：

- timeout
- rate_limit
- provider_error
- invalid_input
- content_rejected
- insufficient_balance
- task_failed

UI 禁止只显示：

```text
请求失败
```

应该尽量显示：

```text
Provider
Model
失败步骤
错误原因
重试次数
可执行动作
```

---

# 19. 30 个 Feature 固定顺序

完整说明见：

```text
docs/FEATURE_SEQUENCE.md
```

顺序固定：

```text
01 创建项目
02 上传原视频
03 视频预处理
04 自动拉片
05 Shot 人工修正
06 自动人物识别
07 人物人工修正
08 ASR 对白识别
09 Speaker / Character 匹配
10 对白人工修正
11 Scene 自动识别
12 Scene 人工修正
13 本土演员库
14 AI 本土选角
15 人工选演员
16 Character Bible
17 Scene Bible
18 Shot Specification
19 Shot Spec 人工确认
20 单 Shot 视频生成
21 Generation 版本管理
22 Auto QC
23 失败 Shot 人工处理
24 批量生成
25 TTS
26 Dialogue Fit
27 Lip Sync
28 最终合成
29 整集 QC
30 导出
```

除非经过明确产品决策，不随意调整。

---

# 20. Feature 01–05：先得到可靠 Final Shot

## Feature 01 — 创建项目

只建立 Project + Workspace。

不要做上传和 AI。

Freeze：

- Project ID
- Workspace 基础规则

## Feature 02 — 上传原视频

只做：

- 选择文件
- 复制/登记
- 读取 metadata
- 播放

不做拉片。

## Feature 03 — 视频预处理

输出：

```text
proxy.mp4
audio.wav
thumbnail.jpg
```

确保时间轴稳定。

## Feature 04 — 自动拉片

输入：Proxy。

输出 AI Shot Boundaries。

必须保留：

```text
detected_start/end
final_start/end
```

## Feature 05 — Shot 人工修正

支持：

- 改起止时间
- 拆分
- 合并
- 删除
- 新增

验收后产生 **Final Shot**。

后续全部读取 Final Shot。

---

# 21. Feature 06–10：得到可靠 Character 与 Dialogue

## Feature 06 — 自动人物识别

流程：

```text
Final Shot
→ Frames
→ Face Detection
→ Tracking
→ Embedding
→ Clustering
```

输出 Candidate Cluster。

## Feature 07 — 人物人工修正

支持：

- 命名
- 合并
- 拆分
- 删除路人
- 主角/配角
- Reference

产生 Final Character。

## Feature 08 — ASR

只解决：

```text
说了什么
什么时候说
```

## Feature 09 — Speaker / Character

结合 Speaker、时间重叠、Character Track、可选 Active Speaker，输出候选 + Confidence。

## Feature 10 — 对白人工修正

人工确认：

- 谁说
- 说什么
- 起止时间

产生 Final Dialogue。

---

# 22. Feature 11–17：Scene、Casting 与 Bible

## Feature 11 — Scene 自动识别

输入 Final Shots。

建议：关键帧 + DINOv2 + 时间连续性 + 聚类。

## Feature 12 — Scene 人工修正

产生 Final Scene。

## Feature 13 — 演员库

先做 Actor 素材管理，不做 AI。

## Feature 14 — AI 本土选角

AI 推荐 Top N，不自动拍板。

## Feature 15 — 人工选演员

产生稳定：

```text
Character → Actor Mapping
```

## Feature 16 — Character Bible

必须结构化。

建议字段：

```text
Identity
Appearance
Face
Hair
Body
Wardrobe Looks
Accessories
Expressions
Behavior
Voice
Relationships
References
Negative Constraints
```

状态：

```text
draft
reviewed
locked
```

只有 locked 用于正式生成。

## Feature 17 — Scene Bible

同样结构化：

```text
Location
Time
Weather
Lighting
Architecture
Layout
Furniture
Props
Color / Style
References
Negative Constraints
```

必须人工确认 + lock。

---

# 23. Feature 18–24：Shot 重生成闭环

## Feature 18 — Shot Specification

输入：

- Final Shot
- Final Character
- Final Dialogue
- Locked Character Bible
- Final Scene
- Locked Scene Bible

输出模型无关 Shot Spec。

## Feature 19 — 人工确认 Shot Spec

只有 approved 才能生成。

## Feature 20 — 单 Shot 视频生成

第一版只做单 Shot。

先不要批量。

## Feature 21 — Generation 版本管理

必须实现 V1/V2/V3 与 Selected Generation。

## Feature 22 — Auto QC

推荐三级：

```text
Technical QC
+ Identity / Scene Consistency QC
+ Semantic VLM QC
```

输出：

```text
PASS
REVIEW
FAIL
```

## Feature 23 — 失败 Shot 人工处理

允许：

- 改 Prompt
- 改允许编辑的 Shot 参数
- 换模型
- 换 Reference
- Regenerate
- 手工上传替换
- 人工通过

## Feature 24 — 批量生成

只能复用已经 Stable 的单 Shot Generation，不允许重新写一套业务逻辑。

---

# 24. Feature 25–30：声音、合成与导出

## Feature 25 — TTS

Character 与 Voice 建立稳定 Mapping。

## Feature 26 — Dialogue Fit

让 Voice Duration 适应 Shot。

不允许把声音强行拉伸到明显失真。

异常进入人工。

## Feature 27 — Lip Sync

Final Generation + Final Voice → Lip Sync Version。

仍然版本化。

## Feature 28 — 最终合成

FFmpeg 只读取所有 Selected / Final Shot Media。

Render 不重新做 AI 理解。

## Feature 29 — 整集 QC

检查：

- Shot 缺失
- 顺序
- 黑帧
- 音频
- 字幕
- 静音
- 音量
- 总时长
- 文件损坏

## Feature 30 — 导出

第一版至少：

```text
final_master.mp4
clean_video.mp4
subtitle.srt
subtitle.vtt
final_audio.wav
project metadata
```

---

# 25. Auto QC 的开发原则

第一版不要先训练专用 QC 大模型。

先组合：

## Level 1 — Technical

本地 FFmpeg / OpenCV：

- damaged file
- black frame
- freeze
- blur
- duration
- FPS
- resolution
- audio track

## Level 2 — Consistency

本地 Embedding：

- Character similarity
- Scene similarity
- visual consistency

## Level 3 — Semantic

强 VLM 判断：

- 人物是否符合
- 动作是否完成
- 场景是否正确
- 情绪是否符合
- 构图是否大致符合
- 是否出现明显异常

统一输出维度分数、Overall 和 Failure Reason。

开发初期不要过早固定 PASS 阈值，先收集真实数据再校准。

---

# 26. 人工审核设计原则

系统价值不在“完全没有人工”，而在：

> **只把真正需要人工判断的异常推给人工。**

人工队列应该显示：

```text
Shot
Failure Reason
QC Score
Current Version
Reference
Actions
```

操作至少：

```text
重新生成
换模型
换参考
修改 Prompt
修改 Shot Spec
上传手工视频
人工通过
```

---

# 27. 成本追踪

即使本地自用，也建议记录外部 API 成本。

按 Generation / Shot / Episode：

```text
provider
model
request duration
input/output usage
cost
success
retry count
```

以后可以得到：

```text
某类 Shot
→ 哪个模型成功率高
→ 平均生成几次
→ 平均成本多少
```

这是未来 Model Router 的数据基础。

---

# 28. 开发时禁止过度设计

第一版不要主动加入：

- SaaS 多租户
- 登录注册
- 企业权限
- 在线充值
- 分布式 Job Queue
- Kubernetes
- 多 GPU 调度集群
- 大型对象存储集群
- 完整 Premiere 多轨编辑器
- 自研视频基础模型

只有实际需求出现后再增加。

---

# 29. 代码结构建议

```text
ai-drama-studio/
├── desktop/
│   ├── electron/
│   └── frontend/
│       └── src/
│           ├── views/
│           ├── components/
│           ├── player/
│           ├── timeline/
│           ├── inspector/
│           ├── stores/
│           ├── api/
│           └── types/
│
├── engine/
│   ├── main.py
│   ├── api/
│   ├── database/
│   ├── services/
│   │   ├── projects/
│   │   ├── media/
│   │   ├── shots/
│   │   ├── characters/
│   │   ├── dialogues/
│   │   ├── scenes/
│   │   ├── casting/
│   │   ├── bible/
│   │   ├── generation/
│   │   ├── qc/
│   │   ├── voice/
│   │   ├── lipsync/
│   │   └── render/
│   ├── local_models/
│   ├── providers/
│   │   ├── vlm/
│   │   ├── video/
│   │   ├── tts/
│   │   └── lipsync/
│   ├── schemas/
│   ├── tasks/
│   └── utils/
│
├── config/
├── docs/
├── templates/
└── workspace/  # gitignored
```

代码目录可以随着实际 Feature 调整，但必须保持职责边界清晰。

---

# 30. AI Coding Agent 执行协议

当被要求“开始开发某个 Feature”时，Agent 必须按顺序执行：

## Step 1 — 确认 Feature

明确：

```text
Feature ID
Feature Name
```

不得顺手开发下一个 Feature。

## Step 2 — 检查上游

确认所有依赖 Feature 已 Stable。

如果上游 Contract 未稳定，不得通过重写上游绕过问题。

## Step 3 — 阅读 Contract

读取：

- SKILL.md
- docs/FEATURE_SEQUENCE.md
- 当前 Feature Spec
- 相关 Stable Contract

## Step 4 — 先设计再编码

至少明确：

- DB changes
- API
- file outputs
- UI state
- error handling
- tests

## Step 5 — 编码范围控制

只修改当前 Feature 允许的文件和对象。

如发现必须修改 Stable 上游：

1. 明确说明原因。
2. 优先 Adapter / additive migration。
3. 不静默破坏 Contract。

## Step 6 — 测试

包括：

- unit test
- integration test
- error path
- persistence after restart
- current Feature rerun

## Step 7 — 真实素材验收

提供操作步骤和观察点。

## Step 8 — 等待人工验收

人工没有确认 Stable 前：

> 不继续依赖 Feature。

## Step 9 — Freeze

验收后更新：

- Feature Spec status = stable
- Stable version
- Freeze fields
- Known limitations

---

# 31. 修改已有代码时的行为规则

Agent 不得：

- 为了“代码更漂亮”大范围重构 Stable 功能
- 未经要求升级所有依赖
- 替换已经能工作的技术栈
- 把本地自用改造成 SaaS 架构
- 把 API 模型写死到业务层
- 删除历史 Generation
- 覆盖 AI 原始结果
- 把媒体 Blob 塞进 SQLite
- 为了性能优化改变业务结果

优先：

> 最小修改完成当前 Feature。

---

# 32. Definition of Done — 项目级标准

任何 Feature 的代码完成不等于功能完成。

真正 Done 必须是：

```text
用户可以按照真实流程操作
+ 输出正确
+ 出错可以恢复
+ 数据可以持久化
+ 应用重启后可继续
+ AI 结果可以人工修正
+ 当前步骤可以单独重跑
+ 不破坏 Stable 上游
+ 使用真实短剧验收通过
```

---

# 33. 当前第一开发目标

整个仓库建立 Skill 后，正式业务开发从：

```text
Feature 01 — 创建项目
```

开始。

不要直接跳到 AI 生成、人物识别或 Bible。

Feature 01 完成、真实测试、人工验收并 Freeze 后，才进入：

```text
Feature 02 — 上传原视频
```

以此类推直到 Feature 30。

---

# 34. 相关文档

详细固定开发顺序：

```text
docs/FEATURE_SEQUENCE.md
```

技术栈与运行规则：

```text
docs/TECH_STACK.md
```

数据与 Freeze：

```text
docs/DATA_AND_FREEZE_RULES.md
```

每个 Feature 的规格模板：

```text
templates/FEATURE_SPEC_TEMPLATE.md
```

---

# 35. 最终判断标准

当面对一个技术选择、产品需求或代码改动时，优先问：

1. 这是不是当前 Feature 必需？
2. 会不会破坏已经 Stable 的上游？
3. AI 结果是否还能人工修正？
4. 单个 Shot 是否还能独立处理？
5. 是否把具体模型写死了？
6. 是否能在 RTX 4060 Ti 16GB 开发环境中验证？
7. 是否增加了当前本地自用场景不需要的复杂度？

如果一个方案更“高级”，但让这七个问题变差，则不采用。
