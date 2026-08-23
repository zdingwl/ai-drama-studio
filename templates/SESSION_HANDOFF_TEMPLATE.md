# Development Session Handoff Template

> 每一次实际开发会话结束时必须创建一份新文档，保存到：
>
> `docs/sessions/YYYY-MM-DD_HHMM_FXX_<topic>.md`
>
> 目标：新的 ChatGPT/Codex 对话在没有旧聊天记录的情况下，也能直接继续开发。

---

# Session Handoff — <日期时间> — Feature XX — <主题>

## 1. 本次开发目标

- 

## 2. 开始前项目状态

- 当前 Feature：
- Feature 状态：
- 前置 Stable Feature：
- 当前 branch：
- 当前 PR：
- 开始前最新 commit：
- 开始前已知问题：

## 3. 本次实际完成

必须写具体结果，不写笼统总结。

- 

## 4. 修改文件清单

### 新增

- `path/to/file` — 作用

### 修改

- `path/to/file` — 修改内容

### 删除

- 无 / `path/to/file`

## 5. 关键代码位置

| 位置 | 作用 | 后续修改注意事项 |
|---|---|---|
| `...` | | |

## 6. API 变化

### 新增

- 无 / `METHOD /api/...`

### 修改

- 无

### 删除

- 无

### 当前 Contract

```text
...
```

## 7. Database 变化

### Migration

- 无 / migration id

### 表/字段变化

- 

### 数据兼容性

- 

## 8. 文件系统变化

- 新增目录：
- 新增生成文件：
- 路径/命名规则：
- 是否改变已有文件 Contract：No / Yes

## 9. 依赖 / 环境变化

- Python package：
- Node package：
- FFmpeg/CUDA要求：
- 环境变量：
- 配置文件：

如果没有，写“无”。

## 10. 技术决策与原因

### Decision 001

- 决策：
- 原因：
- 替代方案：
- 为什么没有采用：
- 对后续的影响：

## 11. 本次没有做的内容

明确避免下一次误以为已经完成。

- 

## 12. 测试执行情况

### 自动测试

```text
命令：
结果：
```

### 手工测试

- 

### 真实素材测试

- 素材：
- 步骤：
- 结果：

## 13. 当前 Bug / 风险

### Bug

- 无 / 

### 风险

- 无 / 

### 临时 workaround

- 无 / 

## 14. Contract 变化检查

- Input Contract：未变 / 已变
- Output Contract：未变 / 已变
- API Contract：未变 / 已变
- DB Contract：未变 / 已变
- File Contract：未变 / 已变
- ID/状态枚举：未变 / 已变

如果任何一项变化，必须说明原因、影响的下游 Feature 和迁移方式。

## 15. 当前 Feature 状态

- 状态：IN_PROGRESS / TESTING / STABLE / FROZEN
- 已完成：
- 未完成：
- 是否可进入下一个 Feature：No / Yes
- 如果 No，缺少：

## 16. Git 状态

- Repository：`zdingwl/ai-drama-studio`
- Branch：
- Commit(s)：
- PR：
- 是否存在未提交修改：

## 17. 下一步唯一推荐动作

必须可直接执行，例如：

> 打开 `engine/api/projects.py`，实现 `POST /api/projects` 的 workspace 创建事务，并补齐失败回滚测试。

不要写：

> 继续开发 Feature 01。

## 18. 新对话读取清单

新的对话开始时按顺序读取：

1. `AGENTS.md`
2. `SKILL.md`
3. `docs/PROJECT_STATE.md`
4. `docs/features/FXX-<current>.md`
5. 本 Session Handoff
6. 下列必要代码文件：
   - `...`

## 19. 给下一位 Agent 的一句话

> <用一句话描述现在做到哪里以及下一步是什么。>
