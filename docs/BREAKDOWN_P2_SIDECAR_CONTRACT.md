# AI Drama Studio — Breakdown P2 Evidence Sidecar Contract

> **Status:** P2.1 + P2.2 + P2.3 IMPLEMENTED / P2 IN PROGRESS / P2.4 NEXT  
> **Contract date:** 2026-08-27  
> **Last synchronized:** 2026-08-27 21:48 +08:00  
> **Parent:** `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`  
> **P1 schema:** `breakdown-draft-v1`  
> **P2 sidecar schema:** `breakdown-p2-evidence-v1`

## 0. 目标

P2 的职责不是创建第二套拉片数据，而是把真实 ASR / OCR / VLM 原始 Evidence 送入已经完成的 P1 Breakdown Contract：

```text
Current ShotRevision
+ ShotRevisionItems / Reference Clips / keyframes
+ Episode audio
        ↓
ASR / OCR / VLM Provider Adapter
        ↓
raw Evidence sidecar（P2）
        ↓
Fusion（P2.5）
        ↓
P1 SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent / PropHint
        ↓
P1 validator
        ↓
BreakdownRun READY / READY_WITH_WARNINGS
```

核心原则：

> 原始模型 Evidence 和融合后的匿名 Draft 必须分层保存；不能只剩一段模型文案。

---

## 1. P2 阶段拆分

```text
P2.1 统一 Evidence/Provider Contract + local sidecar persistence      COMPLETE
P2.2 ASR Provider + segment/word timing                               COMPLETE
P2.3 OCR Observation Provider                                         COMPLETE
P2.4 VLM anonymous Shot semantics Provider                            NEXT
P2.5 ASR/OCR/VLM Fusion → 完整 P1 Draft → validator/publish          PLANNED
P2.6 真实短剧 benchmark + Windows acceptance + docs closure           PLANNED
```

P2.1–P2.3 完成不代表 P2 整体完成。当前完成的是 Provider/runtime/raw Evidence Contract；真实短剧上的模型效果、速度、显存和候选模型对比仍属于 P2.6 benchmark。

---

## 2. P2 Provider 输入 Contract

P2 Provider 的正式输入来自一个已经创建的 `PROCESSING BreakdownRun`。

```text
BreakdownRun
→ project_id
→ episode_id
→ source_shot_revision_id

source ShotRevision
→ exact ShotRevisionItems
→ reference_clip_path
→ thumbnail_path
→ keyframes_json
→ start_us / end_us / duration_us

Episode Preprocess
→ audio_path

Project
→ source_language
```

禁止 Provider 重新从 Current `v2_shots` 猜测历史输入。

### 2.1 Run 状态

只允许 `PROCESSING`。如果 P1.6 已把 Run 标为 `STALE`，P2 Provider 必须停止，不能继续把旧 Revision 的结果登记为活动 Evidence。

### 2.2 ShotRevision 竞态

Provider 推理可能耗时，因此至少三处保护：

```text
推理前：Run source revision == Episode Current revision
推理后写 sidecar 前：再次检查
登记 component artifact 前：再次检查
```

Revision 已变化时 fail closed。

---

## 3. Provider Contract

统一接口：

```python
class BreakdownP2Provider(Protocol):
    component: str

    def analyze(self, context: P2RunContext) -> P2ProviderResult:
        ...
```

组件：`ASR / OCR / VLM`。

业务/Fusion 层只能依赖统一 Result，具体模型 SDK / raw status / tensor 对象必须在 Adapter 内消化。

---

## 4. Provider Result Contract

`P2ProviderResult` 至少包含：

```text
component
provider
model
status
evidence[]
metadata
warnings
```

同步本地 Provider 允许状态：

```text
READY
NO_EVIDENCE
NOT_CONFIGURED
NOT_AVAILABLE
FAILED
```

规则：

```text
READY → 至少一条 Evidence
非 READY → 不携带可消费 Evidence
```

未来外部异步/计费 Provider 不允许把 submit/poll 生命周期硬塞进这些同步状态；必须先实现持久化 Job Contract。

---

## 5. 原始 Evidence Contract

统一 `P2EvidenceRecord`：

```text
source_type
source_id
source_start_us
source_end_us
shot_revision_item_id
text
language
confidence
payload
```

