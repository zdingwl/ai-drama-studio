# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F03 — 视频预处理
Feature Status: PLANNED
F03 Contract: DRAFTED / WAITING_USER_CONFIRMATION
F03 Function Contracts: DRAFTED / WAITING_USER_CONFIRMATION
Business Code: NOT STARTED
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

F03 只能做兼容性 Additive 扩展，特别不得：

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

# F03 权威规划文档

```text
docs/features/F03-video-preprocessing.md
docs/features/F03-function-contracts.md
```

当前尚未获得用户对 F03 Contract 的最终确认，因此：

```text
F03 = PLANNED
Business Code = NOT STARTED
```

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

# F03 Preprocess Profile V1 Draft

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
保留 presentation timestamp 节奏
不强制 CFR
Source 有音频时 Proxy 携带 AAC 128k
```

Analysis Audio：

```text
audio.wav
PCM s16le
16000 Hz
mono
```

Source 无音频时：

```text
不生成假静音 WAV
```

Thumbnail：

```text
thumbnail.jpg
从 Proxy 固定时间点抽取
同时记录 thumbnail_source_time_us
```

---

# F03 Workspace Draft

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

# F03 Database Draft

计划 Migration：

```text
0003_create_source_preprocess
```

计划新增：

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
1 Source Video → 0 或 1 个 ready Preprocess Asset Set
```

保存：

```text
Source SHA snapshot
Proxy path / size / hash / duration / timebase / fps
Proxy→Source offset
Audio path / size / hash / duration / sample rate / channels
Audio→Source offset
Thumbnail path / size / hash / Source timestamp
created_at / completed_at
```

Migration 继续复用已经冻结的 SQLite Upgrade Backup Gate。

---

# F03 Timebase Draft

F03 属于：

```text
Source Domain
```

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

目标媒体映射误差：

```text
<= 1 ms
```

超过时不得静默进入 F04。

---

# F03 Processing / Recovery Draft

```text
验证 Project + F02 Source
→ Source size/hash
→ DB processing
→ staging
→ Proxy
→ Audio（可选）
→ Thumbnail
→ inspect
→ publish staging → final
→ DB ready
```

Final 发布前失败：

```text
清理本次 F03 known staging
+ processing row
```

Final 发布后 DB finalization 失败：

```text
保留 final
保留 processing
→ Startup Recovery
```

Unknown file / invalid final：

```text
保留现场
不递归删除
```

Recovery 永远不能删除 F02 Source。

---

# F03 核心函数 Draft

7 个：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

2 个 Controller：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

每个函数的具体业务作用、调用关系、输入输出、副作用、失败行为、禁止行为和测试要求见：

```text
docs/features/F03-function-contracts.md
```

---

# F03 UI Draft

路由：

```text
/projects/:projectId/preprocess
```

项目流程：

```text
01 项目总览      已完成
02 视频导入      已完成
03 视频预处理    当前开放
04 自动拉片      禁用
```

页面：

```text
Source summary
→ 固定 Preprocess Profile
→ 开始视频预处理
→ Processing（不伪造百分比）
→ Ready：Proxy / Audio / Thumbnail / Timeline Mapping
```

Ready 后 F03 V1 不提供“重新预处理”按钮。

---

# Environment Gate Draft

F03 用户 Windows 环境需要确认：

```powershell
ffmpeg -version
ffmpeg -hide_banner -encoders | findstr /I "libx264 aac pcm_s16le"
ffprobe -version
```

F03 不新增 PyTorch / OpenCV / Shot Detection 依赖。

---

# 当前下一步

等待用户审核：

```text
F03 主 Contract
+
F03 7 个核心函数 / 2 个 Controller 详细职责
```

如果用户确认：

```text
F03 → IN_PROGRESS
→ 0003 Migration + F01/F02 Regression
→ 公共 media-time mapping utility
→ Proxy / WAV / Thumbnail
→ inspect + Recovery
→ API
→ Vue 页面
→ 自动测试 + 真实短剧视频测试
→ READY_FOR_REVIEW
```

未经用户确认不开始 F03 业务代码。

## 最近更新时间

- 日期：2026-08-24 10:46 +08:00
- 状态：用户已明确开始 F03；F03 主 Contract + 详细函数职责已起草并写入 main，等待用户确认后进入编码。
