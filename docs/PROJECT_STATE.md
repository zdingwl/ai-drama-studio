# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: none（F01 已完成；尚未开始 F02）
F01 — 创建项目: STABLE / FROZEN
Verification Gate: PASSED BY USER
READY_FOR_REVIEW: PASSED
Stable Features: F01
Frozen Features: F01
Next Feature: F02 — 上传原视频（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

未经用户明确要求，AI / Codex / Agent 不得新建、切换、删除、重命名分支，也不得擅自创建/关闭/合并/重定向 PR。

当前继续直接维护 `main`；用户尚未要求开始 F02。

---

# F01 权威文档

```text
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
docs/features/F01-stable-snapshot.md
```

其中 `F01-stable-snapshot.md` 是用户验收后的冻结 Contract，后续 Feature 不得静默改变其语义。

---

# F01 验收结论

F01 解决的完整闭环：

```text
创建项目
→ 保存项目
→ 首页能看到
→ 重启后还在
→ 能重新打开
```

用户已在 Windows 本机完成实际测试，并于 2026-08-23 22:34 +08:00 明确确认：

```text
可以，测试也通过，没问题了。
```

因此按 `docs/DATA_AND_FREEZE_RULES.md`：

```text
F01 = STABLE / FROZEN
```

---

# F01 已冻结关键 Contract

## 数据库

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

F01 唯一业务表：`projects`。

冻结字段：

```text
id
name
source_language
target_language
target_region
workspace_path
project_format_version
status
created_at
last_opened_at
```

状态：

```text
creating
ready
```

## Project ID

```text
PROJECT_<32位UUID4小写hex>
```

## Workspace

```text
<workspace_root>/<project_id>/project.json
```

默认根目录：

```text
%USERPROFILE%/AI Drama Studio Projects/
```

`project_format_version = 1`。

## API

```text
GET  /api/health
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

Controller 只负责 HTTP → Schema → 业务函数 → Response；不得直接 SQL、mkdir、写 `project.json`。

## 固定语言 / 地区

创建项目页面固定使用下拉，不允许自由输入不规范代码。

语言：

```text
zh en ja ko es pt fr de id th vi
```

地区：

```text
US GB JP KR ES BR FR DE ID TH VN TW SG
```

前端下拉 + 后端白名单双层保护。

## UI

F01 已采用正式深色 AI短剧工厂工作台 Design System：

```text
StudioShell.vue
ProjectHome.vue
CreateProjectDialog.vue
ProjectCard.vue
ProjectWorkspace.vue
```

桌面端字号已经按真实 Windows 1920px 可读性调整；不再以设计稿缩略图 7–10px 正文为实现基准。

---

# F01 回归基线

后续共享代码若影响 F01，必须至少回归：

```text
应用数据路径
SQLite/Alembic 初始化
Project ID
创建项目
固定语言/地区校验
Workspace/project.json
项目列表
打开项目
creating 恢复
CORS 本机开发端口
前端创建/打开流程
重启后项目仍存在
```

冻结后若必须改变 V1 Contract：

```text
Change Request
→ 影响分析
→ Migration / Adapter / V2
→ 用户确认
→ 修改
→ F01 Regression
```

---

# 当前下一步

```text
F01 已完成，不再继续修改。
F02 — 上传原视频 尚未开始。
```

只有用户明确要求“开始 F02 / 继续下一阶段”后，才进入 F02 Contract 规划或开发。

## 最近更新时间

- 日期：2026-08-23 22:34 +08:00
- 状态：用户确认 F01 测试通过且无问题；F01 已正式 STABLE / FROZEN；等待用户决定是否开始 F02。
