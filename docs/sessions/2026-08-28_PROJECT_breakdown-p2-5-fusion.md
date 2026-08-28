# AI Drama Studio — Breakdown P2.5 Fusion Closure Handoff

> Date: 2026-08-28  
> Repository: `zdingwl/ai-drama-studio`  
> Architecture: Reference Video V2  
> Formal Character runtime: Character V10.1  
> Status: **P2.5 COMPLETE / P2.6 NEXT**

## 1. 恢复入口

新对话先按：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ current code/tests
→ 本 handoff
```

本 handoff 只描述 P2.5 收口，不覆盖上述 CURRENT docs/code。

## 2. P2.5 已完成什么

正式代码：

```text
engine/app/breakdown_p2_fusion_v1.py
engine/tests/v2/test_breakdown_p2_fusion_v1.py
```

正式链：

```text
PROCESSING BreakdownRun
→ load registered immutable ASR/OCR/VLM sidecars
→ verify file/fingerprint/schema/component/run/source revision/provider metadata
→ deterministic multimodal Fusion
→ SceneSegmentDraft
→ ShotSemanticDraft
→ LocalSubject / ShotLocalSubject
→ TimelineEvent / TimelineEventSubject
→ DraftPropHint / DraftPropOccurrence
→ BreakdownEvidenceLink
→ P1 validator
→ publish READY / READY_WITH_WARNINGS
```

P2.5 不隐式重跑 ASR/OCR/VLM。

## 3. Sidecar / lifecycle 保护

消费每个 component 前验证：

```text
artifact_uri is local file://
artifact exists
sha256 fingerprint matches Run provenance
schema == breakdown-p2-evidence-v1
run/project/episode/source_shot_revision/component match
status/provider/model/evidence_count match registered component state
ProviderResult contract passes again
source ShotRevision remains Current
```

组件策略：

```text
VLM READY required
ASR/OCR NO_EVIDENCE or NOT_AVAILABLE → allowed with warnings
FAILED / NOT_CONFIGURED → fail closed
```

Fusion/validator 失败不替换旧 Current READY Run。STALE truth 不被失败处理覆盖。

## 4. Fusion 正式策略

### Scene

只合并连续 ShotRevisionItems。相邻 Shot 只有 normalized：

```text
location_hint
interior_exterior
time_of_day
```

完全一致才保守合并。缺 location 时切新 Segment。

### Shot

每个 source `ShotRevisionItem` 恰好一个 `ShotSemanticDraft`，使用 exact historical Shot/time/ordinal snapshot。

### ASR

跨镜 `ASR_SEGMENT` 与 exact Shot source interval 求交。优先使用 `ASR_WORD` timing 重建每个 Shot 的 dialogue text/time；没有 word timing 的跨镜 segment 只允许 warning-visible fallback。

### OCR

P2.3 raw OCR Observation 保持不变。P2.5 才按：

```text
same Shot
+ normalized text
+ temporal gap
+ geometry compatibility
```

做 conservative stitching/duration inference，且绝不越 Shot boundary。

### VLM events

`start_ratio/end_ratio` 结合对应 exact Shot interval 转正式 source integer microseconds；仅生成 VISUAL/ACTION events。

### Prop

只生成 `DraftPropHint / DraftPropOccurrence`，不是 Final Prop。

### Provenance

只有真实 Draft owner 创建后才写 `BreakdownEvidenceLink`，并只链接实际消费的 raw Evidence source IDs/URIs。

## 5. 同 Shot anonymous subject cannot-link 修复

P2.5 初始实现允许 exact normalized `appearance_summary` 在同一 Scene Segment 内作为弱跨 Shot continuity key。

发现边界：同一个 Shot 中两个不同 `subject_A / subject_B` 如果外观描述完全相同，会错误聚合成一个 LocalSubject，触发 `ShotLocalSubject` unique constraint，也违反产品语义。

正式修复：

```text
如果一个 appearance signature 在任一同一个 Shot 内同时出现 2+ 次：
→ 将该 appearance 标记为本 Segment ambiguous
→ 整个 Segment 内禁止该 appearance 作为跨 Shot merge key
→ 这些 occurrence 使用 shot-local key
→ 同 Shot 两人保持两个 LocalSubject
```

正常场景仍保留：同 Segment、没有 same-Shot collision 的 exact appearance 可以作为匿名弱连续性跨 Shot reuse。

修复代码链结束于 main baseline：

```text
b59309d305a15dfa80e9a6af0f961f93fcac5bf9
```

其中实际逻辑 commit：

```text
071ed27b9c8a7aa078d9d2f1f4df518779683c19
```

## 6. Verification reality

P2.5 初始 hosted run at `942f9f524d0ccd1f11c911d60b9b148b18d9396d`：

```text
full pytest: 29 failed, 248 passed, 1 skipped
P2.5 focused: 5 passed / 1 failed
```

唯一新增的 P2.5 failure 是：

```text
test_same_shot_identical_appearance_subjects_remain_distinct
```

其余 28 个失败仍是已知历史/environment 类别。

修复后做了本地纯逻辑验证：

```text
normal cross-Shot same appearance
→ same anonymous appearance key

