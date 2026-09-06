# AI Drama Studio — AI 软件开发技能手册

> 本手册参考 `zdingwl/fullstack-coding-skills-web` 的技能体系，并按 AI Drama Studio 当前代码、技术栈、Workflow V2 和短剧重做业务规则重新编写。
>
> 它是**软件工程执行层**，不是新的业务规范。任何冲突都必须以当前项目正式文档和 `AGENTS.md / SKILL.md` 为准。

## 0. 指令优先级与读取顺序

### 0.1 指令优先级

1. 用户当前明确要求；
2. `docs/00_短剧重做系统开发总纲.md`；
3. `docs/01_十个模块详细设计.md`；
4. `docs/02_工作流V2技术实现规范.md`；
5. `docs/03_当前项目状态与验收.md`；
6. 与当前任务直接相关的正式文档，例如拉片 UI 读取 `docs/04_AI拉片模块业务方案与UI基线.md`；
7. `AGENTS.md` 与根目录 `SKILL.md`；
8. 本 `AI_SKILLS.md`；
9. 历史文档只作算法、兼容和回归参考。

### 0.2 任意代码任务启动顺序

```text
正式业务文档
→ AGENTS.md / SKILL.md
→ .agents/skills/repository-development/SKILL.md
→ 本文件技能路由
→ 当前相关源码 / 测试 / migration / API 调用方
→ 实施
→ 验证
→ main 交付
```

禁止只读技能手册、不读当前代码就直接改。

## 1. 当前仓库真实技术栈

### 后端

- Python；
- FastAPI；
- Pydantic；
- SQLAlchemy；
- Alembic；
- pytest；
- httpx。

### 前端

- Vue 3；
- TypeScript；
- Pinia；
- Vue Router；
- Vite；
- Vitest；
- vue-tsc。

### 视频 / AI / 本地模型链

- FFmpeg / ffprobe；
- TransNetV2 + PySceneDetect；
- faster-whisper；
- RapidOCR；
- Qwen3-VL；
- YOLOX / MOT / ReID / ONNX Runtime；
- Qwen3-TTS；
- 本地 MiniMax H3 + SGLang；
- LatentSync；
- audio-separator。

任何技能实施都必须尊重这些真实依赖和当前 Provider/Runtime 边界，不平行造第二套框架。

## 2. 技能路由表

| 当前任务 | 必须/建议技能 |
|---|---|
| 任意已有项目代码修改 | Repository Development、Codebase Analysis、Verification、Default Branch Delivery |
| 新业务功能 | Requirement Analysis、Implementation Planning、对应领域技能、TDD、Code Review |
| Workflow V2 / revision / fingerprint / 状态 / task | Architecture、Backend、Database、API、TDD、Verification |
| Bug / 页面不对 / 数据不对 | Systematic Debugging、相关领域技能、Regression Test |
| 前端 / UI / 交互 | Frontend Development、Webapp Testing |
| FastAPI / Service / Worker | Backend Development |
| SQLAlchemy / Alembic / SQLite 迁移 | Database Development |
| GET/POST/任务接口/契约 | API Development |
| 拉片 / 人物 / ASR / OCR / VLM / H3 / TTS / Lip Sync | Backend、Performance、Observability、Verification；涉及契约时补 Architecture/API |
| 重构旧 Vx 代码 | Refactoring、Codebase Analysis、Regression Test |
| 安全敏感 / 文件上传 / 路径 / 外部请求 | Security Review |
| 慢模型 / 慢拉片 / GPU/CPU/内存 | Performance Optimization |
| Python/npm/模型运行时依赖升级 | Dependency Upgrade |
| CI / Actions 失败 | CI/CD Debugging |
| 日志 / task 诊断 / 模型运行状态 | Observability Development |
| 数据迁移 / 真项目切换 / 发布 | Release Delivery |
| 跨前后端纵向功能 | Fullstack Development |

不要把全部技能机械执行一遍，只选择当前任务真正需要的技能。

## 3. 任务分级

