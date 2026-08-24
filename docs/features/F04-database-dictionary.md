# F04 — Database Dictionary

Feature ID: F04  
Feature Name: 自动拉片  
Schema Migration: `0005_create_shot_detection`  
Status: READY_FOR_REVIEW 前数据库说明

> 本字典是 F04 数据库字段的业务权威说明，与 `docs/features/F04-auto-shot-detection.md`、`engine/migrations/versions/0005_create_shot_detection.py` 同步维护。

---

# 1. 表关系与生命周期

```text
projects (F01, Frozen)
   │
   ├── source_videos (F02, Frozen)
   │       │
   │       └── source_preprocess (F03, Frozen)
   │
   └── shot_detection_runs (F04 Auto Evidence)
             │
             └── shot_candidates (F04 Auto Evidence)
```

F04 只新增：

```text
shot_detection_runs
shot_candidates
```

不修改 F01/F02/F03 已冻结表。

生命周期：

```text
POST F04
→ shot_detection_runs.status = processing
→ 本地模型与真实 PTS 分析
→ 单事务 INSERT shot_candidates + UPDATE run ready
```

崩溃时遗留的 `processing` 会在应用下次启动被 Recovery 删除；`ready` 不自动删除。

F04 是 **Auto Evidence**。F05 人工修正必须创建独立 Final 数据，禁止覆盖本字典中的 `detected_*` 自动证据。

---

# 2. `shot_detection_runs`

## 2.1 表说明

用途：保存一次项目级 F04 自动拉片运行的输入快照、算法身份、实际运行环境、检测时间范围和结果统计。

创建者：F04 `run_shot_detection()`。  
修改者：仅 F04，在同一次运行中从 `processing` 转为 `ready`。  
下游：F05 及后续功能只读算法证据/版本与 Candidate 关联；不得修改。  
冻结状态：F04 尚未用户验收，当前为 Candidate Contract；用户验收后随 F04 Freeze。

约束重点：

```text
UNIQUE(project_id)
status ∈ {processing, ready}
0 < detector_threshold < 1
min_boundary_gap_us >= 0
ready → runtime / timeline / count / completed_at 全部完整
ready → shot_count = detected_cut_count + 1
```

