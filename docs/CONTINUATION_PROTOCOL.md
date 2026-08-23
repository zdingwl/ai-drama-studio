# AI Drama Studio — 跨对话持续开发协议

## 1. 目的

聊天窗口可能超限、新对话可能没有历史上下文，也可能由不同 Agent/开发者连续接手。

因此：

> 项目真实上下文必须保存在 GitHub，而不是只存在聊天记录中。

新对话应该能够依赖 `main` 中的文档和代码，直接继续当前 Feature，而不是重新从项目定位开始分析。

---

## 2. main 是正式恢复基线

默认：

```text
main = 最近一次用户已经确认的正式项目状态
```

未合并分支只代表进行中的工作。

只有当用户明确说“继续某个 PR/分支”时，新对话才以该分支为工作基线。

---

## 3. 新对话最短读取顺序

不要一开始读取全部 docs。

强制最短路径：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. 当前 docs/features/FXX-*.md
5. 最新与当前 Feature 相关的 docs/sessions/*.md
6. 根据 Feature 中的 Rule References / P0 Checklist 读取必要的详细规则
7. 查看当前代码 / git diff
8. 从 Next Action 继续
```

这样既能恢复上下文，也避免新聊天被规则文档提前占满。

---

## 4. PROJECT_STATE.md 的职责

它只保存“现在是什么状态”，至少包括：

- 当前 Feature；
- Feature 状态；
- 已 Stable/Frozen Feature；
- 当前 branch/PR；
- 当前代码/DB 状态；
- 当前阻塞项；
- 已知 Bug；
- 已确认关键技术决策；
- 下一步唯一动作；
- 最新 Session Handoff。

历史流水账放 Session，不放 PROJECT_STATE。

---

## 5. Feature 文档是永久技术档案

每个 Feature 一份长期累积文档：

```text
docs/features/F01-create-project.md
docs/features/F02-upload-source.md
...
```

至少维护：

- Scope；
- User Flow；
- Input/Output/API/DB/File Contract；
- Database Dictionary；
- P0 Checklist；
- Code Map；
- 技术决策与原因；
- 测试/Regression/真实素材结果；
- Known Limitations；
- Change Log；
- Freeze Snapshot；
- 下一步。

Feature 文档不是一次性 PR 描述，而是该功能的长期真实档案。

---

## 6. Session Handoff

每一次实际开发结束创建：

```text
docs/sessions/YYYY-MM-DD_HHMM_FXX_topic.md
```

必须回答：

1. 本次目标；
2. 开始前状态；
3. 实际完成；
4. 修改文件；
5. API/DB/File 变化；
6. 技术决策；
7. 没有完成什么；
8. 测试和回归；
9. 当前 Bug/风险；
10. Contract 是否变化；
11. branch/commit/PR；
12. 下一步具体动作；
13. 新对话应该先读哪些文件。

禁止只写“今天完成某功能”。

---

## 7. 文档权威冲突

按 `SKILL.md` 中定义的权威顺序处理：

```text
用户已确认决策
→ Stable/Frozen Contract
→ SKILL/全局规则
→ 当前 Feature Contract
→ PROJECT_STATE
→ Session
→ 历史讨论
```

发现冲突必须显式说明。

---

## 8. Feature 状态权限

Agent 可以将工作推进到：

```text
READY_FOR_REVIEW
```

用户明确确认验收通过后才可以：

```text
STABLE / FROZEN
```

因此 Session Handoff 不能擅自写“已 Stable”，除非有用户明确验收记录。

---

## 9. 代码与文档是一个交付物

每次实际代码修改结束前至少：

```text
更新 Feature 文档
+ 更新 PROJECT_STATE
+ 新建 Session Handoff
```

如果涉及全局 Contract、技术规则或 Feature Sequence，再同步相关全局文档。

代码完成但文档没完成：

> 本次开发未完成。

---

## 10. 开发过程中立刻记录的变化

以下变化不能等会话最后凭记忆补：

- DB Schema/Migration；
- API Contract；
- Stable Contract 影响；
- 新依赖/模型/Provider；
- 环境版本变化；
- 时间轴/文件路径规则；
- Provider workaround；
- 真实素材异常；
- 临时兼容方案；
- P0 实现方式变化。

及时写入当前 Feature Implementation Notes。

---

## 11. 下一步必须可执行

禁止：

```text
下一步：继续优化项目
```

应写到可以直接执行，例如：

```text
下一步：打开 engine/api/projects.py，实现 POST /api/projects 的 workspace 创建事务与失败回滚，并补 F01-API-003 测试。
```

---

## 12. 目标

即使完全没有旧聊天记录，一个新 Agent 也应能：

```text
读取少量入口文档
→ 知道当前 Feature
→ 知道已经冻结什么
→ 知道为什么这样设计
→ 知道当前代码/数据库状态
→ 直接执行 Next Action
```

而不是重新从 Feature 01 或项目定位开始分析。