正式 source type：

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

### 5.1 组件允许的 Evidence

```text
ASR → ASR_SEGMENT / ASR_WORD / AUDIO_RANGE / RULE
OCR → OCR_OBSERVATION / FRAME / RULE
VLM → VLM_OUTPUT / FRAME / AUDIO_RANGE / RULE
```

### 5.2 时间

正式时间为 integer microseconds。

如果 Evidence 已绑定 `shot_revision_item_id`，`source_start_us/source_end_us` 必须完全落入该 `ShotRevisionItem`。

ASR 的 segment/word 在 P2.2 统一保留 Episode source 绝对时间并保持 `shot_revision_item_id = NULL`。原因是对白可能跨镜头切点；P2.5 Fusion 才按 source time 和 exact ShotRevisionItem 边界切成 Shot-relative TimelineEvent。

P2.3 OCR Observation 相反：每一条观测来自某个 exact historical Reference Clip 的某一采样帧，因此必须立即绑定该 `ShotRevisionItem`。OCR 的 `source_start_us` 是采样帧目标位置恢复到 Episode source 的绝对时间；当前用 `source_end_us = source_start_us + 1µs` 表示**点观测**，它不是字幕持续区间。字幕/路牌等文字在多帧上的持续时间只允许 P2.5 Fusion 基于重复 Evidence 推断。

### 5.3 Confidence

```text
0 <= confidence <= 1
或 NULL
```

`ASR_WORD.confidence` 可保存 provider word probability；`OCR_OBSERVATION.confidence` 保存 OCR recognition score。Provider diagnostics 保留在 payload/metadata，不伪造成统一置信度。

### 5.4 匿名边界

P2 raw Evidence 不允许业务 Final ID：

```text
character_id
scene_id
prop_id
asset_revision_id
speaker_character_id
shot_character_binding_id
shot_scene_binding_id
shot_prop_binding_id
```

即使 VLM、OCR 文本或后续 Speaker 模型声称识别出了某身份/资产，P2 也只能保存匿名语义/文本，不能越级变成 Final identity/asset truth。

---

## 6. Raw Evidence sidecar 文件 Contract

P2 不新增一套平行数据库 Evidence 表。原始 Provider 输出保存为 workspace sidecar：

```text
workspace/
└─ <project_id>/
   └─ episodes/
      └─ <episode_id>/
         └─ breakdown/
            └─ <run_id>/
               └─ evidence/
                  ├─ asr/<sha256-fingerprint>.json
                  ├─ ocr/<sha256-fingerprint>.json
                  └─ vlm/<sha256-fingerprint>.json
```

Fingerprint 基于标准化 JSON 内容计算 SHA-256；相同标准化结果复用相同 artifact path，不同结果生成新 artifact，不覆盖历史。写入必须 `.tmp → os.replace → final`。

`BreakdownRun.component_status_json` 只保存快速状态/provenance 摘要，不复制全部模型输出。

---

## 7. BreakdownRun metadata

成功固化 Provider Result 后，P2 可在仍是 PROCESSING 的 Run 内合并：

```text
component_status_json[ASR/OCR/VLM]
→ status / provider / model / artifact_uri / fingerprint / evidence_count / warnings

provider_metadata_json.p2_sidecar[ASR/OCR/VLM]
→ provider/model/non-secret metadata
```

P2.2 ASR metadata 可记录 device/compute/language/duration/segment/word counts。

P2.3 OCR metadata 当前可记录：

```text
engine = onnxruntime
ocr_version = PP-OCRv6
model_type = small|medium
recognition_language
device_requested / device
sample_interval_us
max_frames_per_shot
text_score
shot_count / available_reference_clip_count / missing_reference_clip_count
frames_requested / frames_decoded / frames_analyzed
shot_decode_failures / frame_ocr_failures
observation_count
```

错误 metadata 只记录非敏感 error type/状态，不把 API secret 或不受控异常正文写入 provenance。

---

## 8. P1 `BreakdownEvidenceLink` 的使用时机

`v2_breakdown_evidence_links` 是：

```text
Draft owner → raw Evidence/artifact
```

