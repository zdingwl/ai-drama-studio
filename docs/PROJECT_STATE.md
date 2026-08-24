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
F05 — 镜头人工修正: READY FOR FINAL REGRESSION（NOT FROZEN）

Current Feature: F05 — 三栏拉片工作台 / Final Shot
```

F04 Stable Snapshot：

```text
docs/features/F04-stable-snapshot.md
```

F05 目前**没有 Stable Snapshot**。曾在用户点击 Final Shots 确认后短暂创建过 F05 Stable Snapshot，但随后真实页面发现播放器回归，因此已经删除该 Snapshot，必须重新通过最终回归后才能冻结。

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

真实 Windows 本机最终验收：

```text
31 Shot Candidates
30 Cuts
1659 PTS Aligned Frames
66.360s Source Range
Device: cuda
PyTorch: 2.5.1+cu124
GPU: NVIDIA GeForce RTX 3060 Ti
```

F04 已正式 `STABLE / FROZEN`。

冻结规则：

```text
Source Domain integer microseconds
[start_us, end_us)
禁止 frame_index / fps 作为正式时间
shot_candidates.detected_* 永远是只读 Auto Evidence
普通重复 POST 不覆盖 READY
显式 rerun 先完整计算、后事务原子替换
F05 已存在 shot_edit_sets 后禁止 F04 rerun
```

---

# F05 核心 Contract

F05 是三栏生产工作台：

```text
左：Final Shot 列表 / 缩略图 / 时间 / 当前 Shot 高亮
中：F03 Proxy 播放器 / Shot Timeline / 5 关键帧
右：Final Start/End / 拆分 / 合并 / 确认 / 后续语义占位
```

核心数据关系：

```text
F04 shot_candidates = Auto Evidence（永远只读）
F05 final_shots      = Human Final Draft / Final
```

Final Shot ID：

```text
SHOT_<UUID4>
```

这些 ID 才是后续人物、对白、Scene、生成、QC 应关联的生产身份。

时间 Contract：

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

播放器 / FFmpeg 媒体相对时间：

```text
relative_seconds = (source_us - edit_set.source_start_us) / 1_000_000
```

---

# F05 当前真实数据状态

用户已经在真实项目中点击：

```text
确认 Final Shots
```

因此当前测试项目的 `shot_edit_sets.status` 已为：

```text
confirmed
```

这意味着该项目的边界修改 / 拆分 / 合并已经按设计锁定。

注意：

```text
业务数据 confirmed ≠ Feature 代码 STABLE / FROZEN
```

由于确认后真实页面发现播放器/预览并发回归，F05 Feature 仍需最终回归验证。

---

# F05 已修复的真实回归

## 1. 缩略图破图 / 当前 Shot 不滚动

已改为：

```text
缩略图取镜头中间帧
前端队列加载
失败自动重试一次
当前 Shot 自动 scrollIntoView
```

## 2. 视频播放与预览抢资源

正式调度策略：

```text
播放器 Proxy metadata 优先
当前 Shot 5 张关键帧 = 高优先级，播放中也允许串行加载/生成
整集 Shot 缩略图 = 低优先级，播放期间暂停
暂停后继续补齐缩略图
```

禁止一个 Shot 同时并发启动多个 FFmpeg 关键帧进程。

## 3. Alembic `KeyError: 'config'`

真实 Windows 日志曾出现：

```text
render_workbench_frame
→ init_database
→ alembic.command.upgrade
→ KeyError: 'config'
```

根因：多个 FastAPI worker thread 同时调用 `init_database()`，Alembic `EnvironmentContext` 进程级代理不支持并发 upgrade。

已修：

```text
init_database()
→ 进程级 RLock
→ 每个数据库路径只在当前进程第一次执行 Migration
→ 成功后加入 initialized set
→ 后续请求直接返回 app.db Path
```

新增：

```text
engine/tests/unit/test_database_concurrency.py
```

## 4. 关键帧缓存

后端缓存：

```text
<Project Workspace>/.cache/f05/frames/<source_time_us>.jpg
```

规则：

```text
缓存文件存在且非空
→ 直接返回
→ 禁止再次运行 FFmpeg

边界没变
→ 原时间点永久复用

边界调整 / 拆分 / 合并
→ 只产生新 source_time_us
→ 只补新时间点
→ 其它镜头缓存不动
```

`GET /shot-workbench/frame` 已增加长期浏览器缓存：

```text
Cache-Control: private, max-age=31536000, immutable
```

新增防回归测试：

```text
test_render_workbench_frame_reuses_existing_cache_without_ffmpeg
```

测试会在缓存 JPEG 已存在时强制禁止 `subprocess.run()` 被调用。

---

# F05 Database / API

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

---

# F05 最终回归要求

用户 Windows 本机拉最新 `main`：

```powershell
cd D:\ai-drama-studio
git pull

.\.venv\Scripts\Activate.ps1
python -m pytest engine/tests -q

cd frontend
npm run typecheck
npm run build
```

因为数据库并发修复改了 Python，必须重启后端：

```powershell
cd D:\ai-drama-studio
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8080
```

最终页面回归：

```text
1. 打开已 confirmed 的 F05
2. Proxy 视频能正常播放 / seek
3. 播放跨 Shot 时左侧当前 Shot 自动高亮并滚动
4. 播放过程中当前 Shot 的 5 张关键帧可逐张出现
5. 播放过程中整集后台缩略图不会大量抢资源
6. 暂停后剩余缩略图继续补齐
7. 刷新页面后已缓存关键帧快速复用，不重新 FFmpeg 抽取
8. 后端不再出现 Alembic KeyError: 'config'
9. confirmed 状态下边界 / 拆分 / 合并继续保持锁定
```

全部通过后才能重新创建：

```text
docs/features/F05-stable-snapshot.md
```

当前结论：

```text
F05 READY FOR FINAL REGRESSION
NOT STABLE
NOT FROZEN
```
