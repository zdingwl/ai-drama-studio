# F05 — 镜头人工修正 / 拉片工作台 Contract

Feature ID: F05  
Feature Name: 镜头人工修正 / 三栏拉片工作台  
Status: IN DEVELOPMENT  
Contract Status: CONFIRMED BY USER  
Official Baseline: main  
Upstream: F04 Auto Shot Candidate（F04 当前仍 READY_FOR_REVIEW，用户已明确允许提前开始 F05）

## 1. 目标

F05 把 F04 的自动 Shot Candidate 复制为一套独立的 **Final Shot Draft**，并提供真正可操作的三栏拉片工作台。

```text
左侧：Shot 列表 + 缩略图 + 时间
中间：Proxy 播放器 + Shot Timeline + 当前镜头关键帧
右侧：Final Shot 时间编辑 + 拆分/合并 + 后续语义字段占位
```

F04 的 `detected_*` 自动证据永远只读，F05 禁止覆盖。

## 2. Final Shot 身份

F05 初始化时：

```text
F04 Candidate #001 -> 新建 SHOT_<UUID4>
F04 Candidate #002 -> 新建 SHOT_<UUID4>
...
```

Final Shot ID 是后续人物、对白、Scene、生成、QC 的稳定生产身份。

人工调整边界不改变 Shot ID；拆分创建一个新的 Shot ID；合并保留左侧 Shot ID 并删除右侧 Shot ID。

## 3. Shot Edit Set

每个项目只有一套 F05 Edit Set：

```text
editing   可调整边界、拆分、合并
confirmed 已人工确认，F05 编辑接口全部拒绝修改
```

Edit Set 保存 `source_detection_id`，确保 Final Shot 明确来自哪一次 F04 Auto Evidence。F05 创建后，F04 Detection Run 不应再被删除/替换。

## 4. 时间 Contract

权威时间继续使用 Source Domain integer microseconds。

Final Shot 使用半开区间：

```text
[final_start_us, final_end_us)
```

始终满足：

```text
shot_count >= 1
ordinal = 1..N
start < end
first.start == source_start_us
last.end == source_end_us
prev.end == next.start
无 gap
无 overlap
```

### 调整边界

调整的是两个相邻 Shot 共用的一个 boundary：

```text
left.final_end_us = boundary_us
right.final_start_us = boundary_us
```

禁止只改一侧造成 gap / overlap。

### 拆分（新增镜头）

用户在当前 Shot 内指定 `split_us`：

```text
原 Shot [A, B)
-> 左 Shot [A, split)
-> 新 Shot [split, B)
```

原 Shot ID 保留给左段，新建右段 Shot ID。

### 合并（删除边界）

删除两个相邻 Shot 的公共边界：

```text
Left [A, C) + Right [C, B)
-> Left [A, B)
```

左 Shot ID 保留，右 Shot 删除。

## 5. Auto Evidence / Final 分离

F04：

```text
shot_candidates.detected_start_us
detected_end_us
end_boundary_score
```

F05：

```text
final_shots.final_start_us
final_end_us
```

任何 F05 写操作不得 UPDATE `shot_candidates`。

Final Shot 保存 `origin_candidate_ids_json` 作为追溯信息。拆分会继承来源 Candidate；合并会合并来源 Candidate ID 集合。

## 6. 三栏工作台

### 左栏

- 所有 Final Shot；
- 镜头号；
- 首帧缩略图；
- Source 起点；
- 时长；
- 当前播放 Shot 自动高亮；
- 点击 Shot -> 播放器跳到该 Shot 开始。

### 中栏

- F03 Proxy 视频播放器；
- 当前 Shot 时间范围；
- 按时长比例绘制 Shot Timeline；
- 播放时 Timeline / 左栏同步高亮；
- 当前 Shot 首 / 25% / 50% / 75% / 尾关键帧；
- 点击 Timeline Shot -> seek。

浏览器播放器 `currentTime` 是媒体相对时间，因此：

```text
player_seconds = (source_us - edit_set.source_start_us) / 1_000_000
```

不能把 Source absolute timestamp 直接赋给 `video.currentTime`。

### 右栏

F05 V1 真正可编辑：

- Final Start；
- Final End；
- 在当前播放点拆分；
- 与前一镜合并；
- 与后一镜合并；
- 确认 Final Shots。

以下只占位，不在 F05 提前实现：

```text
人物
场景
景别
机位
运镜
动作
表情
对白
镜头描述
叙事作用
```

## 7. 媒体接口

F05 新增只读媒体入口：

```text
GET /api/projects/{project_id}/shot-workbench/media/proxy
GET /api/projects/{project_id}/shot-workbench/frame?source_time_us=...
```

Proxy 仍是 F03 文件，不复制新视频。

Frame endpoint：

- 输入 Source time；
- 使用 Edit Set source start 映射为播放器相对时间；
- FFmpeg 只抽单帧 JPEG；
- 缓存在 Project Workspace `.cache/f05/frames/`；
- 缓存不是业务资产，删除后可重新生成。

## 8. API

```text
GET  /api/projects/{project_id}/shot-workbench
POST /api/projects/{project_id}/shot-workbench/initialize
POST /api/projects/{project_id}/shot-workbench/boundary
POST /api/projects/{project_id}/shot-workbench/split
POST /api/projects/{project_id}/shot-workbench/merge
POST /api/projects/{project_id}/shot-workbench/confirm
GET  /api/projects/{project_id}/shot-workbench/media/proxy
GET  /api/projects/{project_id}/shot-workbench/frame
```

UI 不允许直接提交 arbitrary SQL / ordinal / duration。ordinal、duration 全部由后端计算。

## 9. Database

Migration：

```text
0006_create_final_shots
```

新增：

```text
shot_edit_sets
final_shots
```

不改写 0001–0005。

## 10. 不在 F05 做

- 人物识别；
- Whisper ASR；
- Speaker；
- Scene 理解；
- Qwen3-VL 镜头语义理解；
- Prompt 编译；
- 视频生成；
- 云端 API。

F05 的任务是把自动 Shot 变成可靠、人工可确认、后续可长期引用的 Final Shot。