## 2.2 字段字典

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Frozen | Example |
|---|---|---:|---|---|---|---|---:|---|
| `id` | VARCHAR(64) | No | None | 一次自动拉片运行的稳定业务 ID。用于关联全部 Candidate，不因文件名、模型设备或项目改名变化。 | F04 UUID4 | F04 create only | Freeze 后 Yes | `SHOT_DETECTION_a1b2...` |
| `project_id` | VARCHAR(64) | No | None | 所属 F01 Project。V1 每个项目只允许一份当前 F04 Run，防止静默覆盖自动证据。 | 当前请求 Project | F04 create only | Freeze 后 Yes | `PROJECT_...` |
| `source_video_id` | VARCHAR(64) | No | None | 本次检测依赖的 F02 Source 身份。读取 ready 时用于判断上游是否变化。 | F03 / F02 snapshot | F04 create only | Freeze 后 Yes | `SOURCE_VIDEO_...` |
| `status` | VARCHAR(16) | No | None | `processing`=检测执行中；`ready`=Candidate 与 runtime 已完整提交。不存在 `failed` 持久态，失败会清理 processing。 | F04 workflow | F04 | Freeze 后枚举 Yes | `ready` |
| `detector_name` | VARCHAR(64) | No | None | 算法实现身份。V1 固定 `transnetv2_pytorch`，UI 不允许自由改检测器。 | Detector Profile V1 | F04 create only | Freeze 后 Yes | `transnetv2_pytorch` |
| `detector_profile_version` | INTEGER | No | None | F04 算法配置语义版本。以后阈值/归一化变化必须升 Profile，不得静默改变历史结果含义。 | Contract | F04 create only | Freeze 后 Yes | `1` |
| `detector_threshold` | FLOAT | No | None | TransNetV2 single-frame transition score 判断阈值。V1 固定 0.5。 | Profile V1 | F04 create only | Freeze 后 Yes | `0.5` |
| `min_boundary_gap_us` | BIGINT | No | None | 自动 Cut 近邻去抖窗口，单位 µs；V1 120ms 内竞争边界保留最高 score。 | Profile V1 | F04 create only | Freeze 后 Yes | `120000` |
| `detector_package_version` | VARCHAR(32) | No | None | Python 实现包版本，用于复现同一算法代码。 | 固定依赖 | F04 create only | Freeze 后 Yes | `1.0.5` |
| `torch_version` | VARCHAR(64) | Yes | NULL | 实际完成本次推理的 PyTorch runtime 版本。processing 阶段尚未完成模型推理时为空。 | 运行时 `torch.__version__` | F04 ready commit | Freeze 后 Yes | `2.5.1+cu121` |
| `detector_device` | VARCHAR(128) | Yes | NULL | 实际模型计算设备。用于区分 CUDA / CPU 运行并协助复现与排错。 | TransNetV2 runtime | F04 ready commit | Freeze 后 Yes | `cuda:0` |
| `ffprobe_version` | VARCHAR(256) | Yes | NULL | 本次提供逐帧真实 PTS 的 FFprobe 版本首行。时间证据追溯使用。 | FFprobe runtime | F04 ready commit | Freeze 后 Yes | `ffprobe version 7.x ...` |
| `preprocess_profile_version` | INTEGER | No | None | F03 Profile 快照。若当前 F03 与快照不同，ready F04 必须视为 stale。 | F03 | F04 create only | Freeze 后 Yes | `1` |
| `proxy_sha256_snapshot` | VARCHAR(64) | No | None | F03 Proxy 内容 SHA-256 快照。运行前和 commit 前双检，读取 ready 时也验证。 | F03 | F04 create only | Freeze 后 Yes | `9e107d...` |
| `proxy_to_source_offset_us` | BIGINT | No | None | F03 已冻结的 Proxy→Source integer µs 偏移快照。所有 Candidate Source 时间均由它映射。 | F03 | F04 create only | Freeze 后 Yes | `2000000` |
| `proxy_start_us` | BIGINT | Yes | NULL | FFprobe 实际 Proxy 主视频流检测起点。processing 时为空；ready 后必须有值。 | F04 FFprobe | F04 ready commit | Freeze 后 Yes | `0` |
| `proxy_end_us` | BIGINT | Yes | NULL | Proxy 检测半开区间终点 `start + stream duration`。最后一个 Candidate 必须覆盖至此。 | F04 FFprobe | F04 ready commit | Freeze 后 Yes | `60400000` |
| `source_start_us` | BIGINT | Yes | NULL | `proxy_start_us` 映射后的 Source Domain 起点。 | F04 + F03 offset | F04 ready commit | Freeze 后 Yes | `2000000` |
| `source_end_us` | BIGINT | Yes | NULL | `proxy_end_us` 映射后的 Source Domain 终点。 | F04 + F03 offset | F04 ready commit | Freeze 后 Yes | `62400000` |
| `analyzed_frame_count` | INTEGER | Yes | NULL | 与 FFprobe 真实 PTS 数量完全对齐并成功参与推理的 prediction 数。不是 FPS 推算帧数。 | F04 model/PTS alignment | F04 ready commit | Freeze 后 Yes | `1812` |
| `detected_cut_count` | INTEGER | Yes | NULL | 连续 transition 归并、区间过滤、去重和 120ms 去抖后的正式自动 Cut 数。 | F04 normalization | F04 ready commit | Freeze 后 Yes | `23` |
| `shot_count` | INTEGER | Yes | NULL | 自动 Candidate 数；必须等于 Cut 数 + 1。无 Cut 时合法为 1。 | F04 candidate builder | F04 ready commit | Freeze 后 Yes | `24` |
| `created_at` | DATETIME(TZ) | No | None | UTC Detection Run 创建时间，即 processing 记录首次持久化时间。 | F04 clock | F04 create only | Freeze 后 Yes | `2026-08-24T14:40:00+00:00` |
| `completed_at` | DATETIME(TZ) | Yes | NULL | UTC ready commit 完成时间。processing 为 NULL；ready 必须非 NULL。 | F04 clock | F04 ready commit | Freeze 后 Yes | `2026-08-24T14:40:28+00:00` |

### Null 行为

`torch_version`、`detector_device`、`ffprobe_version`、timeline/count、`completed_at` 只允许在 `processing` 阶段为空。`ready` 的 DB CHECK 会强制完整。

---

# 3. `shot_candidates`

## 3.1 表说明

用途：保存 F04 自动检测形成的连续 Shot Candidate。一个 Candidate 是“模型自动证据镜头区间”，还不是人工确认后的 Final Shot。

创建者：F04，在 Detection Run ready commit 时批量写入。  
修改者：F04 V1 写入后不可变。  
下游：F05 读取并建立人工 Final Shot；人物、对白、Scene 等后续 Feature 不得反向覆盖自动 detected 值。

跨行必须满足：

```text
ordinal = 1..N
start < end
prev.end == next.start
first.start == detection start
last.end == detection end
无 gap / overlap
Proxy duration == Source duration
```

这些跨行规则由 F04 业务层在 commit 前验证；SQLite 单行 CHECK 只能保护单条记录。

