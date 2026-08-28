# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2-E1 + P2-E2 IMPLEMENTED, LOCAL-REAL ACCEPTANCE PENDING / P2.6 WINDOWS REAL-MODEL ACCEPTANCE NOT PASSED**  
> Date: 2026-08-28  
> Last synchronized: 2026-08-28 19:05 +08:00  
> Production pipeline profile: `breakdown-p2-full-v1`  
> Production VLM profile: `breakdown-p2-vlm-episode-window-e2-v1`  
> Production Fusion profile: `breakdown-p2-fusion-episode-context-e1-v2`  
> Acceptance schema: `breakdown-p2-acceptance-v1`

## 1. 当前验收结论

```text
P1/P2 实现验收                    = CONDITIONAL PASS
P2-E1 Episode-context Fusion       = IMPLEMENTED
P2-E1 真实短剧行为验收             = PENDING
P2-E2 continuous-window Qwen3-VL   = IMPLEMENTED
P2-E2 Windows/真实短剧行为验收      = PENDING
P2.6 Windows / 真实模型验收         = NOT PASSED
完整真实短剧 PASS report            = 尚不存在
```

因此当前不能写 `P2 ACCEPTED`、`P2 CLOSED`、`P2.6 PASS`、`整套 Episode-context 拉片已通过真实模型验收`。

## 2. 当前正式生产链

```text
Episode Current ShotRevision
→ frozen BreakdownRun
→ Episode ASR
→ OCR
→ P2-E2 overlapping Episode-window Qwen3-VL
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E1 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
→ acceptance report
→ human review
```

正式模块：

```text
engine/app/breakdown_p2_vlm_episode_v2.py
scripts/run_breakdown_vlm_qwen3_episode_windows.py
engine/app/breakdown_p2_vlm_runtime_v1.py
engine/app/breakdown_p2_fusion_episode_v2.py
engine/app/breakdown_p2_pipeline_v1.py
engine/app/breakdown_p2_acceptance_v1.py
```

Provider/Fusion/validator 任一硬失败都不能替换旧 Current Breakdown；ShotRevision 变化导致 STALE 时不得覆盖生命周期事实。

## 3. E2 runtime / 窗口参数

默认：

```text
window target = 24 秒
window overlap = 25%
window edge = Shot boundary
每个 Shot 必须完整落入 >=1 window
按 Episode 顺序串行推理
READY preprocess proxy 优先，Episode source fallback
```

允许调参：

```text
20 <= window seconds <= 40
0.10 <= overlap ratio <= 0.50
```

CLI：

```text
python scripts/run_breakdown_p2.py run --episode-id <EPISODE_ID> \
  --vlm-window-seconds 24 \
  --vlm-window-overlap-ratio 0.25
```

Windows runner仍可走原有完整 P2 入口；E2 已通过稳定 `breakdown_p2_vlm_runtime_v1` import 接入 pipeline。

## 4. E2 专项验收 — 连续视觉上下文

真实素材至少包含：

```text
同一 Scene 的大全景/中景
→ 人物特写或背景虚化
→ 手部/手机/关键道具插入
→ 另一人物特写
→ 至少一次真实明确换场
```

重点检查：

```text
1. 特写自己看不到背景时，不应因为“缺少地点”自动换 Scene
2. scene_basis 应能区分 DIRECT / CONTEXT / MIXED / UNCERTAIN
3. scene_continuity 应合理输出 SAME / NEW_SCENE / UNCERTAIN
4. 明确客厅 → 医院/街道等真实换场仍要被发现，不能过度合并
5. 同一人物的匿名外观/动作描述跨相邻镜头应更稳定，但不得变成 Character ID
6. 关键剧情道具跨镜连续性应更稳定
7. 每个最终 VLM_OUTPUT 仍 exact Shot bound，不得把 window 当 Shot 写入 P1
```

E2 Prompt 必须保持：

```text
cut != scene change
closeup/blur/insert only borrows context when supported
uncertain stays UNCERTAIN
no ASR/OCR transcription inside VLM
anonymous subjects only
no Final asset IDs
Simplified Chinese generated prose
```

## 5. E2 provenance / Contract 检查

