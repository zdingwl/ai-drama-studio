# F03 — Migration + Media Time Foundation

时间：2026-08-24 10:56 +08:00  
分支：main（用户未要求新建分支）

## 用户指令

用户在审核 F03 主 Contract 与详细函数职责后回复：

```text
继续
```

按项目 Feature 流程，将该指令视为允许 F03 从规划进入正式编码。

## 状态变化

```text
F01 = STABLE / FROZEN
F02 = STABLE / FROZEN
F03 = IN_PROGRESS
F04 = NOT STARTED
```

## 本次完成

### 1. 0003 Migration

新增：

```text
engine/migrations/versions/0003_create_source_preprocess.py
```

新增表：

```text
source_preprocess
```

设计：

```text
1 Source Video → 0/1 Preprocess Asset Set
status = processing / ready
profile_version = 1
```

`processing` 阶段只保存已经知道的数据：

```text
source_video_id
project_id
source_sha256_snapshot
proxy_relative_path
thumbnail_relative_path
created_at
```

输出媒体 metadata 暂时允许 NULL。

`ready` 阶段数据库 CHECK 强制：

```text
Proxy size/hash/duration/time_base/mapping 完整
Thumbnail size/hash/source_time 完整
Source time_base snapshot 完整
completed_at 存在
```

Audio 约束：

```text
全部为空
→ Source 无音频

或

全部完整
→ audio.wav path/size/hash/duration/16000Hz/mono/offset
```

禁止出现只保存 WAV 路径、却没有 Hash/时长/采样率的半成品状态。

### 2. Migration Backup Gate 回归

仍复用 F02 已冻结的共享：

```text
SQLite Connection.backup()
→ backup 成功
→ Alembic upgrade
```

实际验证：

```text
0002 app.db
→ 生成 1 份 backup
→ backup revision = 0002_create_source_videos
→ upgrade 0003_create_source_preprocess
→ source_preprocess 表存在
→ 第二次 init_database 不重复 backup
```

结果 PASS。

### 3. 公共 Media Time Utility

新增：

```text
engine/app/core/media_time.py
```

能力：

```text
seconds_to_microseconds()
pts_to_microseconds()
microseconds_to_pts()
derived_to_source_microseconds()
source_to_derived_microseconds()
```

规则：

```text
十进制 seconds
→ Decimal
→ integer microseconds

PTS + rational time_base
→ Fraction
→ integer microseconds

source_us = derived_us + offset_us
derived_us = source_us - offset_us
```

支持负 PTS。

以后 F04/F08 等 Source Domain Feature 不得自己重新写：

```text
int(seconds * 1000)
frame_index / fps
```

作为权威时间换算。

### 4. 测试

新增：

```text
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_database_migration_f03.py
```

同时更新：

```text
engine/tests/unit/test_database.py
engine/tests/unit/test_database_migration_f02.py
```

原因：0003 是合法 Additive Migration，因此旧的：

```text
当前 head 必须等于 0002
当前业务表只能有 projects + source_videos
```

已经变成过时断言。

只更新“当前 head / 当前表集合”，没有删除 F01 projects 或 F02 source_videos 的冻结字段、状态、约束回归。

本次 F03 底座针对性验证：

```text
Media Time          6 passed
Migration/Constraint 3 passed
合计                9 passed
```

完整 F01+F02+F03 回归仍需在 F03 全功能完成后执行。

## 下一步

```text
generate_proxy_video()
```

只负责：

```text
F02 original.ext
→ FFmpeg
→ staging proxy.mp4
```

固定 Profile V1：

```text
H.264 libx264
CRF 23
preset fast
yuv420p
最大装入 1280×720
保持比例
禁止放大小视频
不强制 CFR
Source 有音频时 Proxy AAC 128k
```

它不会：

```text
写 DB ready
生成 WAV
生成 Thumbnail
执行 Shot Detection
修改 F02 Source
```

F03 未通过用户验收前不得进入 F04。