- **S**：单文件或局部低风险，不改变数据/API/工作流契约。可短分析后直接修改并验证。
- **M**：多文件、单模块、行为变化。必须有简短实施计划和回归测试。
- **L**：跨前后端、数据库/API、任务状态、SourceDramaSnapshot、ReviewCase、FlowState。必须做影响分析、迁移/兼容和完整计划。
- **XL**：架构级、真实项目迁移、大规模数据契约变化、本地模型运行方式变化。必须先设计、风险、回滚和分阶段验收。

---

# Requirement Analysis｜需求分析

适用于新模块、业务规则复杂、状态多或用户描述与当前实现存在差异的任务。

1. 先回答功能属于 10 个业务模块中的哪一个。
2. 写清输入、自动处理、人工确认条件、正式输出、下游消费者、完成条件。
3. 区分“用户看到的结果”和“内部算法证据”。不要为了内部算法单独增加顶层页面。
4. 明确哪些对象是正式业务数据，哪些只是 Evidence / Attempt / Candidate / Projection。
5. 把模糊要求改写成可测试验收标准。
6. 新需求如果会破坏 SourceDramaSnapshot、完整对白 1:N 投影、人物身份门禁、GenerationSelection、GET 只读等硬规则，必须先指出冲突，不能静默实现。
7. 验收必须分层：代码实现、仓库测试、本地模型、真实项目、用户看听验收不能互相替代。

输出至少包括：目标、范围、非目标、业务规则、边界/异常、正式数据、验收标准、待确认事实。

---

# Codebase Analysis｜代码库分析

任何陌生区域或 M/L/XL 改动都强制执行。

1. 先读 `docs/00/01/02/03`、`AGENTS.md`、`SKILL.md`；拉片页面任务额外读 `docs/04_*`。
2. 识别真实入口：FastAPI route → service/domain → SQLAlchemy/model/repository → task/provider；Vue route/page → store/API → 后端接口。
3. 搜索 1–3 个相似现有实现，理解当前命名、状态、错误、测试方式。
4. 对旧 `v1/v4/v9/v10.1` 文件先判断它是 current、兼容层还是历史实现，不能仅凭版本号选择“最新”。
5. 追数据流：输入 → revision/fingerprint → 正式对象 → FlowState/Validator → 下游消费。
6. 追任务流：显式 POST → Task → Worker/Provider → Attempt/Result → Validator/Selection；确认页面 GET 不会触发写操作。
7. 修改公共函数、模型、schema、Provider 前搜索所有调用方和测试。
8. 列出直接改动点、间接依赖、数据迁移、前端投影、失效规则和回归范围。

禁止只凭文件名猜架构，禁止看到旧逻辑不顺眼就重写整条链。

---

# Architecture Design｜架构设计

跨模块、新数据边界、任务编排、模型 Provider、重大迁移时使用。

必须优先保持当前项目边界：

```text
源事实证据 → SourceDramaSnapshot → Target → Timeline/Segment → H3 → QC/Selection → Post → EpisodeOutput
```

设计时明确：

1. 数据拥有者和唯一事实入口；
2. Source 与 Target 绝不混写；
3. Shot 与 GenerationSegment 不混用；
4. Attempt 与 Selection 不混用；
5. Validity / Readiness / Execution 三维状态；
6. revision / fingerprint / stale 传播；
7. query 与 command 分离；GET 只读、重任务显式 POST；
8. 幂等、并发、checkpoint、heartbeat、retry、resume；
9. Runtime offline 与人工 Review 分离；
10. Provider/Runtime 边界，例如业务层不得直接调用 SGLang。

优先最小可行方案，不因“架构更漂亮”新增无必要服务、页面或状态源。

---

# Implementation Planning｜实施计划

M/L/XL 必须使用。

每个步骤至少写清：

- 目标；
- 具体文件/符号；
- 改什么；
- 依赖什么；
- 数据/API/状态影响；
- 自动测试；
- 真实项目或浏览器验证（需要时）。

优先按可验证纵向切片实施。例如 Workflow V2 功能应尽量按“模型/迁移 → service/validator → API → 前端消费 → 测试”形成闭环，而不是先批量重写所有后端再回头接 UI。

---

# Frontend Development｜前端开发

当前前端以 Vue 3 + TypeScript + Pinia 为基线。

