# Target Script / Localization Professional Skill

## 目标

把已经通过 P11 约束的目标世界落实为正式目标剧本对白，同时完整保留每一句 P6 canonical Source Dialogue 的可追溯来源。

P11 已完成真实人工验收，P12 当前**正式准入真实 Provider 与项目验收**。这不代表 P12 已 PASS；`TARGET_SCRIPT` 在 P12 自身真实人工验收前仍保持 `PLANNED`。

## 硬输入

必须同时使用：

- CURRENT `SOURCE_VIDEO_SNAPSHOT`
- CURRENT `ADAPTATION_PLAN`
- CURRENT `TARGET_BIBLE`

三者必须属于同一条 Source Snapshot / P11 lineage。不能只拿 Target Bible，也不能绕过 Snapshot 去重新拼 P5~P9 Source Facts。

## Source Dialogue 规则

原始对白只能来自 Source Snapshot 中冻结的 `canonical_dialogue`。每条 `utterance_id / utterance_number / start_us / end_us / text / language` 都是只读 Source Truth。

模型不得重新 ASR、OCR、听写、看口型猜词、根据剧情补台词或静默修正 Source `text`。如果原对白需要纠错，必须回到 P6 canonical adjudication / human edit 链路并重新形成下游 Snapshot。

## 对白链

本 Skill 只负责：

`Source Dialogue → Translation → Localization → Final Target Dialogue`

后续：

`Target Speaker/Voice → TTS → Actual Speech Duration → Timing Plan`

不属于 P12。

每条 canonical utterance 在 v1 中严格 1:1 对应一条目标对白记录，且同时保留：

- `translation_text`
- `localization_text`
- `final_target_dialogue`

禁止隐藏 split / merge。

## 角色绑定

若 Source Snapshot 的 Speaker attribution 能唯一落到 Source Character，且 P11 Target Bible 有该 Source Character 的唯一 Target Character 映射，服务端可以确定性写入 `target_character_id`。

否则留空。Provider 不得猜 Target Character，更不得生成 voice / TTS casting。

## 不做什么

- 不改 Story / Beat / Scene / Shot 顺序；
- 不生成 Target Storyboard；
- 不生成 Target Voice 或 TTS；
- 不估算 Actual Speech Duration；
- 不生成 Timing Plan；
- 不生成视频；
- 不做 QC / Selection / Lip Sync / Post。

## 发布

正式执行后，`TARGET_SCRIPT` 必须建立以下输入 lineage：

- `SOURCE_VIDEO_SNAPSHOT -> TARGET_SCRIPT : DERIVED_FROM`
- `ADAPTATION_PLAN -> TARGET_SCRIPT : USES`
- `TARGET_BIBLE -> TARGET_SCRIPT : USES`

新 revision supersede 旧 revision；任一硬输入更新都通过 Artifact Graph 递归使旧 Target Script STALE。

## 当前 admission 状态

用户已经明确 `P11 PASS`，因此：

- `LOCALIZATION = AVAILABLE`
- `TARGET_BIBLE = AVAILABLE`
- P12 独立 admission switch 已正式打开；
- P12 可以创建真实 Provider 任务进行本阶段验收；
- `TARGET_SCRIPT` 仍为 `PLANNED`，直到用户后续明确 `P12 PASS`。

任何请求参数或 UI 都不能绕过三个 CURRENT 硬输入、lineage 与 capability 复核。