P2.1–P2.4 Provider 层还没有生成最终 Draft owner，因此不伪造 Run-level owner。P2.5 Fusion 创建 `SHOT_DRAFT / LOCAL_SUBJECT / TIMELINE_EVENT / SCENE_SEGMENT / PROP_HINT` 后，再为实际消费过的 raw Evidence 创建 `BreakdownEvidenceLink`。

---

## 9. 与旧 F05 ASR/Speaker helper 的关系

历史 `content_analysis_v2.py` 仍保留 `_run_asr / _run_diarization / _attach_speakers / _map_speaker_to_character` 兼容逻辑，但不是 P2 正式 Contract。

P2.2 正式 ASR 入口：

```text
breakdown_p2_asr_v1.py
→ FasterWhisperASRProvider
→ P2ProviderResult
→ P2.1 run_local_provider()
→ immutable ASR sidecar
```

它不写 `studio_v2.Dialogue`，也不执行 speaker→Character。

---

## 10. P2.2 ASR Provider Contract

正式实现：

```text
provider: faster-whisper
pinned package: faster-whisper==1.2.1
default model: large-v3
formal module: engine/app/breakdown_p2_asr_v1.py
```

配置：

```text
AI_DRAMA_P2_ASR_MODEL
AI_DRAMA_P2_ASR_DEVICE        # auto / cpu / cuda
AI_DRAMA_P2_ASR_COMPUTE_TYPE
AI_DRAMA_P2_ASR_MODEL_CACHE
```

默认：`beam_size=5 / vad_filter=true / word_timestamps=true`。

输出 `ASR_SEGMENT + ASR_WORD`，均保存 Episode source integer microseconds。`device=auto` 可以在自动选择 CUDA 后加载失败时显式 warning 并降级 CPU；显式 `device=cuda` 失败必须 FAILED，不静默降级。缺音频为 NOT_AVAILABLE，无可用语音为 NO_EVIDENCE。

`faster-whisper large-v3` 是当前正式基线，不是永久锁死的效果冠军；Qwen3-ASR + ForcedAligner 等保持 P2.6 benchmark 候选。

---

## 11. P2.3 OCR Observation Provider Contract

### 11.1 正式实现

```text
provider: rapidocr
pinned package: rapidocr==3.9.2
OCR version: PP-OCRv6
formal module: engine/app/breakdown_p2_ocr_v1.py
default model type: small
default engine: ONNX Runtime
default device: cpu
```

不引入 PaddlePaddle 作为 P2.3 必需运行时；当前复用项目已有 OpenCV 与 ONNX Runtime 路线。

配置：

```text
AI_DRAMA_P2_OCR_MODEL_TYPE             # small / medium
AI_DRAMA_P2_OCR_DEVICE                 # cpu / auto / cuda
AI_DRAMA_P2_OCR_SAMPLE_INTERVAL_US
AI_DRAMA_P2_OCR_MAX_FRAMES_PER_SHOT
AI_DRAMA_P2_OCR_TEXT_SCORE
AI_DRAMA_P2_OCR_MODEL_CACHE
```

默认：

```text
sample_interval_us = 500000
max_frames_per_shot = 12
text_score = 0.5
```

### 11.2 输入与多帧采样

P2.3 不只扫 Shot 中间缩略图。它对 Run 冻结的每个 exact historical `ShotRevisionItem.reference_clip_path` 生成确定性采样时间，覆盖整个 Shot，同时受 `max_frames_per_shot` 上限保护。

```text
ShotRevisionItem
→ historical Reference Clip
→ deterministic relative timestamps
→ decode frame
→ RapidOCR
```

默认 frame decoder 使用 OpenCV 并在运行时懒加载；测试可注入 frame sampler，因此 lightweight CI 不需要下载 OCR 模型或安装完整视觉运行时。

### 11.3 OCR Evidence

每条有效文字生成：

```text
OCR_OBSERVATION
source_start_us / source_end_us       # 1µs point observation
shot_revision_item_id                 # exact historical item, REQUIRED
text
language
confidence                            # recognition score
payload:
  shot_ordinal
  frame_sample_index
  frame_relative_us
  image_width / image_height
  polygon_px
  bbox_px
  polygon_norm
  recognition_language
```