1. 先找已有页面、组件、store、API 封装和状态展示模式。
2. Project / Review Center / Output / Header / Task Center 应消费统一 `ProjectFlowState`/Workflow Snapshot，不各自猜完成状态。
3. 页面 mount、refresh、Tab/Route 切换必须只读，不能隐式 POST、建 Task、启动模型或重算。
4. 重任务只能由明确用户动作触发，并展示 queued/processing/succeeded/failed 等真实状态。
5. 处理 loading、empty、error、blocked-review、blocked-dependency、waiting-runtime、stale 等真实业务状态。
6. 不用前端 `disabled` 代替服务端幂等/并发保护。
7. 不把 Detection/Track/LocalSubject 伪装成 Final Character，也不把旧 STALE 结果计入当前完成率。
8. 表单和枚举优先复用已有固定选项和校验，不制造第二套语义。
9. UI 修改尽量做真实浏览器验证，并检查 Console/Network 是否出现意外 POST 或错误请求。

---

# Backend Development｜后端开发

当前后端以 FastAPI + Pydantic + SQLAlchemy 为基线。

1. 从真实 route 追到 service/domain/repository/provider，不把业务规则散落到路由函数。
2. GET/read-model 必须只读：不写 DB、不建任务、不关 ReviewCase、不启动模型、不隐式重算。
3. 重任务通过显式 POST command/task 创建，并在服务端校验 Idempotency-Key、expected workflow revision、input fingerprint、processing scope（适用时）。
4. 业务状态转换放在可信服务端边界，不能依赖前端按钮状态。
5. 事务覆盖原子数据库操作；FFmpeg、VLM、H3、TTS、下载/模型调用等慢 I/O 不应长期占用数据库事务。
6. Worker 需要有限 retry、清晰 last_error；支持的任务逐步落实 checkpoint/heartbeat/resume。
7. 模型不可用使用 WAITING_RUNTIME/运行环境语义，不伪造成内容 Review。
8. H3 调用保持 `业务层 → VideoGenerationProvider → MiniMaxH3Provider → H3RuntimeManager → local SGLang`。
9. 下游只能消费 CURRENT + READY 的正式输出；`Execution=SUCCEEDED` 不能单独判业务完成。
10. 日志记录必要关联 ID，不输出 token、secret 或敏感路径内容。

---

# Database Development｜数据库开发

当前使用 SQLAlchemy + Alembic，并存在真实项目/SQLite 迁移需求。

1. 先读 model、migration、实际查询路径、唯一约束和测试 fixture。
2. 新字段/表明确 NULL/default、唯一性、外键、索引、历史数据兼容。
3. revision、fingerprint、current/stale/superseded 语义必须可持久化和追踪，不能只存在前端内存。
4. 源事实修订应形成新 revision，不静默覆盖冻结 ASR/OCR/Shot truth。
5. Source 与 Target 表/对象边界保持清晰；Target 修改不能回写 Source Character/Scene/Dialogue。
6. 完整对白保持 `SourceDialogueUtterance 1:N ShotDialogueProjection`，迁移不能把投影复制成独立业务对白。
7. Review 根问题去重需要数据库/服务端约束，而不是页面去重。
8. destructive migration 前必须备份或提供可执行回滚/不可逆说明。
9. 真实项目迁移先 dry-run、计数核对、fingerprint 校验，再切换 current 指针；旧结果保留历史但不能冒充 current。

---

# API Development｜接口开发

1. 先读现有 FastAPI route、Pydantic schema、错误模型和调用方。
2. Query/Command 分离：GET 只读；创建/修改/重任务用 POST/PATCH 等显式命令。
3. 任务接口明确 202/任务 ID/轮询读取模型；失败任务不能因相同 GET 自动重跑。
4. 写接口校验类型、范围、枚举、资源归属、expected revision、fingerprint 和幂等键（适用时）。
5. 明确 omitted/null/empty 的差异，避免 PATCH 误清空正式数据。
6. 修改已有 contract 前必须搜索 Vue 调用方、测试、worker 和其他 service。
7. 返回的 Workflow/Review 状态必须来自统一服务端计算，不把核心状态拼装责任交给前端。
8. API 成功仅代表命令/查询成功，不自动等价于业务阶段 CURRENT + READY。

---

