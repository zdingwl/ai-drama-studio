# F06 — Database Dictionary

Migration 计划：

```text
0007_create_character_detection
```

F06 只新增 3 张业务表：

```text
character_detection_runs
character_candidates
character_tracks
```

原则：

```text
F05 final_shots = 只读上游
F06 自动 Evidence = 新表
F07 Final Character = 后续新表，禁止提前混入 F06
```

---

# 1. `character_detection_runs`

用途：表示一次完整、可追溯的自动人物识别运行。

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Null Meaning | Downstream Use |
|---|---|---:|---|---|---|---|---|---|
| `id` | TEXT | No | — | Run 稳定 ID：`CHAR_DETECTION_<UUID4>` | F06 | Never | — | F07 来源追溯 |
| `project_id` | TEXT | No | — | 所属项目 | F01/F06 | Never | — | 查询隔离 |
| `source_edit_set_id` | TEXT | No | — | 本 Run 基于哪一套 F05 Edit Set | F05 snapshot | Never | — | Dependency |
| `source_edit_set_revision` | INTEGER | No | — | F05 revision 快照 | F05 snapshot | Never | — | Stale 判断 |
| `status` | TEXT | No | — | `processing / ready / failed` | F06 | F06 | — | UI / recovery |
| `is_current` | INTEGER | No | `0` | 当前项目是否使用此 Ready Run | F06 transaction | F06 | — | F07 默认输入 |
| `profile_version` | TEXT | No | — | 算法参数 Profile，例如 `f06-v1` | F06 config | Never | — | 重现结果 |
| `sampling_profile_json` | TEXT | No | — | target fps / min/max samples / margins | F06 config | Never | — | 重现采样 |
| `detector_model_id` | TEXT | No | — | YuNet 逻辑模型 ID | model registry | Never | — | 模型追溯 |
| `detector_model_sha256` | TEXT | No | — | 实际 YuNet ONNX SHA-256 | model registry | Never | — | 模型身份校验 |
| `recognizer_model_id` | TEXT | No | — | SFace 逻辑模型 ID | model registry | Never | — | 模型追溯 |
| `recognizer_model_sha256` | TEXT | No | — | 实际 SFace ONNX SHA-256 | model registry | Never | — | 模型身份校验 |
| `opencv_version` | TEXT | No | — | 实际运行 OpenCV 版本 | runtime | Never | — | 环境追溯 |
| `runtime_device` | TEXT | No | — | V1 固定 `cpu` | runtime | Never | — | 环境追溯 |
| `sampled_frame_count` | INTEGER | No | `0` | 实际分析帧数 | F06 | F06 | — | 诊断 |
| `face_observation_count` | INTEGER | No | `0` | 合格 Face Observation 数量 | F06 | F06 | — | 诊断 |
| `track_count` | INTEGER | No | `0` | 产生 Track 数 | F06 | F06 | — | UI / validate |
| `candidate_count` | INTEGER | No | `0` | 产生 Candidate 数 | F06 | F06 | — | UI / validate |
| `started_at` | DATETIME | No | — | UTC 开始时间 | F06 | Never | — | 诊断 |
| `completed_at` | DATETIME | Yes | NULL | ready/failed 完成时间 | F06 | F06 | processing 未结束 | 诊断 |
| `error_code` | TEXT | Yes | NULL | 失败错误码 | F06 | F06 | 非 failed | UI / recovery |
| `error_message` | TEXT | Yes | NULL | 可读失败原因 | F06 | F06 | 非 failed | UI / debug |
| `created_at` | DATETIME | No | — | DB 创建 UTC | F06 | Never | — | 审计 |

建议约束：

```text
status IN ('processing','ready','failed')
is_current IN (0,1)
source_edit_set_revision >= 1
sampled_frame_count >= 0
face_observation_count >= 0
track_count >= 0
candidate_count >= 0
ready  -> completed_at IS NOT NULL AND error_code IS NULL
failed -> completed_at IS NOT NULL AND error_code IS NOT NULL
processing -> completed_at IS NULL
is_current=1 -> status='ready'
```

建议索引：

```text
INDEX(project_id, created_at)
UNIQUE INDEX(project_id) WHERE is_current = 1
```

`is_current` 只允许在“新结果已经完整验证”后的事务里切换。

---

# 2. `character_candidates`

用途：保存 F06 自动聚类出的“可能是同一个人”的 Character Candidate。

Candidate 是 AI Evidence，不是 Final Character。

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Null Meaning | Downstream Use |
|---|---|---:|---|---|---|---|---|---|
| `id` | TEXT | No | — | `CHAR_CANDIDATE_<UUID4>` | F06 | Never | — | F07 Evidence |
| `run_id` | TEXT | No | — | 所属 Detection Run | F06 | Never | — | 版本隔离 |
| `project_id` | TEXT | No | — | 所属项目 | F06 | Never | — | 查询隔离 |
| `ordinal` | INTEGER | No | — | Run 内 1-based 显示顺序 | F06 | Never after ready | — | UI |
| `track_count` | INTEGER | No | — | 聚类包含 Track 数 | F06 | Never after ready | — | UI / validate |
| `shot_count` | INTEGER | No | — | 出现的不同 Final Shot 数 | F06 | Never after ready | — | UI |
| `first_seen_us` | BIGINT | No | — | 最早 Source time | F06 | Never after ready | — | Timeline |
| `last_seen_us` | BIGINT | No | — | 最晚 Source time | F06 | Never after ready | — | Timeline |
| `cover_track_id` | TEXT | No | — | 自动 Cover 所属 Track | F06 | Never after ready | — | UI Evidence |
| `cover_source_us` | BIGINT | No | — | 自动 Cover Source time | F06 | Never after ready | — | Cover 重建 |
| `cover_bbox_json` | TEXT | No | — | Cover bbox `[x,y,w,h]` / schema object | F06 | Never after ready | — | Cover crop |
| `centroid_embedding_blob` | BLOB | No | — | Candidate 归一化聚类中心 embedding | F06 | Never after ready | — | F07 辅助 / debug |
| `cluster_score` | REAL | Yes | NULL | Candidate 内聚合置信分；单 Track Candidate 可为空 | F06 | Never after ready | 单 Track无内部相似度 | UI/诊断 |
| `created_at` | DATETIME | No | — | 创建 UTC | F06 | Never | — | 审计 |

