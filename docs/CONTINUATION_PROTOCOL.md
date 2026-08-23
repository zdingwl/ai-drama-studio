# AI Drama Studio — 跨对话持续开发协议

## 1. 目的

本项目可能由多次 ChatGPT / Codex / 人工开发会话连续完成。聊天窗口可能超长、上下文可能丢失，也可能在新的对话中继续。

因此项目上下文必须保存在仓库，而不是只存在聊天记录中。

目标是做到：

> 新对话无需重新分析整个项目，只需读取仓库文档即可准确知道“项目做到哪里、为什么这样做、当前代码状态、下一步做什么”。

---

## 2. 文档即开发成果

每一次实际开发必须同时产生两类成果：

```text
代码成果
+
持续开发文档成果
```

只提交代码、不更新文档，视为开发未完成。

每次开发结束前至少必须更新：

1. 当前 Feature 文档 `docs/features/FXX-*.md`
2. `docs/PROJECT_STATE.md`
3. 一份开发会话交接记录 `docs/sessions/YYYY-MM-DD_HHMM_FXX_topic.md`

如果本次开发修改了 Contract、技术决策或冻结规则，还必须同步更新：

- 当前 Feature 的 Contract
- 相关上游 Feature 文档
- 必要时更新 `SKILL.md` / `docs/DATA_AND_FREEZE_RULES.md`

---

## 3. 新对话开始时的强制读取顺序

新的 AI 对话、Codex 会话或开发人员接手项目时，必须：

```text
1. 读取 SKILL.md
2. 读取 docs/PROJECT_STATE.md
3. 确认 current_feature
4. 读取当前 Feature 文档
5. 读取最新一份与当前 Feature 相关的 session handoff
6. 读取当前 Feature 依赖的 Stable Feature Contract（仅必要部分）
7. 查看当前代码 / git diff
8. 从 Next Action 继续
```

禁止先从头重新设计项目。

如果仓库文档与聊天描述冲突：

> 以最新已提交/已确认的仓库文档为项目基线，并把冲突明确报告给用户。

---

## 4. PROJECT_STATE.md 的职责

`docs/PROJECT_STATE.md` 是整个项目唯一的“当前状态入口”。

必须保持简洁但足够恢复工作，至少包含：

- 当前版本
- 当前分支
- 当前 Feature
- 当前 Feature 状态
- 已完成 / Stable Features
- 正在进行的工作
- 最近一次完成内容
- 当前阻塞项
- 已知 Bug
- 未决策事项
- 当前环境
- 关键技术选择
- 下一步唯一推荐动作
- 最新交接文档链接

每次开发结束必须更新。

禁止让 `PROJECT_STATE.md` 变成历史流水账；历史细节放 session 文档。

---

## 5. Feature 文档的职责

每个 Feature 必须有一份长期累积文档，例如：

```text
docs/features/
F01-create-project.md
F02-upload-video.md
F03-video-preprocess.md
...
```

Feature 文档不是一次性需求文档，而是该功能的永久技术档案。

至少包含：

### 基础信息
- Feature 编号
- 名称
- 状态：PLANNED / IN_PROGRESS / TESTING / STABLE / FROZEN
- 前置 Feature
- 首次开发日期
- 最近更新时间

### 需求和范围
- 功能目标
- 用户流程
- 明确不做什么
- 验收目标

### Contract
- Input Contract
- Output Contract
- API Contract
- DB Contract
- 文件输入输出 Contract
- 状态枚举
- 错误码

### 实现
- 前端文件
- 后端文件
- AI/模型文件
- 数据库 migration
- 关键函数 / 类
- 关键实现说明

### 技术决策
必须记录“为什么这样实现”，尤其是未来容易被误改的地方。

### 测试
- 自动测试
- 手工测试
- 真实短剧测试素材
- 测试结果
- 已知边界

### 变更记录
每次修改追加：

```text
日期
修改内容
修改原因
影响范围
是否改变 Contract
相关 commit / PR
```

### Freeze
Feature Stable 后记录冻结内容。

---

## 6. 每次开发会话 Session Handoff

每次实际编码会话结束时必须新建一份独立文档：

```text
docs/sessions/YYYY-MM-DD_HHMM_FXX_topic.md
```

