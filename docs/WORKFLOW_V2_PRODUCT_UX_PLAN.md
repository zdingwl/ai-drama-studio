# Localized Remake Workflow V2 产品、数据与页面交互规划

> 状态：DRAFT FOR REVIEW  
> 文档用途：作为下一轮产品讨论、数据契约设计、前后端任务拆分和本地验收的共同基线。  
> 当前范围：规划，不代表现有代码已经满足本文契约。  
> 正式产品页面：Project / Review Center / Output。

---

## 1. 为什么需要 Workflow V2

现有代码虽然已经实现 SourceDramaSnapshot、目标人物与场景、目标对白、TTS、RemakeTimeline、GenerationSegment、H3、QC、PostProduction 和 EpisodeOutput 等能力，但当前流程还存在几个根本问题：

1. 页面把“任务执行过”当成“阶段已经完成”；
2. 页面打开、刷新或任务完成可能触发新的后台任务；
3. GET/read 接口存在同步或写入副作用；
4. 上游一个人物问题会扩散成大量下游对白问题；
5. 54 条完整对白被投影到 76 个 Shot 后，下游丢失了完整对白分组；
6. 旧数据已经过期，页面仍可能把它计入当前完成率；
7. 模型离线、业务不确定、任务失败和数据过期没有被清楚区分；
8. Project、Review Center、Output 分别计算状态，导致同一个项目在不同页面显示不同结论。

Workflow V2 的目标不是增加更多阶段，而是重新建立统一的数据、状态、任务和交互契约。

---

## 2. 最高产品原则

### 2.1 页面原则

正式页面仍然只有：

1. Project：项目配置、原片理解、目标设计、对白与生成准备；
2. Review Center：只处理系统无法安全决定的业务问题；
3. Output：H3 重拍、QC、选版、后期、成片和交付。

GenerationSegment、H3 Context、重试、QC、口型内部过程、音频分离等都不是新的顶层页面，只能出现在高级诊断或任务中心。

### 2.2 自动化原则

- 自动工作是后台任务，不是页面；
- 页面打开、刷新、切换 Tab 时只允许读取；
- 只有用户明确点击动作按钮时才允许创建重任务；
- 任务完成后只刷新状态和通知用户，不自动开始下一项重任务；
- 已成功结果应从检查点复用，不得无理由重做。

### 2.3 人工处理原则

- 人物身份、场景含义、说话人、翻译含义、节奏选择等无法安全决定时，交给人工；
- 一个上游根问题只生成一个人工任务；
- 下游受影响数据显示为“被上游阻塞”，不复制成几十条人工任务；
- 人工决定必须写入正式业务数据，不能只是关闭一个提醒；
- 模型或 Worker 离线属于运行环境问题，不伪装成人工内容问题。

### 2.4 数据安全原则

- Source ASR、OCR、Shot 事实下游只读；
- SourceDramaSnapshot 是唯一的下游源事实接口；
- LocalSubject 不等于 Final Character；
- 不降低 Character V10.1 身份阈值来减少人工问题；
- Shot 不等于 GenerationSegment；
- GenerationAttempt 成功不等于可用输出；
- 只有 GenerationSelection / Selected Output 可以进入后期；
- 多脸口型必须先确定目标说话人；
- 原片原始音频不能直接混入目标成片。

### 2.5 容易混淆的对象

以下三个对象不能都简称为“场景”：

| 对象 | 含义 |
|---|---|
| Source semantic Scene | 从原片叙事和时间线中理解出的语义场景 |
| Final Scene Asset | 经过正式确认、可被项目引用的源场景资产 |
| SceneLocalizationMapping | 源场景到目标 KEEP / LOCALIZE 方案的映射 |

人物同样要区分 Scene-local person、人物轨迹、Final Character 和 TargetCharacter。

---

## 3. 总流程

~~~mermaid
flowchart TD
    S0[S0 项目与剧集配置] --> S1[S1 原片理解]
    S1 --> S2[S2 源事实定稿]
    S2 -->|人物 场景 说话人不确定| R[Review Center 人工确认]
    R --> S2

    S2 --> S3[S3 目标人物与场景设计]
    S3 -->|创作选择不确定| R
    S3 --> S4[S4 目标对白与目标语音]
    S4 -->|台词含义不确定| R
    S4 --> S5[S5 重拍时间轴与生成计划]
    S5 -->|节奏需要人工决定| R

    S5 -->|用户明确点击开始| S6[S6 H3重拍 QC和选版]
    S6 -->|连续失败或选版冲突| R
    S6 -->|Selected Output| S7[S7 口型 音轨 字幕 后期]
    S7 -->|多人物说话人不确定| R
    S7 --> S8[S8 整集组装与人工验收]

    X[模型或本地服务不可用] --> W[等待本地服务或显式重试]
~~~

用户看到的是 3 个页面，S0—S8 是后台业务阶段，不应全部做成页面步骤条。

### 3.1 一张表看懂完整流程

