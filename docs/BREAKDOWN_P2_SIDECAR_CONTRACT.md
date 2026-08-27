# AI Drama Studio — Breakdown P2 Evidence Sidecar Contract

> **Status:** P2.1 + P2.2 IMPLEMENTED / P2 IN PROGRESS / P2.3 NEXT  
> **Contract date:** 2026-08-27  
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

为避免 ASR/OCR/VLM、模型下载、GPU、融合、发布一次性耦合，P2 固定按以下顺序落地：

```text
P2.1 统一 Evidence/Provider Contract + local sidecar persistence      COMPLETE
P2.2 ASR Provider + segment/word timing                               COMPLETE
P2.3 OCR Observation Provider                                         NEXT
P2.4 VLM anonymous Shot semantics Provider                            PLANNED
P2.5 ASR/OCR/VLM Fusion → 完整 P1 Draft → validator/publish          PLANNED
P2.6 真实短剧 benchmark + Windows acceptance + docs closure           PLANNED
```

P2.1/P2.2 完成不代表 P2 整体完成。P2.2 目前完成的是正式 Provider Contract/runtime 与确定性的 Evidence 测试；真实短剧上的模型效果、速度、显存和候选模型对比仍属于 P2.6 benchmark。

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

只允许：

```text
PROCESSING
```

如果 P1.6 已把 Run 标为：

```text
STALE
```

P2 Provider 必须停止，不能继续把旧 Revision 的结果登记为活动 Evidence。

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

组件：

```text
ASR
OCR
VLM
```

业务/Fusion 层只能依赖统一 Result，禁止到处出现：

```text
if provider == "xxx": ...
```

具体模型 SDK / raw status / tensor 对象必须在 Adapter 内消化。

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

未来外部异步/计费 Provider 不允许把 submit/poll 生命周期硬塞进这些同步状态；必须先实现 `docs/PROVIDER_JOB_RULES.md` 的持久化 Job Contract。

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

P1 已预留的正式 source type：

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

正式时间仍为 integer microseconds。

如果 Evidence 已绑定 `shot_revision_item_id`：

```text
source_start_us/source_end_us
必须完全落入该 ShotRevisionItem
```

ASR 的 segment/word 在 P2.2 **统一保留 Episode source 绝对时间并保持 `shot_revision_item_id = NULL`**。原因是对白可能跨镜头切点；P2.5 Fusion 才按 source time 和 exact ShotRevisionItem 边界切成 Shot-relative TimelineEvent。禁止 P2.2 仅按“最大 overlap Shot”提前绑定。

### 5.3 Confidence

```text
0 <= confidence <= 1
或 NULL
```

P2.2 `ASR_WORD.confidence` 可以保存 faster-whisper 的 word probability；segment 级 provider diagnostics 保留在 payload/metadata，不伪造成统一置信度。

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

即使 VLM 或后续 Speaker 模型声称识别出了“某角色”，P2 也只能保存匿名语义/文本，不能越级变成 Final identity。

---

## 6. Raw Evidence sidecar 文件 Contract

P2 不新增一套平行数据库 Evidence 表。

原始 Provider 输出保存为 workspace sidecar：

```text
workspace/
└─ <project_id>/
   └─ episodes/
      └─ <episode_id>/
         └─ breakdown/
            └─ <run_id>/
               └─ evidence/
                  ├─ asr/
                  │  └─ <sha256-fingerprint>.json
                  ├─ ocr/
                  │  └─ <sha256-fingerprint>.json
                  └─ vlm/
                     └─ <sha256-fingerprint>.json
```

### 6.1 Fingerprint

Fingerprint 基于标准化 JSON 内容计算 SHA-256，包括：

```text
schema version
run/project/episode
source ShotRevision
component/provider/model/status
metadata/warnings
raw evidence records
```

同一标准化结果：

```text
→ 相同 fingerprint
→ 相同 artifact path
→ 幂等复用
```

不同结果：

```text
→ 新 fingerprint
→ 新 artifact
→ 不覆盖旧 Evidence
```

### 6.2 Atomic write

```text
write .tmp
→ os.replace
→ final .json
```

禁止直接写最终文件导致崩溃后留下半个 JSON。

### 6.3 Artifact 内容

sidecar 保存原始 Evidence；`BreakdownRun.component_status_json` 只保存快速状态/provenance 摘要，不复制全部模型输出。

---

## 7. BreakdownRun metadata

成功固化 Provider Result 后，P2 可在仍是 PROCESSING 的 Run 内合并：

```text
component_status_json[ASR/OCR/VLM]
→ status
→ provider
→ model
→ artifact_uri
→ fingerprint
→ evidence_count
→ warnings

provider_metadata_json.p2_sidecar[ASR/OCR/VLM]
→ provider/model/non-secret metadata
```

这些字段不是 Final Draft，也不替代 Evidence artifact。

P2.2 ASR metadata 当前至少可记录：

```text
device_requested
device
compute_type
beam_size
vad_filter
word_timestamps
language_requested
language_detected
language_probability
audio_duration_us
segment_count
word_count
```

错误 metadata 只记录非敏感 error type/状态，不把 API secret 或不受控异常正文写入 provenance。

---

## 8. P1 `BreakdownEvidenceLink` 的使用时机

P1 表：

```text
v2_breakdown_evidence_links
```

是：

```text
Draft owner
→ raw Evidence/artifact
```

的 provenance link。

P2.1/P2.2 还没有生成 Draft owner，因此不伪造 Run-level owner。

P2.5 Fusion 在创建：

```text
SHOT_DRAFT
LOCAL_SUBJECT
TIMELINE_EVENT
SCENE_SEGMENT
PROP_HINT
```

