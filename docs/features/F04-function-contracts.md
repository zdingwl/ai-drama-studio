# F04 — 自动拉片 Detailed Function Contracts

Feature ID: F04  
Status: PLANNED  
Contract Status: DRAFTED / WAITING_USER_CONFIRMATION

> 本文件专门解释 F04 的 6 个核心后端函数 + 2 个 Controller 到底做什么。不是只列函数名。

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
      ├─ detect_proxy_cut_events()
      ├─ build_shot_candidates()
      └─ private validation / DB helpers

应用启动
└─ recover_shot_detections()
```

Detection Run 内部流程：

```text
F03 ready
→ Proxy integrity gate
→ create processing run
→ detect_proxy_cut_events()
→ build_shot_candidates()
→ validate
→ Proxy integrity re-check
→ one DB transaction:
   candidate rows + run ready
```

---

# 2. `generate_shot_detection_id()`

## 2.1 它具体干什么

生成一次 F04 自动检测任务的稳定业务 ID：

```text
SHOT_DETECTION_<32位UUID4小写hex>
```

例如：

```text
SHOT_DETECTION_4d725cfb82514b9391684a2db5ddc395
```

## 2.2 为什么存在

Detection Run 不是 Project ID，也不是 Source ID。

它代表：

> “基于某一份 F03 Proxy、某一个固定 Detector Profile 执行的一次自动镜头检测结果集合。”

后续 Shot Candidate 都通过该 ID 归属到同一轮检测。

## 2.3 谁调用

```text
run_shot_detection()
```

Controller 不允许自己生成。

## 2.4 输入

```text
无业务输入
```

## 2.5 输出

```python
str
```

固定格式：

```text
^SHOT_DETECTION_[0-9a-f]{32}$
```

UUID version 必须为 4。

## 2.6 会修改什么

```text
不会写数据库
不会 mkdir
不会读媒体
不会调用 FFmpeg
```

纯 ID 函数。

## 2.7 不能随便改什么

一旦 F04 Frozen，ID Prefix / UUID4 格式就是持久化 Contract。

不能改成：

```text
SHOT_001
项目名_检测1
时间戳
随机短字符串
```

## 2.8 测试

```text
格式
UUID4
5000 次无重复
```

---

# 3. `detect_proxy_cut_events()`

## 3.1 它具体干什么

这是 **自动视觉切换检测函数**。

输入 F03 `proxy.mp4`，调用本机 FFmpeg `scdet`，读取真实视频 PTS，返回尚未组装成 Shot 的切换事件。

概念输出：

```text
[
  CutEvent(proxy_time_us=2_433_333, boundary_score=18.72),
  CutEvent(proxy_time_us=5_100_000, boundary_score=31.04),
  ...
]
```

它还必须返回/提供本次实际媒体扫描信息：

```text
proxy_stream_start_us
proxy_stream_duration_us
ffmpeg_version
```

## 3.2 为什么单独存在

自动检测算法和“Shot 如何连续组装”是两件不同的事。

拆开后：

```text
detect_proxy_cut_events()
= 媒体算法证据

build_shot_candidates()
= 确定性业务结构
```

以后即使 Detector Profile V2 换算法，Shot Candidate 连续性 Contract 仍可复用。

## 3.3 谁调用

```text
run_shot_detection()
```

## 3.4 输入

建议：

```python
proxy_path: Path
threshold: float
```

V1 threshold 由业务层固定传：

```text
10.0
```

不能来自用户自由文本。

## 3.5 处理流程

```text
确认 proxy 文件存在
↓
读取 FFmpeg version
↓
FFprobe 主视频流 start_time / duration
↓
运行 FFmpeg scdet threshold=10.0
↓
读取 scdet frame metadata
↓
只保留发生 scene change 的 frame
↓
读取该 frame 的真实 pts_time
↓
Decimal → integer microseconds
↓
读取 lavfi.scd.score
↓
返回原始 CutEvent[] + Proxy Timeline Info
```

## 3.6 FFmpeg 原则

必须：

```text
-nostdin
只读 Proxy
-an
不生成输出视频
输出到 null sink
```

不得：

```text
转码 Proxy
覆盖 F03 文件
抽帧后用 frame_number / fps 算时间
自动切换其它 detector
```

## 3.7 时间

FFmpeg metadata 的 `pts_time` 属于：

```text
Proxy Timeline
```

转换必须复用公共：

```text
seconds_to_microseconds()
```

不能：

```python
int(float_pts * 1000)
```

## 3.8 输出分数含义

```text
boundary_score
```

只是 FFmpeg SCDet 的视觉变化强度。

禁止业务层改名为：

```text
confidence_probability
accuracy
AI confidence %
```

## 3.9 失败

FFmpeg 不存在：

```text
SHOT_DETECTION_FFMPEG_UNAVAILABLE
```

FFprobe 不存在：

```text
SHOT_DETECTION_FFPROBE_UNAVAILABLE
```

命令返回非 0 / metadata 无法解析：

```text
SHOT_DETECTION_FAILED
```

媒体时间不完整：

```text
SHOT_DETECTION_INVALID_RESULT
```

## 3.10 不负责

```text
不写 DB
不生成 Detection ID
不生成 Candidate ID
不做 Source Mapping
不做 120ms 去抖
不组装 Shot
不判断 F03 stale
不做人工修正
```

## 3.11 测试

```text
SCDet metadata parser
score parser
VFR pts_time
proxy start_time 非零
无 cut
FFmpeg missing
FFprobe missing
malformed metadata
```

---

# 4. `build_shot_candidates()`

## 4.1 它具体干什么

把原始 Cut Event 变成**连续可用的 Shot Candidate 列表**。

它不跑 FFmpeg。

输入：

```text
Proxy detection start/end
Proxy→Source offset
原始 CutEvent[]
min_boundary_gap_us = 120000
```

输出示意：

```text
Candidate 1
Proxy:  [0, 2.433333s)
Source: [0, 2.433333s)
End Score: 18.72

