# AI Drama Studio — Agent Entry Rules

当前正式架构：**Reference Video V2**。人物正式运行基线：**Character V10.1 + explicit Shot Character Assignment**。Breakdown-first 后台已完成 **P1 + P2.1–P2.5**；当前下一阶段是 **P2.6 真实短剧 / real-model / Windows-local runtime 验收**。

核心产品原则：

> **先看懂，再识别，再回填。**

## 1. 新对话恢复顺序

必须先读当前仓库事实，不要从旧聊天或旧 Feature 名称猜状态：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
6. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
7. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
8. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md   # 涉及人物时
9. 当前相关代码 / tests
10. 最新 docs/sessions/*.md handoff
```

事实优先级：

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests
= CURRENT executable truth

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= accepted TARGET + phase order
```

不要用历史 F01–F06、Character V1–V10、旧 Frozen Snapshot 覆盖当前 wiring。文件名带 `v6/v9` 不代表正式算法版本。

## 2. 当前可执行基线

```text
Architecture: Reference Video V2
Default branch: main
FastAPI: 2.4.1
Formal Character runtime: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment: v10.1-shot-character-assignment-1
```

Breakdown 状态：

```text
P0 planning/contracts                      COMPLETE
P1 Draft data/runtime/history              COMPLETE
P2.1 Provider/raw Evidence sidecar         COMPLETE
P2.2 ASR Provider                          COMPLETE
P2.3 OCR Observation Provider              COMPLETE
P2.4 VLM anonymous Shot semantics          COMPLETE
P2.5 deterministic multimodal Fusion       COMPLETE
P2.6 real-video/model/runtime closure      NEXT
P3 structured 02 拉片 UI                   PLANNED
P4 Draft-guided Scene/Prop                 PLANNED
P5 Draft ↔ Character safe integration      PLANNED
P6 Final fill-back/renderers               PLANNED
P7 downstream remake                      PLANNED
```

## 3. Breakdown-first 正式后台链

```text
Original Video
→ Preprocess
→ Shot Detection
→ ShotRevision / ShotRevisionItem
→ per-Shot Reference Clip
→ ASR / OCR / Qwen3-VL anonymous semantics
→ immutable raw Evidence sidecars
→ P2.5 deterministic Fusion
→ SceneSegmentDraft
→ ShotSemanticDraft
→ LocalSubject / ShotLocalSubject
→ TimelineEvent
→ DraftPropHint
→ BreakdownEvidenceLink
→ P1 validator
→ BreakdownRun READY / READY_WITH_WARNINGS
```

P2.5 已经实现“原始三模态 Evidence → 完整匿名结构化 Draft”的后台主链，但**P3 UI、Final Asset Resolution、Final Breakdown 仍未实现**。

## 4. Shot / Revision 是正式历史边界

保留：

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
manual boundary edit / split / merge / auto rerun / restore
```

`Shot.id` 不是跨 Revision 永久历史 ID。

正式 Breakdown 锚点：

```text
BreakdownRun.source_shot_revision_id → exact ShotRevision
ShotSemanticDraft.source_shot_revision_item_id → exact historical ShotRevisionItem
source_shot_id_snapshot → historical snapshot only
```

Provider/Fusion 禁止重新从 Current `v2_shots` 猜旧 Run 输入。ShotRevision 变化后旧 active Breakdown 必须 STALE，不能按 ordinal/time 自动迁移旧 Draft。

## 5. Draft / Evidence / Final Asset 必须分层

```text
LocalSubject / 人物A / subject_A != Character
SceneSegmentDraft                 != Final Scene
DraftPropHint                     != Final Prop
P2 raw Evidence                   != Final Asset truth
BreakdownEvidenceLink             != Final Binding
```

Draft 是 soft semantic prior / search hint。检测、Track、Face、Person-ReID、Audio、OCR 等可测 Evidence 才能支持后续身份/资产解析。

P2 全阶段禁止直接写：

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

## 6. P2.5 LocalSubject cannot-link

外观文字只能作为 Scene Segment 内的弱连续性提示：

```text
exact normalized appearance
→ 可以保守链接相邻/跨 Shot anonymous subject
```

但只要同一个 Shot 中有 2+ 个 subject 同时拥有同一 appearance signature：

```text
该 appearance 在整个 Segment 内禁止作为 merge key
→ occurrence 使用 shot-local anonymous key
→ 同 Shot 两个人必须保持不同 LocalSubject
```

这是匿名 Draft 防误合并，不是 Character identity 证明。

## 7. P2 Provider / Fusion 当前正式实现

```text
engine/app/breakdown_p2_sidecar_v1.py
engine/app/breakdown_p2_asr_v1.py
engine/app/breakdown_p2_ocr_v1.py
engine/app/breakdown_p2_vlm_v1.py
engine/app/breakdown_p2_fusion_v1.py
```

当前 Provider baseline：

```text
ASR: faster-whisper 1.2.1 / large-v3 / word_timestamps
OCR: RapidOCR 3.9.2 / PP-OCRv6 small / ONNX Runtime / default CPU
VLM: Qwen/Qwen3-VL-4B-Instruct / isolated local runtime / default CUDA
```

这些是当前工程 baseline，不代表 P2.6 真实短剧 benchmark 已证明它们是永久最佳模型。

`transvlm_runtime_v51.py` / `HeyGenAI/TransVLM-Qwen3-VL-4B-Instruct` 是**转场检测**路线。P2.4 内容理解使用独立 base `Qwen/Qwen3-VL-4B-Instruct` checkpoint；只复用隔离 Python/CUDA 环境，不能混用任务权重。

OCR P2.3 已完成。除非出现明确回归，只把 `breakdown_p2_ocr_v1.py` 当稳定基线，不重新设计/重写 OCR。

## 8. P2.5 Fusion 关键规则

```text
registered immutable sidecars only
no implicit ASR/OCR/VLM rerun
fingerprint/schema/run/revision/provider provenance must match
VLM READY required
ASR/OCR NO_EVIDENCE / NOT_AVAILABLE allowed with warnings
FAILED / NOT_CONFIGURED fail closed
```

Fusion：

```text
Scene: only consecutive Shots; conservative exact scene-signature merge
Shot: exactly one ShotSemanticDraft per source RevisionItem
ASR: split against exact Shot boundaries; word timing preferred
OCR: repeated observations stitched by text + time + geometry
VLM events: ratio → exact Shot source microseconds
Props: only DraftPropHint / occurrence
EvidenceLink: only actual consumed source Evidence
```

最终仍走真实 P1 validator / publish lifecycle。失败 Run 不替换旧 Current READY Run。

## 9. Character V10.1 不可破坏

正式人物链：

```text
Reference Clip / Shot
→ Person observations / Person Evidence
→ mature MOT
→ project-level identity classification
→ RESOLVED / UNRESOLVED
→ independent Shot × known-Character Assignment
→ Final Character Gate
→ Character + ShotCharacterBinding
```

创建新人物最低硬 Gate 保持：

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID
unique winner
same-sample cannot-link satisfied
no high-quality Face hard conflict
```

必须保持：

- Face 是 optional support / known presence / hard conflict，不是新人必需条件；
- same-sample cannot-link 不得绕过；
- 高质量 Face 冲突必须阻断错误合并；
- VLM/LocalSubject 不得创建 Character；
- ASR speaker label 不得直接绑定 Character；
- 带 `shot_assignment_version` 的当前 Run，Final Shot Binding 只能来自 explicit assignment；
- 禁止从 `candidate.tracks` fallback 推导当前 Run Final binding。

详细阈值与正式人物 Contract 以 `docs/ASSET_CHARACTER_RECOGNITION_V10_1.md` 和当前代码为准。

## 10. Scene / Prop 当前边界

当前 Final Scene/Prop resolver 尚未达到 Target Plan。

P2.5 只产：

```text
SceneSegmentDraft / scene hints
DraftPropHint / occurrence
```

P4 才根据 Draft 定向寻找/验证 Scene / Prop Evidence；P5/P6 才允许安全 resolution/fill-back。

## 11. 时间 / 批量 / Run 原则

- 正式媒体时间统一 integer microseconds；
- `Episode.sort_order` 是多集批量顺序依据；
- 重模型默认顺序执行，`concurrency = 1`；
- Reference Clip 是正式 Shot 资产，不是临时缓存；
- 新 Run 完整成功后才切 Current；
- READY AI Evidence/Draft 是历史事实，不允许为了“修结果”直接覆盖；
- MANUAL / RESTORE Revision 默认保护。

## 12. 当前验证现实

不要声称整仓 CI 全绿。

P2.5 初始 hosted run：

```text
focused: 5 passed / 1 failed
```

唯一新增失败是同 Shot 两个 identical-appearance subject 被合并。该逻辑已做窄范围 cannot-link 修复并做本地纯逻辑校验。

用户已明确：**GitHub Actions 当前没有额度，不要主动运行、重跑或依赖 hosted CI。** 因此不要声称修复后有新的 hosted 6/6。P2.6 的真实短剧 / Windows-local GPU 验收才是下一步质量闭环。

## 13. Git / 文档工作方式

仓库默认分支 `main`。修改前确认当前分支和最新 SHA；遵循当前 GitHub 工具安全规则，不覆盖他人更新。

当前用户明确要求避免消耗 GitHub Actions 额度；需要同步 `main` 时，避免主动触发/重跑 hosted CI。

任何正式产品流程、Breakdown、人物身份/绑定、Final Gate、Scene/Prop resolver 或下游 Contract 改动结束前，检查并同步：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md when schema semantics change
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character changes
latest docs/sessions/*.md handoff
```

不要为了文档一致而把未实现目标写成 IMPLEMENTED；也不要代码已经变了却留下会误导新对话的旧 CURRENT 状态。

## 14. 下一步

当前唯一安全 Breakdown 子阶段：

```text
P2.6 real short-drama / real-model benchmark
+ Windows/local CPU/GPU runtime closure
+ ASR/OCR/VLM/Fusion quality failure analysis
```

P2.6 完成前，不跳到 P3 UI，不开始 Final Character/Scene/Prop resolution，不把 fake-provider/contract tests 当真实模型质量证明。