# P9 Speaker staged Character EvidenceRef 整改

> 日期：2026-09-10  
> 状态：P9 工程整改；等待同一真实短剧重新运行 Provider 与人工验收。  
> 优先级：本文补充 `docs/14` 与 `docs/15` 的 P9 当前运行事实；不改变 P9 业务边界，不进入 P10。

## 1. 触发问题

部署 P9 Provider schema v6 后，真实 P9 再次运行，在任务进度 32% 失败：

```text
P9 最终归一失败（P9_EVIDENCE_REF_INVALID）：
P9 Provider 引用了不存在的 Source evidence/candidate id
```

32% 对应 `speaker_attribution` 阶段入口。Character 已完成 staged composition，Speaker Provider 正在消费本轮 staged `SOURCE_CHARACTERS`。

## 2. 确认的工程缺陷

P9 Provider contract 从设计开始就明确允许 Speaker 使用本轮 staged P9 `character_id`：

```text
evidence_refs[].ref_id
= Episode / Shot Anchor / P6 Evidence / P7 candidate / staged P9 character_id
```

并且 Speaker 输入显式包含：

```text
CURRENT SOURCE_CHARACTERS
```

但服务端旧实现的 `_known_ref_ids(inputs)` 只收集 P5/P6/P7/P8 的 Source 输入 ID。P9 `character_id` 是 Character 阶段根据本轮 grouping 生成的稳定 ID，不属于上游 Source 输入，因此不会出现在该集合中。

旧链因此形成契约矛盾：

```text
Character Provider
→ staged P9 Character identity: p9-chr-...

Speaker Provider
→ 合法引用该 p9-chr-... 作为 evidence ref

旧 Speaker composition
→ 使用 Source-only _known_ref_ids()
→ 把合法 staged P9 Character id 当成不存在的 Source id
→ P9_EVIDENCE_REF_INVALID
```

这不是 Provider 创造了未知 Source evidence，而是服务端没有把“同一 P9 run 的 staged Character namespace”纳入 Speaker 专用验证范围。

## 3. 整改规则

本次只调整 Speaker composition 的 evidence namespace，不放宽其他阶段：

1. Character / Scene / Prop 继续只允许 CURRENT Source 输入中的合法 Episode、Shot、P6 Evidence、P7 candidate 等引用；
2. Speaker 在上述 Source refs 之外，额外只允许 **本轮刚完成的 staged CharacterResolutionContent.entities[].character_id**；
3. 历史 P9 Character id、其他 Task 的 Character id、模型自造 `p9-chr-*` 仍必须 fail closed；
4. 即使 `ref_id` 是合法 staged Character id，其 `episode_id / shot_anchor_id / utterance_id` 若填写，也仍必须属于当前 P9 输入；
5. `SpeakerGroupSemantic.character_id` 仍独立校验，只能链接本轮 staged Character identity 或 null；
6. P7 `source_candidate_character_ids` 仍只允许 CURRENT SOURCE_BIBLE Character candidate；
7. Speaker / Character 继续分层，不因为允许 evidence ref 就把两者合并为同一实体。

## 4. Runtime 实现

产品 API 继续通过 `service_v2` 的 P9 background runner 执行。该 adapter 现在拥有 Speaker 专用 composition：

```text
Source-only evidence refs
+
本轮 staged P9 Character ids
↓
Speaker evidence validation
↓
CURRENT P6 utterance set / P7 candidate set / staged Character link 校验
↓
SOURCE_SPEAKERS typed content
```

自动执行顺序仍是：

```text
Character → Speaker → Scene → Prop
```

没有改变 ProviderJob-before-remote、Artifact publication、fingerprint、CURRENT/STALE 或 manual adjudication 规则。

## 5. 自动回归门禁

新增回归必须证明：

- Speaker evidence 可以引用同一 P9 run 生成的 staged `character_id`；
- 输出 Artifact 中保留原始 staged Character evidence ref，不替换成别的 Source id；
- 任意未出现在本轮 staged Character 集合中的伪造 `p9-chr-*` 继续返回 `P9_EVIDENCE_REF_INVALID`；
- Character / Scene / Prop 的 Source-only evidence 校验不被放宽；
- frontend / backend 完整 CI 继续通过。

## 6. 真实重跑与阶段状态

本次没有改变 `p9-source-resolution-v6` Prompt / JSON Schema，因此不升级 prompt version。部署最新代码后，可以在 P9 产品入口重新执行显式“最终归一”；旧失败任务不是最终验收结果。

真实 P9 仍必须继续完成 Character / Speaker / Scene / Prop 的 Provider、数据库、音画和人工 merge/split 验收。在完成前：

```text
IDENTITY_RESOLUTION = PLANNED
SCENE_RESOLUTION = PLANNED
PROP_RESOLUTION = PLANNED
SOURCE_SNAPSHOT = PLANNED
```

P10 `SOURCE_VIDEO_SNAPSHOT` 仍禁止进入。
