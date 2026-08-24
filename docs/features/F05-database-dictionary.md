# F05 Database Dictionary

## `shot_edit_sets`

用途：保存一个 Project 的人工镜头修正工作状态。F05 创建；F06+ 只读。一个项目 V1 只允许一套。

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Frozen | Example |
|---|---|---:|---|---|---|---|---|---|
| `id` | TEXT | No | — | F05 Edit Set 稳定 ID | F05 initialize | Never | Yes after create | `SHOT_EDIT_...` |
| `project_id` | TEXT | No | — | 所属 Project | F01/F05 | Never | Yes | `PROJECT_...` |
| `source_detection_id` | TEXT | No | — | 初始化 Final Shot 所依据的 F04 Detection Run；用于追溯和阻止上游静默替换 | F04 snapshot | Never | Yes | `SHOT_DETECTION_...` |
| `status` | TEXT | No | — | `editing` 可修改；`confirmed` 人工确认后锁定 | F05 | F05 confirm | Yes when confirmed | `editing` |
| `revision` | INTEGER | No | — | 每次边界/拆分/合并/确认递增，用于识别工作区是否发生改变 | F05 | F05 | No | `4` |
| `source_start_us` | BIGINT | No | — | Final Shot 必须覆盖的 Source 起点 | F04 ready snapshot | Never | Yes | `0` |
| `source_end_us` | BIGINT | No | — | Final Shot 必须覆盖的 Source 终点 | F04 ready snapshot | Never | Yes | `66360000` |
| `created_at` | DATETIME | No | — | Edit Set 创建 UTC | F05 | Never | Yes | — |
| `updated_at` | DATETIME | No | — | 最近一次人工结构修改 UTC | F05 | F05 | No | — |
| `confirmed_at` | DATETIME | Yes | NULL | 人工确认 UTC；editing 必须为空 | F05 confirm | F05 confirm | Yes when set | — |

关键约束：

```text
UNIQUE(project_id)
status IN ('editing','confirmed')
revision >= 1
source_end_us > source_start_us
confirmed -> confirmed_at NOT NULL
editing -> confirmed_at IS NULL
```

## `final_shots`

用途：保存人工工作区中的生产级 Final Shot。F04 Candidate 只是 Auto Evidence；F05 Final Shot 才是后续人物、对白、Scene、生成、QC 应关联的 Shot 身份。

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Frozen | Example |
|---|---|---:|---|---|---|---|---|---|
| `id` | TEXT | No | — | 稳定 Final Shot ID；边界调整不改 ID；拆分新建；合并保留左 ID | F05 | Never | Yes | `SHOT_...` |
| `edit_set_id` | TEXT | No | — | 所属人工修正工作区 | F05 | Never | Yes | `SHOT_EDIT_...` |
| `project_id` | TEXT | No | — | 所属 Project | F05 | Never | Yes | `PROJECT_...` |
| `ordinal` | INTEGER | No | — | 当前 1-based 镜头顺序；拆分/合并后重新维护连续 | F05 | F05 | No until confirm | `12` |
| `final_start_us` | BIGINT | No | — | 人工最终 Source 起点 | F04 copy / F05 edit | F05 | Yes after confirm | `23200000` |
| `final_end_us` | BIGINT | No | — | 人工最终 Source 终点 | F04 copy / F05 edit | F05 | Yes after confirm | `25840000` |
| `duration_us` | BIGINT | No | — | `final_end_us - final_start_us` 派生值 | F05 | F05 | Yes after confirm | `2640000` |
| `origin_kind` | TEXT | No | — | `auto` 未发生人工结构改变；`manual` 已调整/拆分/合并 | F05 | F05 | Yes after confirm | `manual` |
| `origin_candidate_ids_json` | TEXT | No | — | 可追溯到哪些 F04 Candidate；拆分继承，合并取并集 | F05 | F05 | Yes after confirm | `["SHOT_CANDIDATE_..."]` |
| `created_at` | DATETIME | No | — | Final Shot 身份首次创建 UTC | F05 | Never | Yes | — |
| `updated_at` | DATETIME | No | — | 最近修改 UTC | F05 | F05 | No until confirm | — |

关键单行约束：

```text
UNIQUE(edit_set_id, ordinal)
ordinal >= 1
final_end_us > final_start_us
duration_us = final_end_us - final_start_us
origin_kind IN ('auto','manual')
```

跨行 Contract 由 `shot_workbench._validate_final_timeline()` 在读取/确认时统一验证：

```text
first.start == edit_set.source_start_us
last.end == edit_set.source_end_us
prev.end == next.start
ordinal == 1..N
无 gap / overlap
```

## F04 / F05 分离

禁止：

```sql
UPDATE shot_candidates SET detected_start_us = ...;
```

人工修改只能写 `final_shots.final_*`。这样自动算法证据与人工最终结果可以长期对比和回溯。