后，再为实际消费过的 raw Evidence 创建 `BreakdownEvidenceLink`。

---

## 9. 与旧 F05 ASR/Speaker helper 的关系

仓库现有 `content_analysis_v2.py` 里保留：

```text
_run_asr()
_run_diarization()
_attach_speakers()
_map_speaker_to_character()
```

这些是历史 F05/F06 compatibility helper，不是 P2 正式 Contract。

P2 可以复用其中成熟的局部实现思想，但不能继续：

```text
ASR → AnalysisDialogue → CharacterCandidate
```

作为正式 Breakdown 主链。

特别是旧 `_map_speaker_to_character()` 直接接 Character Candidate 的方式不能进入 P2，因为 P2 Speaker 只能先保持匿名。

P2.2 正式 ASR 入口是：

```text
engine/app/breakdown_p2_asr_v1.py
→ FasterWhisperASRProvider
→ P2ProviderResult
→ P2.1 run_local_provider()
→ immutable ASR sidecar
```

它不写 `studio_v2.Dialogue`，也不执行 diarization。

---

## 10. P2.2 ASR Provider Contract

### 10.1 正式实现

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

默认推理参数：

```text
beam_size = 5
vad_filter = true
word_timestamps = true
```

`source_language` 会先规范为模型语言码，例如：

```text
zh-CN / zh-TW / yue → zh
en-US / en-GB        → en
ja-JP                 → ja
ko-KR                 → ko
```

### 10.2 输出

每个可用 segment：

```text
ASR_SEGMENT
→ source_start_us / source_end_us
→ text / detected language
→ avg_logprob / no_speech_prob / compression_ratio / temperature 等 provider diagnostics
```

每个可用 word/token：

```text
ASR_WORD
→ source_start_us / source_end_us
→ text
→ confidence = provider word probability when valid
→ payload.segment_id / segment_index / word_index / raw_word
```

P2.2 source IDs 使用 Episode + 顺序索引形成确定性 ID，便于同一次标准化输出重试得到同一 sidecar fingerprint。

### 10.3 设备与 fail-closed

```text
device=auto
→ CTranslate2 检测 CUDA
→ CUDA 可用时先尝试 cuda/float16
→ 自动 CUDA 加载失败时允许显式记录 warning 后降级 cpu/int8

device=cuda（用户显式指定）
→ CUDA 加载失败 = FAILED
→ 禁止静默切 CPU
```

没有 preprocess audio：

```text
NOT_AVAILABLE
```

没有可用语音 Evidence：

```text
NO_EVIDENCE
```

模型加载/转写失败：

```text
FAILED
```

这些状态仍由 P2.5 orchestration 决定最终 Run 是否允许发布；P2.2 自己不发布 BreakdownRun。

### 10.4 模型可替换性与 benchmark

`faster-whisper large-v3` 是 P2.2 当前正式基线，不是永久锁死的“效果冠军”。Qwen3-ASR + Qwen3 ForcedAligner 等保持 P2.6 benchmark 候选。

Provider 切换必须继续满足同一 `P2ProviderResult/P2EvidenceRecord` Contract，因此模型更换不得迫使 P1 Draft schema 改版。

---

## 11. P2.3+ Provider 选择规则

具体 ASR/OCR/VLM 模型不能只凭“名字新”决定。

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

P2.2–P2.4 必须各自有 focused tests；P2.6 再做真实素材 benchmark。

---

## 12. P2 全阶段禁止写

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
AssetRevision
```

也禁止修改：

```text
Character V10.1 identity thresholds
same-sample cannot-link
Face hard conflict
explicit Shot Character Assignment
Final Character Gate
```

---

## 13. Stable Gate

### P2.1 已满足

```text
[x] Provider 输入固定到 BreakdownRun.source_shot_revision_id
[x] exact ShotRevisionItems/Reference Clips/keyframes 可读取
[x] Episode audio/source language 可读取
[x] ASR/OCR/VLM 统一 Result Contract
[x] raw Evidence source type/time/confidence 校验
[x] Final Asset ID leakage fail closed
[x] fingerprint artifact 幂等
[x] atomic sidecar write
[x] component provenance 写回 PROCESSING Run
[x] STALE Run 不能继续写 P2 Evidence
[x] 不新增 Final Asset/Binding write
[x] P1 Windows 32-case gate 不回归
[x] Windows P2 sidecar focused suite 18/18 PASS
[x] Ubuntu full pytest only adds the 5 new P2.1 passes; historical 28 failures unchanged
```

### P2.2 已满足

```text
[x] 正式 faster-whisper Provider 与 P2.1 Contract 解耦
[x] 默认 large-v3，可配置 model/device/compute/cache
[x] word_timestamps=true + VAD + beam search
[x] segment/word 秒时间转换为 integer microseconds
[x] 跨 Shot ASR 不提前绑定 ShotRevisionItem
[x] word probability 可追溯
[x] source/detected language metadata 可追溯
[x] auto CUDA→CPU fallback 可见；显式 CUDA 不静默降级
[x] missing audio / no speech / model failure 状态 fail closed
[x] sidecar + BreakdownRun provenance 复用 P2.1
[x] 不写 Dialogue / Character / Scene / Prop / Final Binding
[x] 6 个新增 ASR focused tests 通过
[x] Windows Breakdown P2 provider suite 24/24 PASS
[x] Windows Breakdown P1 regression gate PASS
[x] Ubuntu full pytest = 28 failed, 230 passed, 1 skipped；历史 28 失败类别未新增
```

P2.2 已关闭。下一步唯一是 **P2.3：OCR Observation Provider**。真实模型效果 benchmark 仍留到 P2.6，不能把 focused contract tests 描述成真实短剧识别效果验收。
