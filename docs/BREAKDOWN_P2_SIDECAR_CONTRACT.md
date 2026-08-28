# AI Drama Studio — Breakdown P2 Evidence Sidecar Contract

> **Status:** P2.1 + P2.2 + P2.3 + P2.4 IMPLEMENTED / P2 IN PROGRESS / P2.5 NEXT  
> **Contract date:** 2026-08-27  
> **Last synchronized:** 2026-08-28 09:22 +08:00  
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

P2.4 完成后，ASR/OCR/VLM 三种 raw Evidence producer 已齐，但 **P2.5 Fusion 尚未实现**，因此完整匿名 Breakdown Draft 仍未自动生成。

---

## 1. P2 阶段拆分

```text
P2.1 统一 Evidence/Provider Contract + local sidecar persistence      COMPLETE
P2.2 ASR Provider + segment/word timing                               COMPLETE
P2.3 OCR Observation Provider                                         COMPLETE
P2.4 VLM anonymous Shot semantics Provider                            COMPLETE
P2.5 ASR/OCR/VLM Fusion → 完整 P1 Draft → validator/publish          NEXT
P2.6 真实短剧 benchmark + Windows acceptance + docs closure           PLANNED
```

P2.1–P2.4 完成不代表 P2 整体完成。当前完成的是 Provider/runtime/raw Evidence Contract；真实短剧上的模型效果、速度、显存和候选模型对比仍属于 P2.6 benchmark。

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

P2.5 读取 sidecar、写 Draft rows、validator/publish 前同样必须确认 Run 仍绑定 Current Revision。

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

#### ASR 时间

ASR 的 segment/word 在 P2.2 统一保留 Episode source 绝对时间并保持 `shot_revision_item_id = NULL`。原因是对白可能跨镜头切点；P2.5 Fusion 才按 source time 和 exact ShotRevisionItem 边界切成 Shot-relative TimelineEvent。

#### OCR 时间

P2.3 OCR Observation 来自 exact historical Reference Clip 的具体采样帧，因此立即绑定该 `ShotRevisionItem`。`source_start_us` 是采样帧目标位置恢复到 Episode source 的绝对时间；`source_end_us = source_start_us + 1µs` 表示**点观测**，不是字幕持续区间。

字幕/路牌等文字的持续时间只允许 P2.5 Fusion 基于连续重复 Evidence、文本与几何关系推断。

#### VLM 时间

P2.4 每个可用 Shot 最多生成一个主 `VLM_OUTPUT`，立即绑定 exact historical `ShotRevisionItem`：

```text
source_start_us = ShotRevisionItem.start_us
source_end_us   = ShotRevisionItem.end_us
```

这是“该语义输出解释整个 Reference Clip / Shot”的范围，不代表内部所有动作都持续整个 Shot。

VLM 内部 `events[].start_ratio / end_ratio` 只是相对该 Shot 的 normalized hint。只有 P2.5 Fusion 可以把 ratio 映射回正式 source integer microseconds，并根据其它 Evidence 决定最终 TimelineEvent 时间。

### 5.3 Confidence

```text
0 <= confidence <= 1
或 NULL
```

- `ASR_WORD.confidence` 可保存 provider word probability；
- `OCR_OBSERVATION.confidence` 保存 OCR recognition score；
- P2.4 `VLM_OUTPUT.confidence = NULL`。

原因：生成式 VLM 文本没有被当作经过校准的统一概率。P2.4 metadata 显式保存：

```text
confidence_policy = provider-output-unscored
```

P2.5 不得为了方便人为伪造统一 VLM probability。

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

即使 VLM、OCR 文本或未来 Speaker 模型声称识别出了某身份/资产，P2 也只能保存匿名语义/文本，不能越级变成 Final identity/asset truth。

P2.4 除依赖 P2.1 的递归 Final-ID guard 外，还先执行**严格白名单 normalization**：模型返回的未知键不会原样进入 sidecar。

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

P2.5 默认必须读取 Run 已登记的 immutable sidecar，不能为了 Fusion 悄悄重新跑模型并产生不可追溯的新事实。

