# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细 Contract、实现和历史过程放在 `docs/features/` 与 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）

F01 — 创建项目:     STABLE / FROZEN
F02 — 上传原视频:   STABLE / FROZEN
F03 — 视频预处理:   STABLE / FROZEN

Stable Features: F01, F02, F03
Frozen Features: F01, F02, F03

F03 User Acceptance: PASSED
Accepted At: 2026-08-24 12:25 +08:00

Next Feature: F04 — 自动拉片（NOT STARTED）
Current Development Feature: NONE
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
→ docs/features/F03-stable-snapshot.md
→ 如果用户明确开始 F04，再创建/读取 F04 Contract
→ 最新相关 docs/sessions/*.md
```

冻结 Feature 的 Stable Snapshot 高于开发阶段 Contract / Implementation Log。

---

# 当前冻结基线

## F01 — 创建项目

权威快照：

```text
docs/features/F01-stable-snapshot.md
```

核心结果：

```text
创建 Project
→ app.db 持久化
→ Workspace/project.json
→ 首页可见
→ 重启后仍存在
→ 可重新打开
```

---

## F02 — 上传原视频

权威快照：

```text
docs/features/F02-stable-snapshot.md
```

核心结果：

```text
1 Project → 0/1 Source Video
→ multipart 分块导入
→ SHA-256 + FFprobe
→ source/SOURCE_xxx/original.<ext>
→ source_videos ready
→ 原片只读
→ 重启后仍可读取
```

---

## F03 — 视频预处理

权威快照：

```text
docs/features/F03-stable-snapshot.md
```

用户于 2026-08-24 12:25 +08:00 明确确认：

```text
测试通过
```

冻结闭环：

```text
F02 ready Source
→ 开始前 size/SHA Integrity Gate
→ source_preprocess processing
→ staging proxy.mp4
→ 有音频时 audio.wav
→ thumbnail.jpg
→ FFprobe / size / SHA / Profile 校验
→ Source↔Proxy / Audio Timeline Mapping
→ publish 前再次检查 Source size/SHA
→ staging publish final
→ source_preprocess ready
→ Vue 显示 PREPROCESS READY
→ 重启后结果仍可读取
```

F03 正式 Workspace：

```text
preprocess/SOURCE_xxx/
├── proxy.mp4
├── audio.wav       # Source 有音频时
└── thumbnail.jpg
```

F03 Migration 历史必须保留：

```text
0003_create_source_preprocess
→ 0004_repair_source_preprocess_audio_constraint
```

0004 是真实用户数据库兼容修复：已经执行过早期 0003 的数据库不会重新执行被修改过的 0003，因此必须通过 0004 修复旧 Audio CHECK。

冻结时间规则：

```text
权威时间 = integer microseconds
source_us = proxy_us + proxy_to_source_offset_us
source_us = audio_us + audio_to_source_offset_us
```

VFR Proxy 不强制 CFR；F04 不得使用 `frame_index / fps` 作为唯一 Source Timeline 定位。

冻结 Profile V1：

```text
Proxy:
H.264 / libx264
CRF 23
preset fast
yuv420p
最大 1280×720
保持比例
不放大小视频
-fps_mode passthrough
有音频时 AAC 128k
faststart

Analysis Audio:
PCM s16le
16000 Hz
mono

Thumbnail:
min(proxy_duration_us / 10, 5_000_000us)
```

冻结恢复规则包括：

```text
ready → 禁止重复预处理
processing + 完整 final → 自动恢复 ready
processing + 最近仍写 staging → PREPROCESS_IN_PROGRESS
旧 staging 且只有系统文件 → 安全清理后允许重试
无文件的旧 processing → 超过保护窗口后清理并允许重试
未知文件 / 异常 final → PREPROCESS_RECOVERY_REQUIRED，保留现场
```

任何 F03 路径都不得覆盖或删除 F02 Source 原片。

---

# Feature Sequence 下一步

正式顺序仍以：

```text
docs/FEATURE_SEQUENCE.md
```

为准。

下一阶段：

```text
F04 — 自动拉片
```

当前：

```text
NOT STARTED
```

用户尚未要求开始 F04，因此：

```text
不写 F04 业务代码
不开放“自动拉片”正式功能
不创建 Shot 数据
不擅自建立分支
```

等用户明确说“开始 F04”或等价指令后，再先读取 F01/F02/F03 Stable Snapshot，规划 F04 Contract 与详细函数职责。

---

# Frozen Change Rule

F01/F02/F03 已由用户实际验收冻结。

后续 Feature 可以做兼容性 Additive 扩展，但如需改变冻结语义，必须：

```text
Change Request
→ 影响分析
→ 用户明确确认
→ Migration / Contract V2（如需要）
→ 实现
→ 上游 Feature 回归
```

禁止以“重构”“最佳实践”“后续需要”为理由静默改变冻结 Contract。

## 最近更新时间

- 日期：2026-08-24 12:25 +08:00
- 状态：F03 用户真实测试通过，已正式 STABLE / FROZEN；F04 尚未开始。
