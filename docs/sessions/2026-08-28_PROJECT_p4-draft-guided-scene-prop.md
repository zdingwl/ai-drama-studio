# P4 Draft-guided Scene / Prop Evidence

日期：2026-08-28

状态：**IMPLEMENTED / LOCAL MODEL ACCEPTANCE PENDING**

## 目标

P2/P3 已经产生匿名 Structured Draft，但 Draft 不是 Final Scene / Prop。P4 的职责是：

```text
当前 READY Structured Draft
→ 缩小 Scene / Prop 搜索范围
→ 当前 Shot 图像重新验证
→ SceneCandidate / ShotSceneEvidence
→ PropCandidate / ShotPropEvidence
→ 继续沿用现有 Final Asset / Revision 工作流
```

核心原则仍然是：

> Draft 是 search prior，不是 Final truth。

## P4.1 Breakdown Asset Guidance Adapter

新增：

```text
engine/app/breakdown_asset_guidance_v1.py
```

正式 profile：

```text
breakdown-asset-guidance-p4-v1
```

只消费满足全部条件的 BreakdownRun：

```text
status in READY / READY_WITH_WARNINGS
is_current = true
source_shot_revision_id == Episode 当前 ShotRevision.id
ShotSemanticDraft.source_shot_revision_item_id 属于该 exact Current Revision
ShotSemanticDraft.source_shot_id_snapshot == ShotRevisionItem.original_shot_id
original_shot_id 仍然是当前 Episode 的 Shot
```

因此：

- STALE Draft 不消费；
- 历史 R2/R3 不按 ordinal 猜回当前 Shot；
- 不按最近时间戳模糊映射；
- Failed / Processing Draft 不消费；
- Current ShotRevision 改变后，旧 Draft 不会污染新资产 Evidence。

Adapter 输出 Shot 级 soft guidance：

```text
SceneSearchGuide
- location_hint
- interior_exterior
- time_of_day
- summary
- environment_description

PropSearchGuide
- label_hint
- importance
- narrative_reason
- source time range
- screen_position_hint
- interaction_summary
- Draft provenance ids
```

这些结构没有 Character / Scene / Prop Final FK。

## P4.2 Draft-guided Qwen3-VL verification

新增：

```text
engine/app/asset_semantics_p4_v1.py
```

现有 `03 资产` 任务已从：

```text
asset_semantics_v3.enrich_asset_run
```

切换为：

```text
asset_semantics_p4_v1.enrich_asset_run
```

### Scene

Draft SceneSegment 只作为假设传入 Prompt。

Qwen3-VL 必须重新观察当前 Shot thumbnail，返回：

```text
scene.label
scene.indoor_outdoor
scene.time_of_day
scene.confidence
scene.draft_match = MATCH / CONFLICT / UNKNOWN
scene.reason
```

即使 Draft 和图片冲突，也要求输出图片真正支持的 Scene label。

Scene 结果仍写回现有：

```text
SceneCandidate
ShotSceneEvidence
```

并在 `SceneCandidate.evidence_json.p4_breakdown_guided` 保留：

- guidance profile；
- verification provider；
- BreakdownRun ids；
- SceneSegmentDraft ids；
- MATCH / CONFLICT / UNKNOWN 统计；
- per-Shot verification observations。

P4 没有创建新的 Final Scene 表。

### Prop

每个 `DraftPropOccurrence` 被转成一个本次请求内的临时 `P1 / P2 / ... target_key`。

Prompt 明确：

```text
Draft 只是待验证假设
看不见 -> observed=false
不允许因为 Draft 写了某物就声称看见
```

只有：

```text
observed = true
confidence >= 0.45
```

的 Draft 道具验证结果才会成为 PropCandidate Evidence。

Draft 漏掉的新关键道具仍可 discovery，但阈值更高：

```text
confidence >= 0.68
```