# Test Driven Development｜测试驱动

核心循环：RED → GREEN → REFACTOR。

1. Bug 修复先写能复现原问题的最小回归测试（可测试时）。
2. 后端优先使用 `engine/tests/v2` 当前 pytest 基线，并补相邻模块测试。
3. 前端使用 Vitest，行为变化同时考虑 typecheck/build。
4. 测试业务行为，不只断言 mock 被调用几次。
5. Workflow 测试重点覆盖：GET 无写入、幂等重放、revision 冲突、stale 传播、根 Review 去重、CURRENT/READY 门禁。
6. AI Provider 单测可以 mock 外部/本地模型，但 mock 通过不能宣称真实模型通过。
7. 本地 H3/Qwen3-VL/TTS/LatentSync 等真实验收必须单独记录输入、模型、耗时、结果和未覆盖范围。

---

# Systematic Debugging｜系统化调试

**没找到根因，不随机修。**

1. 稳定复现，记录项目/episode/shot/task、输入版本、预期和实际结果。
2. 先判断问题属于：数据错误、STALE、BLOCKED_REVIEW、BLOCKED_DEPENDENCY、WAITING_RUNTIME、执行失败还是前端投影错误。
3. 收集 stack trace、日志、Network、SQL/DB 状态、revision/fingerprint、最近 commit。
4. 沿调用/数据链找“最后正确点”和“第一个错误点”。
5. 每次只验证一个可证伪假设。
6. 找到 root cause 后做最小修复，并跑原始复现 + 回归。
7. 不通过吞异常、删除断言、硬编码成功、任意 sleep、降低 Character/H3/Lip Sync 安全门槛来掩盖问题。
8. 页面显示错时先确认后端 read model 是否正确，不要先用前端条件分支遮住脏数据。

---

# Webapp Testing｜Web 应用测试

1. 在真实运行环境打开目标页面。
2. 检查首屏、loading、empty、error、stale、blocked、runtime 等状态。
3. 按真实用户路径操作：项目 → Review → Output，或任务对应的局部路径。
4. 特别验证刷新、重新进入路由、切 Tab 不会产生隐式 POST/Task。
5. 检查 Console、Network、失败请求、重复请求和状态竞态。
6. 修改 Review 操作时验证“写正式业务对象 → Validator → 阻塞消失 → Case RESOLVED”的完整链。
7. Bug 修复后必须重走原复现路径。
8. 没有真的打开页面，就不能写“浏览器验证通过”。

---

# Code Review｜代码审查

按风险从高到低审查：

1. **业务正确性**：10 模块边界、Source/Target、完整对白、人物身份、Shot/Segment、Attempt/Selection。
2. **Workflow**：Validity/Readiness/Execution、revision/fingerprint、stale、根问题 Review。
3. **副作用**：GET 是否写库/建任务/启动模型；任务是否会循环或重复启动。
4. **数据**：事务、迁移、旧数据、唯一性、并发、current 指针。
5. **AI 安全门禁**：Character V10.1、H3 QC、多人 Lip Sync 是否被绕过或降阈值。
6. **API**：兼容、错误语义、幂等、调用方。
7. **可靠性**：超时、retry、checkpoint、资源释放、Runtime offline。
8. **测试**：关键失败路径和真实用户路径是否覆盖。
9. **维护性**：是否新增平行架构、重复状态源、无必要新页面或大范围无关重构。

Finding 必须说明文件/符号、触发条件、影响和最小修复方向。

---

# Security Review｜安全审查

重点追踪：外部视频/文本/路径/请求 → 校验 → 文件系统/FFmpeg/模型/数据库/网络。

检查：

- 上传文件类型、大小、路径穿越、符号链接；
- FFmpeg/子进程参数是否可能命令注入；
- 外部 URL/Provider 是否可能 SSRF；
- API 资源归属/IDOR；
- SQL/template/XSS；
- secret、模型 token、路径和敏感日志泄露；
- 临时文件生命周期和可预测文件名；
- 不安全反序列化；
- CORS/CSRF（适用时）；
- 依赖与模型运行时风险。

没有证据不要夸大，但命中高风险路径必须明确阻断条件和修复。

---

# Refactoring｜重构

