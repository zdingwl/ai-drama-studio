# Feature XX — <功能名称>

> 本模板用于 AI Drama Studio 每一个 Feature 的正式开发规格。
>
> 开发前必须填写，开发完成后补齐测试、验收和 Freeze。没有 Contract，不开始编码。

---

## 0. Feature 状态

```text
Feature ID: FEATURE_XX
Name:
Version: v1
Status: draft | developing | testing | review | stable
Owner:
Created At:
Stable At:
```

---

## 1. 功能目标

一句话说明本 Feature 解决什么问题。

示例：

> 将已导入项目的 Proxy Video 自动切分为 Shot Candidate，并保留 AI 原始边界供人工修正。

### 本 Feature 必须完成

- 
- 

### 本 Feature 明确不做

- 
- 

这部分非常重要，防止一个 Feature 越做越大。

---

## 2. 前置条件

### 依赖的 Stable Feature

- Feature XX
- Feature XX

### 依赖的已冻结对象

- `Project`
- `Episode`
- `...`

如果依赖项不是 Stable，停止当前 Feature 开发。

---

## 3. 用户操作流程

```text
步骤 A
→ 步骤 B
→ 步骤 C
→ 完成
```

写清楚用户看到什么、点什么、结果在哪里出现。

---

## 4. 页面 / UI Contract

### 4.1 页面位置

```text
页面：
区域：
入口：
```

### 4.2 主要控件

- 
- 

### 4.3 页面状态

必须至少考虑：

```text
idle
loading / running
success
empty
error
```

长任务增加：

```text
pending
running
cancelled
failed
completed
```

### 4.4 用户可执行操作

- 
- 

### 4.5 用户禁止操作

- 
- 

---

## 5. Input Contract

列出当前 Feature 可以读取的输入。

| Field / Object | Type | Source Feature | Required | Notes |
|---|---|---|---:|---|
| | | | | |

示例 JSON：

```json
{}
```

---

## 6. Output Contract

列出 Feature 成功后必须产生的输出。

| Field / Object | Type | Destination | Notes |
|---|---|---|---|
| | | | |

示例 JSON：

```json
{}
```

---

## 7. 读取的数据

允许读取：

- 表 / 对象 A
- 表 / 对象 B

说明为什么需要读取。

---

## 8. 允许修改的数据

当前 Feature 只允许修改：

- 表 / 对象 C
- 新增字段 / 新记录
- 当前 Feature 自己的状态

如需迁移，明确 Alembic migration。

---

## 9. 禁止修改的数据

明确列出：

- Stable 上游对象
- 不允许回写的字段
- 不允许覆盖的 AI 原始结果
- 不允许删除的历史版本

示例：

```text
禁止修改 source_video
禁止覆盖 detected_start
禁止重新生成 Character ID
```

---

## 10. DB Schema / Migration

### 新增表

```text
<schema>
```

### 新增字段

```text
<table.field>
```

### Index / Constraint

```text
...
```

### Migration

```text
revision:
down_revision:
```

---

## 11. 文件输入输出

### 输入路径

```text
workspace/<project>/...
```

### 输出路径

```text
workspace/<project>/...
```

### 文件命名规则

```text
...
```

媒体默认禁止写入 SQLite Blob。

---

## 12. 后端 API

### Endpoint 1

```text
METHOD /path
```

Purpose:

Request:

```json
{}
```

Response:

```json
{}
```

Errors:

```text
ERROR_CODE_A
ERROR_CODE_B
```

### Endpoint 2

同上。

---

## 13. WebSocket / Task Event

如为长任务，定义事件：

```json
{
  "task_id": "...",
  "feature": "FEATURE_XX",
  "status": "running",
  "progress": 0,
  "step": "...",
  "message": "..."
}
```

任务必须可识别：

```text
pending
running
completed
failed
cancelled
```

---

## 14. 本地模型 / 云 API

| Ability | Model / Provider | Device | Fallback | Notes |
|---|---|---|---|---|
| | | CPU/GPU/API | | |

如果是外部 Provider，必须经过 Adapter，不允许业务代码直接散落 HTTP 调用。

---

## 15. GPU / Memory 策略

开发环境：RTX 4060 Ti 16GB。

明确：

```text
是否 GPU:
预计显存:
是否必须独占 GPU:
加载方式:
任务后是否卸载:
CPU fallback:
```

默认 concurrency = 1。

---

## 16. 算法流程

```text
Input
↓
Step 1
↓
Step 2
↓
Output
```

只描述本 Feature，不把下游逻辑塞进来。

---

## 17. 人工修正规则

如果 Feature 有 AI 结果：

- AI 原始结果保存在哪里？
- Final 数据保存在哪里？
- 人工可以改哪些字段？
- 是否需要 Confirm / Lock？
- 人工修正是否可撤销？

必须明确 AI Result ≠ Final Result。

---

## 18. Versioning

如果 Feature 会产生可重复生成的媒体或内容，明确：

```text
版本 ID：
版本号规则：
是否允许删除：
Selected ID：
历史是否保留：
```

Video / TTS / Lip Sync 默认必须版本化。

---

## 19. 异常处理

| Error | Trigger | UI 提示 | Retry | 是否影响上游 | Recovery |
|---|---|---|---:|---:|---|
| | | | | | |

禁止只显示“请求失败”。

必须尽量显示：

- 失败步骤
- 错误原因
- 是否已经重试
- 是否可以切模型 / 重试

---

## 20. 日志与可追溯

至少记录：

```text
task_id
feature_id
project_id
episode_id
shot_id（如适用）
start_time
end_time
model/provider（如适用）
status
error
```

外部 API 还要记录 provider task id 和 cost（能获取时）。

---

## 21. 单元测试

### 正常路径

- [ ] Case 1
- [ ] Case 2

### 边界条件

- [ ] Case 3
- [ ] Case 4

### 错误场景

- [ ] Case 5
- [ ] Case 6

---

## 22. 真实素材测试

必须记录真实短剧样本。

```text
Sample:
Duration:
Resolution:
FPS:
Language:
Notes:
```

测试结果：

```text
AI Result:
Human Correction:
Error Cases:
Known Limitations:
```

---

## 23. 人工验收步骤

按真实工作流写：

```text
1. 创建/打开测试项目
2. ...
3. ...
4. 确认输出
```

验收人员不应该需要阅读代码才能验证 Feature。

---

## 24. Definition of Done

- [ ] Scope 明确，没有偷做下游 Feature
- [ ] Input Contract 完成
- [ ] Output Contract 完成
- [ ] UI 完成
- [ ] API 完成
- [ ] DB / Migration 完成
- [ ] 数据持久化完成
- [ ] 应用重启后数据可恢复
- [ ] 错误处理完成
- [ ] 当前 Feature 可独立重跑
- [ ] 不破坏 Stable 上游 Feature
- [ ] 单元测试完成
- [ ] 真实素材测试完成
- [ ] 用户人工验收通过
- [ ] 文档更新完成

---

## 25. Freeze

验收后冻结：

```text
Input Contract:
Output Contract:
API Contract:
DB fields:
ID rules:
File path rules:
Status enum:
Error codes:
```

Stable Version：`v1`

Stable Date：

---

## 26. Known Limitations

明确 V1 已知但接受的问题：

- 
- 

这些问题不要在未授权情况下自动扩大当前 Feature Scope。

---

## 27. Future V2 Ideas

只记录，不在 V1 自动实现：

- 
- 
