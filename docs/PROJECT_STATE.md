# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细 Contract / Function Contract / Database Dictionary / Session 记录放在 `docs/features/` 与 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main

F01 — 创建项目:     STABLE / FROZEN
F02 — 上传原视频:   STABLE / FROZEN
F03 — 视频预处理:   STABLE / FROZEN
F04 — 自动拉片:     READY_FOR_REVIEW（NOT FROZEN）
F05 — 镜头人工修正: IN DEVELOPMENT / READY FOR LOCAL TEST

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
→ docs/features/F04-function-contracts.md
→ docs/features/F04-database-dictionary.md
→ docs/features/F05-shot-workbench.md
→ docs/features/F05-function-contracts.md
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

用户真实视频第一次成功运行得到：

```text
31 Shot Candidates
30 Cuts
1659 PTS Aligned Frames
66.360s Source Range
```

第一次 Detection Run 保存的 runtime：

```text
PyTorch 2.5.1+cpu
Device: cpu
```

用户随后通过当前项目 venv 实际确认：

```text
PyTorch 2.5.1+cu124
CUDA available: True
CUDA runtime: 12.4
GPU: NVIDIA GeForce RTX 3060 Ti
```

F04 已有显式“重新自动拉片”安全重跑：旧 READY 保留到新结果完整成功后再原子替换。

F04 仍需：

```text
重启后端
→ 在进入 F05 前执行一次 CUDA rerun
→ 页面确认 detector_device=cuda / torch=2.5.1+cu124
→ 人工检查明显切镜质量
```

然后才能创建 F04 Stable/Frozen Snapshot。

### 重要顺序

F05 初始化会保存 `source_detection_id` 并开始生产级 Final Shot 工作。为了保证追溯，一旦当前项目存在 F05 `shot_edit_sets`：

```text
F04 rerun -> SHOT_DETECTION_RERUN_CONFLICT
```

因此**同一个现有测试项目如果还要做 F04 CUDA rerun，必须先 rerun，再第一次进入 F05**。

---

# F05 正式目标

F05 不做普通结果表，而是三栏生产工作台：

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

浏览器播放器与 FFmpeg `-ss` 都使用媒体相对时间：

```text
relative_seconds = (source_us - edit_set.source_start_us) / 1_000_000
```

禁止把 Source absolute timestamp 直接当 `video.currentTime`。

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

confirmed 后 F05 写接口拒绝修改。

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

公开职责：

```text
initialize_shot_workbench()  F04 Candidate -> Final Shot Draft
get_shot_workbench()         读取并验证完整 Final Timeline
adjust_shot_boundary()       同时移动相邻两 Shot 的公共边界
split_final_shot()           拆分 / 新增镜头
merge_final_shots()          合并 / 删除公共边界
confirm_final_shots()        人工确认并锁定
get_workbench_proxy_path()   播放 F03 Proxy
render_workbench_frame()     按 Source 时间抽 UI 预览帧
```

详细输入/输出/为什么存在/不能做什么：

```text
docs/features/F05-function-contracts.md
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

已实现：

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

同时修正 F04 Migration Test：F04 只检查自己的表和约束，不再把历史 `0005` 当永久 Alembic head；当前 head 由 F05 Test 断言为 `0006_create_final_shots`。

---

# 当前验收边界

ChatGPT 工具容器无法 DNS clone GitHub，因此本轮没有声称已经执行全仓 pytest / npm typecheck / build。

用户 Windows 本机拉取最新 main 后必须执行：

```powershell
cd D:\ai-drama-studio
git pull

python -m pytest engine/tests -q

cd frontend
npm ci
npm run typecheck
npm run build
```

随后重启 8080 后端和前端。

### 推荐真实验收顺序

```text
A. 如果还没完成 F04 CUDA 验收：
   先进入 04 -> 重新自动拉片 -> 确认 cuda

B. 再进入 05 镜头修正：
   首次自动复制 31 个 Final Shot
   -> 左侧缩略图正常
   -> Proxy 可播放
   -> 点击 Shot 正确跳转
   -> 播放时高亮跟随
   -> 修改一个公共边界
   -> 在播放点拆分一个镜头
   -> 再合并回来
   -> 刷新页面数据仍存在

C. “确认 Final Shots”放到最后测试：
   点击确认后应变为 confirmed
   -> 再尝试边界/拆分/合并应被锁定
```

F05 当前：

```text
IN DEVELOPMENT / READY FOR LOCAL TEST
NOT STABLE
NOT FROZEN
```
