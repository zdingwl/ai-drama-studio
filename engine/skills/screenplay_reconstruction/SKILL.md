# Screenplay Reconstruction Skill

- **Skill ID:** `screenplay_reconstruction`
- **Version:** `1.0.0`
- **Status:** `RUNTIME_READY`
- **Runtime Model / Provider:** V1 使用确定性 source-truth projector；不再调用第二个生成模型改写事实/对白

## Purpose

把已经确认的原片事实和整集剧情理解整理成一份**可阅读、可锁定、可继续本地化的原剧剧本**。这是“还原”，不是二次创作。

## Inputs

- 当前 `SourceDramaSnapshot` 候选版本或其正式编译输入
- 当前 Episode 的正式人物、场景、道具、speaker binding
- 完整 `SourceDialogueUtterance`
- `shot_facts` 当前结果
- `episode_understanding` 当前结果
- Shot 顺序与时间关系
- 人工确认的 source revision

## Rules

1. 剧本按实际叙事组织，可使用 `INT./EXT. + 场景 + 时间` heading。
2. 动作只重组已存在事实，不增加原片没有发生的事件。
3. 对白必须来自当前正式 SourceDialogue；允许格式化标点和剧本排版，但不得改变语义或凭空增加台词。
4. 人物名称/角色引用必须来自正式 Final Character 或明确的 VO/未知 speaker 标记。
5. 表情、情绪、动作、道具和关系只在有 source refs 时写入。
6. 可以把跨多个 Shot 的完整 utterance 作为一条剧本对白，不因 Shot 切分重复对白。
7. 可以把多个 Shot 合并成同一个剧本场景，也可以在同一视觉地点按剧情转折分段，但必须保留 source refs。
8. `episode_understanding` 中的 inference 若尚未确认，只能作为注释/待确认项，不能伪装成剧本事实。
9. 输出要能让人脱离原视频阅读并理解“谁、在哪里、做什么、为什么发生冲突、说了什么”。

## Forbidden Behaviors

- 增加原片没有的对白、事件、人物、道具或结局。
- 为了让剧本更专业而改写原始对白含义。
- 把一个完整 SourceDialogue 因跨 Shot 而复制成多句。
- 用目标地区文化、目标人物名称提前改写原剧。
- 绕过 unresolved source conflict 或未确认 speaker。

## Runtime Binding V1

`engine.app.source_story_skills_v1.reconstruct_source_screenplay_v1` 采用确定性投影：动作只来自当前 Shot 的 `visual_description/performance`，对白只遍历 canonical `SourceDialogueUtterance`，并通过 emitted set 和最终全集合校验保证每条完整 SourceDialogue 恰好输出一次。`episode_understanding` 只提供 Story Beat 引用，不允许模型 inference 变成新动作或新对白。

## Output Contract

```json
{
  "source_revision": "...",
  "skill": {"id": "screenplay_reconstruction", "version": "1.0.0"},
  "title": "...",
  "scenes": [
    {
      "heading": "INT./EXT. ...",
      "source_refs": [],
      "actions": [],
      "dialogue": [],
      "story_beat_refs": []
    }
  ],
  "unresolved": []
}
```

每条 action/dialogue 应可回指 source refs；剧本正文可以有面向人的格式化投影，但结构化事实必须可追溯。

## Validator

- 每条正式对白必须映射到当前完整 SourceDialogueUtterance。
- 每个正式人物必须映射到当前 Final Character/VO。
- 新增 action/event 若无 source ref 直接拒绝或降级为 unresolved。
- 一条 canonical SourceDialogueUtterance 必须在整份剧本中恰好出现一次。
- 阻塞性 source review 未清零时，不得把 reconstruction 标成 LOCKED。
- 输入 revision/fingerprint 变化后旧 reconstruction 必须 stale。

## Completion Criteria

- 可完整阅读并理解原集剧情；
- 对白、人物、动作、事件顺序与正式原片事实一致；
- 没有新增剧情；
- 所有关键内容可回溯；
- 可作为 `country_adaptation` 的锁定输入。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