目标是改变结构，不改变外部可观察行为。

1. 先建立测试护栏和当前行为基线。
2. 对大量 `*_v1/_v4/_v10` 文件先确认 current/compat/history 角色，再决定是否合并。
3. 每次做小、可逆、可验证变化。
4. 不在“重构”里顺便改变 SourceDramaSnapshot、Review、FlowState、API 契约或安全门槛。
5. 不把 Source/Target、Shot/Segment、Attempt/Selection 为减少类数量而合并。
6. 每一步运行相关测试；公共接口变化必须追所有调用方。

---

# Performance Optimization｜性能优化

先测量再优化，尤其是视频和本地模型链。

1. 定义基线：总耗时、单 Shot/Segment 耗时、GPU/CPU、显存/内存、I/O、模型加载时间、DB 查询数。
2. 用真实 profile 找瓶颈，区分模型推理、帧抽取、编码、磁盘、网络和数据库。
3. 优先复用 fingerprint 一致的 current/checkpoint 结果，避免无意义重跑。
4. 评估批处理、模型常驻、帧采样和并发时必须保持质量门禁。
5. 不为了提速降低 Character 身份阈值、H3 QC、完整 decode、Lip Sync 身份确认。
6. GPU/CPU 切换要记录真实设备和模型兼容性；不能把 CPU 测试结果当 GPU 性能结果。
7. 优化后用同一输入复测 before/after，并确认正确性没有回归。

---

# Dependency Upgrade｜依赖升级

1. 记录当前精确版本、目标版本和升级原因。
2. Python 与 npm 分开小步升级，避免一次混入大量无关依赖。
3. PyTorch / ONNX Runtime / CUDA / cuDNN / 模型 Provider 必须检查组合兼容，不只看单包最新版。
4. 读 breaking changes/migration guide（可访问时），搜索仓库实际调用点。
5. 更新后运行 pytest、前端 test/typecheck/build，以及受影响模型 smoke test（可运行时）。
6. 模型运行时依赖升级需要真实 GPU/CPU 环境验证；纯 import 成功不等于推理成功。
7. 不为“保持最新”盲目升级稳定模型链。

---

# Git Workflow｜Git 安全工作流

本项目当前规则：`main = 当前开发`，`backup/* = 回滚恢复`。

1. 开始前确认远端 `main` 最新 HEAD，不基于过期提交写入。
2. 不覆盖或回滚用户的最新提交。
3. 默认修改 `main`；用户明确要求分支/PR 时再切换。
4. commit 按逻辑任务边界，信息描述真实变化。
5. 禁止 force push、reset/clean 破坏用户工作。
6. 远端在工作期间前进时，重新读取最新 HEAD，安全合并/重建提交并重新验证受影响内容。
7. 文档、数据契约和代码同时变化时，commit 中保持它们一致。

---

# CI/CD Debugging｜流水线调试

1. 找第一个真正失败的 job/step，不被后续连锁失败干扰。
2. 对比本地与 CI 的 Python/Node/OS、依赖、env、工作目录、缓存、GPU/模型可用性。
3. 先复现同一失败命令，再形成单一假设。
4. 修根因，禁止通过跳过测试、关闭检查或无限重试掩盖。
5. 模型相关测试若 CI 本来就没有 GPU/权重，应明确区分“仓库测试”和“本地模型验收”，不要伪造模型成功。

---

# Observability Development｜可观测性

围绕真实长任务和用户关键路径设计。

日志建议包含：

- project_id / episode_id / shot_id / segment_id（适用时）；
- task_id / run_id / attempt_id；
- workflow revision；
- input fingerprint；
- provider/model profile；
- execution state / last_error；
- duration / retry index。

规则：

1. 使用结构化、可关联日志，不到处 print。
2. 不记录 secret、完整敏感请求、无必要本地隐私路径。
3. Metrics 用稳定低基数维度，不把 user_id/task_id 直接做高基数 label。
4. Runtime 健康、任务失败、业务 Review 分开观测。
5. 长任务 heartbeat/checkpoint 应能回答“还活着、做到哪、能否恢复”。

---

# Release Delivery｜发布、迁移与真项目切换

