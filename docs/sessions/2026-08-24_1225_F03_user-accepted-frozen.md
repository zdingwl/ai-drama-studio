# 2026-08-24 12:25 — F03 用户验收通过并冻结

## 用户结论

用户在 Windows 本机完成 F03 真实项目复测后明确回复：

```text
测试通过
```

此前真实验收已确认：

```text
PREPROCESS READY
proxy.mp4      生成成功
audio.wav      生成成功
thumbnail.jpg  生成成功
Timeline Mapping 正常显示并持久化
```

并完成关闭/重启后重新进入项目的持久化验证。

## 本次状态变化

```text
F01 — 创建项目:   STABLE / FROZEN
F02 — 上传原视频: STABLE / FROZEN
F03 — 视频预处理: STABLE / FROZEN
F04 — 自动拉片:   NOT STARTED
```

新增权威冻结快照：

```text
docs/features/F03-stable-snapshot.md
```

并同步：

```text
docs/PROJECT_STATE.md
```

## F03 冻结重点

```text
F02 Source 只读
Proxy Profile V1
16kHz/mono/PCM16 Analysis Audio
无音频不生成静音 WAV
Thumbnail 固定时间规则
integer microseconds
Source↔Proxy/Audio offset
VFR 不强制 CFR
开始前 + publish 前双重 Source Integrity
processing / ready
processing 安全重试
未知文件保护
0003 + 0004 Migration 历史
GET/POST preprocess API
7 个核心后端函数职责边界
```

## 真实验收期间修复历史

### 1. stale processing 无法重试

旧逻辑：

```text
GET 无 ready
POST 发现 processing
→ 统一 PREPROCESS_ALREADY_EXISTS
```

最终规则：

```text
完整 final → 恢复 ready
最近仍写 staging → PREPROCESS_IN_PROGRESS
旧系统 staging → 安全清理并重试
无文件旧 processing → 超时后清理并重试
未知/异常文件 → PREPROCESS_RECOVERY_REQUIRED，保留现场
```

### 2. 已部署旧 0003 Audio CHECK

真实 Windows app.db 已经执行过早期 0003，旧约束不允许：

```text
processing + audio_relative_path + NULL audio metadata
```

只修改仓库中的 0003 无法修复已经执行过的数据库，因此新增正式：

```text
0004_repair_source_preprocess_audio_constraint
```

升级前继续通过 SQLite Backup Gate 自动备份，0004 只修 `source_preprocess` Audio CHECK，不修改 F01/F02 业务数据或 Workspace 原片。

## Git / 范围

- Official Baseline：`main`
- 未新建分支
- 未创建/操作 PR
- 未开始 F04

后续如果用户明确开始 F04，必须先读取 F01/F02/F03 Stable Snapshot，再规划 F04；不得静默改变 F03 冻结 Contract。
