# P15 Replica Storyboard / Generation Segments 数据契约

> 日期：2026-09-13  
> 状态：正式工程合同。允许在 P14 链具备 CURRENT 输入后实现和进入统一最终验收；在最终人工 PASS 前 `STORYBOARD = PLANNED`。  
> 本阶段不生成视频，不做 QC / Selection / Lip Sync / Post。

## 1. 唯一职责

P15 把已验收 Source / Target / Audio / Timing 事实编译成两层正式生产计划：

```text
TargetStoryboardShot = 目标导演镜头单位
GenerationSegment    = 真正送视频生成 Provider 的推理窗口
```

二者必须与 Source Shot 分离：

```text
Source Shot != TargetStoryboardShot != GenerationSegment
```

Replica v1 默认一条 Source Shot 对应一条 TargetStoryboardShot，以继承源作剪辑、构图、动作与节奏；但一个 TargetStoryboardShot 可以按 Provider 最大推理时长拆成多个 GenerationSegment。

## 2. 正式硬输入

P15 必须同时读取 CURRENT：

```text
SOURCE_VIDEO_SNAPSHOT
TARGET_BIBLE
TARGET_SCRIPT
TARGET_ASSETS
TARGET_AUDIO
TIMING_PLAN
```

并验证完整 lineage：

- Target Bible 属于 Source Snapshot；
- Target Script 属于 Source Snapshot + Target Bible；
- Target Assets 属于 Target Bible；
- Target Audio 属于 Target Script + Target Bible；
- Timing Plan 属于 Target Script + Target Audio；
- Timing Plan `has_overflow = false`。

任一输入缺失、STALE 或 lineage 不一致，P15 fail closed。

## 3. Deterministic Replica Director v1

P15 v1 不再调用新的创作型 LLM。原因：Replica 的故事/镜头顺序/动作节奏已经由 Source Snapshot 与 P11 preservation locks 冻结，本阶段首先要可靠地把这些正式事实转换为可生成计划，而不是再次自由改编。

确定性编译必须：

1. 以 `SOURCE_VIDEO_SNAPSHOT.source_shot_facts` 的 Shot 顺序和 P5 timing 为基线；
2. Source Character/Scene/Prop binding 通过 Target Bible 一对一映射为 Target identity；
3. 目标视觉只读取 CURRENT TARGET_ASSETS；
4. 对白只读取 CURRENT TARGET_SCRIPT；
5. 音频引用只读取 CURRENT TARGET_AUDIO；
6. 对白落点只读取 CURRENT TIMING_PLAN；
7. CameraLanguage 默认继承 Source Shot；
8. source visual description 可作为动作/构图事实，但必须做已知 Source display name → Target display name 的确定性替换，禁止把 Source actor identity 当目标人物输出；
9. 不新增剧情事件、不重排 Scene / Shot、不改变 source timing。

## 4. TARGET_STORYBOARD typed schema

每个 TargetStoryboardShot 至少包含：

```text
storyboard_shot_id
source_shot_anchor_id
shot_number
episode_id / episode_order
start_us / end_us / duration_us
camera_language
source_visual_description
target_visual_description
target_scene_id?
target_character_ids[]
target_prop_ids[]
target_asset_refs[]
dialogue_refs[]
continuity_constraints[]
negative_constraints[]
```

`dialogue_refs[]` 至少包含：

```text
utterance_id
utterance_number
delivery
target_character_id?
final_target_dialogue
target_audio_clip_id
media_url
planned_speech_start_us / planned_speech_end_us
```

Source Shot 中同一 canonical utterance 跨 Shot 时允许多个 Shot 引用同一正式 utterance/audio；不得因此复制或创建新 Target Script utterance。

## 5. GENERATION_SEGMENTS typed schema

GenerationSegment 至少包含：

```text
generation_segment_id
episode_id / episode_order
segment_number
storyboard_shot_ids[]
start_us / end_us / duration_us
continuation_index / continuation_count
generation_prompt
negative_prompt
target_asset_refs[]
requires_lip_sync
```

第一版限制：

- segment duration 必须 `> 0`；
- 单 segment 最长由服务端配置控制，默认 6 秒；
- 超过上限的 TargetStoryboardShot 确定性拆段；
- 拆段不改变 Shot identity、Source timing 或对白 lineage；
- prompt 必须明确同一 Shot continuation，避免每段重新发明人物/场景。

## 6. Candidate / Review / Publication

P15 compile 先产生一个 `NEEDS_REVIEW` Storyboard bundle candidate，包含完整 TARGET_STORYBOARD + GENERATION_SEGMENTS 草案。页面只读加载不会自动生成。

用户显式 ACCEPT 后，在一个事务中同时发布：

```text
TARGET_STORYBOARD
GENERATION_SEGMENTS
```

Graph 至少：

- `SOURCE_VIDEO_SNAPSHOT -> TARGET_STORYBOARD : DERIVED_FROM`
- `TARGET_BIBLE -> TARGET_STORYBOARD : USES`
- `TARGET_SCRIPT -> TARGET_STORYBOARD : USES`
- `TARGET_ASSETS -> TARGET_STORYBOARD : USES`
- `TARGET_AUDIO -> TARGET_STORYBOARD : USES`
- `TIMING_PLAN -> TARGET_STORYBOARD : USES`
- `TARGET_STORYBOARD -> GENERATION_SEGMENTS : DERIVED_FROM`
- 新 revision -> 旧同类 revision : SUPERSEDES

上游任一 revision 更新必须递归 stale Storyboard 与所有后续生成/后期结果。

## 7. Professional Skill

新增：

```text
storyboard-directing@1.0.0
mode = DETERMINISTIC_REPLICA_COMPILE
```

required capabilities: `STORYBOARD`。  
required inputs: 六个 CURRENT 硬输入。  
outputs: `TARGET_STORYBOARD`, `GENERATION_SEGMENTS`。

## 8. UI

普通用户看到“分镜与生成计划”：

- 按集展示目标分镜；
- 展示镜头时长、目标人物/场景/道具、对白、目标视觉描述；
- 展示每个 Shot 被拆成几个生成段；
- 可预览 candidate；
- 显式确认或拒绝；
- 不暴露 fingerprint / ProviderJob 等工程词。

## 9. 完成定义

P15 工程完成不等于 P15 PASS。至少要完成 schema/model/migration/service/API/UI/tests，并在统一真实验收中证明：

- Source Shot timing/order 继承正确；
- Target identity/assets 映射正确；
- Target dialogue/audio/timing 引用完整；
- GenerationSegment 拆分正确；
- stale propagation 正确；
- 用户确认前不产生 CURRENT 正式结果。
