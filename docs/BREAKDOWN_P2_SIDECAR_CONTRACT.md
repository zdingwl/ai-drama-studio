# AI Drama Studio — Breakdown P2 Evidence Sidecar Contract

> **Status:** P2.1 IMPLEMENTATION CONTRACT  
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
P2.1 统一 Evidence/Provider Contract + local sidecar persistence
P2.2 ASR Provider + segment/word timing
P2.3 OCR Observation Provider
P2.4 VLM anonymous Shot semantics Provider
P2.5 ASR/OCR/VLM Fusion → 完整 P1 Draft → validator/publish
P2.6 真实短剧 benchmark + Windows acceptance + docs closure
```

P2.1 完成不代表 P2 整体完成。

---

## 2. P2.1 输入 Contract

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

Provider 推理可能耗时，因此至少两次检查：

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

P2.1 同步本地 Provider 允许状态：

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

跨 Shot 的 ASR Segment 可以暂时不绑定 Shot；P2.5 Fusion 再按 source time 切到具体 Shot TimelineEvent。

### 5.3 Confidence

```text
0 <= confidence <= 1
或 NULL
```

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

即使 VLM 自己声称识别出了“某角色”，P2 也只能保存匿名语义/文本，不能越级变成 Final identity。

---

## 6. Raw Evidence sidecar 文件 Contract

P2.1 不新增一套平行数据库 Evidence 表。

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

成功固化 Provider Result 后，P2.1 可在仍是 PROCESSING 的 Run 内合并：

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

P2.1 还没有生成 Draft owner，因此不伪造 Run-level owner。

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

---

## 10. P2.2+ Provider 选择规则

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

## 11. P2 全阶段禁止写

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

## 12. P2.1 Stable Gate

P2.1 完成必须满足：

```text
[ ] Provider 输入固定到 BreakdownRun.source_shot_revision_id
[ ] exact ShotRevisionItems/Reference Clips/keyframes 可读取
[ ] Episode audio/source language 可读取
[ ] ASR/OCR/VLM 统一 Result Contract
[ ] raw Evidence source type/time/confidence 校验
[ ] Final Asset ID leakage fail closed
[ ] fingerprint artifact 幂等
[ ] atomic sidecar write
[ ] component provenance 写回 PROCESSING Run
[ ] STALE Run 不能继续写 P2 Evidence
[ ] 不新增 Final Asset/Binding write
[ ] P1 Windows 32-case gate 不回归
```

P2.1 通过后，下一步唯一是 P2.2：接正式 ASR Provider，并把 word timing 作为 raw Evidence 保存。