OCR 层**不做跨帧字幕去重/拼接**。同一字幕在连续采样帧出现时保留为多条 raw Observation；P2.5 Fusion 再依据文本、几何和时间推断持续区间或合并事件。

### 11.4 语言与设备

项目 `source_language` 会映射到 PP-OCRv6 recognition profile：简中→`ch`，繁中/粤语→`chinese_cht`，日语→`japan`，韩语→`korean`，其余按 latin/cyrillic/devanagari 等 profile 选择。

设备策略：

```text
default cpu → 稳定优先
auto → ONNX Runtime 检测 CUDAExecutionProvider
只有 auto-selected CUDA 初始化失败时允许 visible CPU fallback
显式 cuda 不可用/初始化失败 → FAILED，不静默降级
```

### 11.5 状态

```text
无任何历史 Reference Clip → NOT_AVAILABLE
RapidOCR/OpenCV runtime 缺失 → NOT_AVAILABLE
引擎初始化失败 → FAILED
部分 Shot/frame 解码或 OCR 失败 → warning，继续其他 Evidence
所有帧都无法实际分析 → FAILED
帧可分析但无文字 → NO_EVIDENCE
有有效 OCR Observation → READY
```

P2.3 不创建 TimelineEvent，不把 OCR 文本直接物化 Scene/Prop，不写任何 Final Asset/Binding。

---

## 12. P2.4+ Provider 选择规则

每个 Provider 至少评估：

```text
真实短剧准确率/可读性
中文/多语言能力
word/box/structured timing 或坐标能力
Windows 支持
CPU/GPU fallback
显存/速度
模型下载与离线缓存
权重/代码商业授权
Provider 可替换性
```

P2.2–P2.4 必须各自有 focused tests；P2.6 再做真实素材 benchmark。P2.3 的 RapidOCR/PP-OCRv6 small、500ms 采样和 CPU 默认是当前稳定基线，不等于已经证明是真实短剧最佳组合。

---

## 13. P2 全阶段禁止写

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
AssetRevision
```

也禁止修改 Character V10.1 identity thresholds、same-sample cannot-link、Face hard conflict、explicit Shot Character Assignment、Final Character Gate。

---

## 14. Stable Gate

### P2.1 已满足

```text
[x] exact ShotRevision Provider context
[x] unified Provider/Result/Evidence Contract
[x] raw Evidence validation + Final ID leakage fail closed
[x] fingerprinted atomic sidecar
[x] STALE race protection
[x] Windows P2 sidecar focused suite 18/18 PASS
```

### P2.2 已满足

```text
[x] faster-whisper Provider + segment/word timing
[x] cross-shot ASR remains unbound until Fusion
[x] auto CUDA fallback visible; explicit CUDA fail closed
[x] no Dialogue/Final write
[x] 6 ASR focused tests
[x] Windows P2 provider suite 24/24 PASS
[x] Ubuntu full pytest 28 failed, 230 passed, 1 skipped；历史失败类别未新增
```

### P2.3 已满足

```text
[x] RapidOCR 3.9.2 + PP-OCRv6 small formal Provider
[x] exact historical Reference Clip multi-frame sampling
[x] deterministic whole-Shot sampling with max frame cap
[x] OCR source time → Episode integer microseconds
[x] every OCR Observation binds exact ShotRevisionItem
[x] polygon/bbox/normalized geometry + recognition confidence provenance
[x] repeated text remains raw observations; no early subtitle-duration inference
[x] default CPU + configurable auto/cuda
[x] auto CUDA→CPU fallback visible; explicit CUDA fail closed
[x] missing clips/runtime/no-text/all-frame-failure statuses fail closed
[x] sidecar + BreakdownRun provenance reuse P2.1
[x] no TimelineEvent / Character / Scene / Prop / Final Binding write
[x] 7 OCR focused tests
[x] Windows Breakdown P2 provider suite 31/31 PASS
[x] Windows Breakdown P1 regression gate PASS
[x] Ubuntu full pytest = 28 failed, 237 passed, 1 skipped；历史 28 失败类别未新增
```

P2.3 已关闭。下一步唯一是 **P2.4：VLM anonymous Shot semantics Provider**。真实 OCR 模型大小、采样间隔、CPU/GPU 质量/速度 benchmark 仍留到 P2.6。