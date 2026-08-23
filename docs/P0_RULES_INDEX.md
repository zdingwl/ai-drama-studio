# AI Drama Studio — P0 Rules Index

本文件是 5 个 P0 工程 Contract 的索引。

P0 总原则已经合并进根目录 `SKILL.md`；本文件只负责告诉当前 Feature 需要读取哪些详细规范。

## 规则索引

| P0 | 文档 | 解决的问题 | 常见适用 Feature |
|---|---|---|---|
| P0-01 | `docs/DEPENDENCY_AND_INVALIDATION_RULES.md` | 上游 revision 改变后旧下游结果是否仍有效 | F05–F35 |
| P0-02 | `docs/MEDIA_TIMEBASE_CONTRACT.md` | Source/Proxy/Audio/VFR/字幕/口型时间对齐 | F02–F35 |
| P0-03 | `docs/ENVIRONMENT_BASELINE.md` | 环境与模型版本可复现 | 全部 |
| P0-04 | `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md` | SQLite + 文件崩溃/迁移/恢复 | 所有持久化 Feature |
| P0-05 | `docs/PROVIDER_JOB_RULES.md` | Provider timeout、幂等、resume、重复计费 | AI/VLM/Video/TTS/LipSync 等 Provider Feature |

## 开发前

当前 Feature 必须复制/填写：

- `templates/P0_FEATURE_CHECKLIST.md`

规则：

- 适用：写清实现、字段、错误/恢复和测试；
- 不适用：写 `N/A` + 原因；
- 不允许留空；
- 适用 P0 未定义前不编码。

## Stable Gate

```text
P0 DEPENDENCY REVIEW: PASS / N/A
P0 TIMEBASE REVIEW: PASS / N/A
P0 ENVIRONMENT REVIEW: PASS / N/A
P0 RECOVERY REVIEW: PASS / N/A
P0 PROVIDER JOB REVIEW: PASS / N/A
```

任一适用项未 PASS：当前 Feature 不能进入 `READY_FOR_REVIEW` 的最终验收版本，更不能 STABLE/FROZEN。

## 新对话

不要一开始全文读取五份 P0 文档。

先读：

```text
AGENTS.md
→ SKILL.md
→ PROJECT_STATE
→ 当前 Feature
```

然后根据当前 Feature 的 P0 Checklist 只读适用的详细 P0 规则。
