# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

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

# 当前恢复顺序

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

F01、F02 已由用户实际测试并冻结。

权威快照：

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
```

F03 只做 Additive 扩展，没有改变：

```text
Project ID
Source ID
projects 既有字段语义
source_videos 既有字段语义
F02 source/SOURCE_xxx/original.ext 路径
F02 ready Source 只读规则
F01/F02 既有 API 语义
integer microseconds / rational FPS
正式 StudioShell UI 基线
```

---

# F03 已完成业务闭环

```text
F02 ready Source
→ 重新校验实际 size + SHA-256
→ DB source_preprocess = processing
→ preprocess/.staging/SOURCE_xxx/
→ FFmpeg 生成 proxy.mp4
→ Source 有音频时生成 audio.wav
→ 从 Proxy 生成 thumbnail.jpg
→ FFprobe / size / SHA-256 / Profile 校验
→ 读取 Source/Proxy/Audio 实际 stream start timestamp
→ 计算 Source ↔ Proxy / Audio offset
→ staging 发布 preprocess/SOURCE_xxx/
→ DB source_preprocess = ready
→ 页面展示预处理资产和 Timeline Mapping
→ 重启后仍可读取
```

F03 不做：

```text
Shot Detection / Shot Boundary
ASR
人物识别
Scene
任何 AI
GPU/NVENC 优化
多 Proxy Profile
Source 替换/覆盖
```

F04 尚未开始。

---

# F03 Database / Migration

Migration：

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

关键规则：

- processing 阶段允许尚未生成的媒体 metadata 为 NULL；
- 有音频 Source 在 processing 阶段可以先保存 `audio.wav` 目标路径；
- ready 时 Proxy + Thumbnail + Timeline Mapping 必须完整；
- ready 若有 Audio，则 path / size / SHA / duration / 16000Hz / mono / offset 必须全部完整；
- Source 无音频时 Audio 字段全部为空，不伪造静音 WAV；
- Migration 前继续复用 F02 已冻结 SQLite `Connection.backup()` 安全升级 Gate。

开发收尾时修复了一个数据库约束问题：旧 0003 草案会错误拒绝“processing + 已知 audio 目标路径 + metadata 尚未知”。现在 Audio 完整性约束只在 `ready` 时强制，并增加对应回归测试。

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
保持原始画面比例
不放大小视频
-fps_mode passthrough
不强制 VFR → CFR
有音频时 AAC 128k
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
thumbnail_proxy_time_us = min(proxy_duration_us / 10, 5_000_000)
```

所有派生文件都先写 staging、验证后再发布 final；F02 original 永不覆盖。

---

# F03 Time Contract

公共模块：

```text
engine/app/core/media_time.py
```

已实现：

```text
seconds_to_microseconds()
pts_to_microseconds()
microseconds_to_pts()
derived_to_source_microseconds()
source_to_derived_microseconds()
```

权威时间：

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

Offset 来自实际 Source / Derived stream start timestamp，不假设 `Proxy 0 == Source 0`。

VFR 规则：

```text
不强制 CFR
不使用 frame_index / fps 作为唯一权威定位
后续 F04 必须消费 timestamp / mapping
```

---

# F03 7 个核心函数 — 全部完成

```text
generate_proxy_video()          DONE
aextract_analysis_audio()       DONE
generate_thumbnail()            DONE
inspect_preprocess_assets()     DONE
preprocess_source_video()       DONE
get_source_preprocess()         DONE
recover_source_preprocesses()   DONE
```

> 上面 `aextract_analysis_audio()` 仅为本状态文档的显示笔误风险提示；正式代码函数名为 `extract_analysis_audio()`，权威代码见 `engine/app/preprocess.py`。

正式代码函数：

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

Recovery：

```text
processing + 合法 final
→ 重新 inspect → ready

processing + 只有本 Source 明确拥有的 staging
→ 安全清理 + 删除 processing

processing + 无文件
→ 删除 processing

损坏 final / unknown file / 归属不明确
→ 保留现场
```

F03 Recovery 永远不能删除 F02 Source。

---

# F03 API — 全部完成

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

GET：

```text
无 ready F03 → 200 null
ready → 200 SourcePreprocessDTO
```

POST：

```text
不上传文件
只传 Project ID
成功 → 201 Created
```

Controller 继续遵守：

