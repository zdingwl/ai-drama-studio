# Country Adaptation Skill

- **Skill ID:** `country_adaptation`
- **Version:** `1.0.0`
- **Status:** `CONTRACT_ONLY`
- **Runtime Model / Provider:** text reasoning/localization model explicitly configured for the target language and region

## Purpose

把已经锁定的原剧剧本改编成目标语言、目标地区的**本地化目标剧本**。默认目标是“同一部戏在当地重新拍”，不是逐字翻译，也不是自由重写。

## Inputs

- LOCKED source screenplay / `SourceDramaSnapshot`
- `episode_understanding.remake_invariants`
- 目标语言
- 目标地区
- 场景策略：`AUTO` / `KEEP` / `LOCALIZE`
- 已确认的 TargetCharacter / TargetScene / TargetVoiceProfile（如已存在）
- 项目级文化、合规和风格约束

## Rules

1. 默认 `adaptation_mode = CONSERVATIVE`。
2. 必须保留 remake invariants：核心因果、人物关系功能、信息揭示顺序、冲突、反转、高潮、结局/钩子功能。
3. 目标人物必须完成本地化替换；不得直接沿用原片演员身份作为目标人物。
4. 台词按当地自然口语重写，不做机械逐字翻译；语义、人物意图和剧情功能必须保持。
5. 人名、称谓、地点、职业、社会习惯、货币/单位、文化表达可按目标地区本地化。
6. 场景处理严格遵守策略：
   - `KEEP`：保留场景功能和主要视觉环境，只做必要文化适配；
   - `LOCALIZE`：替换为目标地区合理场景，但保持剧情功能；
   - `AUTO`：按文化合理性和重做成本选择，并记录原因。
7. 道具外观和文化形式可以变化，但承担关键剧情功能的道具不能被无故删除。
8. 允许因目标语言表达长度调整句式，但不得为了硬贴原片时长删掉关键剧情信息。
9. 任何会改变 remake invariant 的建议必须进入 `review_items`，不能自动执行。

## Forbidden Behaviors

- 自由续写、增加支线或修改结局。
- 为追求“本地味”改变核心人物关系和冲突原因。
- 逐字翻译导致当地人不自然的台词。
- 未经记录就删除关键动作、线索、反转或钩子。
- 把目标侧改编内容写回 SourceDramaSnapshot。
- 用原目标语音时长反向篡改 source dialogue。

## Output Contract

```json
{
  "source_screenplay_revision": "...",
  "skill": {"id": "country_adaptation", "version": "1.0.0"},
  "adaptation_mode": "CONSERVATIVE",
  "target_language": "...",
  "target_region": "...",
  "character_mapping": [],
  "scene_mapping": [],
  "cultural_localizations": [],
  "screenplay": {},
  "preserved_invariants": [],
  "review_items": []
}
```

## Validator

- target language/region 必须匹配项目当前配置。
- 每个被原剧使用的正式人物必须存在唯一目标人物映射或明确阻塞原因。
- 每条正式目标对白必须能回指 source utterance / story function。
- 所有 remake invariants 必须被标记为 preserved，或产生阻塞性 review item。
- 场景策略不得被 Skill 静默覆盖。
- source screenplay revision 改变后旧 adaptation 必须 stale。

## Completion Criteria

- 当地观众读起来像当地创作的自然剧本；
- 核心剧情效果与原剧保持一致；
- 人物、地点、语言和文化表达完成目标地区适配；
- 所有不可安全自动改动的问题被集中为少量 review items；
- 输出可锁定后供 `script_to_storyboard` 使用。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