| 步骤 | 主要做什么 | 获得的数据 | 后面的用途 |
|---|---|---|---|
| 1. 创建项目 | 导入短剧，设置出海目标 | 原片文件、剧集顺序、源语言、目标语言、目标地区、场景策略 | 决定翻译语言、人物风格、场景是否本土化 |
| 2. 拆分原片 | 读取视频并切成镜头 | 视频时长、分辨率、帧率、音轨、每个镜头起止时间、缩略图、参考片段 | 后续识别、生成、字幕、剪辑都依赖这些时间 |
| 3. 理解剧情 | 分析每个场景和镜头发生了什么 | 场景、剧情摘要、人物动作、表演、运镜、对白、画面文字、道具 | 作为重拍时的剧情、动作、镜头和表演依据 |
| 4. 确定原片人物和场景 | 把画面里观察到的人统一成正式人物 | Final Character、Final Scene、Final Prop、人物与镜头绑定、说话人与人物绑定 | 决定谁需要替换、谁说哪句话、使用谁的声音和脸 |
| 5. 固化原片事实 | 将前面的结果整理成唯一可信版本 | SourceDramaSnapshot、数据版本号、场景/镜头/人物/对白/参考片段关系 | 后续所有本土化和生成只能读取这份数据 |
| 6. 设计目标版本 | 设计出海后的角色和场景 | TargetCharacter、目标姓名、外貌、参考图、场景 KEEP/LOCALIZE 决定、目标场景参考、VoiceProfile | H3 用来生成人物和场景，TTS 用来生成角色声音 |
| 7. 生成目标对白和声音 | 翻译、本土化并生成配音 | 最终目标语言对白、目标说话人物、声音配置、音频文件、真实说话时长、情绪风格 | 用于时间轴、口型、字幕和最终音轨 |
| 8. 重排时间并准备生成 | 根据目标语言时长重新安排镜头 | RemakeTimeline、目标镜头起止时间、对白位置、4—15 秒 GenerationSegment、H3 提示词和参考条件 | 告诉 H3 每次生成什么、生成多长、参考哪个原镜头 |
| 9. H3 重拍与质检 | 生成目标镜头，自动检查并重试 | GenerationAttempt、生成视频、种子、结构检查、人物/场景/动作检查、GenerationSelection | 只有被选中的镜头版本才能进入后期 |
| 10. 后期与成片 | 对口型、混音、字幕、拼接并验收 | 口型视频、目标对白音轨、安全背景音、SRT、最终 MP4、成片版本、验收结果 | 播放、下载和商业交付 |

---

## 4. 统一状态模型

每个阶段必须同时记录三个互相独立的状态。

### 4.1 数据有效性 Validity

| 内部状态 | 页面文案 | 含义 |
|---|---|---|
| NOT_BUILT | 尚未生成 | 从未形成过结果 |
| CURRENT | 当前 | 结果基于最新上游数据 |
| STALE | 需要重算 | 有旧结果，但依赖版本已经改变 |

### 4.2 业务就绪度 Readiness

| 内部状态 | 页面文案 | 含义 |
|---|---|---|
| READY | 可以继续 | 当前结果满足下游契约 |
| BLOCKED_REVIEW | 需要人工确认 | 系统无法安全做业务决定 |
| BLOCKED_DEPENDENCY | 被上游阻塞 | 上游还没有提供有效输入 |
| WAITING_RUNTIME | 等待本地服务 | 模型或 Worker 不可用 |

### 4.3 执行状态 Execution

| 内部状态 | 页面文案 |
|---|---|
| IDLE | 空闲 |
| QUEUED | 等待开始 |
| PROCESSING | 处理中 |
| SUCCEEDED | 本次执行成功 |
| FAILED | 本次执行未完成 |
| INTERRUPTED | 已中断，可恢复 |

### 4.4 可用结果判断

只有同时满足以下条件，阶段结果才允许流入下游：

~~~text
Validity = CURRENT
Readiness = READY
~~~

Execution=SUCCEEDED 只说明这次任务执行完成，不代表输出一定完整、当前或可交付。

如果任务运行成功但发现人物冲突，任务可以结束，阶段仍应保持 BLOCKED_REVIEW。人物未绑定、缺少声音和 fingerprint 过期不能降级成普通 warning。

旧代码中的 WAITING_MODEL 应兼容映射为：

~~~text
Readiness = WAITING_RUNTIME
reason_code = MODEL_OFFLINE / TTS_OFFLINE / H3_OFFLINE / ...
~~~

### 4.5 Fingerprint

每个阶段输入和输出都需要保存 fingerprint，可理解为“数据版本编号”。

上游 fingerprint 改变时：

1. 下游旧结果保留；
2. 旧结果标记为 STALE 或 SUPERSEDED；
3. 清除当前结果指针；
4. 页面显示影响范围；
5. 等待用户明确点击重新计算。

---

## 5. 每阶段详细逻辑

## S0：项目与剧集配置

页面位置：Project。

### 输入

- 项目名称；
- 源语言；
- 目标语言；
- 目标地区；
- 场景策略 AUTO / KEEP / LOCALIZE；
- Episode 视频文件；
- Episode 名称、顺序；
- 用户保存的项目规则版本。

### 系统获取

- 文件是否存在；
- 视频流、音频流；
- 时长、分辨率、帧率；
- FFprobe/解码结果；
- 源媒体 fingerprint。

### 处理逻辑

1. 保存项目规则；
2. 验证 Episode 视频；
3. 记录源媒体版本；
4. 计算配置变化影响；
5. 不自动启动后续任务。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| ProjectSpec | 决定目标语言、地区和场景策略 |
| EpisodeSource | 决定处理范围和最终拼接顺序 |
| Media fingerprint | 判断原片是否变化 |
| Project rule revision | 判断目标设计是否需要重算 |

### 完成条件

- 至少存在一个有效 Episode；
- 目标语言和地区已配置；
- 视频可以读取和解码；
- 项目规则已保存。

### 页面交互

- “保存规则”只保存；
- “开始自动准备”才创建准备任务；
- 修改已参与下游生成的规则时，先展示影响范围；
- 保存后只标记“需要重算”，不自动执行。

---

## S1：原片理解

页面位置：Project 的“原片理解”卡片。

### 输入

- 当前 EpisodeSource；
- 当前源媒体 fingerprint；
- 当前 ShotRevision；
- 原片音视频。

### 系统获取

- Source PTS；
- Shot 边界；
- Reference Clip；
- ASR 原始对白；
- OCR 字幕和画面文字；
- Qwen3-VL 人物、动作、场景和镜头分析；
- 语义场景；
- 场景内临时人物和人物轨迹。

### 处理逻辑

