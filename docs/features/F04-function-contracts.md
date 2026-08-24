# F04 — 自动拉片 Detailed Function Contracts

Feature ID: F04  
Status: IN DEVELOPMENT  
Contract Status: CONFIRMED

> 本文件解释 F04 的核心函数职责。F04 只做“自动切镜证据 → 连续 Shot Candidate”，不承担 F05 人工修正、F06 人物、F08 ASR 或 F11 Scene。

---

# 1. 总调用关系

```text
GET /api/projects/{project_id}/shot-detection
└─ get_shot_detection_api()
   └─ get_shot_detection()

POST /api/projects/{project_id}/shot-detection
└─ run_shot_detection_api()
   └─ run_shot_detection()
      ├─ generate_shot_detection_id()
      ├─ inspect_proxy_timeline()
      ├─ detect_proxy_cut_events()
      │  ├─ TransNetV2 raw frame predictions
      │  └─ FFprobe real frame PTS alignment
      ├─ build_shot_candidates()
      └─ validate + DB transaction

应用启动
└─ recover_shot_detections()
```

---

# 2. `generate_shot_detection_id()`

作用：生成一次 F04 Detection Run 的稳定 ID。

```text
SHOT_DETECTION_<32位 UUID4 小写 hex>
```

纯函数：不访问 DB、不读媒体、不调用模型。

测试：格式、UUID4、批量无重复。

---

# 3. `inspect_proxy_timeline()`

## 3.1 作用

重新读取 F03 `proxy.mp4` 的主视频流时间信息，并取得逐帧真实时间戳。

输出概念：

```text
ProxyTimeline(
  start_us,
  duration_us,
  end_us,
  frame_pts_us=[...],
  ffprobe_version,
)
```

## 3.2 为什么单独存在

TransNetV2 回答“哪一帧像切镜”，但 F03 已冻结：正式时间不能来自 `frame / fps`。因此本函数专门提供 authoritative PTS。

## 3.3 时间戳规则

FFprobe 使用 `-show_frames`。每帧优先读取：

```text
best_effort_timestamp_time
→ pts_time
```

转换使用公共 `seconds_to_microseconds()`。

必须保证：

```text
frame_pts_us 非空
时间戳非递减
stream duration > 0
```

缺失时：

```text
SHOT_DETECTION_INVALID_RESULT
```

FFprobe 不存在：

```text
SHOT_DETECTION_FFPROBE_UNAVAILABLE
```

本函数不跑模型、不写 DB、不按 FPS 补时间。

---

# 4. `detect_proxy_cut_events()`

## 4.1 作用

对 F03 Proxy 执行本地 TransNetV2 推理，并把逐帧 transition score 与 `inspect_proxy_timeline()` 提供的真实 PTS 一一对齐，输出 CutEvent。

概念输出：

```text
DetectionEvidence(
  events=[CutEvent(proxy_time_us=..., boundary_score=...)],
  analyzed_frame_count=...,
  detector_package_version=...,
  torch_version=...,
  detector_device=...,
)
```

## 4.2 输入

```python
proxy_path: Path
frame_pts_us: list[int]
threshold: float = 0.5
```

阈值来自固定 Profile V1，不来自用户输入。

## 4.3 模型处理

```text
加载 transnetv2-pytorch==1.0.5
→ 选择 auto device
→ 加载 bundled TransNetV2 weights
→ predict_video(proxy)
→ 取得 single-frame raw score
→ 转为一维 score 序列
```

若包/模型/权重不可用：

```text
SHOT_DETECTION_MODEL_UNAVAILABLE
SHOT_DETECTION_MODEL_INVALID
```

## 4.4 Frame Alignment Gate

必须：

```text
len(predictions) == len(frame_pts_us)
```

否则：

```text
SHOT_DETECTION_FRAME_ALIGNMENT_FAILED
```

禁止用 FPS 推算缺失时间，也禁止截短两边“凑成一样长”。

## 4.5 连续 transition 归并

固定判断：

```text
score > 0.5
```

连续命中的帧 `[i..j]` 是一个 transition interval。

若 `j + 1` 存在：

```text
cut_proxy_us = frame_pts_us[j + 1]
boundary_score = max(score[i..j])
```

若 transition 一直延伸到最后一帧：不生成额外 cut，由 `video_end` 收尾。

该策略避免淡入淡出被拆成几十个 Shot。

## 4.6 不负责

```text
不做 120ms 去抖
不做 Source Mapping
不生成 Candidate ID
不写 DB
不判断 F03 stale
```

测试：无 transition、单帧 hard cut、多帧 gradual transition、尾部 transition、模型缺失、frame count mismatch、score shape normalization。

