# 原片分析定稿 Professional Skill

## 目标

把 P5~P9 已经建立并验收的 CURRENT Source Facts 确定性冻结为 `SOURCE_VIDEO_SNAPSHOT`。Snapshot 是后续 Target / Production 消费视频 Source Truth 的正式版本边界，而不是一次新的模型理解。

正式契约：

```text
source-video-snapshot@1.0.0
p10-source-video-snapshot-v1
SOURCE_VIDEO_SNAPSHOT schema 1.0
frozen-accepted-source-facts-v1
```

在真实人工验收通过前：

```text
SOURCE_SNAPSHOT = PLANNED
```

## 产品呈现边界

P10 是 **Internal Engineering Slice**，不是新的用户 Product Stage。

普通用户始终只看到“原片理解”及其直接结果：剧情、人物、说话人、场景、道具、对白、Story/Rhythm 与逐镜拉片。不得把 P10 再做成一个独立结果大面板，也不得要求用户理解 `SourceVideoSnapshot / Artifact / fingerprint / provenance / frozen inputs`。

允许在原片理解结果末尾提供一个轻量确认状态：

```text
尚未确认当前原片分析结果
当前原片分析结果已确认
原片分析结果已有更新，请重新确认
```

确认动作仍必须是显式 POST；页面加载和刷新只能 GET，不能自动发布 Snapshot。

技术字段继续完整保留在 API、typed domain、Artifact Graph、自动测试与开发/排障入口中，但不能作为普通用户的主结果展示。

详细产品呈现决定见 `docs/20_P10产品呈现整改_取消独立阶段.md`。

## Source Truth

完整 Episode 永远是最高层 Source Truth。

P10 必须同时读取并冻结：

```text
CURRENT SOURCE_VIDEO
CURRENT SHOT_ANCHORS
CURRENT SOURCE_DIALOGUE
CURRENT SOURCE_BIBLE
CURRENT STORY_SKELETON
CURRENT RHYTHM_SKELETON
CURRENT SOURCE_SHOT_FACTS
CURRENT SOURCE_CHARACTERS
CURRENT SOURCE_SPEAKERS
CURRENT SOURCE_SCENES
CURRENT SOURCE_PROPS
```

`SOURCE_SPEAKERS` 是独立正式输入。Speaker 与 Character 继续分层，不能因为 Speaker 已链接 Character 就省略 Speaker Artifact。

## 不允许做的事

P10 严禁：

- 调用 VLM / LLM / ASR / OCR / identity Provider 再理解一次；
- 创建 ProviderJob；
- 修改 P5 Shot 时间；
- 改写 P6 canonical dialogue / OCR；
- 回写 P7 / P8 / P9 历史 revision；
- 把 P8 provisional candidate 当新最终 truth；
- 把 Speaker 合并进 Character；
- 读取 Target / Production Artifact 来决定 Source Snapshot；
- GET 自动定稿或重算；
- 把 P10 暴露成普通用户必须理解的独立产品阶段；
- 在普通结果页重复渲染 P5~P9 已经展示过的内容。

## 执行方法

### 1. 加载 CURRENT Source 链

首先确认所有硬输入都存在且唯一 CURRENT。P7/P8/P9 typed revision 必须可解析；Episode、ShotBoundarySet、SourceEvidenceSet 必须属于当前完整 SOURCE_VIDEO。

### 2. 重新校验 authority

只做确定性验证：

- P8 每个 Shot 的 `shot_anchor_id/start_us/end_us/duration_us` 与 CURRENT P5 完全相等；
- P8 dialogue 与 CURRENT P6 canonical text/time 完全相等；
- P9 Speaker attribution 与 CURRENT P6 canonical utterance 集合和 text/time 完全相等；
- P9 Scene assignment 的 Shot 时间仍来自 P5；
- P7/P8/P9 provenance 指向当前正式输入；
- Speaker provenance 同时指向 CURRENT SOURCE_DIALOGUE 和 CURRENT SOURCE_CHARACTERS。

任一不一致直接 fail closed。P10 没有“修复”权限。

### 3. Typed freeze

Snapshot 原样复制：

- Episode immutable source metadata 与 SHA256；
- P5 Shot Anchors；
- P6 canonical dialogue / visual text；
- P7 `SourceBibleContent`；
- P8 `SourceShotFactsContent`；
- P9 Character / Speaker / Scene / Prop typed content。

Snapshot 只新增版本边界、引用和 provenance，不新增语义事实。

### 4. Fingerprint

输入 fingerprint 必须覆盖：

- 全部硬输入 Artifact id / revision / fingerprint；
- source asset SHA256；
- ShotBoundarySet / SourceEvidenceSet fingerprint；
- P5 authoritative timing；
- P6 canonical dialogue / OCR；
- P7/P8/P9 typed content hash；
- Professional Skill / schema / source-truth contract；
- 前一 Snapshot id/fingerprint（发布新 revision 时）。

相同 CURRENT Source 链重复点击确认必须幂等返回当前 Snapshot，不制造无意义 revision。

## Artifact Graph

P10 使用现有统一 `source_node -> target_node` dependency 方向，使所有冻结输入都成为 Snapshot 的上游边：

```text
SOURCE_VIDEO        --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SHOT_ANCHORS        --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SOURCE_DIALOGUE     --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SOURCE_BIBLE        --USES---------> SOURCE_VIDEO_SNAPSHOT
STORY_SKELETON      --USES---------> SOURCE_VIDEO_SNAPSHOT
RHYTHM_SKELETON     --USES---------> SOURCE_VIDEO_SNAPSHOT
SOURCE_SHOT_FACTS   --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SOURCE_CHARACTERS   --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
SOURCE_SPEAKERS     --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
SOURCE_SCENES       --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
SOURCE_PROPS        --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
```

当任一冻结上游被新 CURRENT revision 替代，现有递归 downstream invalidation 必须把旧 Snapshot 标记 `STALE / is_current=false`。历史 Snapshot 不删除。

新 Snapshot revision 额外：

```text
new SOURCE_VIDEO_SNAPSHOT --SUPERSEDES--> previous SOURCE_VIDEO_SNAPSHOT
```

## API

```text
POST /api/v3/projects/{project_id}/commands/source-video-snapshot
GET  /api/v3/projects/{project_id}/source-video-snapshot
GET  /api/v3/projects/{project_id}/source-video-snapshot/revisions
```

P10 第一版是同步的轻量确定性 Command，不创建 Task / ProviderJob。未来如果规模需要异步化，业务契约仍保持不变。

## Source / Target 边界

Snapshot 只允许位于 `SOURCE` namespace。Target / Production 可以依赖 CURRENT Snapshot，但不得反向写入或作为 P10 输入。

P10 新产品呈现完成真实人工验收前，不开始 Target Localization / Target Bible 正式实现。