1. 视频预处理和准确时间基准；
2. Shot 检测；
3. 生成 Reference Clip；
4. ASR、OCR、视觉分析可并行执行；
5. Fusion 整合证据，但不修改原始 ASR/OCR；
6. 形成 Scene Timeline；
7. 为每条完整对白建立稳定 dialogue_group_id；
8. 将完整对白投影到相关 Shot。

### 对白数据契约

当前项目已验证的关系是：

~~~text
54 条完整 ASR 对白
→ 76 个跨 Shot 对白投影
~~~

54/76 是当前项目实例，不是系统固定数量。通用契约始终是 N 条完整对白可以形成 M 个 Shot 投影。

每条完整对白只保存一次完整文本、开始时间和结束时间。

每个 Shot 投影保存：

- utterance_id / dialogue_group_id；
- scene_id；
- shot_id；
- projection_index / projection_count；
- Shot 内开始、结束时间；
- 完整对白内部裁切偏移；
- continues_from_previous；
- continues_to_next。

不得把 76 个投影转换成 76 条独立业务对白。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| Shot / Reference Clip | H3 动作、构图、镜头参考 |
| Source utterance | 翻译、目标对白和 TTS |
| Dialogue projection | 时间轴、音频裁切、字幕显示 |
| Scene Timeline | 场景资产和本土化决策 |
| Person track | 正式角色绑定和口型身份证据 |
| Action/camera facts | H3 Context 和语义 QC |

### 完成条件

- ShotRevision 当前；
- Shot 边界合法；
- Reference Clip 可解码；
- 原始识别结果带来源和版本；
- 每条对白有稳定分组；
- 跨 Shot 投影仍指向同一完整对白；
- 不包含目标人物、目标台词等下游数据。

### 异常处理

- Shot 边界确实不确定：创建 SHOT_BOUNDARY Case；
- Qwen/ASR/OCR 服务离线：WAITING_RUNTIME；
- 模型输出格式错误：有限次数自动重试；
- 基础视频或 FFmpeg 损坏：技术失败或操作员处理，不伪装成人工内容问题。

---

## S2：源事实定稿

页面位置：Project 显示摘要，问题进入 Review Center。

### 输入

- S1 证据；
- Character V10.1 人物轨迹；
- Final Character；
- Final Scene；
- Final Prop；
- Shot 资产绑定；
- 对白说话人证据。

### 处理逻辑

1. 将场景内临时人物映射到正式角色；
2. 保持 Character V10.1 fail-closed；
3. 绑定 Shot 与正式人物、场景、道具；
4. 以完整 dialogue_group_id 为单位确定说话人；
5. 编译 SourceDramaSnapshot；
6. 运行只读 Validator；
7. 只为根因同步 Review Case。

### SourceDramaSnapshot 必须保存

- Episode、Scene、Shot；
- Reference Clip；
- 完整 ASR 对白；
- dialogue_group_id；
- Shot 投影；
- 场景内人物；
- Final Character 绑定；
- 说话人；
- 动作、镜头、场景事实；
- 数据来源、revision 和 fingerprint。

下游不得绕过 SourceDramaSnapshot 读取零散的 ASR、OCR、Fusion 临时结果。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| Person → Final Character mapping | TargetCharacter、目标说话人、身份 QC |
| Shot asset binding | H3 人物、场景、道具条件 |
| Dialogue speaker binding | TargetDialogue 和 TTS Voice |
| SourceDramaSnapshot | S3—S8 唯一源事实输入 |

### 完成条件

- 每个重要或说话人物已绑定正式角色，或明确为背景/画外/非角色；
- 同一完整对白的多个投影不能有不同说话人；
- 场景和 Shot 资产关系有效；
- Snapshot 当前；
- 没有阻塞性 S2 Review Case。

### 人工问题

一个人物影响很多 Shot 和对白时，只创建一个人物根 Case。

示例：

~~~text
确认“走廊中的女性”对应哪个正式角色
涉及 18 个 Shot
影响 63 个对白投影
~~~

人工可选择：

- 绑定现有正式角色；
- 新建正式角色；
- 标记为背景人物；
- 标记为画外人物；
- 暂时无法确认。

决定必须写入正式业务对象，再由 Validator 确认问题已经消失。

---

## S3：目标人物与目标场景

页面位置：Project 的“目标人物与场景”卡片。

### 输入

- 当前 SourceDramaSnapshot；
- 目标语言和地区；
- 正式源人物；
- 正式源场景；
- 项目场景策略。

### 处理逻辑

1. 每个必需 Final Character 建立唯一 TargetCharacter；
2. 设置本土化姓名、年龄范围、外观和服装规范；
3. 准备目标人物参考；
4. 为每个目标人物建立 TargetVoiceProfile；
5. 每个场景明确 KEEP / LOCALIZE；
6. LOCALIZE 场景建立目标描述和参考；
7. AUTO 最终也必须落成明确决定。

角色必须替换。KEEP 只表示场景可以保留，不表示保留源人物身份。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| TargetCharacter | 目标对白、H3 人物条件、口型身份 |
| TargetVoiceProfile | TTS 和最终目标声音 |
| SceneLocalizationMapping | H3 场景条件和 QC |
| 目标人物/场景参考 | H3 Context 和语义 QC |

### 完成条件

- 每个必需正式人物都有唯一当前 TargetCharacter；
- 每个目标人物都有声音方案；
- 每个场景都有明确策略；
- 结果对应当前 SourceDramaSnapshot fingerprint。

### 人工问题

- 目标人物创作冲突：TARGET_CHARACTER；
- 场景策略不确定：SCENE_LOCALIZATION；
- 上游人物未绑定时，下游只显示“被上游阻塞”，不重复创建目标人物 Case。

---

## S4：目标对白与目标语音

页面位置：Project 的“对白与生成准备”卡片。