每条最终 Shot VLM Evidence 应继续满足：

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen ShotRevisionItem
source_start_us / source_end_us = exact Shot range
payload.semantic = existing anonymous P2.4 semantic shape
```

同时应存在：

```text
payload.episode_window.profile = breakdown-p2-vlm-episode-window-e2-v1
window_id
window_start_us / window_end_us
supporting_window_ids
selection_policy = max-surrounding-context-margin-v1
scene_continuity
scene_basis
context_note
```

同一 Shot 被多个 window 覆盖时，不能简单“最后一个覆盖前一个”；应选择具有最大前后上下文余量的候选。

Historical BreakdownRun / raw sidecar fingerprint 不允许被 E2 重写。

## 6. E1 专项验收 — 跨镜对白

选择一条跨两个或更多 Shot 的真实对白。必须满足：

```text
ASR_SEGMENT = 完整对白文本真值
每个 Shot-local projection content_text = 完整句
projection dialogue_group_id 相同
projection asr_segment_id 相同
dialogue_source_start_us/end_us = 完整 Segment 范围
continues_from_previous_shot / continues_to_next_shot 正确
ASR_WORD raw Evidence 保持不可变
```

禁止旧行为：

```text
Shot A = “你怎么现在”
Shot B = “才回来？”
```

## 7. E1 专项验收 — Scene continuity

E1 fallback 仍需正确：

```text
UNKNOWN / missing / generic scene hint → inherit current Scene
病房 → 医院病房、客厅 → 家中客厅 → same Scene
明确地点冲突或 INT ↔ EXT → new Scene
```

E2 到位后，E1 不应抢过更强的连续窗口视觉证据；当前 E1 仍主要消费最终 per-Shot VLM semantics，因此 E3/E4 尚未实现前，要特别观察是否存在“E2看懂了、Fusion仍保守过度”的案例。

## 8. Runtime preflight

API：

```text
GET /api/breakdown/p2/runtime-preflight
```

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
```

至少确认：

```text
main Python
faster-whisper
RapidOCR
OpenCV
FFmpeg / FFprobe
isolated VLM Python
Qwen3-VL checkpoint
isolated torch / transformers / qwen_vl_utils
CUDA availability when requested
nvidia-smi GPU/VRAM/driver
E2 window runner file present
```

注意：现有 preflight 实现主要验证既有 VLM runtime/model 基础条件；真实 E2 window materialization/Qwen decode 仍必须通过一次真实 Episode run 才能证明。Preflight 本身不下载模型、不执行真实推理、不等于质量 PASS。

## 9. Acceptance Contract

API：

```text
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

报告默认位置：

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/acceptance/
  p2-acceptance-<run>.json
```

机器结构至少要求：Run READY 类、ASR/OCR/VLM sidecar+fingerprint、VLM READY、Fusion READY 类、Shot Draft 全覆盖。

人工评分继续使用：

```text
asr_dialogue
asr_timing
ocr_text
vlm_scene
vlm_subjects
vlm_actions
vlm_props
fusion_completeness
fusion_timing
fusion_conflict_handling
```

本次人工 notes/blocking_issues 还应明确记录：

```text
E2 same-scene closeup/insert continuity
E2 genuine scene-change detection
E2 anonymous subject continuity
E2 key-prop continuity
E1 cross-shot dialogue continuity
```

PASS 仍要求全部 required score >=4.0 且 blocking_issues 为空。机器指标不能自动变成 PASS。

## 10. 单集 / 批量 / Windows 入口

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
```

批量规则：`Episode.sort_order → 严格逐集 → concurrency=1`。

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
python scripts/run_breakdown_p2.py run --episode-id <EPISODE_ID>
python scripts/run_breakdown_p2.py report --run-id <RUN_ID>
python scripts/run_breakdown_p2.py compare <report-a.json> <report-b.json>
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_breakdown_p2_windows.ps1 `
  -EpisodeId <EPISODE_ID>
```

## 11. Identity / Final Asset 禁止事项

Episode-context 增加语义上下文，但不改变身份/资产边界：

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
P2 cannot write Final Character/Scene/Prop/Binding
```

Character V10.1 same-sample cannot-link、Face hard conflict、>=3 independent Shots/images、explicit Shot Assignment/Final Gate 均不可被 E2 语义放松。

## 12. 工程完成边界

可以确认：

```text
P2-E1 Episode-context Fusion                        IMPLEMENTED
P2-E2 overlapping Episode-window VLM               IMPLEMENTED
E2 stable production runtime wiring                 IMPLEMENTED
E2 unit coverage                                    ADDED
P2.6 orchestrator/preflight/Windows/acceptance      IMPLEMENTED
P1/P2 implementation acceptance                     CONDITIONAL PASS
```

不能确认：

```text
P2-E1 real-short-drama acceptance                   PENDING
P2-E2 real Qwen/Windows acceptance                  PENDING
P2-E3 contextual Shot refinement                    NOT IMPLEMENTED
P2-E4 final Episode-context Fusion                  NOT IMPLEMENTED
P2.6 Windows / real-model acceptance                NOT PASSED
real short-drama full-chain quality                 NOT ACCEPTED
```

下一步先做真实短剧 E2 重跑；只有 E2 runtime/效果稳定后才进入 E3，不能因为代码已提交就提前升级验收状态。