普通家具 / 墙 / 地板 / 人物衣服不作为关键道具 discovery。

如果 Qwen 能可靠定位，保存：

```text
ShotPropEvidence.bbox_json
format = xyxy_norm
bbox = [x1, y1, x2, y2]  # 0..1
provider = Qwen3-VL
profile = breakdown-asset-guidance-p4-v1
```

非法/越界/零面积 bbox 会被丢弃，不伪造位置。

PropCandidate.evidence_json 保留：

- verification mode：DRAFT_GUIDED_VERIFIED / DISCOVERED；
- DraftPropHint ids；
- DraftPropOccurrence ids；
- Shot count；
- visual verification reasons。

## No-Draft fallback

如果项目当前没有 revision-safe Structured Draft：

```text
P4 adapter = NO_CURRENT_DRAFT
→ 完整回退 asset_semantics_v3 legacy unguided path
```

因此旧项目 / 尚未运行 P2 的项目不会因为 P4 被阻断。

## Partial failure

P4 按 Shot 收集验证失败。

- 至少一个 Shot 成功：保留成功 Evidence；
- 部分失败：`READY_WITH_WARNINGS`；
- 一个 Shot 都无法分析：P4 semantic verification 失败；
- Character V10.1 Evidence 不因 Scene/Prop 语义失败而删除。

`03 资产` 后台任务已经识别 P4 的 `READY_WITH_WARNINGS`，不会把部分失败显示成全成功。

## Character V10.1 boundary

本次没有修改：

```text
character_detection / tracking / YoutuReID
Face conflict / cannot-link
>=3 independent Shots / images gate
explicit Shot Character Assignment
asset_final_gate_v10
```

Draft / VLM 仍不能创建 Character。

## Existing Final Asset flow

现有资产系统本来就使用：

```text
AI Candidate/Evidence
→ apply_analysis_to_assets
→ AUTO Asset Revision
→ MANUAL / RESTORE protection
```

P4 只改变 Scene/Prop Candidate 的搜索与验证来源，不新增 `Draft -> Final` 直连。

## Tests added

```text
engine/tests/unit/test_breakdown_asset_guidance_v1.py
engine/tests/unit/test_asset_semantics_p4_v1.py
```

锁定：

- current + READY + exact ShotRevision gate；
- 禁止 ordinal/timestamp 历史猜映射；
- Draft 必须在 Prompt 中定义为 hypothesis；
- guided prop 必须支持 observed=false；
- 临时 target_key 与内部 provenance id 分离；
- normalized bbox validation；
- asset task 必须走 P4 semantics entrypoint。

GitHub hosted Actions 未运行/未查询。

## Local acceptance

更新代码并重启后端后：

1. 确保某 Episode 有当前 READY Structured Draft；
2. 进入 `03 资产`；
3. 运行“资产提取”；
4. 后台任务阶段应出现“Draft 引导场景 / 道具验证”；
5. 检查 Scene / Prop 结果；
6. 检查 task result.semantic：

```text
guidance_profile = breakdown-asset-guidance-p4-v1
guidance_status = READY
guided_shot_count > 0
guided_prop_target_count >= 0
breakdown_run_ids = [...]
```

7. 有 Draft 道具但当前图像看不到时，不应生成对应 PropCandidate；
8. 可见 Draft 道具应有 `DRAFT_GUIDED_VERIFIED` provenance；
9. 有可靠定位时 ShotPropEvidence 应包含 xyxy_norm bbox；
10. Character V10.1 结果与 P4 前保持同一 hard-gate 逻辑。

## Acceptance truth

当前事实：

```text
P4 implementation                 = IMPLEMENTED
P4 local/model acceptance          = PENDING
P1/P2 implementation acceptance    = CONDITIONAL PASS
P2.6 Windows / real-model          = NOT PASSED
P3 UI acceptance                   = IN PROGRESS
```

不得把本次代码完成写成 P4 model-quality PASS。