### 输入

- SourceDramaSnapshot 中的完整对白组；
- Shot 投影；
- 源说话人；
- TargetCharacter；
- TargetVoiceProfile；
- 目标语言和地区；
- 场景上下文。

### 处理逻辑

每个 dialogue_group_id 只生成一条 TargetDialogue：

~~~text
完整源对白
→ 翻译
→ 本土化润色
→ 最终目标台词
→ 目标人物
→ Voice
→ TTS
→ FFprobe 读取真实语音时长
→ 关联原有 Shot 投影
~~~

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| TargetDialogue revision | 字幕、修改历史和人工审核 |
| Target speaker | TTS、H3、口型 |
| SpeechAsset | H3 音频条件和最终音轨 |
| Real speech duration | RemakeTimeline |
| Projection links | 跨 Shot 音频和字幕定位 |

### 完成条件

- 每个完整对白组只有一条当前 TargetDialogue；
- 每条对白有目标人物或明确画外音策略；
- 每条需要发声的对白有 Voice；
- TTS 文件可读取；
- 真实语音时长已保存；
- 所有 Shot 投影关系完整。

### 异常处理

- 源人物未绑定：回到 S2 根问题；
- 台词真正存在多种含义：建立一条 LOCALIZATION Case；
- TTS 离线：WAITING_RUNTIME；
- TTS 临时失败：有限自动重试；
- 不把受同一人物影响的 63 个投影变成 63 个翻译待办。

---

## S5：重拍时间轴与生成计划

页面位置：Project 的“生成准备”区域。

### 输入

- 源 Shot 时间；
- 源动作和镜头事实；
- 目标语音真实时长；
- Shot 对白投影；
- 反应镜和无对白区间；
- 目标人物和场景参考。

### 处理逻辑

1. 比较源对白时长和目标语音时长；
2. 为目标对白选择安全时间策略；
3. 生成 RemakeTimeline；
4. 生成 TargetDialoguePlacement；
5. 按 4—15 秒规则生成 GenerationSegment；
6. 保存跨 Segment 音频偏移；
7. 计算预计生成段数、时长和资源消耗。

允许的时间策略：

| 策略 | 含义 |
|---|---|
| KEEP | 保持当前节奏 |
| TRIM | 安全缩短空白 |
| CARRY_OVER_REACTION | 让对白延续到反应镜 |
| EXTEND | 延长镜头 |
| HUMAN_REVIEW | 需要人工选择 |

### GenerationSegment 规则

- Shot 不等于 GenerationSegment；
- 目标时长小于 4 秒：H3 至少生成 4 秒，再精确裁切；
- 目标时长大于 15 秒：拆成多个 GenerationSegment；
- 跨 Segment 对白必须从正确音频偏移继续，不能每段从句首播放。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| RemakeTimeline | H3 时长、后期、字幕、拼接 |
| TargetDialoguePlacement | 目标音频裁切和位置 |
| GenerationSegment | H3 最小执行单元 |
| Segment audio offsets | 防止跨段对白重复 |
| Generation estimate | Output 启动前 Preflight |

### 完成条件

- 所有需要发声的目标音频已准备；
- 时间轴有序且无非法重叠；
- 所有目标 Shot 都被当前 GenerationSegment 覆盖；
- 跨段音频偏移正确；
- 没有待处理 DIALOGUE_TIMING Case。

### 页面交互

准备完成后 Project 只显示：

~~~text
30 个 Shot
预计 N 个生成段
预计总生成时长
[去成片页开始 H3 重拍]
~~~

该按钮只切换页面，不启动 H3。

---

## S6：H3 重拍、QC 与选版

页面位置：Output。

### 启动方式

只有用户点击“开始 H3 重拍”才允许创建任务。

点击后显示 Preflight：

- Episode 范围；
- Shot 和 GenerationSegment 数量；
- MiniMax H3 状态；
- Qwen3-VL QC 状态；
- 可复用的已完成结果；
- 预计资源消耗。

### 处理逻辑

每个 GenerationSegment：

1. 准备目标人物参考；
2. 准备目标场景参考；
3. 将源 Reference Clip 转为无源音频视觉参考；
4. 使用目标 TTS 作为独立音频条件；
5. 编译 H3 Context；
6. 创建 GenerationAttempt；
7. 下载输出；
8. FFprobe、完整解码和时长检查；
9. Qwen3-VL 语义 QC；
10. 未通过时更换 seed，并加入具体纠正提示；
11. 默认最多自动尝试 3 次；
12. 通过后创建 GenerationSelection。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| H3 Context | 可复现生成输入 |
| GenerationAttempt | 每次生成版本历史 |
| GenerationQualityCheck | 结构和语义证据 |
| GenerationSelection | 当前可用版本指针 |
| Selected Output | S7 唯一视频输入 |

### 异常处理

- H3 服务离线：WAITING_RUNTIME；
- Qwen3-VL QC 离线：WAITING_RUNTIME；
- 连续语义失败：H3_QC Case；
- 硬解码或时长失败不能人工绕过；
- 人工只能选择结构有效版本；
- FL2VA 连续性读取前一个 Selected Output，不读取最近一次普通 SUCCEEDED Attempt。

### 页面交互

- 页面加载、刷新、重新打开都不能启动任务；
- 运行中不显示第二个“开始”按钮；
- 已完成的 Segment 不重做；
- 失败后显示从哪个检查点继续；
- 重试必须显式点击并且服务端幂等；
- QC 冲突进入 Review Center。

---

## S7：口型、目标音轨、字幕与后期

页面位置：Output。

### 输入

- 当前 GenerationSelection；
- TargetDialogue SpeechAsset；
- RemakeTimeline；
- 目标说话人；
- 可选安全背景音；
- 字幕数据。

### 处理逻辑