例如：

```text
docs/sessions/2026-08-23_1420_F01_project-create-api.md
```

Session 文档回答一个核心问题：

> 如果下一次完全是一个新的对话，它应该知道什么才能立即继续？

至少必须包含：

1. 本次目标
2. 开始前状态
3. 实际完成内容
4. 修改文件清单
5. 新增/修改 API
6. 新增/修改 DB
7. 新增/修改文件目录
8. 关键代码位置
9. 技术决策及原因
10. 本次没有做的内容
11. 测试执行情况
12. 测试结果
13. 当前 Bug / 风险
14. Contract 是否变化
15. Feature 当前状态
16. Git branch / commit / PR
17. 下一步明确操作
18. 新对话建议先读哪些文件

禁止只写：“今天完成创建项目功能”。

要达到不看旧聊天也能理解的程度。

---

## 7. 开发过程中也要记录，不等最后回忆

对于超过一个小改动的开发任务，应在开发过程中维护 Feature 文档中的 Implementation Notes 或临时记录。

特别是以下情况发生时必须立刻记录：

- 改变数据结构
- 新增 migration
- 改变 API
- 放弃原方案
- 换模型
- 发现模型限制
- 发现真实素材异常
- 引入临时 workaround
- 修改 Stable 上游 Feature
- 增加新的环境依赖

避免开发完成后依靠记忆补文档导致遗漏。

---

## 8. Contract Snapshot

每个 Feature Stable 时，在 Feature 文档中必须形成可独立阅读的 Contract Snapshot。

示例：

```text
Feature 04 — Shot Detection V1 Contract

Input
- episode_id: string
- proxy_video_path: relative path

Output
- shot_id
- detected_start
- detected_end
- final_start
- final_end

Writes
- shots table

Must NOT modify
- projects
- episode source file
- characters
- dialogues

Status
- detected
- reviewed
- approved
```

下游功能优先依赖这个 Contract，而不是依赖内部实现。

---

## 9. 代码文件必须能追溯到 Feature

推荐目录和命名能够映射到业务 Feature。

必要时在 Feature 文档维护：

```text
Code Map
Frontend:
- desktop/frontend/src/...

Backend:
- engine/services/...

API:
- engine/api/...

DB:
- engine/database/...

Tests:
- tests/...
```

未来接手者不需要全仓库搜索才能理解一个 Feature。

---

## 10. 不允许文档与代码长期不一致

发现不一致时：

- 若代码错误：修代码。
- 若文档过期：更新文档。
- 若无法判断：停止扩展当前 Feature，先确认真实状态。

禁止在已知文档过期的情况下继续开发下游 Feature。

---

## 11. 新对话的推荐启动提示

用户在新的 ChatGPT / Codex 对话中只需要提供仓库，例如：

```text
继续开发 ai-drama-studio。
请先读取 AGENTS.md、SKILL.md、docs/PROJECT_STATE.md、当前 Feature 文档和最新 session handoff，然后从 Next Action 继续，不要重新规划整个项目。
```

仓库文档必须足够让这句话可执行。

---

## 12. Feature 完成 Gate 增加文档要求

原 Feature Gate：

```text
实现
→ 测试
→ 真实素材验证
→ 人工验收
→ Freeze
```

现在升级为：

```text
Contract 完成
→ 编码完成
→ 自动测试
→ 真实素材测试
→ 人工验收
→ Feature 文档更新
→ Session Handoff 写完
→ PROJECT_STATE 更新
→ Freeze
→ 才允许进入下一个 Feature
```

任何一项缺失，都不能标记 STABLE。

---

## 13. 每次小改动也必须留痕

并不是每次小改动都必须新建 Feature，但只要改了项目代码，至少要：

- 更新当前 Feature Change Log
- 更新 session handoff
- 若影响当前状态，更新 PROJECT_STATE

如果只是讨论、分析，没有修改代码或项目规则，可以不生成开发 session 文档。

---

## 14. 目标

最终仓库应该满足：

> 任意一个新 AI Agent 在没有历史聊天记录的情况下，能够在 10–15 分钟阅读仓库文档后准确恢复项目上下文，并继续当前 Feature，而不是重新从 Feature 01 分析。