---

## 7. BreakdownRun metadata

成功固化 Provider Result 后，P2 可在仍是 PROCESSING 的 Run 内合并：

```text
component_status_json[ASR/OCR/VLM]
→ status / provider / model / artifact_uri / fingerprint / evidence_count / warnings

provider_metadata_json.p2_sidecar[ASR/OCR/VLM]
→ provider/model/non-secret metadata
```

### 7.1 ASR metadata

可记录：device / compute / language / duration / segment / word counts。

### 7.2 OCR metadata

当前可记录：

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

P2.4 当前可记录：

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

## 8. P1 `BreakdownEvidenceLink` 的使用时机

`v2_breakdown_evidence_links` 是：

```text
Draft owner → raw Evidence/artifact
```

P2.1–P2.4 Provider 层还没有生成最终 Draft owner，因此不伪造 Run-level owner。

P2.5 Fusion 创建：

```text
SHOT_DRAFT
LOCAL_SUBJECT
TIMELINE_EVENT
SCENE_SEGMENT
PROP_HINT
```

之后，再为**实际消费过的** raw Evidence 创建 `BreakdownEvidenceLink`。

禁止简单地把所有 sidecar Evidence 无差别链接到所有 Draft owner。

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

P2.4 VLM 的视觉 `speaking_state` 也不能替代 diarization / active-speaker Evidence，更不能直接写 Character。

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

### 11.4 设备/状态

```text
default cpu
auto → 可选 CUDAExecutionProvider
auto-selected CUDA 初始化失败 → visible CPU fallback
显式 cuda 不可用/初始化失败 → FAILED
无任何历史 Reference Clip → NOT_AVAILABLE
所有帧都无法实际分析 → FAILED
帧可分析但无文字 → NO_EVIDENCE
有有效 OCR Observation → READY
```

P2.3 不创建 TimelineEvent，不把 OCR 文本直接物化 Scene/Prop，不写任何 Final Asset/Binding。

---

## 12. P2.4 VLM anonymous Shot semantics Provider Contract

### 12.1 正式实现

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

### 12.2 Runtime 隔离

主工程 Python 3.11 不直接加载新版 Qwen3-VL Torch/Transformers runtime。

生产默认：

