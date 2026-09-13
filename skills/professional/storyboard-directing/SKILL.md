# Replica Storyboard Directing

## 目标

把已经确认的 Replica Source/Target/Audio/Timing 事实确定性编译为 `TARGET_STORYBOARD` 和 `GENERATION_SEGMENTS`。本 Skill 不重新创作故事，也不再次调用 LLM 猜镜头。

## 硬输入

必须同时 CURRENT：

- `SOURCE_VIDEO_SNAPSHOT`
- `TARGET_BIBLE`
- `TARGET_SCRIPT`
- `TARGET_ASSETS`
- `TARGET_AUDIO`
- `TIMING_PLAN`

`TIMING_PLAN` 必须没有任何 OVERFLOW。

## 三层镜头身份

严格区分：

`Source Shot != TargetStoryboardShot != GenerationSegment`

Replica v1 默认每个 Source Shot 对应一个 TargetStoryboardShot，完整继承 Source Shot 的顺序、绝对时间、构图和镜头语言。若 Shot 超过视频 Provider 的单次推理时长，可以拆成多个 GenerationSegment；这种拆分只改变推理窗口，不改变 Shot identity 或故事节奏。

## Target 替换

Source Shot 中的人物、场景、道具只能通过 CURRENT Target Bible 的一对一映射转换为 Target identity，并且必须存在 CURRENT Target Assets。Source visual description 可以作为动作和构图事实，但已知 Source display name 要确定性替换为 Target display name，禁止把原演员身份当成目标角色输出。

对白只来自 CURRENT TARGET_SCRIPT，音频只来自 CURRENT TARGET_AUDIO，落点只来自 CURRENT TIMING_PLAN。

## Provider

本 Skill 完全确定性执行，不创建 ProviderJob。真正的视频生成从 P16 开始。

## 人工确认

编译结果先形成 candidate。用户显式接受后才同时发布 CURRENT `TARGET_STORYBOARD` 与 `GENERATION_SEGMENTS`。P15 工程完成不等于 P15 PASS；统一真实验收前 `STORYBOARD` 保持 PLANNED。
