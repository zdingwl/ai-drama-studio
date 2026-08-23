# Feature Implementation Log Template

> 每个 Feature 从 Contract 到 Stable/Frozen 的永久开发档案。
>
> 建议保存为 `docs/features/FXX-<slug>.md` 并持续更新，不要每次重建新文件。

# Feature XX — <功能名称>

## 1. 基础信息

- Feature ID：FXX
- 名称：
- 状态：PLANNED / IN_PROGRESS / TESTING / READY_FOR_REVIEW / STABLE / FROZEN
- 前置 Stable Feature：
- 首次开发日期：
- 最近更新时间：
- 当前 branch：
- 当前 PR：
- 用户验收日期：
- 用户验收记录：

> Agent 只能自行推进到 `READY_FOR_REVIEW`。只有用户明确验收通过后才能填写 STABLE/FROZEN。

---

## 2. 功能目标 / Scope

### 目标

- 

### 明确不做

- 

---

## 3. Contract Snapshot

### Input

- 

### Output

- 

### Reads

- 

### Writes

- 

### Must NOT Modify

- 

### API

- 

### DB / File

- 

### Revision / Stale

- 

---

## 4. P0 Summary

```text
P0 DEPENDENCY: PASS / N/A
P0 TIMEBASE: PASS / N/A
P0 ENVIRONMENT: PASS / N/A
P0 RECOVERY: PASS / N/A
P0 PROVIDER JOB: PASS / N/A
```

详细内容可直接引用本 Feature Contract 的 P0 Checklist。

---

## 5. Database Dictionary

如果涉及数据库，逐表逐字段记录真实业务意义。

| Table.Field | Type | Nullable | Meaning | Source | Mutable By | Frozen | Example |
|---|---|---:|---|---|---|---:|---|
| | | | | | | | |

---

## 6. Code Map

### Frontend

- 

### Backend

- 

### DB / Migration

- 

### Tests

- 

---

## 7. 关键技术决策

### Decision 001

- 决策：
- 原因：
- 替代方案：
- 为什么不选：
- 后续影响：

---

## 8. 实际开发记录

### YYYY-MM-DD — Session XX

#### 目标

- 

#### 完成

- 

#### 修改文件

- `path/to/file`

#### 未完成

- 

#### 发现问题

- 

#### Contract 是否变化

- No / Yes
- 变化：
- 用户是否需要重新确认：

#### 下一步

- 

---

## 9. Current Feature Tests

| Test | Type | Result | Notes |
|---|---|---|---|
| | unit/integration/manual | | |

---

## 10. Regression

### Affected Stable Features

- 

### Results

| Feature | Regression | Result |
|---|---|---|
| | | |

---

## 11. 真实素材测试

```text
Sample:
Duration:
Resolution:
FPS/VFR:
Language:
Environment:
```

- Expected：
- Actual：
- Human Correction：
- Error Cases：
- Known Limitations：

---

## 12. Bug / Risk / Limitation

- 

---

## 13. Comment / Documentation Review

```text
CODE COMMENT REVIEW: PASS / N/A
DATABASE COMMENT REVIEW: PASS / N/A
DATABASE DICTIONARY: COMPLETE / N/A
FEATURE DOCUMENT: UPDATED
SESSION HANDOFF: CREATED
PROJECT_STATE: UPDATED
```

---

## 14. READY_FOR_REVIEW Checklist

- [ ] Contract 实现完成
- [ ] Scope 未扩散
- [ ] P0 适用项通过
- [ ] Current Feature tests 通过
- [ ] Regression 通过/N/A
- [ ] 真实素材测试完成
- [ ] 中文代码/数据库注释完成
- [ ] 文档更新完成
- [ ] 无未解释的 Contract Drift

满足后 Agent 可标记：`READY_FOR_REVIEW`。

---

## 15. 用户人工验收

### 验收步骤

1. 
2. 
3. 

### 用户结果

```text
PENDING / PASSED / REJECTED
```

### 用户反馈

- 

如果 `PASSED` 才允许继续 Freeze。

---

## 16. Freeze Snapshot

### Stable Version

- Version：
- Freeze Date：
- User Acceptance Reference：

### Frozen Contracts

- Input：
- Output：
- API：
- DB Fields：
- IDs：
- Paths：
- States：
- Error Codes：
- Project Format Impact：

### 下游只能依赖

- 

---

## 17. Change Log

| Date | Change | Reason | Impact | Contract Change | Commit/PR |
|---|---|---|---|---|---|
| | | | | | |

---

## 18. Next Action

必须是下一次会话可以直接执行的具体动作。
