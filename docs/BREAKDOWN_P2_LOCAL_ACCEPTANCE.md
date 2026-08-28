# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2-E1 IMPLEMENTED, LOCAL-REAL ACCEPTANCE PENDING / P2.6 WINDOWS REAL-MODEL ACCEPTANCE NOT PASSED**  
> Date: 2026-08-28  
> Last synchronized: 2026-08-28 18:12 +08:00  
> Production pipeline profile: `breakdown-p2-full-v1`  
> Production Fusion profile: `breakdown-p2-fusion-episode-context-e1-v2`  
> Acceptance schema: `breakdown-p2-acceptance-v1`

## 1. 当前验收结论

```text
P1/P2 实现验收                    = CONDITIONAL PASS / 条件通过
P2-E1 Episode-context Fusion       = IMPLEMENTED / 已实现
P2-E1 真实短剧行为验收             = PENDING / 待本地验证
P2.6 Windows / 真实模型验收       = NOT PASSED / 未通过
完整真实短剧 PASS report          = 尚不存在
```

因此当前不能写：

```text
P2 ACCEPTED
P2 CLOSED
P2.6 PASS
整集连续 VLM 已完成
真实模型效果已验收
```

P2-E1 解决的是当前 Fusion 的两个结构性问题：

```text
跨 Shot 对白不再按切镜点切成残句
同场景特写/虚化/环境不足镜头不再因为 UNKNOWN 自动换 Scene
```

但当前 Qwen3-VL 仍逐 Reference Clip 推理；P2-E2 continuous-window VLM 尚未实现。

## 2. 下一次必须满足的重测条件

先完成/确认：

```text
1. OCR runtime/model provisioning
2. Qwen3-VL model/runtime provisioning
3. current main 包含 P2-E1 production wiring
```

然后选一段有以下特征的真实短剧素材：

```text
至少一处对白跨切镜
至少一场包含大全景 + 人物特写/虚化背景/插入镜头
至少一次明确真实换场（例如客厅 → 医院/街道）
```

完整执行：

```text
Episode Current ShotRevision
→ create frozen BreakdownRun
→ Episode ASR
→ OCR
→ current Qwen3-VL
→ immutable Evidence sidecars
→ Episode-context E1 Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
→ P2 acceptance report
→ human review
```

最终 PASS 条件仍是：

```text
机器结构检查通过
+ 所有 required 人工维度都有评分
+ 每个 required score >= 4.0
+ blocking_issues 为空
= PASS
```

## 3. 正式生产入口

核心 orchestrator：

```text
engine/app/breakdown_p2_pipeline_v1.py
```

正式执行顺序：

```text
ASR → OCR → VLM → Episode-context E1 Fusion
```

Fusion 实现：

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

Provider/Fusion/validator 任一硬失败都不能替换旧 Current Breakdown；ShotRevision 变化导致 STALE 时不得覆盖该生命周期事实。

### 单集后台 API

```text
POST /api/episodes/{episode_id}/tasks/breakdown
Task type = EPISODE_BREAKDOWN_P2
```

### 批量后台 API

```text
POST /api/projects/{project_id}/tasks/breakdown-batch
Episode.sort_order → 严格逐集顺序 → concurrency = 1
```

## 4. E1 专项验收 — 跨镜对白

选择一条跨两个或以上 Shot 的真实对白。

原始 ASR 应保持 Episode 时间范围，例如：

```text
ASR_SEGMENT
10.200s → 12.800s
“你怎么现在才回来？”
```

如果切镜发生在 11.300s，E1 允许存在两个 Shot-local DIALOGUE projection，但必须满足：

```text
两个 projection 的 content_text 都是完整句
两个 projection dialogue_group_id 相同
两个 projection asr_segment_id 相同
dialogue_source_start_us/end_us 都指向完整 ASR Segment
第一段 continues_to_next_shot = true
第二段 continues_from_previous_shot = true
```

禁止验收通过的旧结果：

```text
Shot A = “你怎么现在”
Shot B = “才回来？”
```

还要确认：

```text
ASR_WORD raw sidecar 未被修改
ASR_WORD EvidenceLink 仍可追溯到对应 projection
```

## 5. E1 专项验收 — Scene continuity

重点查看同一物理场景中的连续镜头：

```text
建立环境的大全景
→ 人物近景/特写
→ 背景虚化镜头
→ 手部/手机/道具插入镜头
→ 另一人物特写
```

当中间镜头没有足够环境信息时，应当：

```text
UNKNOWN / missing / “室内” / “房间”等弱 hint
→ 继承当前 SceneSegmentDraft
```

兼容的地点粒度也不应切场：

```text
病房 → 医院病房
客厅 → 家中客厅
```

明确变化必须仍能切场：

```text
客厅 → 医院走廊
卧室 → 街道
明确 INT → EXT
明确 EXT → INT
```

E1 的验收核心是：

```text
看不出来 != 换场
但真正换场也不能被吞掉
```

## 6. CLI / Windows 正式入口

