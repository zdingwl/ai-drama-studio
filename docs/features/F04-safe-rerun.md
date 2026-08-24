# F04 — 安全重新自动拉片 Addendum

Feature ID: F04  
Status: READY_FOR_REVIEW  
Applies To: F04 TransNetV2 Profile V1

## 1. 为什么新增

F04 首次运行会把当时真实 runtime 一起保存：

```text
torch_version
detector_device
detector_package_version
```

因此用户在首次检测后升级 CPU PyTorch → CUDA PyTorch 时，旧 READY 页面仍然正确显示第一次运行的 CPU 快照，不应被页面刷新偷偷改写。

为了允许用户用当前本机环境重新验证，F04 新增**显式**“重新自动拉片”。

## 2. API

首次运行仍然使用：

```text
POST /api/projects/{project_id}/shot-detection
```

如果已有 READY，重复首次 POST 仍返回 `SHOT_DETECTION_ALREADY_EXISTS`，不会把误操作当重跑。

只有用户明确点击“重新自动拉片”时使用：

```text
POST /api/projects/{project_id}/shot-detection/rerun
```

## 3. 数据安全

禁止采用：

```text
先 DELETE 旧 READY
→ 再开始模型推理
```

因为 CUDA / 模型 / FFprobe 任意失败都会导致已有 Auto Evidence 丢失。

正式策略：

```text
读取并校验旧 READY
↓
旧 READY 保持不动
↓
重新校验 F03 Proxy
↓
FFprobe 真实 PTS
↓
当前环境 TransNetV2 推理
↓
构建并验证全部新 Shot Candidate
↓
再次校验 Proxy SHA-256
↓
单一 SQLite transaction：
  DELETE old candidates
  DELETE old ready run
  INSERT new ready run
  INSERT all new candidates
↓
commit
```

事务中任何 SQL / CHECK / FK 失败都会 rollback，因此旧 READY 会恢复并继续可读。

模型推理阶段进程崩溃也不会伤害旧 READY，因为替换事务尚未开始。

## 4. F05 边界

当前 F05 尚未开发，因此 F04 重跑只替换 F04 Auto Evidence。

一旦未来 F05 已产生 Final Shot，是否允许继续重跑 F04 必须在 F05 Contract 中重新定义依赖/失效策略；不得擅自让重跑覆盖人工 Final Shot。

## 5. UI

READY 页面增加：

```text
重新自动拉片
```

点击前必须明确确认：

- 使用当前 TransNetV2 / PyTorch / CUDA 环境；
- 新结果成功后才替换旧 Auto Evidence；
- 新检测失败时旧结果保留。

运行期间按钮禁用并显示：

```text
正在重新检测…
```

页面继续保留旧 READY 数据，直到后端返回新的完整 READY。

## 6. 当前验收目标

用户本机已经验证：

```text
PyTorch 2.5.1+cu124
CUDA available = True
NVIDIA GeForce RTX 3060 Ti
```

重启 FastAPI、点击重新自动拉片后，新的 Detector Runtime 预期显示：

```text
detector_device = cuda
torch_version = 2.5.1+cu124
```

同时 Shot Candidate 必须继续满足 F04 原有连续性、PTS 和 Source Mapping Contract。
