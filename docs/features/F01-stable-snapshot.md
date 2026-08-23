# F01 — 创建项目 Stable / Frozen Snapshot

Feature ID: F01  
Feature Name: 创建项目  
Status: STABLE / FROZEN  
User Acceptance: PASSED  
Accepted At: 2026-08-23 22:34 +08:00  
Official Baseline: main

> 本 Snapshot 是 F01 验收通过后的冻结 Contract。F02 及后续 Feature 可以读取和扩展 F01，但不得静默改变下面已经冻结的语义。

---

## 1. 用户验收结论

用户在 Windows 本机完成实际运行和测试，并明确确认：

```text
可以，测试也通过，没问题了。
```

因此按 `docs/DATA_AND_FREEZE_RULES.md`，F01 正式进入：

```text
STABLE / FROZEN
```

---

## 2. F01 冻结目标

F01 只保证下面这个完整闭环：

```text
创建项目
→ 保存项目
→ 首页能看到
→ 软件重启后仍存在
→ 可以重新打开
```

不包含视频上传及任何 F02 以后业务。

---

## 3. Frozen Input Contract

创建项目输入：

```text
name             必填，用户项目名称，1–100 字符，同名允许
source_language  可空；为空表示暂不指定/后续识别
target_language  必填，固定标准代码
target_region    必填，固定标准代码
workspace_root   可空；为空使用默认目录
```

固定语言代码：

```text
zh en ja ko es pt fr de id th vi
```

固定地区代码：

```text
US GB JP KR ES BR FR DE ID TH VN TW SG
```

UI 使用下拉框；API 也必须独立校验固定代码。前端自由输入不能重新成为正式入口。

---

## 4. Frozen Output Contract

项目基础输出：

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

---

## 5. Frozen Project ID Rule

```text
PROJECT_<32位UUID4小写hex>
```

Project ID：

- 创建后永不因名称变化而改变；
- 不使用项目名称生成；
- 作为 DB 主键和 Workspace 目录名；
- 后续 Feature 必须引用该稳定 ID。

---

## 6. Frozen Database Contract

应用级数据库：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

F01 唯一业务表：

```text
projects
```

冻结字段：

```text
id                      TEXT PRIMARY KEY
name                    TEXT NOT NULL
source_language         TEXT NULL
target_language         TEXT NOT NULL
target_region           TEXT NOT NULL
workspace_path          TEXT NOT NULL UNIQUE
project_format_version  INTEGER NOT NULL
status                  TEXT NOT NULL
created_at              DATETIME NOT NULL
last_opened_at          DATETIME NULL
```

冻结状态枚举：

```text
creating
ready
```

后续可以 Additive 增加字段，但不得静默改变这些字段现有语义。

---

## 7. Frozen Workspace / File Contract

默认 Workspace Root：

```text
%USERPROFILE%/AI Drama Studio Projects/
```

项目目录：

```text
<workspace_root>/<project_id>/
└── project.json
```

F01 不提前创建媒体目录。

`project.json` V1：

```json
{
  "project_id": "PROJECT_86f767c94f2c4f96a1676ce36f615406",
  "project_format_version": 1,
  "name": "测试短剧",
  "source_language": "zh",
  "target_language": "en",
  "target_region": "US"
}
```

冻结规则：

- `project_format_version = 1`；
- 不覆盖已存在 Project 目录；
- 不递归删除 Workspace Root；
- 未知用户文件不能自动删除；
- `project.json` 与 DB 的 `project_id` 必须一致才能打开。

---

## 8. Frozen API Contract

```text
GET  /api/health
GET  /api/projects
POST /api/projects                  → 201 Created
POST /api/projects/{project_id}/open
```

Controller 固定职责：

```text
HTTP Request
→ Schema 校验
→ 调用项目业务函数
→ Response
```

Controller 不直接 SQL、不 mkdir、不写 `project.json`、不生成 Project ID。

固定错误 envelope：

```json
{
  "error": {
    "code": "PROJECT_...",
    "message": "..."
  }
}
```

已冻结的主要错误语义包括：

```text
PROJECT_NAME_REQUIRED
PROJECT_NAME_TOO_LONG
PROJECT_TARGET_LANGUAGE_REQUIRED
PROJECT_TARGET_REGION_REQUIRED
PROJECT_SOURCE_LANGUAGE_UNSUPPORTED
PROJECT_TARGET_LANGUAGE_UNSUPPORTED
PROJECT_TARGET_REGION_UNSUPPORTED
PROJECT_REQUEST_INVALID
PROJECT_WORKSPACE_INVALID
PROJECT_CREATE_FAILED
PROJECT_NOT_FOUND
PROJECT_WORKSPACE_MISSING
PROJECT_MANIFEST_INVALID
```

---

## 9. Frozen Create / Recovery Behavior

创建：

```text
校验输入
→ 生成 Project ID
→ DB 写 creating
→ 创建 Workspace + project.json
→ DB 改 ready
→ 记录 last_opened_at
```

失败：

- Workspace 创建失败：本次 creating 记录不能冒充 ready；
- Workspace 已完整创建但 DB 最终更新失败：保留文件，交给启动恢复；
- 不能为了回滚误删未知用户文件。

启动恢复：

- 合法 creating + 完整 Workspace → ready；
- 明确缺失的无效 creating 记录可清理；
- 出现未知文件/无法确认归属 → 保留现场，不自动破坏用户数据。

---

## 10. Frozen UI / Interaction Contract

F01 使用正式 AI短剧工厂深色工作台 Design System，而不是白底 Demo。

当前正式页面：

```text
StudioShell.vue
ProjectHome.vue
CreateProjectDialog.vue
ProjectCard.vue
ProjectWorkspace.vue
```

固定格式字段：

```text
原片语言     下拉
目标语言     下拉
目标地区     下拉
```

桌面端字号已经按真实 1920px Windows 可读性调整，不再以设计稿缩略图中的 7–10px 正文作为实现基准。

F01 Project Workspace 只展示项目容器已就绪和后续流程占位，不提供 F02 视频上传功能。

---

## 11. Regression Baseline

后续任何影响 F01 的共享代码修改，至少必须回归：

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
前端创建项目流程
重启后项目仍存在
历史项目重新打开
```

F01 已由用户在目标 Windows 环境确认测试通过。

---

## 12. Frozen Change Rule

如果后续需要破坏性修改本 Snapshot 中任一 Contract：

```text
Change Request
→ 影响分析
→ 数据/API/文件兼容或迁移方案
→ 回归范围
→ 用户明确批准
→ 才能修改
```

优先使用：

```text
Additive Change
→ Adapter
→ V2 Contract
→ Migration
```

禁止后续 Feature 为了方便偷偷改掉 F01 V1。