same-Shot two subjects with same appearance
→ two distinct shot-local keys
```

**用户明确要求不要运行/重跑 GitHub Actions，因为仓库当前没有 CI 额度。**

因此：

- 修复后没有新的 hosted CI run；
- 不声称 fresh hosted 6/6；
- 不声称 whole repository green；
- 后续不要为了看 CI 绿灯主动消耗 GitHub Actions quota。

## 7. P1 Draft Contract 说明

`docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md` 是 P1 已冻结 Contract；P2.5 没有修改其表结构/schema，所以没有重写它。

该文档在 P1 close 时留下的“P2 not implemented”文字属于历史阶段说明。当前执行状态必须以：

```text
PROJECT_STATE.md
CURRENT_IMPLEMENTATION_MANIFEST.md
BREAKDOWN_P2_SIDECAR_CONTRACT.md
current code/tests
```

为准：P2.5 现在已经按 P1 Contract 自动写完整匿名 Draft。

## 8. OCR 边界

P2.3 OCR 已完成并保持稳定：

```text
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default CPU
```

不要重新实现/重写 OCR。只有明确 regression 才做最小修复。

P2.5 只消费 OCR sidecar 并做 stitching，不修改 OCR Provider 的原始 Evidence 语义。

## 9. Character V10.1 保护

P2.5 没有修改：

```text
identity thresholds
>=3 Shot / >=3 usable images gate
same-sample cannot-link
Face hard conflict
explicit Shot Character Assignment
Final Character Gate
Final Binding source
```

`LocalSubject / subject_A` 仍绝不是 Character。P2.5 的 anonymous cannot-link 也不能替代 Character 身份 Evidence。

## 10. 尚未完成

不要把 P2.5 contract completion 误报为真实模型质量 closure。

尚未完成：

```text
真实短剧上的 faster-whisper large-v3 质量验收
真实短剧上的 PP-OCRv6 small/medium 对比
真实短剧上的 Qwen3-VL-4B semantic quality
2fps/max_pixels sensitivity
Windows/local GPU/CPU/cache/offline runtime closure
完整 fused Draft 真实素材人工验收
P3 02 拉片 structured UI
Draft-guided Final Scene/Prop/Character resolution
Final identity/asset fill-back
Final Breakdown renderer
```

## 11. 下一步唯一安全阶段

```text
P2.6
→ representative real short-drama clips
→ actual local ASR/OCR/VLM inference
→ inspect sidecars + fused Draft
→ record accuracy/timing/conflict/runtime failures
→ compare model/runtime parameters where needed
→ Windows/local GPU/CPU closure
→ then decide whether P2 model defaults are good enough for P3
```

P2.6 完成前，不跳到 P3，不开始 Final Asset resolution，不把 fake-provider/contract tests 当真实模型效果证明。