1. 明确 release 内容、schema/migration、配置、模型版本、feature gate。
2. 数据迁移前备份真实 DB/sidecar；先 dry-run 和计数核对。
3. 只迁移与当前 source fingerprint/revision 一致的决定；不确定数据进入 Review/历史，不强行 current。
4. 旧 TargetDialogue/Timeline/Segment/Output 可保留历史，但必须 STALE/SUPERSEDED。
5. 大迁移优先 shadow/对照验证 ProjectFlowState，再切换正式读取。
6. 发布后检查 health、错误率、任务积压、关键 workflow 指标和真实项目页面。
7. 模型链发布后要把“服务启动”和“真实推理”分开验收。
8. 准备明确回滚路径；不可逆步骤必须显式说明。

---

# Verification Before Completion｜完成前验证

**“代码看起来对”不是完成。**

### 必做

1. 把用户要求逐条映射到实现。
2. 运行与改动匹配的后端 pytest。
3. 前端改动运行适用的：

```bash
npm --prefix frontend run test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

4. Bug 运行原始复现/回归。
5. UI 尽可能真实浏览器验证。
6. DB/API 检查迁移、兼容、幂等、revision/stale。
7. 查看最终 diff，检查 secret、debug、TODO 占位、生成垃圾和无关修改。
8. 数据契约、用户流程或完成条件变化时检查 `docs/00/01/02/03` 是否需要同步。

### 必须分开报告

```text
代码是否实现
仓库自动测试是否通过
本地模型是否真实运行
真实项目是否完整跑通
用户是否看听并验收
```

未执行项目写 `NOT RUN` 和原因，禁止用单元测试替代真实模型/真实项目验收。

---

# Default Branch Delivery｜默认分支交付

当前项目明确以 `main` 为开发分支。

1. 写入前获取远端 `main` 最新 commit/tree。
2. 所有修改基于最新 HEAD，避免覆盖并发提交。
3. 完成验证后只提交本任务文件。
4. 若远端 `main` 已前进，停止使用旧 base，重新同步并重新验证受影响内容。
5. 禁止 force 更新 main。
6. 推送后重新读取 `main`，确认远端 HEAD 已包含新 commit。
7. 最终回复说明 commit SHA、main 更新结果、实际验证和未验证项。

---

# Fullstack Development｜全栈纵向开发

用于同一业务能力同时修改 Vue、API、Service、DB/Workflow。

1. 先定义一个用户可见闭环，不按“前端/后端各自完成”分割验收。
2. 后端先形成唯一正式状态/read model，前端只消费，不复制业务判断。
3. 写操作从用户明确动作开始，经 API → service → 正式对象 → Validator/FlowState，再回到 UI。
4. 数据/API 契约先定清楚，再同步 Pydantic/TypeScript 调用方。
5. 每个切片同时有后端行为测试和前端状态/交互测试；最终做真实页面路径。
6. 如果涉及长模型任务，UI 只展示任务和状态，不承担任务编排。

---

# Repository Development｜仓库开发总控

这是所有代码任务的总控技能。

## 启动

1. 读取正式文档、`AGENTS.md`、根 `SKILL.md`。
2. 读取本文件技能路由，选择需要的专业技能。
3. 做 Codebase Analysis，确认真实调用链和相似实现。
4. 确认 `main` 最新状态、技术栈、测试命令。
5. 按 S/M/L/XL 确定计划深度。

## 实施

1. 从用户可见结果和正式数据出发。
2. 优先复用现有架构和 Provider，不造第二套。
3. 一次完成一个可验证切片。
4. 公共接口先追调用方；数据变化先设计迁移/失效。
5. 严守 SourceDramaSnapshot、Workflow V2、Review、H3 QC、Lip Sync、GET 只读等项目硬规则。

## 完成门禁

1. 实现已落代码/文档，不是 TODO 占位。
2. 相关自动测试和 build/typecheck 已真实运行或明确 NOT RUN。
3. 需要的浏览器/模型/真实项目验收与自动测试分开记录。
4. 最终 diff 无无关修改、secret、调试垃圾。
5. 必要正式文档已同步。
6. commit 已创建并安全更新到 `main`。
7. 重新读取远端 `main` 确认提交存在后，才报告完成。
