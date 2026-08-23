# Feature XX — <功能名称>

> 每个 Feature 正式编码前必须填写。本模板定义当前 Feature 的边界、数据、测试、P0 和验收。
>
> 没有 Contract，不开始编码。

---

## 0. 基础信息

```text
Feature ID: FXX
Name:
Version: v1
Status: PLANNED | IN_PROGRESS | TESTING | READY_FOR_REVIEW | STABLE | FROZEN
Branch:
PR:
Created At:
Last Updated:
```

注意：AI/Agent 最多只能标记 `READY_FOR_REVIEW`。只有用户明确验收通过后才能 `STABLE/FROZEN`。

---

## 1. 功能目标

一句话说明本 Feature 为用户解决什么问题。

### 必须完成

- 

### 明确不做

- 

---

## 2. 前置 Stable Feature

| Feature | Required Contract | Status |
|---|---|---|
| | | |

如依赖项不是 Stable/Frozen，停止编码。

---

## 3. 用户操作流程

```text
步骤1
→ 步骤2
→ 步骤3
→ 完成
```

---

## 4. UI Contract

### 页面/区域

- 页面：
- 入口：
- 工作区：

### 状态

```text
idle
loading/running
empty
success
error
```

长任务按需要增加 pending/running/completed/failed/cancelled/unknown。

### 用户可操作

- 

### 用户禁止操作

- 

---

## 5. Input Contract

| Field/Object | Type | Source Feature | Required | Business Meaning |
|---|---|---|---:|---|
| | | | | |

---

## 6. Output Contract

| Field/Object | Type | Destination | Business Meaning |
|---|---|---|---|
| | | | |

---

## 7. Data Access Contract

### 允许读取

- 

### 允许新增/修改

- 

### 明确禁止修改

- Stable/Frozen 上游对象；
- AI 原始结果（如只允许写 Final）；
- 历史版本；
- Source Asset（默认只读）。

---

## 8. Revision / Dependency / Invalidation

- 本 Feature 依赖哪些上游 revision：
- 本 Feature 自己是否有 semantic revision：
- 本 Feature 产生哪些派生结果：
- 哪些上游变化会使结果 stale：
- stale 后 UI 提示：
- stale 后后端禁止行为：
- 重新计算入口：
- 是否允许人工 override：

---

## 9. Database Contract

### Tables

- 

### New / Changed Fields

- 

### Constraints / Indexes

- 

### Migration

```text
revision:
down_revision:
backup strategy:
downgrade:
```

### Database Dictionary

每个业务字段必须填写：

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Frozen | Example |
|---|---|---:|---|---|---|---|---:|---|
| | | | | | | | | |

---

## 10. File / Workspace Contract

### 输入路径

```text
workspace/...
```

### 输出路径

```text
workspace/...
```

### 文件命名

- 

### 写入与恢复

- staging/tmp：
- 文件校验：
- atomic rename：
- DB commit 时机：
- restart recovery：
- orphan/missing handling：

---

## 11. Project Format 影响

- 是否改变 `project_format_version`：Yes / No
- 原因：
- 旧项目兼容：
- 是否需要 Project Format migration：

普通 DB 字段变化不一定改变 Project Format；Workspace/持久化 JSON/项目结构语义变化时必须评估。

---

## 12. Media Timebase

- 适用：Yes / No
- 输入 timeline：
- 输出 timeline：
- 权威字段：`*_us`
- Source↔Proxy mapping：
- CFR/VFR：
- audio offset/sample rate：
- rounding utility：
- 时间误差验收：

---

## 13. API Contract

### Endpoint

```text
METHOD /api/...
```

Purpose：

Request：

```json
{}
```

Response：

```json
{}
```

Errors：

| Code | Trigger | UI Message | Retryable | Recovery |
|---|---|---|---:|---|
| | | | | |

---

## 14. Task / WebSocket

如果是长任务：

```json
{
  "task_id": "...",
  "feature_id": "FXX",
  "status": "running",
  "progress": 0,
  "step": "...",
  "message": "..."
}
```

说明：取消、重试、restart resume、interrupted 行为。

---

## 15. Local Model / Provider

| Ability | Model/Provider | Version | Device | Fallback | Notes |
|---|---|---|---|---|---|
| | | | CPU/GPU/API | | |

### Provider Job（如适用）

