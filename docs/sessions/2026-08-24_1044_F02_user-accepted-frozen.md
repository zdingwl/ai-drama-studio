# F02 用户验收通过并冻结

时间：2026-08-24 10:44 +08:00  
分支：main（未创建新分支）

## 用户结论

用户明确回复：

```text
测试通过
```

因此正式执行：

```text
F02 — 上传原视频
READY_FOR_REVIEW
→ STABLE / FROZEN
```

只有用户有权限完成这一步状态转换，本次转换依据用户明确验收结果。

## 新增冻结快照

```text
docs/features/F02-stable-snapshot.md
```

冻结内容包括：

- 一 Project 一 Source Video；
- `SOURCE_<UUID4_HEX>`；
- `source/SOURCE_<UUID>/original.<ext>`；
- `source_videos` 核心字段与 importing/ready；
- integer microseconds；
- rational FPS；
- FFprobe 流选择；
- multipart + chunked staging；
- SHA-256 / size；
- final publish / Recovery 安全边界；
- ready Source 只读、不覆盖；
- GET / POST source-video API；
- 视频导入页面状态与交互；
- Migration 前 SQLite backup；
- F01 + F02 回归要求。

## 当前正式状态

```text
F01 = STABLE / FROZEN
F02 = STABLE / FROZEN
F03 = NOT STARTED
```

`PROJECT_STATE.md` 已同步。

## 后续继续规则

下一 Feature 是：

```text
F03 — 视频预处理
```

未经用户明确要求，不自动开始 F03。

F03 必须以 F01/F02 Stable Snapshot 为上游 Contract，特别不能覆盖 F02 的 Source 原片，也不能改变 Source ID、Source Timeline 的 integer microseconds 规则或 F02 Recovery 安全规则。

如果未来要改变 F02 冻结 Contract，必须先：

```text
Change Request
→ 影响分析
→ Migration / V2
→ 用户批准
→ 实现
→ F01 + F02 Regression
```
