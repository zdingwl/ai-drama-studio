# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2.6 WINDOWS REAL-MODEL ACCEPTANCE NOT PASSED**  
> Date: 2026-08-28  
> Last synchronized: 2026-08-28 12:12 +08:00  
> Production profile: `breakdown-p2-full-v1`  
> Acceptance schema: `breakdown-p2-acceptance-v1`

## 1. 当前验收结论

用户当前验收结论：

```text
P1/P2 实现验收                    = CONDITIONAL PASS / 条件通过
P2.6 Windows / 真实模型验收       = NOT PASSED / 未通过
OCR runtime/model                  = 尚未补齐
Qwen3-VL model/runtime             = 尚未补齐
真实短剧完整链                     = 尚未完成
最终人工 PASS report               = 尚不存在
```

因此当前不能写：

```text
P2 ACCEPTED
P2 CLOSED
P2.6 PASS
真实模型效果已验收
```

本次未通过的含义是：**P2.6 的生产代码、Windows runner、preflight 和 acceptance harness 已实现，但实际 Windows 模型环境未满足完整验收条件。**

## 2. 下一次必须满足的重测条件

先完成：

```text
1. OCR runtime/model provisioning
2. Qwen3-VL model/runtime provisioning
```

然后选一段真实短剧素材，完整执行：

```text
Episode Current ShotRevision
→ create frozen BreakdownRun
→ ASR
→ OCR
→ Qwen3-VL
→ immutable Evidence sidecars
→ deterministic Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
→ P2 acceptance report
→ human review
```

最终 PASS 条件：

```text
机器结构检查通过
+ 所有 required 人工维度都有评分
+ 每个 required score >= 4.0
+ blocking_issues 为空
= PASS
```

## 3. 正式生产入口

核心模块：

```text
engine/app/breakdown_p2_pipeline_v1.py
```

正式执行顺序：

```text
ASR → OCR → VLM → Fusion
```

Provider/Fusion/validator 任一硬失败都不能替换旧 Current Breakdown；ShotRevision 变化导致 STALE 时不得覆盖该生命周期事实。

### 单集后台 API

```text
POST /api/episodes/{episode_id}/tasks/breakdown
```

Task type：

```text
EPISODE_BREAKDOWN_P2
```

### 批量后台 API

```text
POST /api/projects/{project_id}/tasks/breakdown-batch
```

批量规则：

```text
Episode.sort_order
→ 严格逐集顺序
→ concurrency = 1
```

## 4. CLI / Windows 正式入口

跨平台 CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
python scripts/run_breakdown_p2.py run --episode-id <EPISODE_ID>
python scripts/run_breakdown_p2.py report --run-id <BREAKDOWN_RUN_ID>
python scripts/run_breakdown_p2.py compare <report-a.json> <report-b.json>
```

Windows 一键运行：

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

Windows runner 默认先执行 strict preflight；runtime 不完整时应直接停止，不允许边跑边猜环境。

## 5. Runtime preflight

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

Preflight 不做：

```text
不下载模型
不运行真实视频 inference
不修改 BreakdownRun
不声称质量通过
```

当前已知重点：下一次 strict preflight 必须明确证明 **OCR + Qwen runtime/model 已可用**，否则不要进入最终真实短剧验收。

## 6. 真实素材 Acceptance Contract

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

必须至少满足：

```text
Run = READY / READY_WITH_WARNINGS
ASR sidecar 已登记 + SHA-256 fingerprint
OCR sidecar 已登记 + SHA-256 fingerprint
VLM sidecar 已登记 + SHA-256 fingerprint
VLM status = READY
FUSION status = READY / READY_WITH_WARNINGS
ShotSemanticDraft 数量 == frozen source ShotRevisionItem 数量
```

结构检查失败：

```text
STRUCTURAL_FAIL
```

### 人工真实视频评分

模板：

```text
scripts/p2_acceptance_review_template.json
```

0–5 分维度：

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

`ocr_text` 如果测试片段确实没有可读画面文字，可显式放入 `not_applicable`。

状态：

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

**机器指标不能自动变成 PASS。**

## 7. Provider / 参数比较

CLI `run` 支持候选参数覆盖：

```text
ASR model / device / compute type
OCR small|medium / device / sampling interval / frame cap / score threshold
VLM model / model path / device / fps / max tokens / max pixels
```

每一种候选组合必须建立新的 BreakdownRun，保留各自 Evidence/报告，不能覆盖旧 raw Evidence。比较已有报告只读取现有 JSON，不自动重跑模型。

## 8. P2 匿名人物 cannot-link

P2.5 Fusion 的匿名主体合并仍是 soft semantic grouping，不是身份识别。

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

## 9. 工程完成边界

可以确认：

```text
P2.1 Provider/raw Evidence Contract                 IMPLEMENTED
P2.2 ASR Provider                                  IMPLEMENTED
P2.3 OCR Observation Provider                      IMPLEMENTED
P2.4 VLM anonymous Shot semantics                  IMPLEMENTED
P2.5 deterministic Fusion + P1 publish             IMPLEMENTED
P2.6 production orchestrator                       IMPLEMENTED
P2.6 runtime preflight                             IMPLEMENTED
P2.6 Windows runner                                IMPLEMENTED
P2.6 acceptance report/scoring/comparison tooling  IMPLEMENTED
P1/P2 implementation acceptance                    CONDITIONAL PASS
```

不能确认：

```text
P2.6 Windows / real-model acceptance               NOT PASSED
real short-drama full-chain quality                NOT ACCEPTED
```

## 10. P2 全阶段禁止事项

P2 仍然禁止写 Final Character/Scene/Prop assets and Final Shot bindings，也禁止让 VLM/ASR 语义绕过 Character V10.1 hard gates。

P2 最终交给 P3 的是：**可追溯、可读取、可展示的匿名结构化 Breakdown Draft**，不是 Final 资产身份。