1. 只读取 Selected Output；
2. 根据目标时间轴裁切正确的目标对白音频；
3. 画外对白保留目标音频，但跳过口型；
4. 单一可见目标说话人：整段 LatentSync；
5. 多脸：先做目标身份定位，再对目标人物 ROI 做 LatentSync；
6. 生成目标时间轴字幕；
7. 可选执行安全背景音增强；
8. 标准化所有分段媒体。

### 背景音安全规则

~~~text
源 Shot 音频
→ 独立 Worker 分离背景 / Instrumental
→ 按 SourceDramaSnapshot 对白窗口再次硬抑制
→ 映射到目标时间
→ 保守增益 对白 duck limiter
→ 与目标对白混合
~~~

禁止直接混入原片原始音频。

背景音 Worker 不可用时，使用目标对白-only安全输出。该结果仍然有效，不创建人工 Case，也不阻塞 EpisodeOutput。

### 产出及用途

| 数据 | 后续用途 |
|---|---|
| PostProductionSegment | S8 拼接输入 |
| 目标音轨 | 最终视频音频 |
| Lip-sync result | 最终人物口型 |
| UTF-8 subtitle items | SRT 和视频字幕 |
| Background mode | 交付说明和质量追踪 |

### 异常处理

- 多脸目标身份不确定：LIP_SYNC_QC；
- LatentSync 离线：WAITING_RUNTIME；
- 身份模型离线：WAITING_RUNTIME；
- 背景音处理失败：TARGET_DIALOGUE_ONLY_FALLBACK；
- PROCESSING、FAILED 或 STALE 的 PostProductionSegment 不能进入 S8。

---

## S8：整集组装与人工验收

页面位置：Output 顶部。

### 输入

- 当前且 SUCCEEDED 的 PostProductionSegment；
- RemakeTimeline；
- 完整目标对白；
- 字幕项目；
- Episode 顺序。

### 处理逻辑

1. 只组装当前成功的后期分段；
2. 按目标时间轴排序；
3. 标准化并拼接视频和音频；
4. 每条完整对白只生成一条字幕；
5. 输出 UTF-8 SRT；
6. 执行 FFprobe、完整解码、时长和音轨检查；
7. 生成不可变 EpisodeOutput 版本；
8. 机器状态只到 READY_FOR_MANUAL_ACCEPTANCE；
9. 用户观看、试听后接受或驳回。

### 产出

- EpisodeOutput；
- MP4；
- SRT；
- QC 摘要；
- checksum；
- 版本号；
- 人工验收记录。

### 驳回路由

| 驳回原因 | 返回阶段 |
|---|---|
| 台词内容 | S4 |
| 语速、停顿、节奏 | S5 |
| 人物、场景、动作、镜头画面 | S6 |
| 口型、音轨、字幕 | S7 |

不允许用通用“忽略问题”绕过硬质量门槛。

上游变化后，旧 EpisodeOutput 保留为历史版本，但不再是当前交付版本。

---

## 6. 页面总体设计

## 6.1 全局骨架

~~~text
┌──────────────────────────────────────────────────────────────────┐
│ ← 项目列表  项目名  中文→英语·美国  [需要人工确认] [任务0] [刷新] │
│ 最后更新 15:42:18                                                │
├──────────────┬───────────────────────────────────────────────────┤
│ 项目         │ 当前唯一下一步                                    │
│ 待确认   3   │ 系统无法把3个出场人物绑定到正式角色               │
│ 成片         │ 影响目标人物、对白和声音              [去待确认]  │
│              ├───────────────────────────────────────────────────┤
│              │ 当前页面内容                                      │
└──────────────┴───────────────────────────────────────────────────┘
~~~

Header 必须分开显示：

- 当前项目；
- 项目整体状态；
- 待确认数量；
- 后台任务数量；
- 最后更新时间。

所有页面消费同一个带 revision 的 Workflow Snapshot。

## 6.2 NextActionBanner

每个页面顶部共享同一个“当前下一步”组件。

内容包括：

- 标题；
- 简短原因；
- 影响范围；
- 一个 Primary Action；
- 最多一个 Secondary Action。

页面不得同时出现多个互相竞争的主按钮。

示例：

~~~text
需要确认3个出场人物
这些人物影响63个Shot对白投影。
先确认人物后，目标人物、对白和声音才能重新计算。
[去待确认] [查看影响范围]
~~~

---

## 7. Project 页面设计

### 7.1 页面层级

~~~text
Project
├─ 当前下一步
├─ 项目与本土化规则
├─ Episode 管理
├─ 自动准备概览
│  ├─ 原片理解
│  ├─ 目标人物与场景
│  └─ 对白与生成准备
└─ 高级维护信息 默认折叠
~~~

### 7.2 业务指标

原片理解卡：

~~~text
Episode       1/1
Shot          30
语义场景      2
完整对白      54
对白投影      76
未绑定人物    3
~~~

目标人物与场景卡：

~~~text
目标人物      1/3
场景决策      1/2
声音配置      0/3
~~~

对白与生成准备卡：

~~~text
目标对白      需按54条完整对白重算
目标语音      0/54
时间轴        需要重算
生成计划      尚未形成当前版本
~~~

主页面不直接展示 ASR、OCR、VLM、LocalSubject 等内部名称；这些只进入高级诊断。

### 7.3 主按钮

| 状态 | 主按钮 | 行为 |
|---|---|---|
| 没有 Episode | 导入原片 | 打开导入界面 |
| 未准备 | 开始自动准备 | 显式 POST |
| 准备运行中 | 查看后台任务 | 打开任务抽屉 |
| 有人工问题 | 去待确认 | 只切换路由 |
| 等待模型服务 | 检查本地服务 | GET Runtime |
| 数据过期 | 重新自动准备 | 影响确认后 POST |
| 技术失败 | 重试自动准备 | 显示检查点后 POST |
| 准备完成 | 去成片页 | 只切换路由 |

