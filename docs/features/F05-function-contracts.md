# F05 — Function Contracts

> 目标：只看这份文档就能知道 F05 每个公开函数为什么存在。禁止把 SQL、播放器时间换算或 F04 自动证据修改散落到 Controller/UI。

## 后端核心 `engine/app/shot_workbench.py`

### `generate_shot_edit_set_id()`

**干嘛：** 创建一套人工镜头修正工作的稳定业务 ID。  
**输入：** 无。  
**输出：** `SHOT_EDIT_<UUID4>`。  
**为什么存在：** Edit Set 是整条 Final Shot 时间轴的容器，不应复用 Project ID 或 Detection ID。  
**不负责：** 不写 DB，不生成 Shot。

### `generate_final_shot_id()`

**干嘛：** 创建后续 Production Feature 使用的稳定 Final Shot ID。  
**输入：** 无。  
**输出：** `SHOT_<UUID4>`。  
**关键规则：** 普通边界调整不换 ID；拆分才新建右段 ID；合并保留左段 ID。  
**不负责：** 不使用 F04 Candidate ID 冒充 Final Shot ID。

### `initialize_shot_workbench(project_id)`

**干嘛：** 第一次进入 F05 时，把 F04 READY Candidate 复制成独立 Final Shot Draft。  
**输入：** Project ID。  
**读取：** 当前 F04 Detection + Candidates。  
**写入：** 1 个 `shot_edit_sets` + N 个 `final_shots`。  
**输出：** 完整 `ShotWorkbenchRecord`。  
**为什么存在：** Auto Evidence 与 Human Final 必须物理分离；不能让 UI 直接编辑 `shot_candidates.detected_*`。  
**关键规则：** 幂等；同一项目已初始化时直接返回现有工作区。  
**不负责：** 不运行 TransNetV2，不改 F04。

### `get_shot_workbench(project_id)`

**干嘛：** 读取当前项目的 Edit Set + 按 ordinal 排序的全部 Final Shot。  
**输入：** Project ID。  
**输出：** `ShotWorkbenchRecord | None`。  
**额外校验：** F04 Detection ID 仍与 `source_detection_id` 一致；Final Shot 无 gap/overlap。  
**为什么存在：** 页面刷新、应用重启后必须能从 DB 恢复同一套人工时间轴。  
**不负责：** 不自动修复损坏数据，不静默重建。

### `adjust_shot_boundary(project_id, left_shot_id, boundary_us)`

**干嘛：** 调整两个相邻 Shot 的一个公共边界。  
**输入：** Project ID、边界左侧 Shot ID、新 Source boundary microseconds。  
**写入：** 同时修改 `left.final_end_us` 与 `right.final_start_us`，并重算两侧 duration。  
**输出：** 修改后的完整工作区。  
**为什么必须同时改两侧：** 只改一个 Shot 会制造 gap 或 overlap。  
**不能做：** 不修改整集首起点/末终点；confirmed 后拒绝。

### `split_final_shot(project_id, shot_id, split_us)`

**干嘛：** 在当前 Shot 内拆分，也就是“新增镜头”。  
**输入：** Project ID、被拆 Shot ID、Source split microseconds。  
**结果：** 原 ID 保留左段，新建右段 `SHOT_<UUID4>`，后续 ordinal 顺延。  
**来源追溯：** 新旧两段继承原来的 Candidate 来源。  
**为什么没有另一套 `add_shot()`：** 连续时间轴里新增 Shot 的合法定义就是在现有 Shot 内增加一个 boundary。  
**不能做：** split 不能落在 Shot 外或恰好等于 start/end。

### `merge_final_shots(project_id, left_shot_id)`

**干嘛：** 删除左 Shot 与下一 Shot 的公共边界，也就是合并/删除一个镜头边界。  
**输入：** Project ID、左 Shot ID。  
**结果：** 左 ID 保留并扩展到右 Shot end；右 ID 删除；后续 ordinal 前移。  
**来源追溯：** 两边 Candidate ID 去重合并。  
**为什么没有另一套 `delete_shot()`：** 连续时间轴里直接删除一个 Shot 会产生空洞；真正业务动作应是删除边界并由相邻 Shot 吞并。  
**不能做：** 最后一个 Shot 不能作为 left 与“不存在的下一镜”合并。

### `confirm_final_shots(project_id)`

