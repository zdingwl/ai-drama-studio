# F04 Stable Snapshot — 自动拉片

冻结日期：2026-08-24  
状态：STABLE / FROZEN  
正式分支：main

## 1. 用户验收结论

F04 已通过真实 Windows 本机视频验收。

最终 GPU Detection Run 页面确认：

```text
Shot Candidates: 31
Normalized Cuts: 30
PTS Aligned Frames: 1659
Source Range: 00:00:00.000 -> 00:01:06.360
Detector: transnetv2_pytorch
Package: 1.0.5
Threshold: 0.50
Debounce: 120 ms
Device: cuda
PyTorch: 2.5.1+cu124
GPU: NVIDIA GeForce RTX 3060 Ti
```

因此 F04 Freeze Gate 已满足，不再处于 READY_FOR_REVIEW。

## 2. 冻结技术链路

```text
F03 proxy.mp4
-> FFprobe 逐帧真实 PTS
-> TransNetV2 raw transition prediction
-> prediction index 与 PTS 一一对齐
-> 连续 transition frames 合并
-> transition 后第一帧 PTS 作为 Cut
-> 120ms 确定性近邻去抖
-> Proxy -> Source integer microseconds
-> 连续 Shot Candidate
-> SQLite ready
```

Detector Profile V1：

```text
detector_name = transnetv2_pytorch
transnetv2-pytorch = 1.0.5
torch = 2.5.1
threshold = 0.5
min_boundary_gap_us = 120000
preferred_device = auto
```

## 3. 冻结时间契约

所有正式镜头时间使用：

```text
Source Domain integer microseconds
[start_us, end_us)
```

模型 frame index 只用于和 FFprobe 解码顺序对齐，禁止：

```text
frame_index / fps
```

正式 Cut：

```text
continuous transition [i..j]
-> cut_proxy_us = actual PTS of frame j+1
-> cut_source_us = cut_proxy_us + proxy_to_source_offset_us
```

Prediction 数与 FFprobe PTS 数不一致必须失败关闭：

```text
SHOT_DETECTION_FRAME_ALIGNMENT_FAILED
```

Candidate 必须完整覆盖检测区间、无 gap、无 overlap。无 Cut 时生成 1 个 Candidate 是合法结果。

## 4. 冻结数据库

Migration：

```text
0005_create_shot_detection
```

表：

```text
shot_detection_runs
shot_candidates
```

`shot_candidates.detected_*` 是 F04 Auto Evidence，F05 及后续 Feature 禁止覆盖。

F05 只能复制 Candidate 创建独立 Final Shot。

## 5. 冻结业务/API

核心实现：

```text
engine/app/shot_detection.py
engine/app/shot_detection_rerun.py
```

主要职责：

```text
inspect_proxy_timeline()
detect_proxy_cut_events()
build_shot_candidates()
run_shot_detection()
get_shot_detection()
recover_shot_detections()
rerun_shot_detection()
```

API：

```text
GET  /api/projects/{project_id}/shot-detection
POST /api/projects/{project_id}/shot-detection
POST /api/projects/{project_id}/shot-detection/rerun
```

普通重复 POST 不覆盖 READY；只有用户显式触发 rerun 才允许重新计算。rerun 采用先完整计算、后单事务原子替换，失败保留旧 READY 结果。

一旦 F05 `shot_edit_sets` 已存在，F04 rerun 必须拒绝，防止 Final Shot 来源失去追溯性。

## 6. 冻结前端行为

Route：

```text
/projects/:projectId/shot-detection
```

页面展示：

```text
Shot Count
Cut Count
PTS Aligned Frames
Detector Runtime
Device
PyTorch Version
Candidate Source start/end/duration
Boundary score
```

边界分数只能称 `boundary score / transition score`，禁止称“准确率”。

## 7. Scope Boundary

F04 只负责：

```text
Shot Boundary Detection
Auto Evidence
Shot Candidate
```

F04 不负责：

```text
人工边界修正
人物识别
对白 ASR
场景理解
Qwen3-VL 镜头语义分析
生成提示词
```

这些能力必须由后续 Feature 基于 Final Shot 继续实现。

## 8. 变更规则

本快照冻结后，任何会改变下列语义的修改都不能作为“顺手修复”直接进入：

```text
时间域/单位
Cut 定位规则
threshold
120ms debounce
TransNetV2 版本
Auto Evidence 字段语义
Candidate 连续性规则
rerun 安全语义
```

需要修改时必须新建明确版本/迁移/兼容方案，并对 F05 Final Shot 来源做影响分析。