---

## 8. Review Center 页面设计

### 8.1 页面层级

~~~text
Review Center
├─ 待确认摘要
├─ 分类与筛选
├─ Review Workspace
│  ├─ 左：人工任务队列
│  ├─ 中：证据和上下文
│  └─ 右：正式决定编辑器
├─ 全部完成后的验证卡
└─ 已处理历史 默认折叠
~~~

### 8.2 统计方式

显示用户需要做的决定数，不显示底层证据行数：

~~~text
需要决定       3
阻塞后续       3
影响 Shot      18
影响对白投影   63
~~~

### 8.3 队列分组

~~~text
原片事实
  人物身份与绑定   3
  场景绑定         可能需要重新验证
  说话人           被人物绑定阻塞

目标创作
  目标人物         被上游阻塞
  场景本土化       被上游阻塞
  对白与时长       被上游阻塞

生成结果
  H3画面质量       尚未开始
  口型目标         尚未开始
~~~

被上游阻塞的项目不进入当前人工队列。

### 8.4 人物 Case 证据

- 人物 Crop；
- 所在 Shot 视频；
- 前后镜头；
- 已有 Final Character 候选；
- 系统无法确定的原因；
- 影响 Shot 和对白数量；
- 技术 ID 默认折叠。

### 8.5 正式决定编辑器

| Case 类型 | 正式决定 |
|---|---|
| 人物绑定 | 绑定现有角色 / 新建角色 / 背景或非角色 |
| 说话人 | 正式角色 / 画外音 / 暂时无法确认 |
| 目标人物 | 姓名、外观、参考、声音 |
| 场景 | KEEP / LOCALIZE 和目标描述 |
| 对白 | 最终目标台词 |
| Timing | 延长、跨反应镜、拆分等 |
| H3 QC | 选择有效版本 / 带意见重试 |
| Lip Sync | 选择目标说话人轨迹 |

按钮：

- 仅保存；
- 保存并下一项；
- 稍后处理。

禁止通用“标记已处理”。

### 8.6 全部处理完成

~~~text
已完成3个人物绑定
预计可重新计算63个对白投影。
尚未启动后台任务。
[验证依赖并继续准备]
~~~

只有这个明确按钮才创建 continuation 任务。

---

## 9. Output 页面设计

### 9.1 页面层级

~~~text
Output
├─ Episode 选择
├─ 结果或当前下一步
├─ 最终播放器和下载 结果存在时优先
├─ 镜头重拍与质检
├─ 口型 音轨 字幕 后期
├─ Episode 列表
├─ 版本与交付信息
└─ 高级诊断 默认折叠
~~~

Output 不重复展示完整的原片理解阶段条。准备未完成时，只显示当前前置条件。

### 9.2 准备未完成

~~~text
第01集尚未具备镜头重拍条件

人物绑定      需要确认
目标人物      1/3
目标语音      0/54
时间轴        需要重算
生成计划      需要重算

[去待确认]
~~~

页面加载不得 POST。

### 9.3 可以开始 H3

~~~text
已准备30个Shot，预计形成N个生成段
人物、场景、目标对白、声音和时间轴已通过准备Gate。
[开始 H3 重拍]
~~~

点击后先打开 Preflight，确认后才 POST。

### 9.4 H3 运行中

~~~text
正在重拍第12/30个Shot
已选用8个版本
2个正在自动质检
[查看任务详情]
~~~

不显示第二个启动按钮。

### 9.5 可以开始后期

~~~text
30/30个生成段已有当前Selected Output
[开始口型与整集后期]
~~~

Preflight 说明：

- LatentSync 是否必需和可用；
- FFmpeg 是否可用；
- Background Audio Worker 是可选项；
- Worker 离线时将输出目标对白-only版本。

### 9.6 成片完成

~~~text
第01集 当前交付版本 V1
[播放器]

人物一致性    通过
H3质检        通过
目标音轨      完成
字幕          完成
背景音        对白-only安全降级

[下载MP4] [下载SRT] [接受] [驳回]
~~~

### 9.7 多 Episode

每集独立显示：

- 当前业务状态；
- 当前有效版本；
- 已完成 Shot / 总 Shot；
- 阻塞原因；
- 人工任务数量；
- 当前可执行动作。

一集完成不能让整个项目显示完成。

没有依赖冲突的 Episode 或实体可以继续并行处理；但只有全部必需项都通过时，Project 级阶段才显示 READY。

---

## 10. 任务中心

任务中心位于 Header 右侧抽屉，不占据主页面底部空间。

### 10.1 结构

~~~text
任务中心
├─ 当前运行
├─ 需要注意
├─ 最近完成
└─ 技术详情
~~~

### 10.2 任务卡

~~~text
自动准备目标对白
第01集
正在处理完整对白 18/54
最近心跳 6 秒前
[查看对应页面] [展开详情]
~~~

只有进度可准确计算时才显示百分比。

单次模型调用显示“正在等待本地模型返回”，不能显示硬编码假进度。

### 10.3 用户状态

| 内部状态 | 用户显示 |
|---|---|
| QUEUED | 等待开始 |
| PROCESSING | 处理中 |
| RETRYING | 自动重试 2/3 |
| NEEDS_REVIEW | 已暂停，需要人工确认 |
| WAITING_RUNTIME | 等待本地服务 |
| FAILED | 未完成 |
| CANCELLED | 已取消 |
| COMPLETE | 已完成 |
| COMPLETE_NOTICE | 已完成，有非阻塞提示 |

### 10.4 任务行为

- “查看对应页面”只按后端 target_surface 跳转；
- “重试”只在后端明确允许时显示；
- 重试展示检查点和复用范围；
- “取消”只在任务支持取消时显示；
- “隐藏通知”不得修改 Task、Review Case 或业务数据；
- Stall 由服务端 heartbeat 和任务类型判断，浏览器不能固定用两分钟推断。