跨平台 CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
python scripts/run_breakdown_p2.py run --episode-id <EPISODE_ID>
python scripts/run_breakdown_p2.py report --run-id <BREAKDOWN_RUN_ID>
python scripts/run_breakdown_p2.py compare <report-a.json> <report-b.json>
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_breakdown_p2_windows.ps1 `
  -EpisodeId <EPISODE_ID>
```

带人工验收表：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_breakdown_p2_windows.ps1 `
  -EpisodeId <EPISODE_ID> `
  -ReviewJson .\scripts\p2_acceptance_review_template.json
```

Windows runner 默认先执行 strict preflight；runtime 不完整时应直接停止。

## 7. Runtime preflight

API：

```text
GET /api/breakdown/p2/runtime-preflight
```

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
```

检查至少包括：

```text
主 Python
faster-whisper package
RapidOCR package
OpenCV
FFmpeg / FFprobe
isolated VLM Python
VLM runner script
Qwen3-VL model path
isolated torch / transformers / qwen_vl_utils import
VLM CUDA availability when device=cuda
nvidia-smi GPU / VRAM / driver metadata
```

Preflight 不下载模型、不运行真实视频 inference、不修改 BreakdownRun，也不声称质量通过。

## 8. 真实素材 Acceptance Contract

模块：

```text
engine/app/breakdown_p2_acceptance_v1.py
```

API：

```text
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

默认报告位置：

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/acceptance/
  p2-acceptance-<run>.json
```

### 机器结构检查

至少满足：

```text
Run = READY / READY_WITH_WARNINGS
ASR sidecar 已登记 + SHA-256 fingerprint
OCR sidecar 已登记 + SHA-256 fingerprint
VLM sidecar 已登记 + SHA-256 fingerprint
VLM status = READY
FUSION status = READY / READY_WITH_WARNINGS
FUSION profile = breakdown-p2-fusion-episode-context-e1-v2
ShotSemanticDraft 数量 == frozen source ShotRevisionItem 数量
```

结构检查失败 = `STRUCTURAL_FAIL`。

### 人工真实视频评分

现有模板：

```text
scripts/p2_acceptance_review_template.json
```

0–5 分维度继续使用：

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

同时人工备注必须明确记录本次 E1 专项结果：

```text
cross_shot_dialogue_continuity
same_scene_closeup_continuity
genuine_scene_change_detection
```

`ocr_text` 如果测试片段确实没有可读画面文字，可显式放入 `not_applicable`。

状态仍为：

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

**机器指标不能自动变成 PASS。**

## 9. Provider / 参数比较

CLI `run` 支持候选参数覆盖：

```text
ASR model / device / compute type
OCR small|medium / device / sampling interval / frame cap / score threshold
VLM model / model path / device / fps / max tokens / max pixels
```

每一种候选组合必须建立新的 BreakdownRun，保留各自 Evidence/报告，不能覆盖旧 raw Evidence。历史 Runs 不会自动获得 E1 结果；必须新跑 BreakdownRun。

## 10. P2 匿名人物 cannot-link

Episode-context Scene continuity不能放松匿名主体安全规则：

```text
同一 Scene Segment
+ normalized appearance 完全一致
+ 没有同镜头冲突
→ 可作为跨 Shot LocalSubject 合并 hint

某 normalized appearance 在任一同 Shot 同时出现 >=2 人
→ 该 appearance 在整个 Segment 禁止跨 Shot 合并
→ 回退到 shot-local anonymous key
```

最终人物身份仍由 Character V10.1 / 后续 P5 解决。

## 11. 工程完成边界

可以确认：

```text
P2.1 Provider/raw Evidence Contract                 IMPLEMENTED
P2.2 Episode ASR Provider                           IMPLEMENTED
P2.3 OCR Observation Provider                       IMPLEMENTED
P2.4 current single-Reference-Clip VLM              IMPLEMENTED
P2-E1 Episode-context Fusion                        IMPLEMENTED
P2.6 production orchestrator                        IMPLEMENTED / wired to E1
P2.6 runtime preflight                              IMPLEMENTED
P2.6 Windows runner                                 IMPLEMENTED
P2.6 acceptance report/scoring/comparison tooling   IMPLEMENTED
P1/P2 implementation acceptance                     CONDITIONAL PASS
```

不能确认：

```text
P2-E1 real-short-drama behavior acceptance          PENDING
P2-E2 continuous-window VLM                         NOT IMPLEMENTED
P2.6 Windows / real-model acceptance                NOT PASSED
real short-drama full-chain quality                 NOT ACCEPTED
```

## 12. P2 全阶段禁止事项

P2 仍然禁止写 Final Character/Scene/Prop assets and Final Shot bindings，也禁止让 VLM/ASR 语义绕过 Character V10.1 hard gates。

P2 最终交给 P3 的是：**可追溯、可读取、具有 Episode 上下文连续性的匿名结构化 Breakdown Draft**，不是 Final 资产身份。
