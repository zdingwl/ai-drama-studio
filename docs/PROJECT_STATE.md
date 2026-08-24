# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: none（等待用户开始 F03）
F01 — 创建项目: STABLE / FROZEN
F02 — 上传原视频: STABLE / FROZEN
Stable Features: F01, F02
Frozen Features: F01, F02
Next Feature: F03 — 视频预处理（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建、切换、删除、重命名分支，也不创建或操作 PR。

---

# 当前恢复顺序

新对话继续开发时按以下顺序读取：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ 当前要开发 Feature 的 Contract / Function Contracts
→ 最新相关 docs/sessions/*.md
```

F01 / F02 已冻结，不再以它们开发阶段 Contract 顶部的旧状态字段作为当前 Feature 状态；冻结快照优先级更高。

---

# F01 冻结基线

权威快照：

```text
docs/features/F01-stable-snapshot.md
```

F01 冻结：

```text
Project ID = PROJECT_<UUID4_HEX>
app.db
projects 基础表和字段语义
Project Workspace
project.json V1
创建 / 列表 / 打开 API
creating → ready
固定语言/地区选择 + 后端白名单
正式 StudioShell UI 基线
```

后续 Feature 只能兼容性扩展；改变 F01 冻结 Contract 必须先 Change Request。

---

# F02 冻结基线

用户于 2026-08-24 明确确认：

```text
测试通过
```

因此：

```text
F02 = STABLE / FROZEN
```

权威冻结快照：

```text
docs/features/F02-stable-snapshot.md
```

历史规划 / 实现文档：

```text
docs/features/F02-upload-source-video.md
docs/features/F02-function-contracts.md
docs/features/F02-implementation-log.md
```

其中冻结状态、最终 Contract 和后续变更规则以 `F02-stable-snapshot.md` 为准。

---

# F02 冻结能力

完整闭环：

```text
项目进入“视频导入”
→ 选择 / 拖拽本地视频
→ 导入前允许重新选择
→ multipart 上传到本机 FastAPI
→ 1 MiB 分块写 staging
→ 同时计算 file_size_bytes + SHA-256
→ FFprobe 验证真实视频并读取基础媒体信息
→ staging 发布成正式 Source 原片
→ source_videos = ready
→ 页面展示 metadata
→ 软件重启后仍可读取
```

Source Contract：

```text
1 Project → 0 或 1 个 Source Video
Source ID = SOURCE_<32位UUID4小写hex>
ready 后只读，不提供替换/删除
```

正式 Workspace：

```text
<workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

导入 staging：

```text
<workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

---

# F02 Database / Time Contract

F02 新增：

```text
0002_create_source_videos
source_videos
```

状态：

```text
importing
ready
```

冻结时间规则：

```text
duration_us           integer microseconds
source_start_time_us  integer microseconds / nullable
fps_num / fps_den     rational FPS
```

ready 前数据库 CHECK 强制核心媒体 metadata 完整合法。

---

# F02 Core Functions / API

冻结 6 个核心函数：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

冻结 2 个 API：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

Controller 继续保持：

```text
HTTP → Business → Response
```

不直接 SQL、写文件、Hash、FFprobe 或 Recovery。

---

# F02 Recovery / Safety

冻结规则：

```text
Final 发布前失败
→ 只清理本 Source staging + importing row

Final 已发布但 DB ready 失败
→ 保留 final + importing
→ 启动 Recovery 恢复

未知文件 / 归属不明确 / 损坏 final
→ 保留现场，不递归删除
```

Ready Source 不能被后续 Feature 覆盖。

已有 `app.db` 做 pending Migration 时继续遵守：

```text
SQLite Connection.backup()
→ backup 成功
→ Alembic upgrade
```

---

# F02 验收基线

开发自动验证记录：

```text
27 passed
```

覆盖 F01 Regression + F02 Migration / Source ID / streaming / SHA / FFprobe / import / GET / duplicate / rollback / Recovery / API。

开发环境还完成真实媒体技术链路：

```text
视频
→ multipart
→ staging
→ FFprobe
→ final
→ DB ready
→ GET
```

用户随后在 Windows 本机完成实际测试并明确确认通过，所以 F02 User Acceptance Gate 已关闭。

---

# F03 状态

```text
F03 — 视频预处理
Status: NOT STARTED
```

未经用户明确说“开始”或等价指令，不自动开发 F03。

F03 后续只能以 F01 + F02 两个冻结快照为上游基线，特别不能：

```text
覆盖 F02 original.<ext>
改变 Source ID
把 Proxy 时间直接当 Source Timeline
把 float 秒替代整数微秒权威时间
绕过 Source Video 的只读 Contract
```

---

# Frozen Change Rule

F01 / F02 冻结后，如确实需要改变既有 Contract：

```text
Change Request
→ 影响分析
→ 数据迁移 / V2 设计
→ 用户明确批准
→ 实现
→ F01 + F02 Regression
```

Agent 不能因为后续 Feature 开发方便而静默修改冻结规则。

## 最近更新时间

- 日期：2026-08-24 10:44 +08:00
- 状态：用户确认 F02 测试通过；F02 正式 STABLE / FROZEN；等待用户决定是否开始 F03。