Candidate 2
Proxy:  [2.433333s, 5.100000s)
Source: [2.433333s, 5.100000s)
End Score: 31.04

Candidate 3
Proxy:  [5.100000s, 6.000000s)
Source: [5.100000s, 6.000000s)
End: video_end
```

## 4.2 为什么存在

Scene Detector 只告诉我们：

```text
“这里可能发生切换”
```

生产系统需要的是：

```text
“整个视频被哪些连续 Shot 区间覆盖”
```

这个转换必须确定性、可测试，不能散落在 Controller/UI 里。

## 4.3 谁调用

```text
run_shot_detection()
```

## 4.4 输入

建议数据：

```python
cut_events: list[CutEvent]
proxy_start_us: int
proxy_end_us: int
proxy_to_source_offset_us: int
min_boundary_gap_us: int
```

## 4.5 原始事件归一化

按顺序执行：

```text
1. 按 proxy_time_us 排序
2. 删除 <= proxy_start 的事件
3. 删除 >= proxy_end 的事件
4. exact timestamp 去重
5. 120ms 窗口内聚合近邻事件
6. 每个窗口只保留 boundary_score 最大的事件
7. 再次确认严格递增
```

### 为什么不是保留第一个

软转场/闪帧可能连续数帧都超过 threshold。

保留窗口内最高 score，比“碰到第一个就截断”更稳定，同时仍保留原始自动判断语义。

## 4.6 Source Mapping

每个 Proxy 边界：

```text
source_us = proxy_us + offset_us
```

必须使用：

```text
derived_to_source_microseconds()
```

## 4.7 Candidate ID

Candidate ID 可以由本函数或 private helper 生成：

```text
SHOT_CANDIDATE_<UUID4>
```

不单独提升成第 7 个核心函数。

## 4.8 连续性

生成后必须统一验证：

```text
N >= 1
ordinal = 1..N
start < end
prev.end == next.start
first.start == video_start
last.end == video_end
Proxy 与 Source duration 一致
Source duration = end - start
```

任何不一致：

```text
SHOT_DETECTION_INVALID_RESULT
```

不能“尽量保存能保存的 Shot”。

## 4.9 没有 Cut

```text
cut_events = []
```

合法输出：

```text
1 个 Candidate
[video_start, video_end)
```

## 4.10 输出字段

每个 Candidate 至少：

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

其它：

```text
end_boundary_kind = cut
end_boundary_score = 对应 SCDet score
```

## 4.11 不负责

```text
不 SQL
不 FFmpeg
不 Hash
不读 Project
不写 Final Shot
不人工修边界
```

## 4.12 测试

```text
无 cut → 1 Shot
1 cut → 2 Shot
多 cut → N+1
无 gap
无 overlap
半开区间
非零 Proxy start
非零 Source offset
120ms 内保留最高 score
边界在视频外被丢弃
最后一个 video_end score NULL
```

---

# 5. `run_shot_detection()`

## 5.1 它具体干什么

F04 **唯一业务总调度函数**。

用户点击“开始自动拉片”后，真正的业务闭环全部由它负责。

## 5.2 谁调用

```text
run_shot_detection_api()
```

Controller 只传 Project ID。

## 5.3 输入

```python
project_id: str
app_data_path: Path | None = None
```

正常 UI 不允许传：

```text
threshold
min gap
detector name
```

这些属于冻结 Detector Profile V1。

## 5.4 完整流程

```text
init_database()
↓
验证 F01 Project ready + Manifest
↓
读取 F03 get_source_preprocess()
↓
无 F03 → PREPROCESS_REQUIRED
↓
检查是否已有 detection run
↓
ready → ALREADY_EXISTS
processing → IN_PROGRESS
↓
解析 F03 proxy 正式路径
↓
磁盘 proxy size/hash 校验
↓
生成 Detection ID
↓
DB INSERT processing run
并保存：
  source_video_id
  preprocess profile
  proxy hash snapshot
  offset snapshot
  detector profile
