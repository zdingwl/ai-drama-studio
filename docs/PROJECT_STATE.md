# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F03 — 视频预处理
Feature Status: IN_PROGRESS
F03 Contract: CONFIRMED
F03 Function Contracts: CONFIRMED
F03 0003 Migration: IMPLEMENTED / TARGETED TEST PASS
F03 Media Time Utilities: IMPLEMENTED / TARGETED TEST PASS
Business Code: IN_PROGRESS
F01 — 创建项目: STABLE / FROZEN
F02 — 上传原视频: STABLE / FROZEN
Stable Features: F01, F02
Frozen Features: F01, F02
Next After F03: F04 — 自动拉片（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建、切换、删除、重命名分支，也不创建或操作 PR。

---

# 当前恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-video-preprocessing.md
→ docs/features/F03-function-contracts.md
→ 最新相关 docs/sessions/*.md
```

---

# F01 / F02 冻结基线

权威快照：

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
```

F03 只能 Additive 扩展，特别不得：

```text
覆盖 F02 original.<ext>
改变 Source ID
改变 F02 source_videos 既有字段语义
把 Proxy Timeline 直接当 Source Timeline
用 float 秒替代 integer microseconds
用 frame_index / fps 作为 VFR 唯一定位
改变 F01/F02 已验收 StudioShell 基线
```

---

# F03 权威文档

```text
docs/features/F03-video-preprocessing.md
docs/features/F03-function-contracts.md
```

用户已通过“继续”明确确认 F03 当前规划并允许进入编码，因此 F03 已从 PLANNED 切换为 IN_PROGRESS。

---

# F03 目标

```text
F02 ready Source
→ Source integrity check
→ proxy.mp4
→ audio.wav（有音频时）
→ thumbnail.jpg
→ validate/hash/metadata
→ Source ↔ Proxy / Audio Mapping
→ source_preprocess ready
→ 重启后仍可读取
```

F03 不做：

```text
Shot Detection
Shot Boundary
ASR
人物识别
Scene
AI
GPU/NVENC 优化
多 Profile
Source 替换/覆盖
```

F04 仍未开始。

---

# F03 Preprocess Profile V1

Proxy：

```text
MP4
H.264 / libx264
CRF 23
preset fast
yuv420p
最大装入 1280×720
保持比例
不放大小视频
不强制 CFR
保留 presentation timestamp 节奏
Source 有音频时 Proxy 携带 AAC 128k
```

Analysis Audio：

```text
audio.wav
PCM s16le
16000 Hz
mono
```

Source 无音频时不生成假静音 WAV。

Thumbnail：

```text
thumbnail.jpg
thumbnail_proxy_time_us = min(proxy_duration_us / 10, 5_000_000)
同时保存 thumbnail_source_time_us
```

---

# F03 Workspace

```text
<workspace>/preprocess/
├── .staging/
│   └── SOURCE_<UUID>/
│       ├── proxy.mp4
│       ├── audio.wav      # 可选
│       └── thumbnail.jpg
└── SOURCE_<UUID>/
    ├── proxy.mp4
    ├── audio.wav          # 可选
    └── thumbnail.jpg
```

F02 Source 保持：

```text
source/SOURCE_<UUID>/original.<ext>
```

F03 绝不覆盖原片。

---

# F03 Database / Migration — 已完成底座

新增 Migration：

```text
0003_create_source_preprocess
```

新增表：

```text
source_preprocess
```

状态：

```text
processing
ready
```

F03 V1：

```text
1 Source Video → 0 或 1 个 Preprocess Asset Set
```

主要保存：

```text
Source SHA snapshot
Proxy path / size / hash / duration / timebase / fps
Proxy→Source offset
Audio path / size / hash / duration / sample rate / channels
Audio→Source offset
Thumbnail path / size / hash / Source timestamp
created_at / completed_at
```

数据库规则：

```text
processing
→ 只要求已知 Source snapshot + 目标路径
→ 输出 metadata 可以 NULL

ready
→ Proxy + Thumbnail 核心 metadata 必须完整
→ Source/Proxy time_base + mapping 必须存在

Audio
→ 全部 NULL（无音频）
或
→ path/size/hash/duration/16000Hz/mono/offset 全部完整
```

F01/F02 的 `projects` / `source_videos` 既有字段没有修改。

---

# F03 Migration Backup Gate — 已验证

真实升级路径验证：

```text
0002 app.db
→ init_database()
→ backups/app_<UTC>_0002_create_source_videos.db
→ backup revision = 0002
→ Alembic upgrade 0003
→ source_preprocess 存在
→ 第二次 init_database() 不重复生成 backup
```

结果：PASS。

共享备份机制仍来自 F02 已冻结的 SQLite `Connection.backup()` Gate，没有重新发明第二套 Migration 流程。

---

# F03 公共 Media Time Utility — 已完成底座

新增：

```text
engine/app/core/media_time.py
```

公共能力：

```text
seconds_to_microseconds()
pts_to_microseconds()
microseconds_to_pts()
derived_to_source_microseconds()
source_to_derived_microseconds()
```

规则：

```text
FFprobe 十进制秒
→ Decimal
→ integer microseconds

PTS + rational time_base
→ Fraction
→ integer microseconds

Proxy/Audio Mapping
source_us = derived_us + offset_us
derived_us = source_us - offset_us
```

支持负 PTS，不把媒体起始时间强制裁成 0。

禁止 F03/F04/F08 后续自己重复写 `int(seconds * 1000)` / `frame_index / fps` 作为权威时间逻辑。

针对性测试：

```text
Decimal 秒值 / half-up                 PASS
NaN 拒绝                              PASS
1/90000 PTS round-trip                PASS
负 PTS round-trip                     PASS
Source↔Derived integer offset round-trip PASS
非法 time_base 拒绝                   PASS
```

Media Time：6 passed。

Migration/Constraint：3 passed。

当前底座针对性合计：

```text
9 passed
```

完整 F01 + F02 + F03 回归仍在 F03 后续开发完成后执行，当前不能把 Feature 标成 READY_FOR_REVIEW。

---

# F03 核心函数进度

正式 7 个核心函数：

```text
generate_proxy_video()         NEXT
extract_analysis_audio()       NOT STARTED
generate_thumbnail()           NOT STARTED
inspect_preprocess_assets()    NOT STARTED
preprocess_source_video()      NOT STARTED
get_source_preprocess()        NOT STARTED
recover_source_preprocesses()  NOT STARTED
```

Controller：

```text
GET  /api/projects/{project_id}/preprocess   NOT STARTED
POST /api/projects/{project_id}/preprocess   NOT STARTED
```

详细职责见 `docs/features/F03-function-contracts.md`。

---

# F03 Timebase Contract

F03 属于 Source Domain。

权威单位：

```text
integer microseconds
```

Proxy Mapping：

```text
source_us = proxy_us + proxy_to_source_offset_us
proxy_us  = source_us - proxy_to_source_offset_us
```

Audio Mapping：

```text
source_us = audio_us + audio_to_source_offset_us
```

VFR：

```text
不强制 CFR
不使用 frame_index / fps 作为唯一定位
后续使用 timestamp mapping
```

媒体映射目标误差：

```text
<= 1 ms
```

超过时不得静默进入 F04。

---

# 当前下一步

```text
0003 Migration                 DONE / targeted PASS
Media Time Utility            DONE / targeted PASS
→ generate_proxy_video()
→ extract_analysis_audio()
→ generate_thumbnail()
→ inspect_preprocess_assets()
→ preprocess / get / recovery
→ 2 个 API
→ Vue F03 页面
→ F01 + F02 + F03 全量自动回归
→ Windows 真实短剧视频验收
→ READY_FOR_REVIEW
→ 用户验收
```

F03 未通过用户验收前不得进入 F04。

## 最近更新时间

- 日期：2026-08-24 10:56 +08:00
- 状态：用户确认 F03 规划并进入开发；0003 Migration + 公共媒体时间换算底座已实现，针对性 9 tests PASS；下一核心函数为 `generate_proxy_video()`。
