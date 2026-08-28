# AI Drama Studio — Breakdown P2 Evidence Sidecar + Fusion Contract

> **Status:** P2.1 + P2.2 + P2.3 + P2.4 + P2.5 IMPLEMENTED / P2 IN PROGRESS / P2.6 NEXT  
> **Contract date:** 2026-08-27  
> **Last synchronized:** 2026-08-28  
> **Parent:** `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`  
> **P1 schema:** `breakdown-draft-v1`  
> **P2 sidecar schema:** `breakdown-p2-evidence-v1`

## 0. 目标

P2 不创建第二套拉片数据，而是把真实 ASR / OCR / VLM 原始 Evidence 送入已经完成的 P1 Breakdown Contract：

```text
Current ShotRevision
+ ShotRevisionItems / Reference Clips / keyframes
+ Episode audio
        ↓
ASR / OCR / VLM Provider Adapter
        ↓
raw Evidence sidecar（P2.1-P2.4）
        ↓
deterministic Fusion（P2.5）
        ↓
P1 SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent / PropHint
        ↓
BreakdownEvidenceLink provenance
        ↓
P1 validator
        ↓
BreakdownRun READY / READY_WITH_WARNINGS
```

核心原则：

> 原始模型 Evidence 和融合后的匿名 Draft 必须分层保存；不能只剩一段模型文案。

P2.5 完成后，ASR/OCR/VLM raw Evidence 已能自动融合为完整匿名 P1 Draft。P2 仍未整体关闭，因为 P2.6 还要验证真实短剧效果、模型组合、Windows/local GPU 和运行成本。

---

## 1. P2 阶段拆分

```text
P2.1 统一 Evidence/Provider Contract + local sidecar persistence      COMPLETE
P2.2 ASR Provider + segment/word timing                               COMPLETE
P2.3 OCR Observation Provider                                         COMPLETE
P2.4 VLM anonymous Shot semantics Provider                            COMPLETE
P2.5 ASR/OCR/VLM Fusion → 完整 P1 Draft → validator/publish          COMPLETE
P2.6 真实短剧 benchmark + Windows/local-model acceptance + closure    NEXT
```

P2.1–P2.5 完成不代表“当前模型组合已经是效果冠军”。真实素材准确率、速度、显存和候选模型对比仍属于 P2.6。

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

只允许 `PROCESSING`。如果 P1.6 已把 Run 标为 `STALE`，P2 Provider/Fusion 必须停止，不能继续把旧 Revision 的结果登记或发布成活动 Draft。

### 2.2 ShotRevision 竞态

Provider 推理可能耗时，因此至少三处保护：

```text
推理前：Run source revision == Episode Current revision
推理后写 sidecar 前：再次检查
登记 component artifact 前：再次检查
```

P2.5 也必须在：

```text
读取 sidecar 前
写 Draft rows 前
validator/publish 前
```

确认 Run 仍绑定 Current Revision。Revision 已变化时 fail closed。

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

`P2ProviderResult`：

```text
component
provider
model
status
evidence[]
metadata
warnings
```

同步本地 Provider 状态：

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

#### ASR

P2.2 的 segment/word 保留 Episode source 绝对时间并保持 `shot_revision_item_id = NULL`。对白可能跨镜头切点；P2.5 才按 exact ShotRevisionItem source interval 拆成 Shot 内 `TimelineEvent`。

#### OCR

P2.3 `OCR_OBSERVATION` 绑定 exact historical `ShotRevisionItem`。`source_start_us` 是采样帧恢复到 Episode source 的绝对时间，`source_end_us = source_start_us + 1µs` 表示**点观测**，不是字幕持续区间。

P2.5 基于同 Shot 内连续重复 Evidence、normalized text、时间间隔和 geometry compatibility 做保守 stitching/duration inference；推断出的 duration 不能越 Shot 边界。

#### VLM

P2.4 每个可用 Shot 最多一个主 `VLM_OUTPUT`：

