# P14 Timing 回退 P12 定向对白修订闭环

> 日期：2026-09-13  
> 状态：工程合同正式建立；用于完成 P14 真实验收前的 Timing overflow 收口。  
> 说明：本文补充 `docs/25`、`docs/27`、`docs/32~47`。P12 已 PASS / TARGET_SCRIPT 已 AVAILABLE；本合同不是重新验收 P12，而是为已被 P14 真实时长证明过长的目标对白建立可审计 revision 路径。P14 最终 PASS 前 `TTS / TIMING` 继续保持 `PLANNED`。

## 1. 问题与唯一目标

P14 已经用真实 TARGET_AUDIO + ffprobe 得到 Actual Speech Duration。若某条目标对白在允许的受控 Retake 下仍理论上无法放回 Source slot，则必须回到 P12 对 **Final Target Dialogue** 做定向缩写，而不能：

- 修改 Source Dialogue；
- 拉长 Source Shot；
- 用极端语速硬塞；
- 静默合并/拆分 canonical utterance；
- 整部重新生成并无故改变已经成立的其他目标对白。

本文建立：

```text
CURRENT TARGET_SCRIPT
+ CURRENT TARGET_AUDIO
+ CURRENT P14 Timing candidate
        ↓
server-side timing triage
        ↓
selected SCRIPT_REWRITE utterances only
        ↓
P12 targeted rewrite Provider
        ↓
new TARGET_SCRIPT revision
        ↓
old TARGET_AUDIO / TIMING_PLAN recursively STALE
        ↓
rebuild TARGET_AUDIO → ffprobe → TIMING
```

## 2. 准入规则

定向修订只允许 REPLICA，且必须同时满足：

1. CURRENT `SOURCE_VIDEO_SNAPSHOT`；
2. CURRENT `ADAPTATION_PLAN`；
3. CURRENT `TARGET_BIBLE`；
4. CURRENT `TARGET_SCRIPT`；
5. CURRENT `TARGET_AUDIO`；
6. 存在属于上述 CURRENT Script/Audio 的 `NEEDS_REVIEW` Timing candidate；
7. 请求中的 `expected_target_script_artifact_id / revision` 与服务器 CURRENT 完全一致；
8. `expected_timing_generation_sequence` 与 Timing candidate 完全一致；
9. 被选 utterance 当前必须是 `OVERFLOW`；
10. 服务器计算 `source_slot_duration / actual_speech_duration < 0.80`，即属于 `SCRIPT_REWRITE`，而不是可先尝试受控 Retake 的区间。

任一条件不满足必须 fail closed，且不得创建 ProviderJob / 新 TARGET_SCRIPT。

## 3. Source Truth 与不可变字段

整个 revision 中以下字段必须逐值复制旧 CURRENT TARGET_SCRIPT / Source Snapshot，Provider 无权返回或修改：

```text
utterance_id
utterance_number
source_start_us
source_end_us
source_text
source_language
target_character_id
translation_text
```

`translation_text` 继续代表对 Source Dialogue 的直接语义翻译。Timing 回退只能修改目标地区表达层：

```text
localization_text
final_target_dialogue
localization_notes
```

不得 split / merge / reorder / create utterance。

## 4. Provider 最小输入与输出

Provider 只读取：

- CURRENT Target Bible / Adaptation Plan 中与对白表达相关的正式约束；
- 被选择 utterance 的旧 Translation / Localization / Final Target Dialogue；
- source slot duration；
- 当前真实 speech duration；
- server 计算的 `required_duration_factor`；
- 明确的“优先压缩到更适合时长，但不能牺牲核心语义、人物关系、剧情信息、语气功能”的规则。

Provider 只能返回选中 utterance 的：

```text
utterance_id
localization_text
final_target_dialogue
localization_notes[]
```

Provider 不得声称新文案一定 FIT。真实是否 FIT 只由新 TTS + ffprobe + Timing 再计算决定。

## 5. 未选对白必须完全复用

未选择的 utterance 不进入 Provider 请求；服务端直接从 CURRENT TARGET_SCRIPT 原样复制全部字段。发布前必须验证：

- utterance 集合、顺序与数量完全不变；
- selected 之外每条 dialogue 的 `model_dump(mode="json")` 与旧 revision 完全相同；
- selected 行仅允许目标表达三字段变化；
- 新 revision 继续指向相同 CURRENT Source Snapshot / Adaptation Plan / Target Bible lineage。

## 6. Revision / Provenance

TARGET_SCRIPT provenance 增加兼容字段：

```text
revision_mode = FULL_GENERATION | TIMING_REWRITE
base_target_script_artifact_id?
rewritten_utterance_ids[]
timing_candidate_id?
timing_generation_sequence?
```

历史 revision 缺失这些字段时按 `FULL_GENERATION` 解析，不做 migration 改写。

定向 revision 的 fingerprint 必须包含：

- base TARGET_SCRIPT id/revision/fingerprint；
- 三个 P12 硬输入 id/revision/fingerprint；
- selected utterance IDs；
- Timing candidate id / sequence；
- 每条 source slot / actual duration / required factor；
- Provider profile / prompt / schema / contract version。

## 7. Artifact Graph 与 STALE

发布新 TARGET_SCRIPT 时：

- 保持 `SOURCE_VIDEO_SNAPSHOT -> TARGET_SCRIPT : DERIVED_FROM`；
- 保持 `ADAPTATION_PLAN -> TARGET_SCRIPT : USES`；
- 保持 `TARGET_BIBLE -> TARGET_SCRIPT : USES`；
- `new TARGET_SCRIPT -> old TARGET_SCRIPT : SUPERSEDES`；
- 发布前对旧 CURRENT TARGET_SCRIPT 执行既有递归 stale。

因此依赖旧 Script 的：

```text
TARGET_AUDIO
TIMING_PLAN
TARGET_STORYBOARD
GENERATION_SEGMENTS
GENERATED_VIDEO
GENERATION_SELECTION
FINAL_OUTPUT
```

如果未来存在，都必须递归 STALE，不允许继续误用。

## 8. API / UI

新增显式 command：

```text
POST /api/v3/projects/{project_id}/commands/target-script/rewrite-for-timing
```

GET 仍全部只读。

P14 Timing 分诊面板应允许：

- 仅选择 server 判定为 `SCRIPT_REWRITE` 的句子；
- 显示 Source slot、Actual duration、required factor、当前 Final Target Dialogue；
- 用户显式启动“回目标剧本缩短选中对白”；
- Task 成功后刷新看到新 TARGET_SCRIPT revision，旧音频/Timing 进入 STALE；
- 用户再显式执行新配音、听审、Timing。

## 9. 完成定义

工程完成至少要求：

1. 定向 rewrite contract / schema / Provider / Task / API；
2. optimistic concurrency；
3. 仅 selected utterance 调 Provider；
4. 未选 dialogue 逐值不变；
5. Source truth 不变；
6. 新 Script publication 原子；
7. 下游递归 STALE；
8. UI 可从 Timing triage 显式启动；
9. 自动测试覆盖错误门禁与 stale graph；
10. P14 最终人工验收前不得把 `TTS / TIMING` 标记 AVAILABLE。
