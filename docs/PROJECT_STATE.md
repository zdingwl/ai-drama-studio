# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细 Contract / Function Contract / Database Dictionary / Stable Snapshot / Session 记录放在 `docs/features/` 与 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main

F01 — 创建项目:     STABLE / FROZEN
F02 — 上传原视频:   STABLE / FROZEN
F03 — 视频预处理:   STABLE / FROZEN
F04 — 自动拉片:     STABLE / FROZEN
F05 — 镜头人工修正: STABLE / FROZEN

Current Feature: none
Next Planned Feature: F06 — 人物对白
```

Stable Snapshots：

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
docs/features/F03-stable-snapshot.md
docs/features/F04-stable-snapshot.md
docs/features/F05-stable-snapshot.md
```

---

## 恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-stable-snapshot.md
→ docs/features/F04-stable-snapshot.md
→ docs/features/F05-stable-snapshot.md
→ docs/features/F05-shot-workbench.md
→ docs/features/F05-function-contracts.md
→ docs/features/F05-database-dictionary.md
→ 最新 docs/sessions/*.md
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建/切换/删除分支，不创建 PR。

---

# F04 冻结事实

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

真实 Windows 本机验收：

```text
31 Shot Candidates
30 Cuts
1659 PTS Aligned Frames
66.360s Source Range
Device: cuda
PyTorch: 2.5.1+cu124
GPU: NVIDIA GeForce RTX 3060 Ti
```

冻结规则：

```text
Source Domain integer microseconds
[start_us, end_us)
禁止 frame_index / fps 作为正式时间
shot_candidates.detected_* 永远只读
普通重复 POST 不覆盖 READY
显式 rerun 先完整计算、后事务原子替换
F05 已存在 shot_edit_sets 后禁止 F04 rerun
```

权威文档：

```text
docs/features/F04-stable-snapshot.md
```

---

# F05 冻结事实

F05 是三栏 Final Shot 工作台：

```text
左：Final Shot 列表 / 缩略图 / 时间 / 当前 Shot 高亮
中：F03 Proxy 播放器 / Shot Timeline / 5 关键帧
右：Final Start/End / 拆分 / 合并 / 确认 / 语义占位
```

核心关系：

```text
F04 shot_candidates = Auto Evidence（只读）
F05 final_shots      = 后续生产级 Shot
```

Final Shot ID：

```text
SHOT_<UUID4>
```

当前真实测试项目：

```text
31 Final Shots
shot_edit_sets.status = confirmed
```

confirmed 后边界 / 拆分 / 合并全部锁定。

---

## F05 Time Contract

```text
Source Domain integer microseconds
[start_us, end_us)
first.start == edit_set.source_start_us
last.end == edit_set.source_end_us
prev.end == next.start
ordinal = 1..N
无 gap
无 overlap
```

播放器 / FFmpeg：

```text
relative_seconds = (source_us - edit_set.source_start_us) / 1_000_000
```

---

## F05 已冻结的真实回归修复

### 1. 缩略图与左侧跟随

```text
缩略图取镜头中间位置
当前 Shot 自动高亮
播放跨 Shot 自动切换
左侧自动跟随并保留上下可视空间
```

### 2. 播放器 / 预览调度

```text
Proxy metadata / 播放优先
当前 Shot 5 张关键帧 = 高优先级，播放中允许串行加载/生成
整集缩略图 = 低优先级，播放期间暂停
暂停/结束后继续补齐缩略图
```

禁止同一 Shot 并发启动多个 FFmpeg 关键帧进程。

### 3. Alembic 并发

真实 Windows 曾出现：

```text
render_workbench_frame
→ init_database
→ alembic.command.upgrade
→ KeyError: 'config'
```

冻结修复：

```text
init_database()
→ 进程级 RLock
→ 每个 database path 当前进程只执行一次 Migration
→ 成功后加入 initialized set
→ 后续请求直接复用 app.db
```

回归测试：

```text
engine/tests/unit/test_database_concurrency.py
```

### 4. 关键帧缓存

```text
<Project Workspace>/.cache/f05/frames/<source_time_us>.jpg
```

规则：

```text
缓存存在且非空 -> 直接返回，禁止重新 FFmpeg
边界没变       -> 原时间点持续复用
边界变化       -> 只补新 source_time_us
```

HTTP：

```text
Cache-Control: private, max-age=31536000, immutable
```

缓存复用测试会在 JPEG 已存在时强制禁止 `subprocess.run()`。

---

## F05 Database / API

Migration：

```text
0006_create_final_shots
```

表：

```text
shot_edit_sets
final_shots
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

权威冻结文档：

```text
docs/features/F05-stable-snapshot.md
```

---

# 后续边界

F05 不负责：

```text
人物识别
角色身份
Whisper ASR
说话人绑定
场景识别
景别 / 机位 / 运镜 / 动作 VLM
Prompt 编译
视频生成
QC
```

这些能力从 F06 开始必须建立在冻结的 Final Shot ID 和 Final Timeline 上。

当前结论：

```text
F01-F05 = STABLE / FROZEN
F06      = NOT STARTED
```