```text
source_start_us = ShotRevisionItem.start_us
source_end_us   = ShotRevisionItem.end_us
shot_revision_item_id = exact historical item
```

`events[].start_ratio / end_ratio` 只是该 Shot 内 normalized hint。P2.5 用对应 Shot source interval 映射为正式 integer microseconds。

### 5.3 Confidence

```text
0 <= confidence <= 1
或 NULL
```

- `ASR_WORD.confidence` 可保存 provider word probability；
- `OCR_OBSERVATION.confidence` 保存 OCR recognition score；
- `VLM_OUTPUT.confidence = NULL`。

生成式 VLM 不被伪装成统一校准概率：

```text
metadata.confidence_policy = provider-output-unscored
```

P2.5 不得人为伪造统一 VLM probability。

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

P2.4 先执行严格白名单 normalization，P2.1 再递归检查 Final-ID leakage。

P2.5 只写匿名 P1 Draft，不会把 VLM/ASR/OCR 内容升级成 Final identity/asset truth。

---

## 6. Raw Evidence sidecar 文件 Contract

P2 不新增平行数据库 Evidence 表。原始 Provider 输出保存为 workspace sidecar：

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

P2.5 必须读取 Run 已登记的 immutable sidecar，不能为了 Fusion 悄悄重新跑模型并产生不可追溯的新事实。

### 6.1 P2.5 sidecar 验证

每个 component 在消费前必须验证：

```text
artifact_uri 是本地 file://
artifact 文件存在
sha256(serialized JSON) == Run 登记 fingerprint
schema_version == breakdown-p2-evidence-v1
run_id / project_id / episode_id / source_shot_revision_id / component 匹配
status / provider / model / evidence_count 与 Run component provenance 匹配
P2 ProviderResult Contract 再次通过 validate_provider_result()
```

任一不匹配 fail closed。

---

## 7. BreakdownRun metadata

Provider sidecar 完成后：

```text
component_status_json[ASR/OCR/VLM]
→ status / provider / model / artifact_uri / fingerprint / evidence_count / warnings

provider_metadata_json.p2_sidecar[ASR/OCR/VLM]
→ provider/model/non-secret metadata
```

P2.5 完成后增加：

```text
component_status_json[FUSION]
→ READY | READY_WITH_WARNINGS
→ profile / version / warnings / generated_counts

provider_metadata_json.p2_fusion
→ deterministic Fusion policies/version
```

### 7.1 ASR metadata

可记录：device / compute / language / duration / segment / word counts。

### 7.2 OCR metadata

可记录：

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

### 7.3 VLM metadata

可记录：

```text
semantic_schema = breakdown-p2-vlm-shot-semantics-v1
model_family = Qwen3-VL
device_requested
video_fps
max_new_tokens
max_pixels
shot_count
available_reference_clip_count
missing_reference_clip_count
shots_analyzed
semantic_output_count
shot_failure_count
confidence_policy = provider-output-unscored
source_language
runtime_isolated = true
```

错误 metadata 只记录非敏感 error type/状态，不把 API secret、模型异常正文、stdout/stderr 或不受控原文写入 provenance。

---

## 8. P1 `BreakdownEvidenceLink`

`v2_breakdown_evidence_links`：

```text
Draft owner → raw Evidence/artifact
```

P2.1–P2.4 Provider 层没有最终 Draft owner，因此不伪造 Run-level owner。

P2.5 创建真实 Draft owner：

```text
SCENE_SEGMENT
SHOT_DRAFT
LOCAL_SUBJECT
TIMELINE_EVENT
PROP_HINT
```

之后只为**实际消费过的** raw Evidence 创建 `BreakdownEvidenceLink`。

禁止把所有 sidecar Evidence 无差别链接到所有 Draft owner。

---

## 9. 与旧 F05 ASR/Speaker helper 的关系