建议约束：

```text
UNIQUE(run_id, ordinal)
ordinal >= 1
track_count >= 1
shot_count >= 1
last_seen_us >= first_seen_us
cluster_score IS NULL OR (cluster_score >= 0 AND cluster_score <= 1)
```

禁止字段：

```text
name
role_type
is_main_character
final_reference
```

这些属于 F07。

---

# 3. `character_tracks`

用途：保存一个人物在一个 Final Shot 内的一段人脸 Evidence Track。

Track 不跨 Shot。

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Null Meaning | Downstream Use |
|---|---|---:|---|---|---|---|---|---|
| `id` | TEXT | No | — | `TRACK_<UUID4>` | F06 | Never | — | Evidence |
| `run_id` | TEXT | No | — | 所属 Detection Run | F06 | Never | — | 版本隔离 |
| `project_id` | TEXT | No | — | 所属项目 | F06 | Never | — | 查询隔离 |
| `final_shot_id` | TEXT | No | — | 所属 F05 Final Shot | F05/F06 | Never | — | Shot 关联 |
| `candidate_id` | TEXT | No | — | F06 自动聚类 Candidate | F06 cluster | Never after ready | — | Candidate Evidence |
| `track_ordinal_in_shot` | INTEGER | No | — | 当前 Shot 内 Track 顺序 | F06 | Never after ready | — | UI / deterministic ordering |
| `start_us` | BIGINT | No | — | Track 最早 Observation Source time | F06 | Never after ready | — | Timeline |
| `end_us` | BIGINT | No | — | Track 最晚 Observation Source time | F06 | Never after ready | — | Timeline |
| `representative_source_us` | BIGINT | No | — | 最适合展示的 Observation 时间 | F06 | Never after ready | — | Track preview |
| `representative_bbox_json` | TEXT | No | — | 对应 bbox | F06 | Never after ready | — | Face crop |
| `sample_count` | INTEGER | No | — | Track 内 Observation 数 | F06 | Never after ready | — | UI / quality |
| `mean_face_quality` | REAL | No | — | Track 平均 Face quality 0..1 | F06 | Never after ready | — | UI / cover ranking |
| `max_face_quality` | REAL | No | — | Track 最佳 Face quality 0..1 | F06 | Never after ready | — | Cover selection |
| `track_embedding_blob` | BLOB | No | — | Track 归一化 mean embedding | F06 | Never after ready | — | clustering / F07 evidence |
| `samples_json` | TEXT | No | — | 轻量 Observation 列表：time/bbox/detection_score/quality | F06 | Never after ready | — | Debug / Evidence Timeline |
| `created_at` | DATETIME | No | — | 创建 UTC | F06 | Never | — | 审计 |

建议约束：

```text
UNIQUE(run_id, final_shot_id, track_ordinal_in_shot)
track_ordinal_in_shot >= 1
end_us >= start_us
representative_source_us >= start_us
representative_source_us <= end_us
sample_count >= 1
mean_face_quality BETWEEN 0 AND 1
max_face_quality BETWEEN 0 AND 1
max_face_quality >= mean_face_quality
```

`end_us` 表示最后一个 Evidence sample time，不代表人物持续占据画面直到某个半开区间终点，因此这里不使用 Shot 的 `[start,end)` 语义冒充连续可见区间。

---

# 4. Foreign Keys / Delete Policy

计划：

```text
character_candidates.run_id -> character_detection_runs.id
character_tracks.run_id -> character_detection_runs.id
character_tracks.candidate_id -> character_candidates.id
character_tracks.final_shot_id -> final_shots.id
```

历史 Run 默认保留，不提供普通 UI 删除。

F06 不允许删除/覆盖 F05 `final_shots`。

---

# 5. Embedding Storage Contract

SFace embedding 保存为 BLOB，必须同时由 Run 绑定：

```text
recognizer_model_id
recognizer_model_sha256
profile_version
```

编码前必须固定 BLOB serialization：

```text
float32
little-endian
C-contiguous
normalized vector
```

读取时必须校验：

```text
expected dimension
byte length
finite values
norm within tolerance
```

禁止使用 Python pickle 保存 embedding。

---

# 6. `samples_json` Contract

V1 每个 Track 的 `samples_json` 只保存轻量 Evidence：

```json
[
  {
    "source_time_us": 23150000,
    "bbox": [418, 96, 144, 182],
    "detection_score": 0.9821,
    "face_quality": 0.91
  }
]
```

不保存：

```text
base64 JPEG
完整 per-sample embedding
任意 Python object serialization
```

目的：控制 SQLite 体积，同时保证 Track 可审计。

---

# 7. Cache ≠ Database

F06 图片缓存：

```text
.cache/f06/frames/
.cache/f06/faces/
.cache/f06/candidates/
```

可以清理。

数据库中的时间、bbox、embedding、candidate assignment 才是正式自动 Evidence。

缓存缺失时应可根据 DB + F03 Proxy 重建，不允许把“JPEG 不见了”等同于 Run 数据损坏。
