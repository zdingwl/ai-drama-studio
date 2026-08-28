# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P2 IMPLEMENTATION CODE COMPLETE / REAL-VIDEO ACCEPTANCE PENDING**  
> Date: 2026-08-28  
> Production profile: `breakdown-p2-full-v1`  
> Acceptance schema: `breakdown-p2-acceptance-v1`

## 1. 这份文档解决什么

P2.1–P2.5 已经分别具备 Provider、raw Evidence sidecar 和 deterministic Fusion，但只有单独模块并不等于用户可以“一次完成 AI 拉片”。P2.6 因此补齐两个正式入口层：

```text
生产执行层
Episode
→ create frozen BreakdownRun
→ ASR
→ OCR
→ VLM
→ Fusion
→ P1 validator
→ publish READY / READY_WITH_WARNINGS

验收层
已完成 BreakdownRun
→ structural checks
→ runtime preflight
→ explicit human review
→ immutable-style JSON acceptance report
```

生产执行和验收必须分开。验收代码绝不隐式重跑 Provider，也不能把人工评分写成 Final Character/Scene/Prop truth。

## 2. 正式生产入口

核心模块：

```text
engine/app/breakdown_p2_pipeline_v1.py
```

正式执行顺序固定为：

```text
ASR → OCR → VLM → Fusion
```

原因：

- ASR/OCR/VLM 都先通过 P2.1 Contract 固化 immutable sidecar；
- Fusion 只消费已经登记的 sidecar，不隐式重跑模型；
- VLM 必须 READY 才能发布完整匿名 Shot semantics；
- ASR/OCR 可在 `NO_EVIDENCE / NOT_AVAILABLE` 时保守降级，最终 Run 进入 warning 语义；
- Provider/Fusion/validator 任一硬失败都不能替换旧 Current Breakdown；
- ShotRevision 变化产生 STALE 时，Pipeline 不覆盖该生命周期事实。

### 2.1 单集后台 API

```text
POST /api/episodes/{episode_id}/tasks/breakdown
```

Task type：

```text
EPISODE_BREAKDOWN_P2
```

进度阶段：

```text
准备 AI 拉片
→ 对白识别
→ 画面文字识别
→ 视频内容理解
→ 多模态融合
→ AI 拉片完成
```

### 2.2 批量后台 API

```text
POST /api/projects/{project_id}/tasks/breakdown-batch
```

Task type：

```text
BATCH_BREAKDOWN_P2
```

批量规则：

```text
Episode.sort_order
→ 严格逐集顺序
→ concurrency = 1
```

禁止同时并发多个 ASR/VLM 重任务轰炸 GPU。单集失败会记录结果并继续后续剧集，批量 Task 最终以 `READY_WITH_WARNINGS` 表示存在失败或 warning。

## 3. CLI / Windows 正式入口

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

Windows runner 默认先执行 strict preflight；本机 runtime 不完整时直接停止，不会边跑边下载/猜环境。

## 4. Runtime preflight

API：

```text
GET /api/breakdown/p2/runtime-preflight
```

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
```

检查：

```text
主 Python
faster-whisper package
RapidOCR package
OpenCV
FFmpeg
FFprobe
isolated VLM Python
VLM runner script
Qwen3-VL model path
isolated torch / transformers / qwen_vl_utils import
VLM CUDA availability when device=cuda
nvidia-smi GPU / VRAM / driver metadata
```

Preflight **不做**：

```text
不下载模型
不运行真实视频 inference
不修改 BreakdownRun
不声称质量通过
```

主环境依赖已在 `engine/requirements.txt` 固化：

```text
faster-whisper==1.2.1
rapidocr==3.9.2
opencv-python==4.11.0.86
onnxruntime-gpu[cuda,cudnn]==1.21.1
```

VLM 继续使用独立 `.runtime/TransVLM/inference` 环境和独立 base Qwen3-VL checkpoint；不把新版 VLM runtime 强塞进主 Python。

## 5. 真实素材 Acceptance Contract

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

### 5.1 机器结构检查

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

### 5.2 人工真实视频评分

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

通过规则：

```text
机器结构检查通过
+ 所有 required 人工维度都有评分
+ 每个 required score >= 4.0
+ blocking_issues 为空
= PASS
```

状态：

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

**机器指标不能自动变成 PASS。** 这是故意的：P2.6 的目标是验证真实短剧效果，而不是让代码给自己打分。

## 6. Provider / 参数比较

CLI `run` 支持候选参数覆盖：

```text
ASR model / device / compute type
OCR small|medium / device / sampling interval / frame cap / score threshold
VLM model / model path / device / fps / max tokens / max pixels
```

每一种候选组合必须建立新的 BreakdownRun，保留各自 Evidence/报告，不能覆盖旧 raw Evidence。

比较已有报告：

```text
python scripts/run_breakdown_p2.py compare report-a.json report-b.json
```

比较只读取现有 JSON，不自动重跑模型。

注意：成功的候选 Run 会遵守 P1 publish 规则成为 Episode Current Breakdown。因此 benchmark 应使用专门测试项目/剧集，或明确接受 Current Breakdown 会随候选 Run 更新。

## 7. P2 匿名人物 cannot-link

P2.5 Fusion 的匿名主体合并仍是 soft semantic grouping，不是身份识别。

正式保守规则：

```text
同一 Scene Segment
+ normalized appearance 完全一致
+ 没有同镜头冲突
→ 可作为跨 Shot LocalSubject 合并 hint

某 normalized appearance 在任一同 Shot 同时出现 >=2 人
→ 该 appearance 在整个 Segment 禁止跨 Shot 合并
→ 回退到 shot-local anonymous key
```

宁可多生成匿名 LocalSubject，也不能把同镜头两个人错误合成一个人。最终人物身份仍由 Character V10.1 / 后续 P5 解决。

## 8. P2 完成边界

当前可以确认的工程事实：

```text
P2.1 Provider/raw Evidence Contract                 COMPLETE
P2.2 ASR Provider                                  COMPLETE
P2.3 OCR Observation Provider                      COMPLETE
P2.4 VLM anonymous Shot semantics                  COMPLETE
P2.5 deterministic Fusion + P1 publish             COMPLETE
P2.6 production orchestrator                       COMPLETE
P2.6 runtime preflight                             COMPLETE
P2.6 Windows runner                                COMPLETE
P2.6 acceptance report/scoring/comparison tooling  COMPLETE
```

当前**不能**伪造的事实：仓库没有真实短剧视频样本，本次开发环境也不是用户 Windows GPU 主机，因此没有执行真实 Qwen3-VL / faster-whisper / RapidOCR 全链素材验收。

所以状态必须写成：

```text
P2 IMPLEMENTATION CODE = COMPLETE
P2 REAL-VIDEO ACCEPTANCE EXECUTION = PENDING
```

一旦用户 Windows 机器对真实样本生成 `PASS` acceptance report，才能进一步写成：

```text
P2 = ACCEPTED / CLOSED
```

## 9. P2 全阶段禁止事项

P2 仍然禁止写：

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

也禁止：

```text
VLM subject_A = Character
ASR speaker = Character
剧情语义覆盖 Face hard conflict
绕过 Character V10.1 same-sample cannot-link
修改 explicit Shot Character Assignment 权威来源
把真实素材未跑过描述成“效果已验收”
```

P2 最终交给 P3 的是：**可追溯、可读取、可展示的匿名结构化 Breakdown Draft**，不是 Final 资产身份。