↓
detect_proxy_cut_events()
↓
验证实际 Proxy stream duration 与 F03 duration <=1ms
↓
build_shot_candidates()
↓
业务连续性校验
↓
再次 Hash Proxy
↓
确认 Proxy 未在处理中变化
↓
DB 单事务：
  INSERT all candidates
  UPDATE run ready + timeline/count/version
↓
返回 DetectionDTO
```

## 5.5 为什么 processing 要先提交

如果程序在 FFmpeg 扫描中崩溃，需要数据库知道：

```text
“这个项目曾开始过 F04，但没有完成。”
```

重启时才能由 Recovery 清理。

否则下一次无法区分：

```text
从未运行
vs
运行中异常退出
```

## 5.6 为什么 Candidates + ready 必须同一事务

不允许出现：

```text
run = ready
但只保存了一半 Candidate
```

也不允许：

```text
Candidate 已存在
run 仍 processing
```

正常 final commit 必须：

```text
all candidates + ready
```

一起成功/一起回滚。

## 5.7 Proxy 双重完整性

开始前：

```text
磁盘 SHA == F03 proxy_sha256
```

完成后、commit 前：

```text
磁盘 SHA == F03 proxy_sha256 == run snapshot
```

如果用户在检测过程中手工替换 proxy：

```text
SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH
```

不保存 ready。

## 5.8 失败清理

Detection ready commit 前任何失败：

```text
删除本次 Candidate（正常情况下事务未提交）
删除本次 processing run
```

这是安全的，因为 F04：

```text
无付费任务
无正式生成媒体
```

用户之后可以重试。

## 5.9 并发

如果第二次 POST 到来时：

```text
已有 processing
```

立即：

```text
SHOT_DETECTION_IN_PROGRESS
```

不能“先删了再跑”。

## 5.10 ready 后重复点击

```text
SHOT_DETECTION_ALREADY_EXISTS
```

F04 V1 不做覆盖重跑。

原因：F05 就是人工修正层；避免 F04 一次重跑把 F05 未来 Final 依赖的 Evidence 身份静默换掉。

## 5.11 不负责

```text
不做 F05 人工修正
不生成 Final Shot
不做人物/ASR/Scene
不修改 F03 Proxy
不修改 Source
```

## 5.12 测试

必须覆盖：

```text
F03 missing
Proxy missing
Proxy hash mismatch
existing processing
existing ready
normal no cut
normal multi cut
Proxy 处理中变化
DB candidate insert failure
DB ready update failure
结果连续性失败
```

---

# 6. `get_shot_detection()`

## 6.1 它具体干什么

读取某个 Project 当前 F04 Detection Run。

这是：

```text
页面首次进入
页面刷新
应用重启
项目总览判断阶段
```

统一读取入口。

## 6.2 输入

```python
project_id
app_data_path=None
```

## 6.3 无结果

数据库没有 Detection Run：

```text
return None
```

Controller：

```text
200 null
```

## 6.4 processing

如果 run：

```text
status = processing
```

返回：

```text
DetectionDTO
status=processing
candidates=[]
```

不能伪装成“未运行”。

这样用户刷新页面时可以看到：

```text
正在自动拉片
```

而不是重新出现“开始”按钮。

## 6.5 ready

读取：

```text
run
+ candidates ORDER BY ordinal
```

然后再次验证依赖：

```text
F03 仍 ready
Source ID 相同
F03 profile 相同
Proxy SHA snapshot 相同
Offset 相同
磁盘 Proxy hash 相同
```

再验证 Candidate：

```text
数量 == run.shot_count
ordinal 连续
时间连续
first/last 与 run detection interval 一致
```

异常：

```text
SHOT_DETECTION_STALE
或
SHOT_DETECTION_INVALID_RESULT
```

## 6.6 它不能做什么

```text
不重新跑 FFmpeg
不自动修改 Detection
不自动修 Shot 边界
不把 processing 删除
```

## 6.7 测试

```text
None
processing
ready
candidate order
stale F03 snapshot
missing proxy
hash mismatch
broken candidate continuity
```

---

# 7. `recover_shot_detections()`

## 7.1 它具体干什么

应用启动时清理**上一次进程异常退出留下的 F04 processing 状态**。

## 7.2 为什么和 F03 Recovery 不一样

F03 有：

```text
Proxy / WAV / Thumbnail 正式文件
```

因此必须谨慎保护 final。

F04 V1 没有新增正式媒体文件。

自动检测过程只产生：

```text
内存 Cut Event
DB processing run
```

Candidates 只有在最后一个 DB transaction 才正式保存。

所以应用重启以后：

```text
旧 process 的 FFmpeg 检测任务已经不属于当前应用生命周期
```

可以安全重新检测。

## 7.3 调用时机

FastAPI lifespan：

```text
init_database()
→ recover F01
→ recover F02
→ recover F03
→ recover_shot_detections()
→ app ready
```

顺序不能放在 F03 Recovery 前面，因为 F04 依赖 F03。

## 7.4 恢复流程

查：

```text
shot_detection_runs.status = processing
```

对每个：

```text
DB transaction:
DELETE shot_candidates WHERE detection_id = run.id
DELETE shot_detection_runs WHERE id = run.id AND status=processing
```

返回统计：

```text
removed
preserved
```

正常情况下 processing 不应有 Candidate，但清理它们是防御性措施。

## 7.5 什么情况保留

如果 DB transaction 本身失败：

```text
preserved += 1
```

不假装成功。

ready 永远不由 Recovery 删除。

## 7.6 不负责

```text
不删除 Proxy
不删除 Source
不重新跑 Detection
不修改 ready run
```

## 7.7 测试

```text
processing 无 candidate → 删除
processing 有异常 candidate → 一并删除
ready → 保留
DB error → preserved
再次 Recovery 幂等
```

---

# 8. `get_shot_detection_api()`

## 8.1 业务作用

HTTP GET 边界：

```text
GET /api/projects/{project_id}/shot-detection
```

页面通过它恢复 F04 状态。

## 8.2 流程

```text
取 project_id
→ get_shot_detection()
→ None: 200 null
→ processing: 200 DTO
→ ready: 200 DTO + candidates
```

## 8.3 不能做

```text
不 SQL
不 JOIN candidates
不 Hash Proxy
不检查 F03
不排序 Candidate
不跑 FFmpeg
```

全部交给业务层。

## 8.4 错误

使用统一：

```json
{
  "error": {
    "code": "SHOT_DETECTION_STALE",
    "message": "..."
  }
}
```

---

# 9. `run_shot_detection_api()`

## 9.1 业务作用

用户点击：

```text
开始自动拉片
```

触发：

```text
POST /api/projects/{project_id}/shot-detection
```

## 9.2 输入

只需要：

```text
project_id
```

F04 V1 不收 JSON 参数。

原因：

```text
threshold / min gap / detector
```

属于固定 Detector Profile V1，不允许浏览器提交任意值破坏结果可复现性。

## 9.3 流程

```text
取 project_id
→ run_shot_detection(project_id)
→ 返回 DetectionDTO
```

成功：

```text
201 Created
```

## 9.4 Controller 禁止

```text
不生成 Detection ID
不决定 threshold
不调用 FFmpeg
不解析 metadata
不做时间换算
不写 SQL
不生成 Candidate
不 Recovery
```

---

# 10. DTO 结构建议

## Detection DTO

```text
id
project_id
source_video_id
status