## 3.2 字段字典

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Frozen | Example |
|---|---|---:|---|---|---|---|---:|---|
| `id` | VARCHAR(64) | No | None | 自动 Candidate 稳定业务 ID。明确不是未来 Final Shot ID。 | F04 UUID4 | F04 create only | Freeze 后 Yes | `SHOT_CANDIDATE_a1b2...` |
| `detection_id` | VARCHAR(64) | No | None | 所属 `shot_detection_runs.id`；run 被清理时 Candidate 随 FK cascade 删除。 | 当前 F04 run | F04 create only | Freeze 后 Yes | `SHOT_DETECTION_...` |
| `project_id` | VARCHAR(64) | No | None | Candidate 所属 F01 Project。便于下游按项目读取；业务层必须与 Run 的 project_id 一致。 | 当前 Project | F04 create only | Freeze 后 Yes | `PROJECT_...` |
| `ordinal` | INTEGER | No | None | Detection Run 内 1-based 镜头顺序，必须连续无跳号。 | F04 builder | F04 create only | Freeze 后 Yes | `12` |
| `detected_proxy_start_us` | BIGINT | No | None | Auto Evidence 在 Proxy Timeline 的半开区间起点。来自视频起点或前一个归一化 Cut。 | F04 real PTS | F04 create only | Freeze 后 Yes | `23120000` |
| `detected_proxy_end_us` | BIGINT | No | None | Auto Evidence 在 Proxy Timeline 的半开区间终点。来自 transition 后第一帧真实 PTS，末镜头来自 video_end。 | F04 real PTS | F04 create only | Freeze 后 Yes | `25840000` |
| `detected_start_us` | BIGINT | No | None | `detected_proxy_start_us + F03 offset` 的 Source Domain 自动起点。F05 人工修正不得覆盖。 | F04 mapping | F04 create only | Freeze 后 Yes | `25120000` |
| `detected_end_us` | BIGINT | No | None | `detected_proxy_end_us + F03 offset` 的 Source Domain 自动终点。F05 人工修正不得覆盖。 | F04 mapping | F04 create only | Freeze 后 Yes | `27840000` |
| `duration_us` | BIGINT | No | None | Source 自动区间时长；DB 强制等于 `detected_end_us - detected_start_us`。 | F04 builder | F04 create only | Freeze 后 Yes | `2720000` |
| `end_boundary_kind` | VARCHAR(16) | No | None | `cut` 表示由 TransNetV2 自动 Cut 结束；`video_end` 表示最后镜头由视频终点自然收口。 | F04 builder | F04 create only | Freeze 后枚举 Yes | `cut` |
| `end_boundary_score` | FLOAT | Yes | NULL | 结束 Cut 的 TransNetV2 transition sigmoid score，范围 0..1，仅用于排序/诊断，**不代表准确率**。末尾 `video_end` 必须为 NULL。 | F04 model | F04 create only | Freeze 后 Yes | `0.9472` |

### Null 行为

唯一允许为空的业务字段是：

```text
end_boundary_score
```

且仅当：

```text
end_boundary_kind = video_end
```

`cut` 必须有 score；DB 同时限制 score 为 0..1。

---

# 4. 写入权限矩阵

| 数据 | F04 | F05 | F06+ |
|---|---:|---:|---:|
| `shot_detection_runs` create/ready | Write | Read | Read |
| `shot_candidates.detected_*` | Write once | Read only | Read only |
| `end_boundary_score` | Write once | Read only | Read only |
| 人工 Final Shot 边界 | Not in F04 | Future Write | Future Read |

核心规则：

> F05 可以根据人工操作产生新的最终边界，但绝不能 UPDATE `shot_candidates.detected_*` 把 AI 原始证据抹掉。

---

# 5. Stale / Recovery 语义

ready Detection Run 通过以下快照绑定 F03：

```text
source_video_id
preprocess_profile_version
proxy_sha256_snapshot
proxy_to_source_offset_us
```

任何一项不一致：

```text
SHOT_DETECTION_UPSTREAM_CHANGED
```

Proxy 实体缺失、size/hash 不一致：

```text
SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH
```

应用启动对 `processing`：

```text
DELETE possible candidate orphan
DELETE processing run
```

对 `ready`：

```text
禁止自动删除
禁止自动重跑覆盖
```

---

# 6. Database Comment Review

当前 F04 收尾检查：

```text
新增表中文业务说明：PASS
每个字段业务语义：PASS
Source / Mutable By / Null 行为：PASS
Migration 顶部说明：PASS
Migration 关键字段中文注释：PASS
Auto Evidence / Human Final 分离：PASS
integer microseconds / Source Mapping：PASS
```

用户验收 F04 前，本字典属于 `READY_FOR_REVIEW` 文档；用户验收后随 F04 Stable Snapshot 冻结。