历史 `content_analysis_v2.py` 仍保留 `_run_asr / _run_diarization / _attach_speakers / _map_speaker_to_character` 兼容逻辑，但不是 P2 正式 Contract。

P2.2 正式 ASR：

```text
breakdown_p2_asr_v1.py
→ FasterWhisperASRProvider
→ P2ProviderResult
→ P2.1 run_local_provider()
→ immutable ASR sidecar
```

它不写 `studio_v2.Dialogue`，也不执行 speaker→Character。

P2.4 VLM 的视觉 `speaking_state` 也不能替代 diarization / active-speaker Evidence，更不能直接写 Character。

---

## 10. P2.2 ASR Provider Contract

```text
provider: faster-whisper
pinned package: faster-whisper==1.2.1
default model: large-v3
formal module: engine/app/breakdown_p2_asr_v1.py
beam_size = 5
vad_filter = true
word_timestamps = true
```

配置：

```text
AI_DRAMA_P2_ASR_MODEL
AI_DRAMA_P2_ASR_DEVICE        # auto / cpu / cuda
AI_DRAMA_P2_ASR_COMPUTE_TYPE
AI_DRAMA_P2_ASR_MODEL_CACHE
```

`device=auto` 可在自动选择 CUDA 后加载失败时显式 warning 并降级 CPU；显式 `device=cuda` 失败必须 FAILED。缺音频为 NOT_AVAILABLE，无可用语音为 NO_EVIDENCE。

`large-v3` 是当前正式基线，不是永久效果冠军；其它候选留给 P2.6。

---

## 11. P2.3 OCR Observation Provider Contract

```text
provider: rapidocr
pinned package: rapidocr==3.9.2
OCR version: PP-OCRv6
formal module: engine/app/breakdown_p2_ocr_v1.py
default model type: small
default engine: ONNX Runtime
default device: cpu
```

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

P2.3 对每个 exact historical `ShotRevisionItem.reference_clip_path` 做 deterministic whole-Shot sampling，而不是只扫中间缩略图。

每条有效文字：

```text
OCR_OBSERVATION
source_start_us / source_end_us       # 1µs point observation
shot_revision_item_id                 # exact historical item
text
language
confidence
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

OCR 层不做跨帧字幕去重/拼接。

状态：

```text
default cpu
auto-selected CUDA 初始化失败 → visible CPU fallback
显式 cuda 不可用/初始化失败 → FAILED
无任何历史 Reference Clip → NOT_AVAILABLE
所有帧都无法实际分析 → FAILED
帧可分析但无文字 → NO_EVIDENCE
有有效 OCR Observation → READY
```

P2.3 不创建 TimelineEvent，不把 OCR 文本直接物化 Scene/Prop，不写 Final Asset/Binding。

---

## 12. P2.4 VLM anonymous Shot semantics Provider Contract

```text
provider: qwen3-vl
model: Qwen/Qwen3-VL-4B-Instruct
semantic schema: breakdown-p2-vlm-shot-semantics-v1
formal module: engine/app/breakdown_p2_vlm_v1.py
isolated runner: scripts/run_breakdown_vlm_qwen3.py
setup: scripts/setup_breakdown_vlm_runtime.ps1
default device: cuda
video fps request: 2.0
max_new_tokens: 1536
max_pixels: 524288
```

配置：

```text
AI_DRAMA_P2_VLM_MODEL
AI_DRAMA_P2_VLM_MODEL_PATH
AI_DRAMA_P2_VLM_PYTHON
AI_DRAMA_P2_VLM_RUNNER
AI_DRAMA_P2_VLM_DEVICE             # auto / cpu / cuda
AI_DRAMA_P2_VLM_FPS
AI_DRAMA_P2_VLM_MAX_NEW_TOKENS
AI_DRAMA_P2_VLM_MAX_PIXELS
AI_DRAMA_P2_VLM_FFMPEG_BIN
```

### 12.1 Runtime 隔离

```text
engine/app/breakdown_p2_vlm_v1.py
→ subprocess
→ .runtime/TransVLM/inference/.venv Python 3.12
→ scripts/run_breakdown_vlm_qwen3.py
→ .runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

