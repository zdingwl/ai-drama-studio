# Screenplay Reconstruction Skill

- **Skill ID:** `screenplay_reconstruction`
- **Version:** `1.0.0`
- **Status:** `RUNTIME_READY`
- **Runtime Model / Provider:** 本地 Qwen 文本模型负责 grounded screenplay planning；确定性 renderer 负责插入正式 SourceDialogue

## Purpose

把已经确认的原片事实和整集剧情理解整理成一份**真正可阅读、可锁定、可继续本地化的原剧剧本**。这是“还原”，不是二次创作，也不是把每个 Shot 的 visual/action 字段重新拼一遍。

## Inputs

- 当前 `SourceDramaSnapshot`
- 当前 Episode 的正式人物、场景、道具、speaker binding
- 完整 `SourceDialogueUtterance`
- `shot_facts` 当前结果
- `episode_understanding` 当前结果
- Shot / Scene 时间顺序
- 当前 source revision / fingerprint

## Rules

1. 剧本按 Scene 组织，使用 `INT./EXT. + 场景 + 时间` heading。
2. 模型可以把连续 Shot 的重复描述**合并成简洁的剧本 ACTION**，但每条 ACTION 必须引用当前 source refs。
3. 剧本动作重点保留人物行动、反应、关键道具、信息揭露和冲突推进；纯技术性的机位/构图/重复景别不应成为用户主文本。
4. 模型不得生成对白正文。它只能通过 `dialogue_group_id` 决定完整对白在 ACTION 之间的位置。
5. 正式对白由确定性 renderer 从当前 canonical `SourceDialogueUtterance` 原样插入，不翻译、不缩写、不润色。
6. 一个完整 utterance 即使跨多个 Shot，也必须在整份剧本中恰好出现一次。
7. 人物名称来自当前正式 Character；未确认说话人只能显示明确的未知标记，不能猜身份。
8. `episode_understanding` 用来判断哪些动作/反应对剧情重要，但 inference 不能升级成未经 source refs 支持的新事实。
9. 模型输出的 Scene 顺序必须与当前 source Scene 完全一致，对白不能被移动到其他 Scene。
10. 输出要让人脱离原视频也能顺畅阅读，不再有“旧拉片换包装”的感觉。

## Forbidden Behaviors

- 逐 Shot 照抄 `visual_description` 形成技术报告式“剧本”。
- 增加原片没有的对白、事件、人物、道具、关系、心理事实或结局。
- 为了更专业而改写、补写或删减正式原始对白。
- 把完整 SourceDialogue 因跨 Shot 而复制成多句。
- 生成无法回指当前 Scene/Shot 的 ACTION。
- 用目标地区文化、目标人物名称提前改写原剧。
- 绕过 unresolved source conflict 或未确认 speaker。

## Runtime Binding V1

正式入口使用 `engine.app.source_screenplay_runtime_v2.compile_grounded_screenplay_reconstruction_v2`：

1. `episode_understanding` 先完成整集剧情结构理解；
2. screenplay planning 模型只输出 Scene 内的 `ACTION` 与 `DIALOGUE_REF` 顺序；
3. `ACTION` 必须通过 `supporting_fact_refs` 通过事实门禁；
4. `DIALOGUE_REF` 只能引用当前 canonical `dialogue_group_id`；
5. 确定性 renderer 再插入当前 SourceDialogue 的 speaker / text / timing；
6. 任意未知 ref、遗漏/重复对白、跨 Scene 移动对白均 fail closed；
7. 生成结果单独物化为 derived artifact，不写回 SourceDramaSnapshot。

GET `/api/episodes/{episode_id}/source-screenplay` 只能读取已物化结果，禁止模型执行；POST `/api/episodes/{episode_id}/source-screenplay/compile` 才允许显式生成。

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
      "actions": [
        {"text": "连续镜头合并后的剧本动作段落", "source_refs": ["shot:..."]}
      ],
      "dialogue": [],
      "story_beat_refs": []
    }
  ],
  "screenplay_text": "...",
  "unresolved": []
}
```

## Validator

- 每个 ACTION 至少有一个当前 Scene/Shot source ref。
- ACTION 引用不存在的 source ref 直接拒绝。
- Scene 集合和顺序必须与当前 source Scene 一致。
- 每条正式对白必须映射到当前完整 `SourceDialogueUtterance`。
- 一条 canonical SourceDialogueUtterance 必须在整份剧本中恰好出现一次。
- 对白不能被移动到与第一投影不一致的 Scene。
- 输入 revision/fingerprint 变化后已保存剧本必须显示 STALE，不能冒充 current。
- 阻塞性 source review 未清零时，不得把 reconstruction 标成 LOCKED。

## Completion Criteria

- 用户看到的是 Scene 级剧本，而不是 Shot 字段列表；
- 连续重复 Shot 可以被合并成自然 ACTION；
- 对白、人物、动作、事件顺序与正式原片事实一致；
- 没有新增剧情；
- 每条完整对白只出现一次；
- 所有 AI 整理动作可回溯；
- 可作为后续 `country_adaptation` 的锁定输入。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
