# Episode Understanding Skill

- **Skill ID:** `episode_understanding`
- **Version:** `1.0.0`
- **Status:** `CONTRACT_ONLY`
- **Runtime Model / Provider:** long-context reasoning model explicitly configured for source-drama understanding

## Purpose

把已经确认的镜头事实、完整对白、正式人物和场景连成**整集剧情结构理解**。本 Skill 回答的不只是“镜头里有什么”，还要回答“这个镜头为什么存在、观众在什么时候知道什么、情绪如何推进、重做时什么不能丢”。

## Inputs

- 当前 Episode revision
- 当前有效 `shot_facts` 结果
- `SourceDialogueUtterance` 与 Shot Dialogue Projection
- 正式 Final Character / Final Scene / Final Prop 及当前 binding
- speaker binding
- Shot 顺序、时间轴和必要的相邻 continuity
- 已确认的人工作品事实修订

输入必须来自当前正式版本；瞬态 detection/track/ASR 草稿只能通过其正式事实投影间接使用。

## Rules

1. 明确区分 `facts` 与 `inferences`。
2. 推断必须列出 supporting fact refs 和 confidence；没有证据的推断不得升级为 source truth。
3. 按叙事功能整理 `scene_blocks`，它可以跨多个视觉场景，也可以把一个视觉场景拆成多个剧情段。
4. 提取 `story_beats`，例如 Setup / Reveal / Suspicion / Escalation / Reaction / Reversal / Payoff / Hook。
5. 建立 `information_flow`：观众、各角色在何时知道/不知道什么，尤其记录信息差、误会、隐藏和揭示。
6. 建立 `emotion_curve`：每个重要角色与整集的情绪变化及转折点。
7. 给关键 Shot / Shot group 标记 `narrative_function`，例如铺垫、线索、遮蔽、反应、升级、停顿、反转、钩子。
8. 输出 `remake_invariants`：目标国家重做时必须保留的因果、关系、信息揭示顺序、冲突、反转、高潮、结局功能和关键镜头功能。
9. 不把“画面场景”与“剧情 Scene Block”混为一谈。
10. 不修改正式 Shot Facts、Character、Scene、Dialogue 或 speaker；只建立高层理解层。

## Forbidden Behaviors

- 为了让剧情更顺而补写原片不存在的事件或对白。
- 把推测的身份、动机、关系直接写回正式人物事实。
- 因单镜模型遗漏就静默删除已经确认的原片事实。
- 用目标国家偏好反向污染原片理解。
- 将 unresolved source conflict 自动判定为已解决。

## Output Contract

```json
{
  "episode_revision": "...",
  "skill": {"id": "episode_understanding", "version": "1.0.0"},
  "episode_summary": "...",
  "scene_blocks": [],
  "story_beats": [],
  "information_flow": [],
  "emotion_curve": [],
  "shot_functions": [],
  "remake_invariants": [],
  "inferences": [
    {
      "claim": "...",
      "supporting_fact_refs": [],
      "confidence": 0.0
    }
  ],
  "unresolved": []
}
```

## Validator

- 所有引用必须解析到当前 Episode 的当前 revision。
- `facts` 不得包含没有 provenance 的新增事实。
- 每条 inference 必须至少有 supporting fact ref 或被标记为 unresolved。
- remake invariant 必须能回指 source fact / beat / information-flow / emotion evidence。
- 存在阻塞性 source review case 时不得宣称整集 source truth 已冻结。

## Completion Criteria

- 已能用剧情段、节拍、信息差、情绪曲线和镜头功能解释整集；
- 已得到目标重做必须保留的核心戏剧功能；
- 事实与推断严格分层；
- 可供 `screenplay_reconstruction` 和 SourceDramaSnapshot 编译使用。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