只复用 TransVLM 的隔离 Python/CUDA 环境，**不复用**转场任务 checkpoint `HeyGenAI/TransVLM-Qwen3-VL-4B-Instruct` 做内容语义。

P2.4 使用独立 base `Qwen/Qwen3-VL-4B-Instruct`。模型下载只在 setup 阶段发生；正式推理默认 offline。

### 12.2 输入/执行

```text
PROCESSING BreakdownRun
→ exact source ShotRevision
→ exact historical ShotRevisionItems
→ existing historical Reference Clips
→ one isolated runner
→ model loads once
→ sequential Shot inference
```

### 12.3 Prompt 分工

VLM 只分析视觉可支持内容：

```text
场景 hint
镜头 summary / visual description
shot type / camera motion / composition hint
匿名 subject_A / subject_B ...
人物外观/动作/屏幕位置/可见性
视觉 speaking_state hint
VISUAL / ACTION event
剧情关键 prop hint
```

明确不要求：对白/字幕/路牌/手机/文档 transcription、真实人物姓名/全局身份、Final Character/Scene/Prop。

### 12.4 VLM_OUTPUT 白名单

```text
VLM_OUTPUT
source_start_us = historical Shot start
source_end_us   = historical Shot end
shot_revision_item_id = exact historical item
text = normalized shot summary 或 NULL
language = project source language
confidence = NULL
payload:
  shot_ordinal
  semantic:
    schema_version
    scene
    shot
    subjects[]
    events[]
    props[]
```

白名单：

```text
scene:
  location_hint
  interior_exterior = INT|EXT|MIXED|UNKNOWN
  time_of_day
  environment_description

shot:
  summary
  visual_description
  shot_type_hint
  camera_motion_hint
  narrative_function_hint
  composition_hint

subjects[]:
  label = subject_*
  appearance_summary
  activity_summary
  screen_position
  visibility = FULL|PARTIAL|OCCLUDED|UNKNOWN
  speaking_state = LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN

events[]:
  event_type = VISUAL|ACTION
  start_ratio / end_ratio in 0..1
  content
  subject_labels[] limited to declared anonymous subjects

props[]:
  label
  importance = LOW|MEDIUM|HIGH
  narrative_reason
  subject_labels[] limited to declared anonymous subjects
```

未知模型字段在 Adapter 边界丢弃。P2.1 recursive Final-ID validation 是第二重保护。

### 12.5 状态

```text
没有历史 Reference Clip → NOT_AVAILABLE
隔离 Python/runner/checkpoint 缺失 → NOT_AVAILABLE
runner/subprocess 整体失败 → FAILED
部分 Shot 失败 + 仍有合法 semantics → READY + warnings
全部 Shot 输出失败/不可用 → FAILED
有至少一个合法 VLM_OUTPUT → READY
```

P2.4 不创建 P1 Draft rows / Final Asset / Final Bindings。

---

## 13. P2.5 Fusion Contract — IMPLEMENTED

正式实现：

```text
engine/app/breakdown_p2_fusion_v1.py
engine/tests/v2/test_breakdown_p2_fusion_v1.py
profile = breakdown-p2-fusion-v1
```

### 13.1 输入与组件门槛

```text
BreakdownRun component provenance
→ load ASR/OCR/VLM immutable sidecars
→ verify file/fingerprint/schema/component/run/source revision/provider metadata
```

组件状态：

```text
VLM READY = required
VLM non-READY = hard fail
ASR/OCR READY = consume
ASR/OCR NO_EVIDENCE / NOT_AVAILABLE = allowed with warnings
FAILED / NOT_CONFIGURED = hard fail
```

### 13.2 SceneSegmentDraft

