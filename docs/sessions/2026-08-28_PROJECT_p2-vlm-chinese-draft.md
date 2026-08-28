# P2 VLM 中文 Draft 源头生成

日期：2026-08-28

状态：**IMPLEMENTED / NEW REAL-MODEL RUN REQUIRED**

## 目标

P3 已经完成界面中文化，但历史 `Structured Draft` 中的 Scene / Shot / 人物活动 / VLM Event / 道具文案仍可能是英文，因为旧 P2.4 Prompt 只要求“尽量使用项目原始语言”。

本次修改把中文要求放到 P2.4 Qwen3-VL **第一次生成语义的源头**，而不是在 P3 前端二次翻译。

## 生产语言策略

生产 Prompt Profile：

- `breakdown-p2-vlm-zh-draft-v1`
- `draft_text_language = zh-CN`

VLM 生成的以下自然语言字段必须使用简体中文：

- `scene.location_hint`
- `scene.time_of_day`
- `scene.environment_description`
- `shot.summary`
- `shot.visual_description`
- `shot.shot_type_hint`
- `shot.camera_motion_hint`
- `shot.narrative_function_hint`
- `shot.composition_hint`
- `subjects[].appearance_summary`
- `subjects[].activity_summary`
- `subjects[].screen_position`
- `events[].content`
- `props[].label`
- `props[].narrative_reason`

## 不翻译的内容

以下内容继续保持原始/机器 Contract，不做中文改写：

- JSON key；
- `subject_A / subject_B ...` Shot-local 匿名标签；
- `INT|EXT|MIXED|UNKNOWN`；
- `FULL|PARTIAL|OCCLUDED|UNKNOWN`；
- `LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN`；
- `VISUAL|ACTION`；
- `LOW|MEDIUM|HIGH`；
- ASR 对白原文；
- OCR 识别原文。

ASR / OCR 仍由独立 Provider 负责，VLM Prompt 明确禁止转录对白、字幕、招牌、手机屏幕和文档。

## Fusion 稳定性

P2.5 deterministic Fusion 不做翻译，直接消费 VLM semantic。

为了避免中文自由措辞降低现有 Fusion 稳定性，Prompt 额外要求：

- `scene.location_hint` 使用简短、稳定、通用的中文地点类别；
- 同类场景避免无证据的地点措辞漂移；
- `appearance_summary` 固定按可区分外观特征顺序描述，减少跨 Shot 文本漂移；
- `props[].label` 使用稳定中文名词；
- 景别 / 运镜使用短中文术语。

这不会改变 P1/P2 schema、数据库或 Final Asset Contract。

## Provenance

`engine.app.breakdown_p2_vlm_runtime_v1.Qwen3VLSemanticProvider` 会在 VLM sidecar metadata 记录：

- `prompt_profile = breakdown-p2-vlm-zh-draft-v1`
- `draft_text_language = zh-CN`
- `vlm_natural_language_policy = simplified-chinese`
- `asr_ocr_translation_policy = preserve-raw-source-text`

因此历史 Run 可以追溯其生成语言策略。

## Production runner

正式 P2 pipeline 仍使用：

`breakdown_p2_pipeline_v1.py`
→ `breakdown_p2_vlm_runtime_v1.py`
→ `run_breakdown_vlm_qwen3_strict_reader.py`
→ `run_breakdown_vlm_qwen3_diagnostic.py`
→ Qwen3-VL

Strict reader 先安装：

1. Windows decord strict-reader compatibility；
2. `breakdown-p2-vlm-zh-draft-v1` 中文 Prompt Profile；

再进入真实 Qwen 推理。

fail-closed、Windows decord、诊断 transport 均保持不变。

## 历史 Run

旧 `BreakdownRun` / VLM sidecar / Draft 是 immutable history，不会被重新翻译或覆盖。

因此只有**新创建的 BreakdownRun**会生成中文 VLM Draft 文案。

## 本地验收

更新代码并重启后端后，新建一次真实剧集 BreakdownRun。

验收重点：

1. Scene 地点 / 环境描述为简体中文；
2. Shot 摘要 / 视觉描述 / 景别 / 运镜 / 叙事功能为简体中文；
3. 人物外观与动作描述为简体中文；
4. VLM 画面/动作 Event 为简体中文；
5. 道具名和叙事原因为简体中文；
6. ASR 对白保持源视频原始语言；
7. OCR 文字保持画面原文；
8. VLM sidecar metadata 能看到中文 Prompt Profile；
9. P2.5 Fusion / P1 validator 正常完成。

## Acceptance truth

本修改不改变当前阶段验收事实：

- `P1/P2 implementation acceptance = CONDITIONAL PASS`
- `P2.6 Windows / real-model acceptance = NOT PASSED`

只有完成真实短剧全链 + acceptance report + human review 后，才能把 P2.6 标记为 PASS。
