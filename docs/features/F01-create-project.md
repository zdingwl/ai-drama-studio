# Feature 01 — 创建项目（Create Project）

> F01 已由用户完成目标 Windows 环境测试并明确验收通过。
>
> 当前状态：`STABLE / FROZEN`  
> 验收时间：`2026-08-23 22:34 +08:00`  
> Frozen Snapshot：`docs/features/F01-stable-snapshot.md`
>
> Git：按用户要求直接维护 `main`，不得擅自新建/切换分支或 PR。

## 0. 一句话目标

用户填写项目基础信息后，系统把项目保存到 SQLite，并创建独立 Workspace 和 `project.json`；软件关闭重启后，项目仍能在首页看到并重新打开。

该目标已经完成并由用户验收通过。

---

# 1. F01 最终范围

已完成：

```text
Vue 3 前端工作台
FastAPI 后端
应用级 app.db
projects 表
创建项目
项目列表
打开项目
Workspace/project.json
creating 简单恢复
固定语言/地区下拉 + API 白名单
正式深色 UI Design System
桌面端可读字号
中文业务注释
目标环境测试
用户验收
```

明确不属于 F01：视频上传、FFmpeg/FFprobe、Episode、Asset、Shot、人物、对白、Scene、演员库、AI/Provider、GPU、TTS、Lip Sync、项目删除/重命名/归档/导入导出、复杂 Repair UI、Electron。

F02 前不写任何上传原视频业务。

---

# 2. 数据与文件 Contract

应用数据库：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

测试可用 `AI_DRAMA_APP_DATA_DIR` 覆盖。

默认 Workspace Root：

```text
%USERPROFILE%/AI Drama Studio Projects/
```

Project ID：

```text
PROJECT_<32位UUID4小写hex>
```

Workspace：

```text
<workspace_root>/<project_id>/project.json
```

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

F01 不提前创建媒体目录。

以上 Contract 已冻结；详细冻结语义见 `F01-stable-snapshot.md`。

---

# 3. Database Dictionary

F01 只有一张业务表：`projects`。

| Field | Type | Nullable | Default | 业务作用 |
|---|---|---:|---|---|
| `id` | TEXT PK | No | - | 稳定项目业务 ID |
| `name` | TEXT | No | - | 用户看到的项目名称，同名允许 |
| `source_language` | TEXT | Yes | NULL | 原片语言；空表示未确认 |
| `target_language` | TEXT | No | - | 目标语言 |
| `target_region` | TEXT | No | - | 本土化目标地区 |
| `workspace_path` | TEXT | No | - | 项目 Workspace 绝对路径 |
| `project_format_version` | INTEGER | No | 1 | Workspace/project.json 格式版本 |
| `status` | TEXT | No | creating | 只允许 creating / ready |
| `created_at` | DATETIME | No | - | 项目创建时间 |
| `last_opened_at` | DATETIME | Yes | NULL | 最近成功进入 Workspace 时间 |

约束：

```text
PRIMARY KEY(id)
UNIQUE(workspace_path)
CHECK(status IN ('creating', 'ready'))
```

Migration：`engine/migrations/versions/0001_create_projects.py`。

---

# 4. 固定语言 / 地区 Contract

固定格式数据不允许自由输入。

前端：

```text
source_language  下拉，可选自动识别
target_language  下拉，必选
target_region    下拉，必选
```

语言代码：

```text
zh en ja ko es pt fr de id th vi
```

地区代码：

```text
US GB JP KR ES BR FR DE ID TH VN TW SG
```

后端 `CreateProjectRequest` 使用白名单 Schema 再做一次独立校验，防止绕过前端写入非标准值。

---

# 5. API Contract

```text
GET  /api/health
GET  /api/projects
POST /api/projects                  # 201 Created
POST /api/projects/{project_id}/open
```

Controller 只负责 HTTP → Schema → Business → Response，不直接 SQL、mkdir、写 `project.json` 或生成 ID。

统一错误 envelope：

```json
{
  "error": {
    "code": "PROJECT_WORKSPACE_INVALID",
    "message": "项目保存位置不可创建或不可写"
  }
}
```

---

# 6. 创建与恢复

创建流程：

```text
校验输入
→ generate_project_id()
→ DB status=creating 并提交
→ create_project_workspace()
→ project.json 原子写入
→ DB status=ready + last_opened_at
```

失败安全边界：

- Workspace 创建失败：删除本次 creating 行；
- 已完整写好 Workspace、但最终 DB 更新失败：保留 Workspace + creating，交给启动恢复；
- 不递归删除 Workspace Root；
- 不覆盖已存在 Project 目录；
- 未知用户文件永远不自动删除。

`recover_creating_projects()`：完整 Workspace 转 ready；明确缺失/可安全清理的半成品删除；未知文件保留现场。

---

# 7. 最终实现

后端核心函数：

```text
get_app_data_path()
generate_project_id()
init_database()
create_project_workspace()
create_project()
list_projects()
open_project()
recover_creating_projects()
create_app()
```

Controller：

```text
health_api()
list_projects_api()
create_project_api()
open_project_api()
```

前端核心动作：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

正式页面：

```text
StudioShell.vue
ProjectHome.vue
CreateProjectDialog.vue
ProjectCard.vue
ProjectWorkspace.vue
```

卡片点击只导航；Workspace 页面统一调用 `openProject()`，因此卡片点击、刷新、直接 URL 都只调用一次后端 `/open`。

---

# 8. 验收与测试结论

开发过程已完成后端自动测试、API 联调、CORS 修复、固定字段后端校验、正式 UI 重构和桌面字号修正。

用户最终在 Windows 本机完成实际测试，并明确确认：

```text
可以，测试也通过，没问题了。
```

因此最终状态：

```text
Feature Status = STABLE / FROZEN
Verification Gate = PASSED BY USER
User Acceptance = PASSED
```

后续修改共享代码如果影响 F01，必须执行 F01 Regression。

---

# 9. Frozen Change Rule

F01 的 Input / Output / API / 核心 DB 字段语义 / Project ID / Workspace / project.json V1 / Status / Error Contract 已冻结。

如果以后确实必须改变：

```text
Change Request
→ 影响分析
→ Additive Change / Adapter / V2 / Migration
→ 回归方案
→ 用户明确批准
→ 修改
```

禁止 F02 及后续 Feature 静默改变 F01 V1。

---

# 10. 下一步

```text
F01 已完成。
F02 — 上传原视频：NOT STARTED。
```

只有用户明确要求开始下一阶段后，才进入 F02 Contract 规划/开发。
