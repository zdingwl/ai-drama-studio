# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2-E1 + P2-E2 + P2-E3 IMPLEMENTED, LOCAL-REAL ACCEPTANCE PENDING / P2.6 WINDOWS REAL-MODEL ACCEPTANCE NOT PASSED**  
> Date: 2026-08-28  
> Last synchronized: 2026-08-28 19:39 +08:00  
> Production pipeline profile: `breakdown-p2-full-v1`  
> Production E2 VLM profile: `breakdown-p2-vlm-episode-window-e2-v1`  
> Production E3 refinement profile: `breakdown-p2-contextual-shot-refinement-e3-v1`  
> Production Fusion profile: `breakdown-p2-fusion-episode-context-e1-v2`  
> Acceptance schema: `breakdown-p2-acceptance-v1`

## 1. 当前验收结论

```text
P1/P2 实现验收                    = CONDITIONAL PASS
P2-E1 Episode-context Fusion       = IMPLEMENTED
P2-E1 真实短剧行为验收             = PENDING
P2-E2 continuous-window Qwen3-VL   = IMPLEMENTED
P2-E2 Windows/真实短剧行为验收      = PENDING
P2-E3 contextual Shot refinement   = IMPLEMENTED
P2-E3 Windows/真实短剧行为验收      = PENDING
P2-E4 final Episode Fusion          = NOT IMPLEMENTED
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
→ P2-E3 contextual Shot refinement
→ one immutable exact-Shot VLM_OUTPUT sidecar
   payload.e2_semantic = E2 visual result
   payload.semantic = E3 refined result
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
engine/app/breakdown_p2_refinement_v1.py
scripts/run_breakdown_refinement_qwen3.py
engine/app/breakdown_p2_vlm_runtime_v1.py
engine/app/breakdown_p2_fusion_episode_v2.py
engine/app/breakdown_p2_pipeline_v1.py
engine/app/breakdown_p2_acceptance_v1.py
```

E3 保持在 formal VLM Provider 内，因此 pipeline 仍然是 `ASR → OCR → VLM → Fusion`，API 和 frozen P2 component contract 不变。

Provider/E3/Fusion/validator 任一整体硬失败都不能替换旧 Current Breakdown；ShotRevision 变化导致 STALE 时不得覆盖生命周期事实。

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
7. E2 原始视觉语义必须在最终 sidecar 的 payload.e2_semantic 中可回看
```

E2 Prompt 必须保持：

```text
cut != scene change
closeup/blur/insert only borrows context when supported
uncertain stays UNCERTAIN
no ASR/OCR transcription inside visual E2
anonymous subjects only
no Final asset IDs
Simplified Chinese generated prose
```

## 5. E3 专项验收 — 当前 Shot 上下文精修

E3 每个 Shot 使用：

```text
provisional Scene context
previous/current/next E2 Shot semantic
selected/supporting E2 window summaries
overlapping ASR_SEGMENT
overlapping OCR_OBSERVATION
```

真实验收最重要的是：**上下文让当前镜头更好懂，但不能把邻镜头的视觉事实搬过来。**

逐 Shot 检查：

```text
1. summary / narrative_function 是否比单纯视觉描述更符合剧情上下文
2. Scene UNKNOWN/泛化描述是否只在前后证据充分时被补全
3. 当前镜头没有出现的人，不能因为上一/下一镜头出现就被新增进 subjects
4. current E2 没有的 subject_X 不能被 E3 新造出来
5. 邻镜头独有的道具不能因为 ASR/OCR 提到就被写成当前镜头“可见”
6. 景别/运镜/构图不能由对白推断并覆盖明确 E2 视觉事实
7. ASR_SEGMENT 文本不能被 E3 改写、翻译或用于猜 speaker identity
8. OCR 文本不能被 E3 改写
9. Final Character/Scene/Prop/Binding ID 不得进入 semantic/provenance
```

单 Shot E3 失败允许：

```text
contextual_refinement.status = FALLBACK_E2
payload.semantic = 该 Shot E2 semantic
warning 明确记录
```

但整套 E3 runtime 缺失/整体 inference 失败必须导致 production VLM `FAILED`，不能静默声称 E3 已执行。

## 6. E2 + E3 provenance / Contract 检查

每条最终 Shot VLM Evidence 必须继续满足：

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen ShotRevisionItem
source_start_us / source_end_us = exact Shot range
```

最终 payload 应同时存在：

```text
payload.e2_semantic
payload.semantic
payload.episode_window
payload.contextual_refinement
```

其中：

```text
payload.e2_semantic = original E2 visual semantic
payload.semantic = E3 refined semantic consumed by Fusion
payload.episode_window.profile = breakdown-p2-vlm-episode-window-e2-v1
payload.contextual_refinement.profile = breakdown-p2-contextual-shot-refinement-e3-v1
```

