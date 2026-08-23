# AI Drama Studio — P0 Rules Index

本文件是 5 个 P0 工程 Contract 的索引。

这些规则解决的不是“功能做不出来”的问题，而是防止项目在后续 Feature、换新对话、升级依赖、修改上游数据、程序崩溃或 Provider 超时时出现隐蔽错误。

## 规则索引

| P0 | 文档 | 解决的问题 | 哪些 Feature 常见适用 |
|---|---|---|---|
| P0-01 | `DEPENDENCY_AND_INVALIDATION_RULES.md` | 上游修改后旧下游结果是否仍有效 | F05–F30 |
| P0-02 | `MEDIA_TIMEBASE_CONTRACT.md` | 视频/音频时间码、Proxy、VFR、帧与字幕对齐 | F02–F30 |
| P0-03 | `ENVIRONMENT_BASELINE.md` | 新电脑/新对话能否复现环境，避免“latest”漂移 | 全部 |
| P0-04 | `DATA_RECOVERY_AND_MIGRATION_RULES.md` | SQLite 与媒体文件不一致、崩溃、migration 恢复 | 全部涉及持久化的 Feature |
| P0-05 | `PROVIDER_JOB_RULES.md` | API 超时造成重复计费、任务丢失、无法恢复 | F14、F16–F18、F20、F22、F24–F27 |

## 开发前

每个 Feature Contract 必须复制并填写：

`templates/P0_FEATURE_CHECKLIST.md`

规则：

- 适用：写清实现方式、数据字段、测试用例。
- 不适用：必须写 `N/A` 和原因，不能空着。
- P0 适用项未定义：不开始编码。

## 开发完成后

Stable Gate 必须包含：

```text
P0 DEPENDENCY REVIEW: PASS / N/A
P0 TIMEBASE REVIEW: PASS / N/A
P0 ENVIRONMENT REVIEW: PASS / N/A
P0 RECOVERY REVIEW: PASS / N/A
P0 PROVIDER JOB REVIEW: PASS / N/A
```

## 新对话

新的 Agent 在读取 `SKILL.md` 后，还必须读取：

1. `SKILL_P0.md`
2. 本文件
3. 当前 Feature 标记为适用的 P0 详细规范

不要求每次完整阅读所有详细规则，但禁止忽略当前 Feature 的适用 P0。