---

## 11. 页面交互硬规则

| 事件 | 允许行为 | 禁止行为 |
|---|---|---|
| 打开 Project/Review/Output | GET Snapshot | POST、重算、关闭 Case |
| 切换页面 | 更新路由、GET | 启动任务 |
| 点击刷新 | GET 最新状态 | 写业务数据 |
| 创建任务 | 更新 Store、提示用户 | 自动跳页 |
| 任务完成 | 刷新 Snapshot、通知 | 自动开始下一任务 |
| 保存人工决定 | 写正式业务对象 | 只改提醒状态 |
| 最后一项确认完成 | 显示验证摘要 | 自动消耗 GPU |
| 点击验证并继续 | POST continuation | 重做已通过上游 |
| Runtime 恢复 | 显示可以重试 | 未经点击自动运行 |
| 上游变化 | 下游标记 STALE | 使用旧结果继续 |
| 浏览器重新打开 | 恢复当前 Snapshot | 再创建 AUTO_OUTPUT |

### 11.1 Loading

- 初次加载使用 skeleton；
- 后续刷新保留旧 Snapshot；
- 只让触发动作的按钮进入 pending；
- 禁止整页闪空。

### 11.2 GET 失败

~~~text
状态刷新失败
当前展示15:42:18的最近结果。
[重新刷新]
~~~

不得把读取失败转成“等待生成”。

### 11.3 并发编辑

所有修改携带 revision。

如果人工编辑期间上游数据变化：

~~~text
这项确认所依据的镜头或人物数据已经更新。
请刷新证据后重新确认。
~~~

保存按钮禁用，但保留用户尚未提交的输入。

---

## 12. 后端读取与命令契约

### 12.1 只读接口

~~~text
GET /api/projects/{project_id}/flow-state
GET /api/projects/{project_id}/review-cases
GET /api/projects/{project_id}/runtime-status
GET /api/projects/{project_id}/outputs
~~~

GET 必须：

- 无业务写入；
- 无任务创建；
- 无 Review Case 自动关闭；
- 过期数据返回结构化 STALE，而不是用 409 代替业务状态。

### 12.2 明确命令

推荐 V2 语义：

~~~text
POST /api/projects/{project_id}/commands/prepare-remake
POST /api/projects/{project_id}/commands/h3-generate-ready
POST /api/projects/{project_id}/commands/postproduction
~~~

也可以保留现有 tasks URL，但必须满足相同语义：只有明确用户动作才调用。

每个命令携带：

- Idempotency-Key；
- expected workflow revision；
- input fingerprint；
- Episode 或处理范围；
- 用户动作来源。

### 12.3 Task Receipt

每个任务返回并持久化：

- task_id；
- task_type；
- input fingerprint；
- execution 状态；
- checkpoint；
- current / total；
- heartbeat；
- retry_count / max_retries；
- cancellable；
- target_surface；
- last_error；
- started_at / updated_at / finished_at，且时间必须带时区。

---

## 13. Workflow Snapshot

所有页面只消费同一个 ProjectFlowState。

核心字段：

~~~text
project_id
revision
generated_at
overall_status
next_action
can_continue
active_command
review_summary
runtime_summary
episodes[]
stages[]
~~~

每个 stage 至少包含：

~~~text
stage_key
validity
readiness
execution
consumable
reason_code
reason
current_input_fingerprint
built_input_fingerprint
metrics
open_review_cases
active_command
warnings
last_success
~~~

页面不得根据 Episode 是否存在、Task 是否成功或阶段序号自行推断完成状态。

---

## 14. Review Case 数据设计

Review Case 表示“用户需要做的一次决定”。

Review Issue 或 Evidence 表示支持该决定的具体证据。

### 14.1 Case 字段

- case_id；
- project_id；
- case_type；
- subject_type / subject_id；
- cause_fingerprint；
- reason；
- severity；
- OPEN / RESOLVING / RESOLVED / SUPERSEDED；
- blocking_stages；
- candidate_actions；
- affected_shot_count；
- affected_dialogue_projection_count；
- revision。

唯一性建议：

~~~text
project + case_type + subject + cause_fingerprint
~~~

### 14.2 同步规则

Review Case 只在以下时机同步：

1. 某阶段任务写入新结果后；
2. 用户保存正式业务决定后；
3. 上游 revision 改变后。

GET 页面时不得执行 Review 同步。

### 14.3 关闭规则

不能使用通用 PATCH resolved。

正确顺序：

~~~text
用户提交正式决定
→ 写入正式业务对象
→ 运行阶段Validator
→ 阻塞条件消失
→ Review Case变为RESOLVED
~~~

---

## 15. 数据失效矩阵

| 上游变化 | 下游失效范围 |
|---|---|
| 替换原视频 | S1—S8 |
| 修改 Shot 或原片理解 | S2—S8 |
| 修改人物、场景、说话人绑定 | S3—S8 |
| 修改目标地区或场景策略 | S3—S8 |
| 修改目标人物、声音、目标场景 | S4—S8 |
| 修改目标台词或 TTS | S5—S8 |
| 修改 RemakeTimeline 或 GenerationSegment | S6—S8 |
| 修改 GenerationSelection | S7—S8 |
| 修改 PostProductionSegment | S8 |

旧版本不删除，只标记 STALE 或 SUPERSEDED，并清除 current pointer。

---

## 16. 当前项目迁移后的正确页面状态

### 16.1 Overall

~~~text
整体状态：需要人工确认
当前下一步：确认3个尚未安全绑定的场景人物
~~~

### 16.2 Source

~~~text
Episode             1
Shot                30
语义场景            2
完整对白            54
Shot对白投影        76
场景内人物          4
可靠正式角色映射    1
~~~

