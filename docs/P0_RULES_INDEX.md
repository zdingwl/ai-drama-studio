# AI Drama Studio — P0 Rules Index

本文件是 5 个 P0 工程 Contract 的索引。

P0 总原则已经合并进根目录 `SKILL.md`；本文件只负责告诉当前工作需要读取哪些详细规范。

## 规则索引

| P0 | 文档 | 解决的问题 | 常见适用范围 |
|---|---|---|---|
| P0-01 | `docs/DEPENDENCY_AND_INVALIDATION_RULES.md` | 上游 revision 改变后旧下游结果是否仍有效 | 资产及后续生产 |
| P0-02 | `docs/MEDIA_TIMEBASE_CONTRACT.md` | Source/Proxy/Audio/VFR/字幕/口型时间对齐 | 媒体及后续生产 |
| P0-03 | `docs/ENVIRONMENT_BASELINE.md` | 环境与模型版本可复现 | 全部 |
| P0-04 | `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md` | SQLite + 文件崩溃/迁移/恢复 | 所有持久化能力 |
| P0-05 | `docs/PROVIDER_JOB_RULES.md` | Provider timeout、幂等、resume、重复计费 | AI/VLM/Video/TTS/LipSync 等 Provider 能力 |

## 开发前

如果当前工作仍使用 P0 Feature Checklist，则必须明确填写适用项；不适用写 `N/A + 原因`，不能留空。

旧 F01-F35 编号属于历史 Feature 体系时，不得为了匹配旧文档而把当前 Reference Video V2 工作强行塞回旧 Feature 顺序。

## Stable Gate

```text
P0 DEPENDENCY REVIEW: PASS / N/A
P0 TIMEBASE REVIEW: PASS / N/A
P0 ENVIRONMENT REVIEW: PASS / N/A
P0 RECOVERY REVIEW: PASS / N/A
P0 PROVIDER JOB REVIEW: PASS / N/A
```

任一适用项未 PASS：当前工作不能被宣称 STABLE/FROZEN。

## 新对话

不要一开始全文读取五份 P0 文档，也不要先从旧 Feature 文件推断当前版本。

先读：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ PROJECT_STATE 明确点名的 current implementation doc
→ current code
```

然后只读取当前工作真正适用的 P0 详细规则。

如果 P0 文档中的历史 Feature 编号与当前架构冲突，以当前 Reference Video V2 实现和 `PROJECT_STATE` 为准，并记录/修正文档冲突。
