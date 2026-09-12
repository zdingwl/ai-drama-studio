# P14 Retake 分组折叠与 OVERFLOW 筛选工作台整改

## 1. 问题

真实项目当前包含两集共 89 条目标对白。旧版 `TargetAudioRetakeWorkspace` 会一次性渲染全部对白卡片、播放器、表演指令和两个滑杆，页面从 P14 Retake 区一直延伸到最终验收区，真实制作时很难定位需要处理的对白。

该问题属于产品呈现和制作效率问题，不改变 P14 Target Audio / Timing 数据契约。

## 2. 新工作台规则

Retake 工作区按 CURRENT Target Script 的 `episode_order + utterance_id` 建立对白所属集；按 CURRENT Target Bible 的 `target_character_id -> display_name` 显示可读角色名。不得根据重复的 `utterance_number` 猜测集数，也不得把内部 character id 当作主要角色名称。

默认只显示集级和角色级摘要，具体对白卡片在用户展开对应分组后才渲染。支持：

- 按集折叠 / 展开；
- 集内按角色折叠 / 展开；
- 搜索目标对白、角色、声线、`#对白序号`、`第N集`；
- `只看 OVERFLOW`；
- `只看已选重录`；
- 展开全部 / 折叠全部 / 清空筛选。

筛选只改变 UI 展示，不改变 `draft.selected`、Acting Direction、`emo_alpha`、`duration_factor`、Retake command 或 ProviderJob 行为。

## 3. OVERFLOW 事实源

`只看 OVERFLOW` 只消费当前 P14 Timing candidate 中 `fit_status = OVERFLOW` 的 utterance id。系统不得根据文本长度或 TTS 时长自行猜测超时。

启用搜索、OVERFLOW 或已选过滤后，命中的集和角色分组自动展开，便于直接处理结果。

## 4. Retake 行为不变

- 单句 Retake 仍只重录当前句；
- 批量 Retake 仍只发送显式选中的 utterance；
- 未选句继续复用既有 WAV，不新增 TTS ProviderJob；
- 筛选隐藏的已选句仍保持选中，底部 sticky action 始终显示真实已选总数；
- `duration_factor` 产品范围仍为 `0.8 ~ 1.25`；
- 不修改 Final Target Dialogue。

## 5. 阶段状态

本整改只提升 P14 人工制作效率，不等于 P14 PASS，不改变 TTS / TIMING capability availability，也不进入 Target Storyboard / Generation / QC / Lip Sync / Post。
