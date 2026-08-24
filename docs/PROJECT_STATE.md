# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细 Contract / Database Dictionary / Session 记录放在 `docs/features/` 与 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main

F01 — 创建项目:     STABLE / FROZEN
F02 — 上传原视频:   STABLE / FROZEN
F03 — 视频预处理:   STABLE / FROZEN
F04 — 自动拉片:     READY_FOR_REVIEW（NOT FROZEN）
F05 — 镜头人工修正: IN DEVELOPMENT

Current Feature: F05 — 三栏拉片工作台 / Final Shot
```

用户在 2026-08-24 明确要求开始 F05，因此允许在 F04 最终 GPU 重跑验收前提前开发 F05；这不等于 F04 已通过 Freeze Gate。

---

## 恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-stable-snapshot.md
→ docs/features/F04-auto-shot-detection.md
→ docs/features/F04-database-dictionary.md
→ docs/features/F05-shot-workbench.md
→ docs/features/F05-database-dictionary.md
→ 最新 docs/sessions/*.md
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建/切换/删除分支，不创建 PR。

---

# F04 当前事实

正式算法：

```text
F03 proxy.mp4
→ FFprobe 逐帧真实 PTS
→ TransNetV2 1.0.5
→ transition merge
→ 120ms debounce
→ Proxy -> Source integer microseconds
→ Shot Candidate
```

用户真实视频已成功得到：

```text
31 Shot Candidates
30 Cuts
1659 PTS Aligned Frames
66.360s Source Range
```

第一次运行保存的 runtime 是：

```text
PyTorch 2.5.1+cpu
Device: cpu
```

用户随后确认当前 Windows venv：

```text
PyTorch 2.5.1+cu124
CUDA available: True
GPU: NVIDIA GeForce RTX 3060 Ti
```

已增加显式“重新自动拉片”安全重跑：旧 READY 保留到新结果完整成功后再原子替换。

F04 仍需用户在重启后端后完成一次 CUDA rerun，并人工确认切镜质量，才能创建 Stable/Frozen Snapshot。

---

# F05 正式目标

F05 不再做普通结果表，而是三栏生产工作台：

```text
左：Final Shot 列表 / 缩略图 / 时间 / 当前 Shot 高亮
中：F03 Proxy 播放器 / Shot Timeline / 5 关键帧
右：Final Start/End / 拆分 / 合并 / 确认 / 后续语义占位
```

核心原则：

```text
F04 shot_candidates = Auto Evidence（永远只读）
F05 final_shots      = Human Final Draft / Final
```

F05 初始化时为每个 Candidate 创建新的稳定：

```text
SHOT_<UUID4>
```

这些 Final Shot ID 才是后续人物、对白、Scene、生成、QC 应关联的生产身份。

---

# F05 Time Contract

继续使用：

```text
Source Domain integer microseconds
[start_us, end_us)
```

必须始终满足：

```text
first.start == edit_set.source_start_us
last.end == edit_set.source_end_us
prev.end == next.start
ordinal = 1..N
无 gap
无 overlap
```

调整一个边界必须同时更新：

```text
left.final_end_us
right.final_start_us
```

拆分 = 新增镜头；合并 = 删除公共边界。F05 不为同一语义维护“新增/删除”第二套重复算法。

---

# F05 Database

Migration：

```text
0006_create_final_shots
```

新增：

```text
shot_edit_sets
final_shots
```

Edit Set：

```text
editing
confirmed
```

confirmed 后 F05 写接口必须拒绝修改。

详细字段语义：

```text
docs/features/F05-database-dictionary.md
```

---

# F05 Backend / API

核心业务：

```text
engine/app/shot_workbench.py
```

已实现：

```text
initialize_shot_workbench()
get_shot_workbench()
adjust_shot_boundary()
split_final_shot()
merge_final_shots()
confirm_final_shots()
get_workbench_proxy_path()
render_workbench_frame()
```

API：

```text
GET  /api/projects/{project_id}/shot-workbench
POST /api/projects/{project_id}/shot-workbench/initialize
POST /api/projects/{project_id}/shot-workbench/boundary
POST /api/projects/{project_id}/shot-workbench/split
POST /api/projects/{project_id}/shot-workbench/merge
POST /api/projects/{project_id}/shot-workbench/confirm
GET  /api/projects/{project_id}/shot-workbench/media/proxy
GET  /api/projects/{project_id}/shot-workbench/frame?source_time_us=...
```

F05 一旦初始化，F04 显式 rerun 会返回已有 `SHOT_DETECTION_RERUN_CONFLICT`，防止替换 Final Shot 正在追溯的 Auto Evidence。

---

# F05 Frontend

Route：

```text
/projects/:projectId/shot-workbench
```

主要文件：

```text
frontend/src/views/ShotWorkbench.vue
frontend/src/shot-workbench.css
frontend/src/types/shot-workbench.ts
frontend/src/api/shot-workbench.ts
frontend/src/stores/shot-workbench.ts
```

已接入：

```text
左侧 05 镜头修正导航
项目总览 F05 入口
Shot 缩略图列表
点击 Shot -> player seek
播放时间 -> 当前 Shot 自动高亮
按时长比例 Shot Timeline
首/25%/中/75%/尾关键帧
Final Start / End 公共边界编辑
播放点拆分
与前/后一镜合并
Final Shots 确认锁定
人物/场景/景别/运镜/动作/对白占位（不伪造结果）
```

---

# F05 Tests

新增：

```text
engine/tests/unit/test_database_migration_f05.py
engine/tests/unit/test_shot_workbench_f05.py
```

同时修正 F04 Migration Test：不再把历史 `0005` 当成永久 Alembic head；当前 head 由 F05 Test 断言为 `0006_create_final_shots`。

---

# 当前验收边界

ChatGPT 工具容器无法 DNS clone GitHub，因此本轮没有声称已经执行全仓 pytest / npm build。

用户 Windows 本机拉取最新 main 后必须执行：

```powershell
python -m pytest engine/tests -q

cd frontend
npm ci
npm run typecheck
npm run build
```

然后重启后端（8080）和前端，真实验收：

```text
项目总览 -> 05 镜头修正
-> 首次自动复制 31 个 Final Shot
-> 左侧缩略图正常
-> 视频可播放
-> 点击 Shot 正确跳转
-> 播放时高亮跟随
-> 修改一个公共边界
-> 拆分一个镜头
-> 合并回来
-> 刷新页面数据仍存在
-> 最后再测试 Confirm（确认后不可再编辑）
```

F05 当前状态：

```text
IN DEVELOPMENT / READY FOR LOCAL TEST
NOT STABLE
NOT FROZEN
```
