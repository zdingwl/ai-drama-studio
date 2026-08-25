# Workflow Task Progress Contract

## 目标

所有耗时操作都不能让页面长时间等待一个 HTTP 请求，也不能把进度只保存在前端内存。

统一模型：

```text
用户动作
→ 创建 Background Task
→ HTTP 202 立即返回 task_id
→ 后台执行
→ 前端每 1 秒读取 Task
→ Task 完成后工作区重新读取最新业务数据
```

Task 与业务 Run / Revision 必须分开：

- Task：执行状态、进度、当前阶段、错误。
- Run / Revision：算法或人工结果的版本。

Task 失败不能删除或替换旧 Current Run。

## 状态

- `QUEUED`
- `PROCESSING`
- `READY`
- `READY_WITH_WARNINGS`
- `FAILED`
- `CANCELLED`

## 进度规则

能真实计算时使用 `determinate`：

- 批量剧集：`7 / 16`
- Reference Clip：`18 / 31`
- Shot 生成：`126 / 450`

不能真实计算时使用 `indeterminate`，只显示当前阶段，禁止伪造百分比：

- VLM 单次推理
- 无内部回调的第三方模型
- 某些远程生成任务

## 第一批接入

- 单集视频预处理
- 批量顺序视频预处理
- 单集拉片
- 批量顺序拉片
- F05 资产提取

预处理真实阶段：

```text
FFprobe
→ Proxy
→ Audio
→ Persist
```

拉片真实阶段：

```text
Media Probe
→ FFprobe Real PTS
→ TransNetV2
→ Shot Boundary
→ Reference Clip N / Total
→ Persist
```

批量任务严格按 `Episode.sort_order` 逐集执行，不并行处理多个剧集。

单集失败时，批量任务记录失败并继续后续 Episode；任务最终为 `READY_WITH_WARNINGS`，失败集可单独重试。

## 持久化与重启

Task 保存到 `v2_background_tasks`。

页面刷新或切换工作区后，从数据库恢复状态。

当前执行器运行在 FastAPI 本地进程中，因此服务进程退出后原函数无法继续。应用启动时，遗留的 `QUEUED / PROCESSING` Task 必须转成 `FAILED`：

```text
TASK_INTERRUPTED_BY_PROCESS_RESTART
```

用户可以重新执行，不能让 UI 永久卡在“处理中”。

## 前端

`TaskProgressDock` 是全局组件：

- 有活动 Task 时固定显示进度条；
- `determinate` 显示真实百分比；
- `indeterminate` 显示动态阶段条；
- 每秒轮询一次；
- Task 完成后当前 RouterView 重新挂载，读取最新 Project / Shot / Asset 数据；
- 没有活动 Task 时自动隐藏。

后续 ASR、Qwen3-VL、生成、TTS、LipSync、QC、最终合成全部复用同一个 Task Contract。