Scene Segment 只能由连续历史 Shot 组成。

相邻 Shot 只有在以下 normalized signature 完全一致时才合并：

```text
location_hint
interior_exterior
time_of_day
```

缺少 location 时保守切新 Segment，避免无依据地把不同场景粘在一起。

### 13.3 ShotSemanticDraft

每个 source `ShotRevisionItem` 必须恰好一个 `ShotSemanticDraft`：

```text
source_shot_revision_item_id = exact historical item
source_shot_id_snapshot      = item.original_shot_id
shot_ordinal_snapshot        = item.ordinal
source_start_us/end_us       = exact item interval
```

缺少某 Shot VLM_OUTPUT 时仍保守生成该 ShotDraft，并把缺失写入 warning/metadata，保证 P1 cardinality/coverage Contract。

### 13.4 LocalSubject + same-Shot cannot-link

LocalSubject 只在 Scene Segment 内有效，不是 Character。

正常弱连续性：

```text
exact normalized appearance_summary
→ 可作为同一 Segment 内跨 Shot 的 anonymous continuity key
```

硬保护：

```text
如果某 appearance signature 在任一同一个 Shot 内同时出现在 2+ 个 subject：
→ 该 appearance 在整个 Segment 内不得继续作为跨 Shot merge key
→ 相关 occurrence 使用 shot-local key
→ 同 Shot 两个人必须生成不同 LocalSubject / ShotLocalSubject
```

这条规则防止“两个都穿黑衣的年轻女性”被语义层误合并。它只是 Draft cannot-link，不创建/确认 Character identity。

VLM `subject_A / subject_B` 只用于同 Shot 语义引用，不作为跨 Shot 全局 ID。

### 13.5 VLM TimelineEvent

只消费 `VISUAL / ACTION`：

```text
source_start = Shot.start + duration * start_ratio
source_end   = Shot.start + duration * end_ratio
```

结果 clamp 在对应 Shot 内，并同时写严格一致的 shot-relative time。

### 13.6 ASR TimelineEvent

`ASR_SEGMENT` 与每个 exact historical Shot 求时间交集。

若有 `ASR_WORD`：

```text
只取与当前 Shot 相交的 word
→ 用 word source timing 决定事件 start/end
→ 优先用 raw_word/word text 重建本 Shot dialogue text
```

若跨 Shot segment 没有可用 word timing，只能把 segment text 作为 warning-visible fallback，不能假装精确切词。

### 13.7 OCR TimelineEvent

P2.5 按同 Shot 内：

```text
normalized text
+ temporal gap
+ normalized bbox IoU / center distance compatibility
```

做 conservative cluster。

单帧仍是 point observation；连续重复 Observation 才推断持续区间。所有 duration clamp 在 Shot 内。

### 13.8 DraftPropHint

VLM plot-relevant prop hint → Segment-scoped `DraftPropHint` + per-Shot `DraftPropOccurrence`。

同 Segment 相同 normalized label 可聚合为一个 hint；importance 保留更高等级。仍不是 Final Prop。

### 13.9 EvidenceLink

Fusion 创建实际 Draft owner 后，再精确链接消费过的：

```text
VLM_OUTPUT
ASR_SEGMENT / ASR_WORD
OCR_OBSERVATION
```

`source_id + source_uri` 保留到 immutable sidecar provenance。

### 13.10 生命周期/失败

完整 Draft graph 写入后调用真实 P1 validator/publish。

```text
validator pass → READY / READY_WITH_WARNINGS
validator hard fail → FAILED
source revision stale → refuse publish / preserve STALE truth
Fusion exception while still PROCESSING → safe fail Run
older Current READY Run never被失败新 Run 替换
```

P2.5 仍禁止写 Final Character/Scene/Prop/AssetRevision/Final Shot Bindings，也不修改 Character V10.1 硬 Gate。

---

## 14. Provider 选择 / P2.6 benchmark 规则

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