detector_name
detector_profile_version
detector_threshold
min_boundary_gap_us
ffmpeg_version

preprocess_profile_version
proxy_sha256_snapshot
proxy_to_source_offset_us

proxy_start_us
proxy_end_us
source_start_us
source_end_us

detected_cut_count
shot_count
created_at
completed_at

candidates[]
```

processing 时：

```text
ready-only fields = null
candidates = []
```

ready 时全部核心字段完整。

## Candidate DTO

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

---

# 11. 核心函数数量控制

F04 只把下面 6 个当核心业务函数：

```text
generate_shot_detection_id()
detect_proxy_cut_events()
build_shot_candidates()
run_shot_detection()
get_shot_detection()
recover_shot_detections()
```

开发中需要下面这类函数时，只作为 private helper：

```text
_parse_scdet_metadata()
_probe_proxy_timeline()
_hash_file()
_generate_candidate_id()
_validate_candidate_sequence()
_row_to_detection()
_candidate_row_to_dto()
_read_ffmpeg_version()
```

这些 helper 仍需中文业务注释和测试，但不要为了“架构完整”变成十几二十个核心函数。

---

# 12. F05 强制继承规则

F04 Frozen 后，F05 必须把：

```text
shot_candidates.detected_start_us
shot_candidates.detected_end_us
```

视为原始自动证据。

F05 人工操作：

```text
调整
拆分
合并
新增
删除
```

都不能覆盖 F04 原始 Candidate。

最终 Shot 必须可回答：

```text
它来自哪个 Detection Run？
参考了哪些 Candidate？
人工做过什么变化？
```

具体 Schema 留给 F05 Contract，不在 F04 提前实现。
