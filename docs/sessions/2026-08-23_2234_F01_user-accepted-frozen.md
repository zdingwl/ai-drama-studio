# Session Handoff — F01 用户验收通过并冻结

时间：2026-08-23 22:34 +08:00  
分支：main（未创建新分支）

## 用户最终确认

用户在 Windows 本机完成 F01 实际运行和测试后明确表示：

```text
可以，测试也通过，没问题了。
```

该表述视为 F01 正式人工验收通过。

## 状态变化

```text
F01
IN_PROGRESS / VERIFICATION_PENDING
→ STABLE / FROZEN
```

Agent 没有擅自提前冻结；本次冻结由用户明确验收触发，符合 `docs/DATA_AND_FREEZE_RULES.md`。

## 新增 Frozen Snapshot

```text
docs/features/F01-stable-snapshot.md
```

冻结内容包括：

```text
Input Contract
Output Contract
Project ID
projects 核心字段
Workspace/project.json V1
API Contract
status enum
error envelope / 主要错误语义
固定语言/地区下拉 + API 白名单
创建/恢复安全边界
F01 正式 UI 交互基线
Regression Baseline
```

## F01 最终范围

已经验收：

```text
创建项目
→ 保存到 app.db
→ 创建独立 Workspace/project.json
→ 首页项目列表
→ 重启后仍存在
→ 历史项目可重新打开
```

同时完成：

```text
深色正式工作台 UI
固定语言/地区下拉
后端白名单校验
本机 CORS 开发端口兼容
桌面端可读字号修正
```

F01 仍然没有任何 F02 上传原视频业务。

## 后续开发纪律

F02 及以后 Feature 可以依赖 F01 Frozen Contract，但不得静默改变：

```text
PROJECT_<UUID4_HEX> ID 规则
projects 现有字段语义
creating / ready
app.db 作为应用级项目索引
<workspace_root>/<project_id>/project.json
project_format_version = 1
现有 Project API 行为
固定错误 envelope
```

如必须破坏兼容：

```text
Change Request
→ 影响分析
→ Migration / Adapter / V2
→ 用户明确批准
→ 修改
→ F01 Regression
```

## 下一步

```text
F01 = STABLE / FROZEN
F02 = NOT STARTED
```

不要自动开始 F02。只有用户明确要求“开始下一阶段 / 开始 F02 / 继续开发”后，才进入 F02 Contract 规划。
