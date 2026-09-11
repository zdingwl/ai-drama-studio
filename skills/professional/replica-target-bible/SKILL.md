# Replica Target Bible Skill

`replica-target-bible@1.0.0`

## 目标

把已经通过 P10 冻结的 `CURRENT SOURCE_VIDEO_SNAPSHOT` 转换成复刻项目的正式目标世界：

```text
SOURCE_VIDEO_SNAPSHOT
→ Replica preservation locks
→ localization decisions
→ ADAPTATION_PLAN + TARGET_BIBLE
```

本 Skill 只负责 P11，不生成 Target Script、Target Storyboard、TTS、Timing 或视频生成参数。

## 唯一 Source 边界

`CURRENT SOURCE_VIDEO_SNAPSHOT` 是唯一 Source 世界版本锚点。

需要人物、场景、道具、Story/Rhythm、逐镜或对白细节时，只能读取 Snapshot 中冻结的 typed content / lineage。不得绕开 Snapshot，从散落 P5~P9 CURRENT Artifact 重新拼一套“当前事实”。

Snapshot 缺失或 STALE 时必须阻断。

## Preservation Locks

服务端确定性建立，Provider 只读：

- 故事主线；
- Hook；
- 冲突与冲突顺序；
- 反转与反转顺序；
- 信息揭示顺序；
- 情绪峰值；
- Payoff；
- Cliffhanger；
- Story Beat timing；
- Shot rhythm baseline；
- Scene order baseline；
- Shot logic / action rhythm baseline。

原则：故事不乱改，节奏不重做，文化和表达才本土化。

## Target 允许设计

- Target 世界背景与社会文化语境；
- 人物目标身份、姓名、外形方向；
- 场景文化环境；
- 关键道具文化替代；
- 货币 / 公司 / 学校 / 职业 / 居住 / 社交习惯等映射；
- 称谓、文化表达与后续对白风格策略；
- visual style；
- continuity rules。

## Target Identity

Target Character / Scene / Prop 必须保留 Source lineage，但不能复用 Source identity 冒充 Target identity。

服务端生成：

```text
target_character_id ← source_character_id + target configuration
target_scene_id     ← source_scene_id + target configuration
target_prop_id      ← source_prop_id + target configuration
```

Provider 只返回以 Source identity 为 key 的语义映射。

P11 v1 强制一对一完整覆盖全部 Source Character / Scene / Prop；任何遗漏、重复 source ref 或无 lineage 主要实体都 fail closed。

## Provider 规则

Provider 必须：

1. 只消费 Snapshot typed content 与目标配置；
2. 遵守 preservation locks；
3. 完整覆盖 Source Character / Scene / Prop；
4. 只输出 Target 设计语义；
5. 不生成正式 Artifact id / revision / fingerprint；
6. 不生成完整 Target Script / Target Storyboard / TTS / Timing / Generation；
7. 不反向修改 Source Facts。

## Publication

一次 P11 运行是一个原子 publication set：

```text
ADAPTATION_PLAN
TARGET_BIBLE
revision rows
Artifact Graph edges
```

必须在同一事务完成；任一步失败整体 rollback，旧 CURRENT Target set 不被覆盖。

Graph：

```text
SOURCE_VIDEO_SNAPSHOT --DERIVED_FROM--> ADAPTATION_PLAN
SOURCE_VIDEO_SNAPSHOT --DERIVED_FROM--> TARGET_BIBLE
ADAPTATION_PLAN        --USES---------> TARGET_BIBLE
new artifact           --SUPERSEDES---> old same-type artifact
```

## Task / ProviderJob

- GET 只读；
- 只有显式 `POST /commands/target-bible` 启动；
- Task 输入只绑定 CURRENT Snapshot artifact；
- 外部请求前先持久化 ProviderJob；
- ProviderJob 绑定 Snapshot artifact；
- 支持有限 retry / cancel / resume；
- 同输入幂等，不制造无意义 revision。

## 完成条件

- Snapshot CURRENT；
- preservation locks 完整；
- Target entities 一对一覆盖 Source entities；
- Target identity 独立；
- `ADAPTATION_PLAN + TARGET_BIBLE` 原子发布；
- revision / fingerprint / provenance / Artifact Graph 完整；
- Source 更新可递归使 Target STALE；
- 普通页面可读；
- 没有提前进入 P12+。

在真实人工验收明确 PASS 前：

```text
LOCALIZATION = PLANNED
TARGET_BIBLE = PLANNED
```