---

# 5. `build_shot_candidates()`

## 5.1 作用

把 CutEvent 转成连续、无 gap、无 overlap 的 Shot Candidate。

输入：

```python
cut_events
proxy_start_us
proxy_end_us
proxy_to_source_offset_us
min_boundary_gap_us=120000
```

## 5.2 事件归一化

固定顺序：

```text
排序
→ 删除 <= start / >= end
→ exact timestamp 去重（同 timestamp 保留 score 高者）
→ 120ms 近邻窗口聚合（保留 score 高者）
→ 保证时间严格递增
```

## 5.3 Source Mapping

使用：

```text
derived_to_source_microseconds(proxy_us, offset_us)
```

禁止直接在多处手写 offset 运算。

## 5.4 输出

每个 Candidate：

```text
id
ordinal
detected_proxy_start_us
detected_proxy_end_us
detected_start_us
detected_end_us
duration_us
end_boundary_kind
end_boundary_score
```

最后一个：

```text
end_boundary_kind = video_end
end_boundary_score = null
```

没有 cut 时合法输出 1 个 Candidate。

## 5.5 Continuity Gate

必须统一验证：

```text
N >= 1
ordinal == 1..N
start < end
prev.end == next.start
first.start == detection_start
last.end == detection_end
Proxy/Source duration 一致
```

任何异常：`SHOT_DETECTION_INVALID_RESULT`，不保存部分结果。

---

# 6. `run_shot_detection()`

F04 唯一业务总调度函数。

完整流程：

```text
init_database()
→ 验证 Project + Manifest
→ get_source_preprocess()
→ 无 F03: SHOT_DETECTION_PREPROCESS_REQUIRED
→ 检查 existing run
   ready: ALREADY_EXISTS
   processing: IN_PROGRESS
→ 解析正式 Proxy path
→ 开始前 Proxy size/hash 校验
→ INSERT processing run（保存 upstream + detector profile snapshot）
→ inspect_proxy_timeline()
→ 校验 F03 duration 与实际 duration <= 1ms
→ detect_proxy_cut_events()
→ build_shot_candidates()
→ 再次校验 Proxy hash 未变化
→ 单事务：INSERT all candidates + UPDATE run ready
→ 返回完整 DTO
```

异常且 ready 未提交：删除本次 processing run。因为 F04 不产生正式新媒体，这种清理不会删除用户素材。

并发：已有 processing 时不得先删后跑。

ready：F04 V1 不覆盖重跑。

---

# 7. `get_shot_detection()`

作用：读取当前项目已有的 Detection Run + Candidates。

无记录：`None`。  
ready：按 ordinal 返回全部 Candidate。  
processing：可返回 run 元信息但没有伪造 Candidate。

读取 ready 时必须验证上游：

```text
source_video_id
preprocess_profile_version
proxy_sha256_snapshot
proxy_to_source_offset_us
```

不一致：`SHOT_DETECTION_UPSTREAM_CHANGED`。

同时确认 Proxy 文件存在；缺失/Hash mismatch 返回明确错误。

该函数不重新运行模型、不修改 completed_at。

---

# 8. `recover_shot_detections()`

应用启动时处理异常退出留下的 F04 `processing`。

F04 V1 没有可恢复的外部 Provider Job，也没有正式媒体 staging，因此：

```text
processing run + candidate orphan（若有）
→ DB transaction 删除
```

`ready` 永远不自动删除。

返回统计：

```text
{"removed": n}
```

---

# 9. Controller

## `get_shot_detection_api()`

```text
GET /api/projects/{project_id}/shot-detection
```

只调用 `get_shot_detection()` 并序列化，不直接 SQL/FFprobe/模型推理。

## `run_shot_detection_api()`

```text
POST /api/projects/{project_id}/shot-detection
```

只传 `project_id` 给 `run_shot_detection()`。不接受 threshold/device/model path 等自由参数。

---

# 10. 职责边界速查

| 函数 | 模型 | FFprobe | PTS | Source Mapping | DB | Recovery |
|---|---:|---:|---:|---:|---:|---:|
| generate_shot_detection_id | No | No | No | No | No | No |
| inspect_proxy_timeline | No | Yes | Yes | No | No | No |
| detect_proxy_cut_events | Yes | No | 对齐输入 | No | No | No |
| build_shot_candidates | No | No | Yes | Yes | No | No |
| run_shot_detection | 调度 | 调度 | 校验 | 调度 | Yes | 失败清理 |
| get_shot_detection | No | No | No | 快照校验 | Read | No |
| recover_shot_detections | No | No | No | No | Delete processing | Yes |

这张表是后续代码审核的职责基线。