现有 3 个 Final Character 资产不代表其余场景人物已经完成绑定。

场景是否需要新增人工 Case，应由新的 Scene Validator 根据真实语义和绑定证据判断，不能只因为数量不同就直接创建。

### 16.3 Target

~~~text
现有目标人物        1
目标人物方案        未完成
场景映射            需要重新验证
声音配置            0
~~~

### 16.4 Dialogue

旧结构当前有：

~~~text
76 条 TargetDialogue 行
13 READY
63 REVIEW
~~~

这些旧行不能直接作为 V2 的 54 条完整目标对白继续使用。应先按 dialogue_group_id 归并，再判断哪些人工决定可以安全迁移。

### 16.5 Generation

~~~text
目标语音            0
RemakeTimeline      STALE
GenerationSegment   STALE
H3                  被准备数据阻塞
Postproduction      被Selected Output阻塞
EpisodeOutput       无当前有效版本
~~~

Output 页面不应显示“H3等待中”，因为当前尚未到达 H3 Runtime Gate。

---

## 17. 实施顺序

## P0：先停止错误行为

- 页面 mount 不再 POST；
- refresh 不再 POST；
- task finished 不再重新挂载并启动；
- Review GET 不得写数据库；
- 所有任务增加幂等保护；
- STALE 数据不得计入当前完成率；
- 先停止当前可能存在的循环任务。

## P1：建立 V2 数据契约

- SourceDialogueUtterance；
- ShotDialogueProjection；
- Person → Final Character Mapping；
- SourceDramaSnapshot V2；
- ReviewCase；
- ProjectFlowState；
- 各阶段 input/output fingerprint。

## P2：实现每阶段 Validator

Validator 只返回：

- 输入是否当前；
- 输出是否完整；
- blocking errors；
- review candidates；
- runtime requirements；
- metrics；
- warnings；
- next action。

Validator 不创建任务，不修改业务对象。

## P3：重做任务编排

- 显式命令；
- Idempotency-Key；
- checkpoint；
- heartbeat；
- 中断恢复；
- 有限自动重试；
- 已成功结果复用；
- 页面无关的后台执行。

## P4：重做前端

1. 全局 Workflow Store 和 Header；
2. NextActionBanner；
3. Project；
4. Review Center；
5. Output；
6. 右侧任务中心；
7. 删除前端阶段推断和自动启动代码。

## P5：迁移当前项目

1. 备份 SQLite/sidecar；
2. 停止循环任务；
3. 使用正式 migration runner 建立 V2 表；
4. dry-run 验证 54 条完整对白和 76 个投影；
5. 只迁移仍然一致的人工决定；
6. 旧 TargetDialogue、Timeline、Segment、Output 标记为历史；
7. 影子计算 V2 状态并与旧页面比较；
8. 按项目切换到 V2；
9. 进行真实本地端到端验收。

---

## 18. 验收标准

必须分别记录三种事实：

1. 代码和数据契约是否实现；
2. 本地模型与 Worker 是否真实可用；
3. 当前真实项目是否经过观看、试听和人工验收。

不能用“代码已实现”代替本机真实模型和真实项目验收。

- [ ] 打开、刷新、切换任一页面时没有 POST；
- [ ] 一次按钮点击至多创建一个任务；
- [ ] 任务完成和组件重新挂载不会创建下一轮任务；
- [ ] Review GET 不产生数据库写入；
- [ ] 54 条完整对白、76 个 Shot 投影关系保持不变；
- [ ] 3 个人物根问题不扩散成 63 条对白人工任务；
- [ ] LocalSubject 不被直接当成 Final Character；
- [ ] Character V10.1 身份阈值没有降低；
- [ ] 0 个 Review Case 不等于“可以生成成片”；
- [ ] STALE 数据不计入当前完成率；
- [ ] TTS/H3/Qwen/LatentSync 离线不创建人工内容问题；
- [ ] 每阶段独立判断，不根据阶段序号打勾；
- [ ] 同一个 Snapshot revision 驱动 Header、Project、Review、Output 和任务中心；
- [ ] 只有 Selected Output 能进入后期；
- [ ] H3 硬解码失败不能人工绕过；
- [ ] 多脸口型先通过目标身份门槛；
- [ ] 原片原始音频不会直接混入目标成片；
- [ ] 背景音 Worker 失败时安全降级且不阻塞交付；
- [ ] 任务中断后可以从检查点恢复；
- [ ] 最终完成一次真实本地 H3→QC→Selection→Postproduction→EpisodeOutput；
- [ ] 用户实际观看、试听并完成成片验收。

---

## 19. 后续讨论与修改区

以下内容需要在进入实现前逐项确认：

- [ ] Workflow V2 是直接替换旧接口，还是先按项目 feature flag 影子运行；
- [ ] SourceDialogueUtterance 是否新建表，还是从现有 ASR 表建立稳定只读映射；
- [ ] ReviewCase 与现有 v2_review_issues 的迁移关系；
- [ ] ProjectFlowState 是实时计算、物化快照，还是两者结合；
- [ ] 是否保留现有 tasks URL，只升级任务语义；
- [ ] 多 Episode 项目的默认执行范围；
- [ ] TargetCharacter 的“必需人物”判断规则；
- [ ] Scene AUTO 最终决策由哪个 Validator 固化；
- [ ] H3 Preflight 是否展示预计耗时，还是只展示段数和 Runtime；
- [ ] 人工验收是 Episode 级还是 Project 级；
- [ ] 旧版本历史在普通 UI 中保留多久；
- [ ] V2 首个迁移项目是否固定使用当前测试项目。

### 修改记录

| 日期 | 修改人 | 修改内容 | 决策状态 |
|---|---|---|---|
| 2026-09-02 | Codex | 根据代码、数据与页面审核导出 Workflow V2 初稿 | 待用户修改 |