**干嘛：** 对整套 Final Shot 做最终连续性校验并把 Edit Set 从 `editing` 改为 `confirmed`。  
**输入：** Project ID。  
**输出：** 已锁定工作区。  
**副作用：** `confirmed_at` 写入，revision +1。  
**为什么存在：** 后续人物/对白/生成开始前必须有明确的“人工边界已经定稿”状态。  
**不能做：** confirmed 后不提供 unconfirm；需要改变该 Contract 时另开明确 Feature。

### `get_workbench_proxy_path(project_id)`

**干嘛：** 找到 F03 已生成的 `proxy.mp4`，供浏览器 `<video>` 通过本地 HTTP 播放。  
**输入：** Project ID。  
**输出：** 安全限制在 Project Workspace 内的绝对 Path。  
**为什么存在：** 浏览器不能可靠直接读取 Windows 任意 `file://` 路径。  
**不能做：** 不复制、不转码、不生成第二份视频。

### `render_workbench_frame(project_id, source_time_us)`

**干嘛：** 为左侧 Shot 缩略图和中间 5 关键帧读取/抽取 JPEG。  
**输入：** Project ID + Source Domain microseconds。  
**时间换算：** `relative_seconds = (source_time_us - edit_set.source_start_us) / 1e6`。  
**输出：** Workspace `.cache/f05/frames/<source_us>.jpg`。  
**为什么要减 source_start：** FFmpeg `-ss` 与浏览器 currentTime 都是媒体相对时间，不能直接使用 Source absolute timestamp。  
**缓存命中规则：** 如果 `.cache/f05/frames/<source_us>.jpg` 已存在且非空，必须直接返回，禁止再次启动 FFmpeg。  
**缓存失效规则：** Final Shot 边界没有变化时，原时间点图片永久复用；边界调整、拆分、合并只会产生新的 `source_time_us`，只补新时间点，不批量重生成其它 Shot。  
**HTTP 缓存：** `/shot-workbench/frame` 对稳定时间点返回长期浏览器缓存头；同一 URL 再次打开页面时优先由浏览器/磁盘缓存复用。  
**缓存语义：** UI cache，不是正式业务资产；人工删除缓存后允许按同一时间点重建。  
**不能做：** 不创建正式 Keyframe 数据库资产。

## Controller `engine/app/main.py`

Controller 只有下面职责：Pydantic 校验 → 调业务函数 → response/error envelope。

| Endpoint | Controller 作用 | 真正业务归属 |
|---|---|---|
| `GET /shot-workbench` | 返回工作区或 null | `get_shot_workbench()` |
| `POST /initialize` | 首次进入 F05 | `initialize_shot_workbench()` |
| `POST /boundary` | 接收 left_shot_id + boundary_us | `adjust_shot_boundary()` |
| `POST /split` | 接收 shot_id + split_us | `split_final_shot()` |
| `POST /merge` | 接收 left_shot_id | `merge_final_shots()` |
| `POST /confirm` | 人工最终确认 | `confirm_final_shots()` |
| `GET /media/proxy` | FileResponse | `get_workbench_proxy_path()` |
| `GET /frame` | JPEG FileResponse + 长期缓存头 | `render_workbench_frame()` |

Controller 禁止自己写 SQL、算 ordinal、算 duration、改 F04 Candidate 或调用 FFmpeg。

## 前端 Store `frontend/src/stores/shot-workbench.ts`

### `loadOrInitialize()`
页面进入时先 GET；没有 F05 才 POST initialize。它不自己复制 Candidate。

### `adjustBoundary()` / `split()` / `merge()` / `confirm()`
只调用对应 API，并用统一 `_save()` 管理 saving/error/currentWorkbench。

### `_save()`
这是内部状态辅助，不是新业务动作。它存在的原因是避免四个按钮各自复制 `saving=true/false` 和错误处理。

## 页面 `ShotWorkbench.vue`

页面只负责：

```text
选择 Shot
Source time <-> player currentTime 显示换算
触发 Store action
播放时高亮当前 Shot
当前 Shot 的 5 张关键帧高优先级串行加载（播放中也允许）
整集 Shot 缩略图低优先级补齐（播放中暂停）
```

页面禁止：

```text
直接修改 Pinia shots 数组当作保存
自己重排 ordinal
自己决定 DB 事务
自己覆盖 detected_*
并发启动同一个 Shot 的多个 FFmpeg 关键帧任务
伪造人物/场景/景别/对白结果
```
