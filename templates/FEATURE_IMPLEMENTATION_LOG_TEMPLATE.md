# Feature Implementation Log Template

> 用于记录一个 Feature 从开始实现到 Stable/Frozen 的完整开发过程。复制后保存到 `docs/features/FXX-<slug>.md`，并持续更新，不要每次重建。

---

# Feature XX — <功能名称>

## 1. 基础信息

- Feature ID：FXX
- 名称：
- 状态：PLANNED / IN_PROGRESS / TESTING / STABLE / FROZEN
- 前置 Stable Feature：
- 首次开发日期：
- 最近更新时间：
- 当前负责人/Agent：
- 当前 branch：
- 当前 PR：

---

## 2. 功能目标

说明这个 Feature 为用户解决什么问题，以及完成后的可见结果。

---

## 3. 明确不做什么

列出本 Feature 不负责的内容，防止范围蔓延。

---

## 4. 用户操作流程

```text
步骤 1
→ 步骤 2
→ 步骤 3
```

---

## 5. Input Contract

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| | | | | |

---

## 6. Output Contract

| 字段 | 类型 | 说明 |
|---|---|---|
| | | |

---

## 7. Data Access Contract

### 允许读取

- 

### 允许新增/修改

- 

### 明确禁止修改

- 

---

## 8. Database Contract

### Tables

- 

### New / Changed Fields

- 

### Migration

- migration id：
- up：
- down：

---

## 9. File Contract

### 输入文件

- 

### 输出文件

- 

### 路径规则

```text
workspace/...
```

---

## 10. API Contract

### Endpoint

```text
METHOD /api/...
```

### Request

```json
{}
```

### Response

```json
{}
```

### Error Codes

| Code | 场景 | UI 提示 |
|---|---|---|
| | | |

---

## 11. UI 规格

### 页面/区域

- 

### 操作

- 

### 状态

- loading
- empty
- success
- error

---

## 12. 技术实现

### Frontend Code Map

- 

### Backend Code Map

- 

### AI / Media Code Map

- 

### Tests Code Map

- 

---

## 13. 模型 / Provider / GPU

- 是否使用本地模型：
- 模型：
- 是否使用 API：
- Provider：
- GPU 策略：
- 4060 Ti 16GB 注意事项：

---

## 14. 关键技术决策

### Decision 001

- 决策：
- 原因：
- 被否决方案：
- 为什么否决：
- 后续影响：

---

## 15. 实际开发记录

### YYYY-MM-DD — 开发记录 01

#### 本次目标

- 

#### 完成

- 

#### 修改文件

- `path/to/file`

#### 未完成

- 

#### 发现的问题

- 

#### 技术决策

- 

#### Contract 是否变化

- No / Yes
- 如果 Yes，说明具体变化与原因。

---

## 16. 测试记录

### 自动测试

| 测试 | 命令/方法 | 结果 |
|---|---|---|
| | | |

### 手工测试

| 场景 | 预期 | 实际 | 结果 |
|---|---|---|---|
| | | | |

### 真实短剧素材测试

- 素材：
- 时长：
- 编码/分辨率：
- 测试步骤：
- 结果：
- 异常：

---

## 17. 已知 Bug / 风险 / 边界

- 

---

## 18. Definition of Done

- [ ] Contract 已确认
- [ ] 功能实现完成
- [ ] 错误处理完成
- [ ] 自动测试通过
- [ ] 手工测试通过
- [ ] 真实短剧素材测试通过
- [ ] 用户人工验收通过
- [ ] Feature 文档已更新
- [ ] 最新 Session Handoff 已创建
- [ ] `docs/PROJECT_STATE.md` 已更新
- [ ] Freeze Snapshot 已完成

---

## 19. Freeze Snapshot

### Stable Version

- Version：V1
- Freeze Date：

### Frozen Input

- 

### Frozen Output

- 

### Frozen API

- 

### Frozen DB Fields

- 

### Frozen Paths / IDs / States

- 

### 下游只能依赖

- 

---

## 20. Change Log

| 日期 | 修改 | 原因 | 影响范围 | Contract变化 | Commit/PR |
|---|---|---|---|---|---|
| | | | | | |

---

## 21. 下一步

明确写一个可执行动作，不写“继续优化”。

例如：

> 用户验收 Feature 01 后，将其标记 STABLE，并复制模板创建 Feature 02 — 上传视频 Contract。