E3 provenance 应至少能看到：

```text
raw_vlm_source_id
selected_window_id
supporting_window_ids
asr_source_ids
ocr_source_ids
```

Historical BreakdownRun / raw sidecar fingerprint 不允许被 E2/E3 重写；新逻辑只作用于新 Run。

## 7. E1 专项验收 — 跨镜对白

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

E3 读取 ASR 只用于上下文理解，不得改变上述 E1 dialogue truth。

## 8. E1 专项验收 — Scene continuity

E1 fallback 仍需正确：

```text
UNKNOWN / missing / generic scene hint → inherit current Scene
病房 → 医院病房、客厅 → 家中客厅 → same Scene
明确地点冲突或 INT ↔ EXT → new Scene
```

当前 E1 已会消费 E3 的 `payload.semantic`，但 E4 尚未把 E2 的 explicit `scene_continuity/scene_basis/window_summary` 作为主要 Scene continuity truth。因此真实验收要记录是否存在“E2/E3 已看懂，但 E1 Scene planner 仍然保守过度或切错”的案例；这将直接决定 E4 的实现优先级。

## 9. Runtime preflight

API：

```text
GET /api/breakdown/p2/runtime-preflight
```

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
```

基础条件至少确认：

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
```

另外 **当前 acceptance preflight 代码仍主要检查历史 VLM 基础 runtime/runner，不足以单独证明新的 E2/E3 两个 runner 都就绪**。在 preflight 代码升级前，本地验收必须额外确认文件存在：

```text
scripts/run_breakdown_vlm_qwen3_episode_windows.py
scripts/run_breakdown_refinement_qwen3.py
```

并以一次真实 Episode 成功跑过 `E2 → E3` 作为最终 runtime 证据。Preflight 本身不下载模型、不执行真实推理、不等于质量 PASS。

## 10. Acceptance Contract

API：

```text
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

报告默认位置：

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/acceptance/
  p2-acceptance-<run>.json
```

现有机器结构至少要求：Run READY 类、ASR/OCR/VLM sidecar+fingerprint、VLM READY、Fusion READY 类、Shot Draft 全覆盖。

由于 acceptance schema 尚未为 E3 单独加新 score key，本轮人工 review 必须同时检查 VLM provider metadata / sidecar：

```text
contextual_refinement_profile = breakdown-p2-contextual-shot-refinement-e3-v1
contextual_refinement_status = READY or READY_WITH_WARNINGS
fusion_semantic_source = VLM_OUTPUT.payload.semantic
e2_semantic_preservation = VLM_OUTPUT.payload.e2_semantic
```

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
E3 current-Shot grounding / no neighbor-fact leakage
E3 Scene contextual refinement quality
E3 anonymous subject grounding
E3 key-prop grounding
E1 cross-shot dialogue continuity
```

PASS 仍要求全部 required score >=4.0 且 blocking_issues 为空。机器指标不能自动变成 PASS。

## 11. 单集 / 批量 / Windows 入口

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

## 12. Identity / Final Asset 禁止事项

Episode-context 增加语义上下文，但不改变身份/资产边界：

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
P2 cannot write Final Character/Scene/Prop/Binding
```

Character V10.1 same-sample cannot-link、Face hard conflict、>=3 independent Shots/images、explicit Shot Assignment/Final Gate 均不可被 E2/E3 语义放松。

## 13. 工程完成边界

可以确认：

```text
P2-E1 Episode-context Fusion                        IMPLEMENTED
P2-E2 overlapping Episode-window VLM               IMPLEMENTED
P2-E3 contextual Shot refinement                    IMPLEMENTED
E2+E3 stable production VLM wiring                  IMPLEMENTED
E2/E3 unit coverage                                 ADDED
P2.6 orchestrator/preflight/Windows/acceptance      IMPLEMENTED（但 preflight E2/E3 runner 检查仍需增强）
P1/P2 implementation acceptance                     CONDITIONAL PASS
```

不能确认：

```text
P2-E1 real-short-drama acceptance                   PENDING
P2-E2 real Qwen/Windows acceptance                  PENDING
P2-E3 real contextual-refinement acceptance         PENDING
P2-E4 final Episode-context Fusion                  NOT IMPLEMENTED
P2.6 Windows / real-model acceptance                NOT PASSED
real short-drama full-chain quality                 NOT ACCEPTED
```

下一步先做真实短剧 E2+E3 重跑；只有新 VLM 语义与 E1 Fusion 行为稳定后才进入 E4，不能因为代码已提交就提前升级验收状态。