```text
engine/app/breakdown_p2_vlm_v1.py
→ subprocess
→ .runtime/TransVLM/inference/.venv Python 3.12
→ scripts/run_breakdown_vlm_qwen3.py
→ .runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

这里**只复用现有 TransVLM 的隔离 Python/CUDA 环境**。

禁止复用：

```text
HeyGenAI/TransVLM-Qwen3-VL-4B-Instruct
```

作为 Breakdown 内容理解 checkpoint，因为它属于转场检测任务的专用 checkpoint。

P2.4 使用独立 base `Qwen/Qwen3-VL-4B-Instruct` 做内容语义。模型下载只在 setup 阶段发生；正式推理默认设置 Hugging Face/Transformers offline。

### 12.3 输入与执行顺序

```text
PROCESSING BreakdownRun
→ exact source ShotRevision
→ exact historical ShotRevisionItems
→ 只选择真实存在的 historical Reference Clips
→ 一次启动 isolated runner
→ 模型加载一次
→ 按 Shot 顺序 sequential inference
```

P2.4 不重新读取 Current `v2_shots` 猜输入，不并发轰炸 GPU，也不把 thumbnail 当唯一内容依据。

### 12.4 VLM Prompt 分工

VLM 只分析**视觉可支持**的内容：

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

明确不要求 VLM 做：

```text
对白 transcription
字幕 transcription
路牌/手机/文档文字 transcription
真实人物姓名/全局身份识别
Final Character / Scene / Prop 判断
```

这些职责分别属于 ASR、OCR 或后续 Resolution。

### 12.5 VLM_OUTPUT 白名单

每个可用 Shot 最多一个主 `VLM_OUTPUT`：

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

白名单内容：

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

所有其它模型字段都在 Adapter 边界丢弃。P2.1 的递归 Final-ID validation 继续作为第二重保护。

### 12.6 Confidence 与时间语义

P2.4 不伪造统一生成式置信度：

```text
VLM_OUTPUT.confidence = NULL
metadata.confidence_policy = provider-output-unscored
```

`events[].start_ratio/end_ratio` 只是 Shot 内相对位置提示；它们不是正式时间事实。P2.5 才能结合 exact Shot source interval 映射为 integer microseconds，并与 ASR/OCR Evidence 一起融合。

### 12.7 状态

```text
没有任何历史 Reference Clip → NOT_AVAILABLE
隔离 Python/runner/checkpoint 缺失 → NOT_AVAILABLE
runner/subprocess 整体失败 → FAILED
部分 Shot 输出缺失/失败/不可用 + 仍有合法 Shot semantics → READY + warnings
全部 Shot 输出失败或不可用 → FAILED
有至少一个合法 VLM_OUTPUT → READY
```

P2.4 不创建：

```text
SceneSegmentDraft
ShotSemanticDraft
LocalSubject
ShotLocalSubject
TimelineEvent
TimelineEventSubject
DraftPropHint
DraftPropOccurrence
BreakdownEvidenceLink
Dialogue
Character
Scene
Prop
AssetRevision
Final Shot Bindings
```

以上 Draft rows 归 P2.5 Fusion；Final Asset/Binding 更晚。

---

## 13. P2.5 Fusion Contract — NEXT

P2.5 必须消费 P2.1–P2.4 已固化 sidecar，不再发明新的并行 raw Evidence schema。

主线：

```text
BreakdownRun component provenance
→ load ASR/OCR/VLM immutable sidecars
→ verify schema/component/fingerprint/source revision
→ align all Evidence to exact historical ShotRevisionItems
→ ASR cross-cut splitting
→ OCR temporal stitching / dedupe / persistence inference
→ VLM shot semantics + ASR/OCR facts Fusion
→ write complete P1 Draft rows
→ create precise BreakdownEvidenceLink provenance
→ P1 validator
→ publish READY / READY_WITH_WARNINGS
```

P2.5 必须遵守：

- 不隐式重跑 Provider；
- ASR 不能提前按最大 overlap 粗暴绑定一个 Shot；
- OCR 的单帧 point observation 不能直接变成持续字幕；
- VLM normalized ratios 不能在没有 Shot source interval 的情况下当绝对时间；
- VLM `subject_A` 不能直接等同 Character；
- SceneSegmentDraft 不等于 Final Scene；
- DraftPropHint 不等于 Final Prop；
- 每个 READY source ShotRevisionItem 必须获得完整 `ShotSemanticDraft` 覆盖；
- EvidenceLink 只记录实际消费关系；
- validator hard error → Run FAILED，不替换旧 Current；
- publish 前必须确认 source revision 仍 Current。

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

P2.6 真实素材 benchmark 至少比较：

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
  Windows GPU stability
  Qwen3-VL-4B vs viable licensed alternatives if needed

Fusion:
  final anonymous Breakdown completeness
  event timing
  OCR dedupe
  conflict handling
  provenance correctness
```

P2.2–P2.4 focused tests 验证 Contract/runtime adapter，不等于真实短剧效果冠军证明。

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
[x] Windows P2 sidecar focused suite baseline established
```

### P2.2 已满足

```text
[x] faster-whisper Provider + segment/word timing
[x] cross-shot ASR remains unbound until Fusion
[x] auto CUDA fallback visible; explicit CUDA fail closed
[x] no Dialogue/Final write
[x] 6 ASR focused tests
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
[x] 7 OCR focused tests
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
[x] Ubuntu compile + FastAPI import PASS
[x] Ubuntu full pytest 28 failed, 243 passed, 1 skipped; historical failure category unchanged
[x] Windows Breakdown P2 provider suite 37/37 PASS
```

P2.4 已关闭。下一步唯一安全子阶段是 **P2.5：ASR/OCR/VLM Fusion → 完整 P1 anonymous Draft → validator/publish**。

真实模型质量、速度、显存、Windows GPU 和模型组合结论仍留到 P2.6。
