# Script To Storyboard Skill

- **Skill ID:** `script_to_storyboard`
- **Version:** `1.0.0`
- **Status:** `CONTRACT_ONLY`
- **Runtime Model / Provider:** storyboard/planning reasoning model; downstream video provider is MiniMax H3

## Purpose

把已经锁定的目标国家剧本转换成**目标分镜与生成计划**。目标是重新导演一遍同一段戏，而不是机械复制原片 Shot 数量或把翻译后的对白硬塞回原时长。

## Inputs

- LOCKED target screenplay revision
- `episode_understanding.remake_invariants`
- TargetCharacter / TargetScene / TargetProp bindings
- 原片可用 Reference Clip / camera / performance / continuity facts
- 项目目标语言、地区和场景策略
- 已知目标对白文本；若已有真实 TTS duration，则同时输入

## Rules

1. 先按目标剧本的剧情节拍和人物动作决定分镜，再考虑原片 Reference Clip 如何帮助重拍。
2. 目标 Shot / GenerationSegment 不要求与原片 1:1。
3. 一个原 Shot 可以被拆成多个目标生成段；多个原 Shot 也可在不破坏戏剧功能时合并。
4. 每个关键段必须说明：
   - `reference_anchors`：人物、场景、动作、构图等参考来源；
   - `continuity_handoff`：上一段结束状态与下一段开始状态；
   - `camera` / `framing` / `composition` / `motion`；
   - `performance`：人物情绪、表情、身体动作、互动；
   - `action_timeline`：必要时按秒或阶段安排动作；
   - `audio_track`：该段承载的对白/环境声/静默功能；
   - `narrative_function`：该段在剧情中的目的。
5. Reference Video 是参考，不是绝对时长模板。目标语言变长/变短时优先保持戏剧功能和动作自然度。
6. 若真实目标 TTS duration 尚未生成，只能给 `duration_strategy`，不能把估算时长当最终时间轴。
7. 若真实 TTS duration 已存在，分镜时长必须以真实音频为重要约束进行重排。
8. 必须保留人物进入/离开、视线方向、手持道具、服装、站位和动作因果等 continuity。
9. 输出 GenerationSegment 意图，但不直接执行 H3。

## Forbidden Behaviors

- 强制目标 Shot 数量等于原片 Shot 数量。
- 为了保持原片时长截断目标对白语义。
- 把 Shot 与 GenerationSegment 当作同一数据对象。
- 随意改变已锁定 TargetCharacter / TargetScene。
- 删除关键反应镜头、反转、停顿或信息揭示，只因为生成更方便。
- 在本 Skill 内调用 H3、TTS 或 LatentSync。

## Output Contract

```json
{
  "target_screenplay_revision": "...",
  "skill": {"id": "script_to_storyboard", "version": "1.0.0"},
  "segments": [
    {
      "source_story_refs": [],
      "narrative_function": "...",
      "target_character_refs": [],
      "target_scene_ref": "...",
      "target_prop_refs": [],
      "duration_strategy": {},
      "reference_anchors": [],
      "continuity_handoff": {},
      "camera": {},
      "performance": {},
      "action_timeline": [],
      "audio_track": {},
      "h3_generation_intent": {}
    }
  ],
  "continuity_checks": [],
  "review_items": []
}
```

## Validator

- 所有目标人物/场景/道具引用必须属于当前 target revision。
- 每个关键 remake invariant 必须由至少一个 segment 承接。
- continuity handoff 的前后状态必须可连接；冲突进入 review item。
- 若 segment 标记 `duration_source=MEASURED_TTS`，必须存在对应真实音频 revision 和 measured duration。
- 不得生成 H3 attempt 或伪造视频资产。
- target screenplay revision 变化后旧 storyboard 必须 stale。

## Completion Criteria

- 目标剧本的每个关键剧情节拍都有可生成的画面计划；
- 人物、场景、动作、镜头和连续性定义清楚；
- 时长策略允许目标语言自然伸缩；
- 原片 Reference Clip 被作为参考锚点而非死板模板；
- 输出可供后续 TTS/Retiming/H3 generation command 使用。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