P2.6 至少比较：

```text
ASR:
  dialogue recall/error
  word timing
  cross-cut behavior
  large-v3 vs viable alternatives

OCR:
  subtitle recall/precision
  phone/sign/small text
  PP-OCRv6 small vs medium
  sampling interval
  CPU/GPU

VLM:
  subject/action/scene/plot-relevant prop semantics
  anonymous-subject consistency within Shot
  2fps/max_pixels sensitivity
  VRAM/speed
  short/long Shot behavior
  Windows/local GPU stability
  Qwen3-VL-4B vs viable licensed alternatives if needed

Fusion:
  final anonymous Breakdown completeness
  event timing
  OCR dedupe
  same-Shot subject cannot-link
  conflict handling
  provenance correctness
```

Contract/fake-engine/fake-runner tests不等于真实短剧效果冠军证明。

---

## 15. P2 全阶段禁止写

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

## 16. Stable Gate

### P2.1 已满足

```text
[x] exact ShotRevision Provider context
[x] unified Provider/Result/Evidence Contract
[x] raw Evidence validation + Final ID leakage fail closed
[x] fingerprinted atomic sidecar
[x] STALE race protection
```

### P2.2 已满足

```text
[x] faster-whisper Provider + segment/word timing
[x] cross-shot ASR remains unbound until Fusion
[x] auto CUDA fallback visible; explicit CUDA fail closed
[x] no Dialogue/Final write
[x] focused tests exist
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
[x] no TimelineEvent / Character / Scene / Prop / Final Binding write
[x] focused tests exist
```

### P2.4 已满足

```text
[x] independent Qwen3VLSemanticProvider through P2.1 Contract
[x] separate base Qwen/Qwen3-VL-4B-Instruct content-semantic checkpoint
[x] isolated Python 3.12/CUDA runtime; main Python 3.11 dependency boundary preserved
[x] exact historical Reference Clip input / exact ShotRevisionItem output anchor
[x] sequential model use; one model load per runner process
[x] strict anonymous semantic JSON whitelist
[x] ASR/OCR responsibility separation
[x] VLM_OUTPUT uses full historical Shot source interval
[x] event ratios remain hints for P2.5, not fake absolute timing
[x] provider-output-unscored / confidence NULL
[x] unknown model keys and attempted business IDs do not persist
[x] no P1 Draft rows / Final Asset / Final Binding write
[x] 6 VLM focused tests
```

### P2.5 已满足

```text
[x] immutable registered ASR/OCR/VLM sidecars only; no implicit rerun
[x] fingerprint/schema/run/revision/component/provider provenance validation
[x] VLM READY hard requirement; ASR/OCR degraded warning policy
[x] exact consecutive SceneSegment generation
[x] exactly one ShotSemanticDraft per source ShotRevisionItem
[x] Segment-scoped anonymous LocalSubject
[x] same-Shot identical-appearance subject cannot-link
[x] VLM ratio → exact Shot source/relative time
[x] ASR cross-Shot split with word-timing preference
[x] OCR text/time/geometry stitching without crossing Shot boundary
[x] DraftPropHint + occurrence
[x] precise BreakdownEvidenceLink provenance
[x] real P1 validator + publish lifecycle reused
[x] no Final Asset/Binding write
[x] focused test suite exists
```

P2.5 初始 hosted run 在 `942f9f524d0ccd1f11c911d60b9b148b18d9396d` 为 5/6 focused pass；唯一新失败是 same-Shot identical appearance merge。修复链结束于 `b59309d305a15dfa80e9a6af0f961f93fcac5bf9`，并做了本地纯逻辑验证。按用户要求，因 GitHub Actions 无可用额度，修复后**没有主动重跑 hosted CI**，因此不能宣称新的 hosted 6/6。

P2.1–P2.5 已关闭。下一步唯一安全子阶段是 **P2.6：真实短剧 / real-model benchmark + Windows/local runtime closure**。