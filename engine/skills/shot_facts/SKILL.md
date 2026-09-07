# Shot Facts Skill

- **Skill ID:** `shot_facts`
- **Version:** `1.0.0`
- **Status:** `CONTRACT_ONLY`
- **Runtime Model / Provider:** Qwen3-VL semantic provider or an explicitly configured equivalent

## Purpose

把一个当前有效 Shot / ShotRevision 看懂，输出**镜头级原片事实**。目标不是写故事，而是给后续人物归并、整集理解、剧本还原和 H3 重做提供可追溯事实。

## Inputs

必须显式绑定当前版本：

- `shot_revision_id`
- 当前 Shot 的 Reference Clip / 采样帧
- 当前 Shot 时间范围
- 与当前 Shot 对齐的 ASR/OCR evidence（如有）
- 已存在但不得被覆盖的正式人物/对白引用（如有）
- 必要时只读相邻 Shot 摘要，用于 continuity，不得把相邻镜头内容写成本镜头事实

## Rules

1. 只写当前画面或声音证据能够支持的事实。
2. 人物先描述可见状态、动作、表情、位置、互动；未知身份保持未知。
3. 场景描述地点语义、内外景、时间感、环境、光线和天气等可见属性。
4. 道具只保留叙事有意义或人物正在使用/互动的关键物件。
5. 对白文本以正式 SourceDialogue/ASR-OCR 融合链为准；本 Skill 可以说明“画面中谁似乎正在说话”，但不得擅自改正文。
6. 镜头语言至少覆盖：Camera、Framing、Composition、Motion、Lighting、Continuity。
7. 动作和表演至少覆盖：Subject、Action、Expression、Interaction。
8. 所有不确定判断必须放入 `uncertainties`，不能伪装成确定事实。
9. 输出必须保留 evidence/provenance 引用，能追溯到当前 ShotRevision。

## Forbidden Behaviors

- 猜测人物姓名、亲属关系、职业或身份并写成事实。
- 根据剧情常识补写镜头中没有发生的动作、对白或道具。
- 覆盖正式人物绑定、正式对白、speaker、Shot boundary。
- 重跑或修改 ASR/OCR。
- 读取历史失效 ShotRevision 并与当前版本混用。
- 因为模型无法判断而自动降低人物合并阈值。

## Output Contract

语义结构至少包含：

```json
{
  "shot_revision_id": "...",
  "skill": {"id": "shot_facts", "version": "1.0.0"},
  "facts": {
    "subjects": [],
    "actions": [],
    "expressions": [],
    "interactions": [],
    "scene": {},
    "props": [],
    "camera": {},
    "framing": {},
    "composition": {},
    "motion": {},
    "lighting": {},
    "continuity": {}
  },
  "evidence": [],
  "uncertainties": []
}
```

字段可以在后续 minor 版本扩展，但不得把推断混入 `facts`。

## Validator

- `shot_revision_id` 必须等于当前有效 revision。
- 必需事实字段存在且类型正确。
- evidence 引用必须属于当前 Shot/Revision 或明确标记为只读邻镜上下文。
- 不允许生成新的正式 character/dialogue/speaker ID。
- stale revision 输出必须直接拒绝。

## Completion Criteria

- 当前镜头的主要人物、动作、表演、场景、关键道具和镜头语言已有结构化结果；
- 不确定项被显式隔离；
- 未覆盖任何正式原片事实；
- 结果能够直接供 `episode_understanding` 和资产归并链消费。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/02_工作流V2技术实现规范.md`
- `docs/04_AI拉片模块业务方案与UI基线.md`
