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
F03 Pre-Acceptance Audit: COMPLETE
F03 Retry Recovery Fix: COMPLETE
F03 0004 Compatibility Migration Fix: COMPLETE
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
→ 开始前核验 Source size + SHA-256
→ DB source_preprocess = processing
→ preprocess/.staging/SOURCE_xxx/
→ proxy.mp4
→ audio.wav（Source 有音频时）
→ thumbnail.jpg
→ FFprobe / size / SHA / Profile 校验
→ Source↔Proxy / Audio 时间映射
→ publish 前再次核验 Source size + SHA-256 未在处理中变化
→ staging publish final
→ DB source_preprocess = ready
→ Vue 页面展示资产和 Timeline Mapping
→ 重启后仍可读取
```

F03 不做 Shot Detection、ASR、人物识别、Scene 或任何 AI。F04 尚未开始。

---

# F03 Database / Migration

```text
0003_create_source_preprocess
→ 0004_repair_source_preprocess_audio_constraint   ← 当前 head

Table:  source_preprocess
Status: processing / ready
```

规则：

- processing 可以保存已知目标路径，未知媒体 metadata 允许 NULL；
- ready 时 Proxy + Thumbnail + Timeline Mapping 必须完整；
- ready 若有 Audio，则 path / size / hash / duration / 16000Hz / mono / offset 必须全部完整；
- Source 无音频时 Audio 字段为空，不生成假静音 WAV；
- 所有已存在数据库升级仍使用 SQLite `Connection.backup()` 安全备份。

### 0004 为什么必须存在

用户真实 Windows 数据库已经执行过早期 0003。早期 0003 的 Audio CHECK 是：

```text
Audio 字段必须“全空或全完整”
```

但合法 F03 processing 阶段会出现：

```text
audio_relative_path 已知
size/hash/duration 尚未生成
```

因此旧数据库会把正常 INSERT 拒绝。之后只修改仓库里的 0003 文件并不能修复已经执行过 0003 的 app.db，因为 Alembic 不会重复运行同一 revision。

现在由正式兼容 Migration 处理：

```text
0003 旧数据库
→ init_database() 先创建一致性 backup
→ 0004 检测 ck_source_preprocess_audio_all_or_none
→ SQLite batch rebuild source_preprocess
→ 替换为 ck_source_preprocess_audio_ready_consistency
→ F01/F02/F03 已有数据保留
```

如果是全新数据库，当前 0003 已经包含正确约束，0004 检测后不重复重建，只推进 revision。

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

# F03 Time / Source Integrity

Mapping：

```text
source_us = proxy_us + proxy_to_source_offset_us
source_us = audio_us + audio_to_source_offset_us
```

Offset 来自实际 stream start timestamp，不假设 `Proxy 0 == Source 0`。

媒体时长：

```text
selected stream.duration
→ 缺失时 format.duration
```

Source 完整性：

```text
开始前：磁盘 size/hash == F02 DB
publish 前：磁盘 size/hash == F02 DB == source_sha256_snapshot
```

处理中 Source 发生外部替换时禁止发布。

---

# F03 processing 重试规则

用户真实验收曾出现：页面没有 ready 结果，但 DB 留有旧 `processing`，旧实现导致再次点击统一报“当前项目已经存在视频预处理记录”。该问题已修复。

现在规则：

```text
已有 ready
→ PREPROCESS_ALREADY_EXISTS
→ 仍然禁止重复预处理

已有 processing + 完整 final
→ 校验后自动恢复 ready

已有 processing + staging 最近 30 秒仍在写
→ PREPROCESS_IN_PROGRESS
→ 不删除，避免误伤正在运行的 FFmpeg

已有 processing + staging 已停止写入且只有系统已知文件
→ 安全清理 staging + processing
→ 当前点击继续重新预处理

已有 processing + 无 staging/final 且记录已过保护窗口
→ 删除旧 processing
→ 当前点击继续重新预处理

存在未知文件 / 异常 final / Source Hash 不一致
→ PREPROCESS_RECOVERY_REQUIRED
→ 保留现场，不自动删除
```

新增 HTTP 409 状态：

```text
PREPROCESS_IN_PROGRESS
PREPROCESS_RECOVERY_REQUIRED
```

上述重试/清理永远不得修改或删除 F02 Source Video。

---

# F03 Core / API

7 个核心函数：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

2 个 API：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

Controller 只做 `HTTP → Business → Response`。

---

# F03 Frontend

路由：

```text
/projects/:projectId/preprocess
```

左侧 `03 视频预处理` 已开放；`04 自动拉片` 仍禁用。

页面支持：无 Source 阻止、固定 Profile、开始处理、真实 processing 状态、Ready 资产详情、Timeline Mapping、无音频提示。处理中不伪造百分比。

---

# Verification

已经实际执行的开发阶段验证：

```text
Media Time targeted tests                         6 PASS
0003 Migration / Constraint targeted tests       3 PASS
0002 → backup → 0003 Upgrade                     PASS
1920×1080 + Audio 实际 FFmpeg 链路               PASS
No-Audio 实际 FFmpeg 链路                        PASS
Source start_time=2s → Proxy offset=2,000,000us PASS
Synthetic VFR → Proxy 仍保留多种 PTS 间隔        PASS
processing Audio 路径允许 metadata 暂空          PASS
ready Audio metadata 不完整被拒绝                PASS
0004 SQLite/Alembic batch constraint replacement PASS（隔离机制验证）
```

已加入仓库测试：

```text
engine/tests/unit/test_database_migration_f03.py
engine/tests/unit/test_database_migration_f03_compat.py
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_preprocess_f03.py
engine/tests/unit/test_preprocess_vfr_f03.py
engine/tests/unit/test_preprocess_integrity_f03.py
engine/tests/unit/test_preprocess_retry_recovery_f03.py
```

最新增加覆盖：

```text
真实旧 0003 Audio CHECK → 0004 自动修复
0004 前自动备份仍是旧 0003
修复后 processing + audio target path 可以落库
全新正确 0003 → 0004 不重复重建
旧 processing 无文件 → 自动清理并允许重试
最近仍写 staging → 不误删
未知 staging 文件 → 保留现场
Source 在处理中被替换 → 禁止 publish
stream.duration 优先于 container duration
```

当前工具环境无法完整 clone 最新仓库，因此最终全量 `pytest engine/tests`、`npm run typecheck`、`npm run build` 仍由用户 Windows 工作副本完成。

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

本次用户需要优先复测：

```text
git pull origin main
重启 FastAPI
启动时 app.db 应从 0003 自动升级到 0004
进入原项目 F03
再次点击“开始视频预处理”
有音频 Source 不应再因旧 Audio CHECK 返回 409
```

F03 未通过用户验收前不得进入 F04 正式开发。

## 最近更新时间

- 日期：2026-08-24 11:57 +08:00
- 状态：F03 READY_FOR_REVIEW；已新增 0004 正式兼容迁移修复用户已部署旧 0003 Audio CHECK，等待 Windows 复测。
