# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细过程放 `docs/features/*-implementation-log.md` 和 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F03 — 视频预处理
Feature Status: READY_FOR_REVIEW
F03 Contract: CONFIRMED
F03 Function Contracts: CONFIRMED
F03 Business Code: COMPLETE
F03 Frontend: COMPLETE
F03 User Acceptance: PENDING

F01 — 创建项目: STABLE / FROZEN
F02 — 上传原视频: STABLE / FROZEN
Stable Features: F01, F02
Frozen Features: F01, F02

Next After F03: F04 — 自动拉片（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建、切换、删除、重命名分支，也不创建或操作 PR。

---

# 恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-video-preprocessing.md
→ docs/features/F03-function-contracts.md
→ docs/features/F03-implementation-log.md
→ 最新相关 docs/sessions/*.md
```

---

# 冻结上游

F01、F02 已由用户实际测试并冻结：

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
```

F03 只做 Additive 扩展，没有改变 F01/F02 的 Project ID、Source ID、既有表字段语义、Source 正式路径、ready Source 只读规则、既有 API、integer microseconds / rational FPS 或 StudioShell 基线。

---

# F03 权威文档

```text
docs/features/F03-video-preprocessing.md
docs/features/F03-function-contracts.md
docs/features/F03-implementation-log.md
```

当前真实实现状态以本文件和 `F03-implementation-log.md` 为准。

---

# F03 已完成闭环

```text
F02 ready Source
→ 重新核验 Source size + SHA-256
→ DB source_preprocess = processing
→ preprocess/.staging/SOURCE_xxx/
→ proxy.mp4
→ audio.wav（Source 有音频时）
→ thumbnail.jpg
→ FFprobe / size / SHA / Profile 校验
→ Source↔Proxy / Audio 时间映射
→ staging publish final
→ DB source_preprocess = ready
→ Vue 页面展示资产和 Timeline Mapping
→ 重启后仍可读取
```

F03 不做 Shot Detection、ASR、人物识别、Scene 或任何 AI。F04 尚未开始。

---

# F03 Database / Migration

```text
Migration: 0003_create_source_preprocess
Table:     source_preprocess
Status:    processing / ready
```

规则：

- processing 可以保存已知目标路径，未知媒体 metadata 允许 NULL；
- ready 时 Proxy + Thumbnail + Timeline Mapping 必须完整；
- ready 若有 Audio，则 path / size / hash / duration / 16000Hz / mono / offset 必须全部完整；
- Source 无音频时 Audio 字段为空，不生成假静音 WAV；
- 0002→0003 升级继续使用 SQLite `Connection.backup()` 安全备份。

收尾审查已修复 Audio Constraint：有音频 Source 在 processing 阶段可以先保存 `audio.wav` 目标路径，不会因为 size/hash 尚未知而被数据库错误拒绝。

---

# F03 Preprocess Profile V1

Proxy：

```text
proxy.mp4
H.264 / libx264
CRF 23
preset fast
yuv420p
最大 1280×720
保持比例
不放大小视频
-fps_mode passthrough
不强制 VFR→CFR
Source 有音频时 AAC 128k
faststart
```

Analysis Audio：

```text
audio.wav
PCM s16le
16000 Hz
mono
```

Thumbnail：

```text
thumbnail.jpg
proxy time = min(proxy_duration_us / 10, 5_000_000us)
```

F02 `original.<ext>` 永不覆盖。

---

# F03 Time Contract

公共模块：

```text
engine/app/core/media_time.py
```

公共函数：

```text
seconds_to_microseconds()
pts_to_microseconds()
microseconds_to_pts()
derived_to_source_microseconds()
source_to_derived_microseconds()
```

Mapping：

```text
source_us = proxy_us + proxy_to_source_offset_us
source_us = audio_us + audio_to_source_offset_us
```

Offset 来自实际 stream start timestamp，不假设 `Proxy 0 == Source 0`。

VFR Proxy 不强制 CFR；F04 不得把 `frame_index / fps` 当作唯一 Source Timeline 定位方式。

---

# F03 Core / API

7 个核心函数全部完成：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

主文件：

```text
engine/app/preprocess.py
```

2 个 API 全部完成：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

Controller 只做 `HTTP → Business → Response`，不直接 SQL、FFmpeg、FFprobe、Hash、文件发布或 Recovery。

---

# F03 Frontend

已完成：

```text
frontend/src/types/preprocess.ts
frontend/src/api/preprocess.ts
frontend/src/stores/preprocess.ts
frontend/src/views/VideoPreprocess.vue
frontend/src/preprocess.css
```

并更新 Router、StudioShell、ProjectWorkspace、main.ts。

路由：

```text
/projects/:projectId/preprocess
```

左侧 `03 视频预处理` 已开放；`04 自动拉片` 仍禁用。

页面支持：无 Source 阻止、固定 Profile、开始处理、真实 processing 状态、Ready 资产详情、Timeline Mapping、无音频提示。处理中不伪造百分比。

---

# Verification

已经实际执行：

```text
Media Time targeted tests                         6 PASS
0003 Migration / Constraint targeted tests       3 PASS
0002 → backup → 0003 Upgrade                     PASS
Python preprocess.py / media_time.py py_compile PASS
1920×1080 + Audio 实际 FFmpeg 链路               PASS
No-Audio 实际 FFmpeg 链路                        PASS
Source start_time=2s → Proxy offset=2,000,000us PASS
Synthetic VFR → Proxy 仍保留多种 PTS 间隔        PASS
processing Audio 路径允许 metadata 暂空          PASS
ready Audio metadata 不完整被拒绝                PASS
```

已加入仓库测试：

```text
engine/tests/unit/test_database_migration_f03.py
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_preprocess_f03.py
engine/tests/unit/test_preprocess_vfr_f03.py
```

当前工具容器无法联网完整 clone 仓库，因此本轮没有冒充执行完整 `pytest engine/tests`、`npm ci`、`vue-tsc`、`vite build`。这些由用户 Windows 工作副本完成最终 Review Gate。

---

# 用户验收 Gate

F03 当前最高允许状态：

```text
READY_FOR_REVIEW
```

用户实际测试并明确确认通过后，才允许：

```text
F03 → STABLE / FROZEN
```

最终验收重点：

```text
pytest engine/tests -q
npm ci
npm run typecheck
npm run build
真实短剧原片预处理
Proxy / WAV / Thumbnail 正确
Timeline Mapping 正确
Source 原片未改变
无音频不产生假 WAV
重启后结果仍存在
重复预处理被阻止
F01 / F02 回归正常
```

F03 未通过用户验收前不得进入 F04 正式开发。

## 最近更新时间

- 日期：2026-08-24 11:03 +08:00
- 状态：F03 全部规划代码、API、Recovery、Vue 页面和自动测试已提交 main；当前 READY_FOR_REVIEW，等待用户 Windows 真实视频验收。