- local_job_id 创建时机：
- request_fingerprint：
- provider idempotency：
- provider_task_id 保存：
- submit timeout：
- poll retry：
- restart resume：
- cost：

---

## 16. Environment / Dependency Change

- 新增 Python 依赖：
- 新增 Node 依赖：
- 新增 Native Tool：
- 新增本地模型：
- lock 更新：
- model source/hash：
- RTX 4060 Ti 16GB 可运行性：
- 新电脑安装验证：

---

## 17. 算法 / 业务流程

```text
Input
↓
Step 1
↓
Step 2
↓
Output
```

关键阈值/经验规则必须说明为什么存在，以及是否属于可配置参数。

---

## 18. AI Result / Human Final

如果存在 AI 结果：

- AI 原始结果字段：
- 人工 Final 字段：
- 人工可修改：
- Confirm/Lock：
- 是否有 Revision Snapshot：
- Undo/回退方式：

---

## 19. Versioning

如果产生可重复内容：

```text
版本对象：
version id：
历史是否保留：
selected/final id：
删除规则：
```

Video / TTS / Lip Sync 默认必须版本化。

---

## 20. 代码与中文注释要求

### Code Map

Frontend：
- 

Backend：
- 

DB：
- 

Tests：
- 

检查：

- [ ] 核心文件有职责说明
- [ ] Service/公开方法有 docstring
- [ ] 复杂业务逻辑解释“为什么”
- [ ] API Schema 字段有 description
- [ ] DB 表/字段有业务说明
- [ ] Migration 有中文说明
- [ ] Database Dictionary 同步

---

## 21. P0 Checklist

把 `templates/P0_FEATURE_CHECKLIST.md` 内容复制到这里或明确链接到当前 Feature 的 P0 区域。

Stable 前所有适用项必须 PASS。

---

## 22. Current Feature Tests

### Unit

- [ ] 

### Integration

- [ ] 

### Error / Recovery

- [ ] 

---

## 23. Regression Scope

### Affected Stable Features

- FXX：原因

### Regression Tests

| Feature | Test | Result |
|---|---|---|
| | | |

如果没有 Stable Feature，写 `N/A — no stable upstream feature yet`。

---

## 24. 真实素材测试

```text
Sample:
Duration:
Resolution:
FPS/VFR:
Language:
Audio:
Environment Snapshot:
```

结果：

```text
Expected:
Actual:
Human Correction:
Error Cases:
Known Limitations:
```

---

## 25. 用户人工验收步骤

写成不需要读代码就能执行的步骤：

```text
1. ...
2. ...
3. ...
```

Agent 测试通过后状态为 `READY_FOR_REVIEW`，等待用户执行/确认。

---

## 26. Definition of Done

- [ ] Scope 明确
- [ ] Input/Output Contract 完成
- [ ] Data Access Contract 完成
- [ ] Revision/Invalidation 完成或 N/A
- [ ] UI/API 完成
- [ ] DB/Migration 完成或 N/A
- [ ] File Recovery 完成或 N/A
- [ ] Media Timebase 完成或 N/A
- [ ] Provider Safety 完成或 N/A
- [ ] Environment Lock 完成或 N/A
- [ ] 中文代码/数据库注释完成
- [ ] Current Feature tests 通过
- [ ] Regression 通过或 N/A
- [ ] 真实素材测试完成
- [ ] Feature 文档更新
- [ ] Session Handoff 创建
- [ ] PROJECT_STATE 更新
- [ ] 状态已到 READY_FOR_REVIEW
- [ ] 用户明确验收通过
- [ ] Freeze Snapshot 完成

---

## 27. Freeze Snapshot

用户验收后填写：

```text
Stable Version:
Stable Date:
User Acceptance Reference:
Frozen Input:
Frozen Output:
Frozen API:
Frozen DB Fields:
Frozen File Paths:
Frozen IDs:
Frozen States:
Frozen Error Codes:
Project Format Impact:
```

---

## 28. Known Limitations

- 

V1 接受的限制要明确写出，不要隐藏成“测试通过”。

---

## 29. Change Log

| Date | Change | Reason | Impact | Contract Changed | Commit/PR |
|---|---|---|---|---|---|
| | | | | | |

---

## 30. Next Action

必须具体到可执行动作。

错误：

```text
继续优化
```

正确示例：

```text
打开 engine/api/projects.py，实现 POST /api/projects 的 workspace 创建事务和失败回滚，并补 F01-API-003。
```
