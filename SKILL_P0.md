---
name: ai-drama-studio-p0-engineering
version: 1.1.0
description: AI Drama Studio 主 Skill 的 P0 工程规则补充。与 SKILL.md 共同构成必须遵守的项目 Skill。
---

# AI Drama Studio — P0 Engineering Skill Addendum

> 本文件不是可选参考。`SKILL.md + SKILL_P0.md` 共同构成项目完整 Skill。
>
> 任意开发人员、ChatGPT、Codex 或其他 Agent 在开始 Feature 开发前，都必须遵守本文件中的 5 个 P0 Contract。

## 1. P0 规则总览

任何 Feature 在编码前都必须检查以下 5 项是否适用：

1. **Dependency / Revision / Invalidation**：上游数据变化后，下游派生结果是否需要标记过期。
2. **Media Timebase Contract**：是否读写视频、音频、字幕、Shot、Dialogue 等时间信息。
3. **Environment Baseline**：是否新增/升级运行时、Python/Node 包、本地模型、FFmpeg/CUDA 依赖。
4. **DB + File Recovery**：是否同时写数据库与本地媒体/缓存文件，是否涉及 migration。
5. **Provider Job Safety**：是否调用可能计费、异步、可重试的外部 Provider。

详细规则见：

- `docs/P0_RULES_INDEX.md`
- `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
- `docs/MEDIA_TIMEBASE_CONTRACT.md`
- `docs/ENVIRONMENT_BASELINE.md`
- `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
- `docs/PROVIDER_JOB_RULES.md`

每个 Feature 在 Contract 阶段必须填写：

- `templates/P0_FEATURE_CHECKLIST.md`

未完成 P0 检查，不允许开始编码。

---

## 2. Dependency / Revision / Invalidation

### 2.1 派生结果必须知道自己基于哪个上游版本

只要一个结果是由其它业务对象派生出来，就必须能追溯到上游 revision / version。

例如 Generation 必须能知道它基于：

```text
Shot revision
Character Bible revision
Scene Bible revision
Shot Specification revision
Reference asset version/hash
Provider + model version
```

### 2.2 上游语义变化时，旧下游结果不能继续假装有效

必须标记 `stale`，而不是自动删除。

```text
upstream changed
→ compare dependency revision
→ downstream becomes STALE
→ UI 显示原因
→ 用户选择重新计算/重新生成
```

### 2.3 失效必须按影响范围处理

显示名称变化不等于业务语义变化。

例如：

- Character display name 修改：通常不使 ASR/Generation 失效。
- Character→Actor Mapping 修改：Character Bible、Shot Spec、Generation、QC 需要重新评估或 stale。
- Shot 边界修改：Character analysis、Scene relation、Shot Spec、Generation、QC 可能 stale。

详细矩阵在 `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`。

---

## 3. Media Timebase Contract

### 3.1 业务时间禁止以 float 秒作为唯一权威值

统一业务时间单位：

```text
integer microseconds (µs)
```

字段推荐：

```text
start_us
end_us
duration_us
```

### 3.2 Source Timeline 是母时间轴

Proxy、WAV、Shot、Dialogue、Subtitle、TTS、Lip Sync、Render 的时间都必须可映射回 Source Timeline。

Proxy 只是预览/分析媒介，不能形成第二套不可对齐的独立时间轴。

### 3.3 保留媒体原始时间信息

必要时保留：

```text
time_base
pts
dts
fps_num
fps_den
sample_rate
source_start_time
```

尤其 VFR 视频不得假设 `frame_index / fps` 永远准确。

详细规则见 `docs/MEDIA_TIMEBASE_CONTRACT.md`。

---

## 4. Environment Baseline

### 4.1 禁止依赖“latest”

所有关键开发依赖必须可复现：

- Python exact version
- Node exact version
- 包管理器版本
- Python lock file
- Frontend lock file
- PyTorch
- CUDA runtime expectation
- FFmpeg build/version
- 本地模型名称、版本、来源、hash（能获取时）

### 4.2 新增依赖必须更新环境基线

如果一个 Feature 新增依赖但没有更新环境文档/lock：

> Feature 不允许标记完成。

### 4.3 升级依赖必须经过回归测试

禁止为了“顺手升级”在当前 Feature 同时升级大量无关依赖。

详细规则见 `docs/ENVIRONMENT_BASELINE.md`。

---

## 5. DB + File Recovery

SQLite 与媒体文件不是一个事务系统，因此必须明确崩溃恢复策略。

### 5.1 媒体写入默认流程

```text
创建 pending DB record / operation
→ 写 *.tmp
→ 校验文件
→ atomic rename 到最终路径
→ 更新 DB 为 ready/completed
```

禁止：

```text
先把 DB 标记 completed
→ 再慢慢写最终视频文件
```

### 5.2 Migration 前必须备份

数据库 schema migration 前必须生成可恢复备份，并记录 schema revision。

### 5.3 启动时允许完整性检查

至少能够识别：

- DB 记录存在但文件不存在
- 文件存在但 DB 无记录
- `.tmp` / interrupted operation
- SQLite integrity 问题

详细规则见 `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`。

---

## 6. Provider Job Safety

外部视频、TTS、Lip Sync 等任务可能计费，网络超时不能等价于“Provider 没收到请求”。

### 6.1 本地 Job 必须先创建

```text
local_job_id
request_id
request_fingerprint
attempt
```

在调用 Provider 前先持久化。

### 6.2 provider_task_id 一旦获得必须立即持久化

程序重启后：

```text
provider_task_id exists
→ resume polling/query
```

而不是重新创建付费任务。

### 6.3 Timeout = UNKNOWN，不自动视为 FAILED

只有能确认 Provider 未创建任务时，才允许安全自动重试创建请求。

### 6.4 人工重新生成必须创建新 attempt/version

不得覆盖原 Job，也不得复用会造成歧义的状态。

详细规则见 `docs/PROVIDER_JOB_RULES.md`。

---

## 7. Feature Stable Gate 增加 P0 检查

Feature 进入 `STABLE / FROZEN` 前必须记录：

```text
P0 DEPENDENCY REVIEW: PASS / N/A
P0 TIMEBASE REVIEW: PASS / N/A
P0 ENVIRONMENT REVIEW: PASS / N/A
P0 RECOVERY REVIEW: PASS / N/A
P0 PROVIDER JOB REVIEW: PASS / N/A
```

如果适用项不是 PASS：

> Feature 不得 Freeze。

---

## 8. P0 规则的优先级

若当前 Feature 实现方式与 P0 Contract 冲突：

1. 优先保持已冻结业务 Contract；
2. 调整当前 Feature 实现；
3. 若确实必须修改上游 Contract，按照 V2 / migration / impact analysis 流程处理；
4. 禁止静默绕过 P0 规则。
