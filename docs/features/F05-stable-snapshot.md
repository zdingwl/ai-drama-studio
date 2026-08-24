# F05 Stable Snapshot — 镜头人工修正 / 三栏拉片工作台

状态：`STABLE / FROZEN`  
冻结日期：2026-08-24  
Official Baseline：`main`

## 1. 冻结结论

F05 已在 Windows 本机真实项目中完成最终回归，用户明确确认通过。

当前真实项目已经完成：

```text
31 Final Shots
shot_edit_sets.status = confirmed
```

F05 从此作为后续人物、对白、Scene、镜头语义、生成与 QC 的稳定镜头时间轴来源。

---

## 2. 上游与身份

```text
F04 shot_candidates
→ F05 initialize
→ shot_edit_sets
→ final_shots
```

F04 `shot_candidates.detected_*` 永远保持只读 Auto Evidence。

F05 Final Shot ID：

```text
SHOT_<UUID4>
```

冻结身份规则：

```text
普通边界调整 -> Final Shot ID 不变
拆分           -> 左段保留原 ID，右段新建 ID
合并           -> 左段保留 ID，右段 ID 删除
```

后续 Feature 必须关联 Final Shot ID，不得直接把 F04 Candidate ID 当作生产级镜头身份。

---

## 3. 时间 Contract

权威时间：

```text
Source Domain integer microseconds
```

区间：

```text
[start_us, end_us)
```

整套 Final Timeline 必须满足：

```text
first.start == edit_set.source_start_us
last.end == edit_set.source_end_us
prev.end == next.start
ordinal == 1..N
start < end
无 gap
无 overlap
```

移动公共边界必须同时修改：

```text
left.final_end_us
right.final_start_us
```

浏览器播放器 / FFmpeg 使用媒体相对时间：

```text
relative_seconds = (source_us - edit_set.source_start_us) / 1_000_000
```

禁止把 Source absolute timestamp 直接作为 `video.currentTime` 或 FFmpeg `-ss`。

---

## 4. Database

Migration：

```text
0006_create_final_shots
```

冻结表：

```text
shot_edit_sets
final_shots
```

Edit Set 状态：

```text
editing
confirmed
```

`confirmed` 后：

```text
边界修改 -> 拒绝
拆分     -> 拒绝
合并     -> 拒绝
```

F05 V1 不提供静默 unconfirm。

---

## 5. 后端冻结职责

核心模块：

```text
engine/app/shot_workbench.py
```

公开业务职责：

```text
initialize_shot_workbench()  F04 Candidate -> Final Shot Draft
get_shot_workbench()         读取并验证完整 Final Timeline
adjust_shot_boundary()       移动相邻 Shot 公共边界
split_final_shot()           拆分 / 新增镜头
merge_final_shots()          合并 / 删除公共边界
confirm_final_shots()        最终确认并锁定
get_workbench_proxy_path()   提供 F03 Proxy 播放路径
render_workbench_frame()     Source 时间 -> UI JPEG 预览帧
```

这些函数不得扩展成 F06+ 的人物识别、ASR、说话人绑定、Scene/VLM 或生成逻辑。

---

## 6. API

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

## 7. 三栏工作台冻结交互

Route：

```text
/projects/:projectId/shot-workbench
```

布局：

```text
左：Final Shot 列表 / 缩略图 / 时间 / 当前 Shot 高亮
中：F03 Proxy 播放器 / Shot Timeline / 5 关键帧
右：Final Start/End / 拆分 / 合并 / 来源追溯 / 确认 / 后续语义占位
```

已通过真实回归：

```text
Proxy 正常播放 / seek
点击 Shot 跳转播放器
播放跨 Shot 自动切换当前 Shot
左侧当前 Shot 自动跟随并保留可视空间
缩略图正常显示
当前 Shot 5 张关键帧播放中可串行加载/生成
整集缩略图播放中暂停、暂停后继续补齐
confirmed 后编辑按钮保持锁定
```

---

## 8. 关键帧 / 缩略图缓存 Contract

UI 预览缓存：

```text
<Project Workspace>/.cache/f05/frames/<source_time_us>.jpg
```

冻结规则：

```text
缓存 JPEG 已存在且非空
→ 直接返回
→ 禁止再次启动 FFmpeg

Final Shot 边界未变化
→ 原 source_time_us 图片持续复用

边界调整 / 拆分 / 合并
→ 只为新的 source_time_us 补图
→ 其它 Shot 缓存不重生成
```

HTTP 缓存：

```text
Cache-Control: private, max-age=31536000, immutable
```

UI cache 不是正式业务资产，人工删除后允许重建；后续正式 VLM 分析资产应另行定义，不得偷偷改变 F05 UI cache 语义。

---

## 9. 播放器 / 预览资源调度 Contract

正式优先级：

```text
1. Proxy 播放器优先取得 metadata / 播放资源
2. 当前 Shot 5 张关键帧 = 高优先级，播放中允许，但必须串行
3. 整集 Shot 缩略图 = 低优先级，播放期间暂停
4. 暂停 / 结束后继续后台缩略图补齐
```

禁止为同一 Shot 并发启动多个 FFmpeg 关键帧进程。

---

## 10. 数据库并发修复冻结事实

真实 Windows 回归曾出现：

```text
render_workbench_frame
→ init_database
→ alembic.command.upgrade
→ KeyError: 'config'
```

根因：多个 FastAPI worker thread 同时进入 Alembic `EnvironmentContext`。

冻结修复：

```text
init_database()
→ 进程级 RLock
→ 每个 database path 当前进程只执行一次 Migration
→ 成功后记入 initialized set
→ 后续业务请求直接复用 app.db
```

回归测试：

```text
engine/tests/unit/test_database_concurrency.py
```

同时存在缓存复用测试，保证已有 JPEG 时禁止再次调用 FFmpeg。

---

## 11. Scope Boundary

F05 不负责：

```text
人物识别 / 角色身份
Whisper ASR
说话人绑定
场景识别
景别 / 机位 / 运镜 / 动作 VLM 分析
生成 Prompt
视频生成
QC
```

这些能力由后续 Feature 在冻结的 Final Shot ID 和 Final Timeline 上继续建设。

---

## 12. Freeze Rule

从本 Snapshot 生效后：

```text
F05 = STABLE / FROZEN
```

后续允许做不改变 Contract 的兼容性缺陷修复；任何改变以下语义的改动必须先解除冻结并重新评审：

```text
Final Shot ID
Source Timeline
confirmed 锁定
F04 Auto Evidence 只读
关键帧缓存命中不重生成
播放器 / 预览调度优先级
```