```text
HTTP → Business → Response
```

不直接执行 SQL、FFmpeg、FFprobe、Hash、mkdir、publish 或 Recovery。

---

# F03 Frontend — 全部完成

新增：

```text
frontend/src/types/preprocess.ts
frontend/src/api/preprocess.ts
frontend/src/stores/preprocess.ts
frontend/src/views/VideoPreprocess.vue
frontend/src/preprocess.css
```

修改：

```text
frontend/src/router/index.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/main.ts
```

路由：

```text
/projects/:projectId/preprocess
```

交互：

```text
没有 Source
→ 明确阻止并返回 F02

有 Source / 无 F03
→ 展示 Source 摘要 + 固定 Profile
→ “开始视频预处理”

处理中
→ 显示真实 processing 状态
→ 不伪造百分比

Ready
→ Proxy / Audio / Thumbnail
→ size / duration / FPS / timebase
→ Timeline Mapping
→ Source SHA Snapshot
→ F04 尚未开放提示
```

项目左侧导航已正式开放 `03 视频预处理`，`04 自动拉片` 继续禁用。
项目总览会根据真实 Source / Preprocess 数据判断当前阶段，不硬编码 F02。
流程栏已修为 8 列，避免第 8 阶段换行。

---

# 自动验证记录

## 已实际执行

F03 Foundation：

```text
Media Time targeted tests            6 PASS
0003 Migration/Constraint tests      3 PASS
0002 → backup → 0003 Upgrade         PASS
```

开发后实际媒体技术链路（FFmpeg/FFprobe 7.1.5 Debian build）：

```text
1920×1080 + audio
→ Proxy + 16k mono WAV + Thumbnail + inspect     PASS

Source 无音频
→ Proxy + Thumbnail，不生成静音 WAV              PASS

Source stream start_time = 2s
→ proxy_to_source_offset_us = 2,000,000          PASS
```

VFR 技术样本：

```text
Source 同时包含约 33ms / 66ms / 100ms 帧间隔
→ F03 Proxy 仍保留多种 PTS 间隔
→ 未被强制转为单一 CFR                         PASS
```

公共媒体代码：

```text
python -m py_compile preprocess.py media_time.py  PASS
```

数据库 Audio 生命周期约束：

```text
processing + audio target path + metadata NULL   PASS
ready + audio path + metadata 不完整             REJECT / PASS
```

## 已加入仓库的 F03 测试

```text
engine/tests/unit/test_database_migration_f03.py
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_preprocess_f03.py
engine/tests/unit/test_preprocess_vfr_f03.py
```

覆盖 Source Integrity、业务发布、无音频、重复预处理、Recovery、unknown file 保护、HTTP GET/POST、真实 FFmpeg 和 VFR。

## 当前工具环境限制

当前执行容器无法通过网络完整 clone 当前 GitHub 仓库，因此本轮没有冒充执行：

```text
整个 engine/tests 的最终 pytest 全量回归
frontend npm ci / vue-tsc / vite build
```

这两项作为用户 Windows 最终 Review Gate 执行。

---

# F03 User Review Gate

代码已经完整提交 `main`，当前允许的最高状态：

```text
READY_FOR_REVIEW
```

只有用户实际测试并明确确认通过，才允许：

```text
F03 → STABLE / FROZEN
```

用户最终需要验证：

```text
1. git pull origin main
2. 后端启动 8080
3. npm ci / npm run typecheck / npm run build
4. 打开已有 F02 ready 项目
5. 左侧进入“03 视频预处理”
6. 点击开始预处理
7. 检查 proxy.mp4 / audio.wav（有音频时）/ thumbnail.jpg
8. 页面 metadata / Timeline Mapping 正常
9. Source 原片 SHA/文件不被修改
10. 重启后 F03 结果仍存在
11. 无音频视频不产生假的 audio.wav
12. 再次 POST/重复执行被阻止
13. F01 创建/打开、F02 Source 页面仍正常
```

F03 未经用户验收不得进入 F04 正式开发。

## 最近更新时间

- 日期：2026-08-24 11:03 +08:00
- 状态：用户要求直接完成 F03 全部开发；F03 后端、API、Recovery、Vue 页面和测试已全部落到 main，当前 READY_FOR_REVIEW，等待用户 Windows 真实视频验收。
