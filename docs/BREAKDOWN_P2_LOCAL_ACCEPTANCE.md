# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2-E1 + E2 + E3 + E4 IMPLEMENTED / LOCAL-REAL ACCEPTANCE NOT PASSED**  
> Date: 2026-08-29  
> Production pipeline: `breakdown-p2-full-v1`  
> Production E2 VLM: `breakdown-p2-vlm-episode-window-e2-v1`  
> Production E3: `breakdown-p2-contextual-shot-refinement-e3-v1`  
> Production E4 Fusion: `breakdown-p2-fusion-episode-context-e4-v1`  
> Acceptance schema: `breakdown-p2-acceptance-v1`

## 1. 当前验收结论

```text
P1/P2 实现验收                    = CONDITIONAL PASS
P2-E1 Scene/Dialogue              = IMPLEMENTED
P2-E2 continuous-window Qwen3-VL  = IMPLEMENTED
P2-E3 contextual refinement       = IMPLEMENTED / QUALITY NOT ACCEPTED
P2-E4 Episode-context Fusion      = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / 真实模型验收        = NOT PASSED
完整真实短剧 PASS report           = 尚不存在
```

最新 E4 之前的真实 Run 明确 **REJECTED**：

```text
30 Shots
21 LocalSubjects
Scene 04 客厅 / 19 Shots -> 14 LocalSubjects
实际 visible cast -> 同一女一男
E3 -> TimeoutExpired -> 全部 FALLBACK_E2
```

因此当前不能写 `P2 ACCEPTED`、`P2 CLOSED`、`P2.6 PASS`。

## 2. 当前正式生产链

```text
Episode Current ShotRevision
→ frozen BreakdownRun
→ Episode ASR
→ OCR
→ E2 overlapping Episode-window Qwen3-VL
→ preserve subject/prop continuity hints
→ E3 contextual Shot refinement
   └─ E3-only failure -> FALLBACK_E2
→ immutable exact-Shot VLM_OUTPUT sidecar
→ E4 Episode-context Fusion
   ├─ E1 Scene continuity
   ├─ E1 ASR dialogue projection
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
→ acceptance report
→ human review
```

正式模块：

```text
engine/app/breakdown_p2_vlm_episode_v2.py
scripts/run_breakdown_vlm_qwen3_episode_windows.py
engine/app/breakdown_p2_refinement_v1.py
scripts/run_breakdown_refinement_qwen3.py
engine/app/breakdown_p2_vlm_runtime_v1.py
engine/app/breakdown_p2_vlm_continuity_v1.py
engine/app/breakdown_p2_fusion_episode_v2.py
engine/app/breakdown_p2_fusion_episode_v4.py
engine/app/breakdown_p2_pipeline_v1.py
engine/app/breakdown_p2_acceptance_v1.py
```

## 3. E2 runtime / continuity evidence

默认：

```text
window target = 24 秒
allowed = 20..40 秒
overlap = 25%
allowed = 10..50%
window edge = Shot boundary
每个 Shot 完整落入 >=1 window
Episode 顺序串行
READY proxy 优先，Episode source fallback
```

E2 window output 必须包含并允许保留：

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
```

旧 normalizer 丢掉了 subject/prop continuity hints。当前 production wrapper `breakdown_p2_vlm_continuity_v1.py` 会把它们规范化并保留在 `ProviderResult.metadata.window_summaries`，供 E4 使用。

E2 Prompt 仍必须保持：

```text
cut != scene change
closeup/blur/insert only borrows context when supported
uncertain stays UNCERTAIN
anonymous subjects only
no ASR/OCR transcription inside visual E2
no Final asset IDs
```

## 4. E3 专项验收

E3 每 Shot 使用：

```text
provisional Scene
previous/current/next E2 semantic
selected/supporting E2 window summaries
overlapping ASR_SEGMENT
overlapping OCR
```

硬规则：

```text
只精修 current Shot
不能把邻 Shot 独有人/物搬入 current Shot
不能新造 current E2 不存在的 subject label
ASR/OCR text read-only
不能猜 speaker identity
景别/运镜/构图保持 E2-grounded
禁止 Final IDs
```

当前 failure policy：

```text
单 Shot malformed -> FALLBACK_E2
E3 runtime/model/subprocess/TimeoutExpired -> FALLBACK_E2
E2 visual failure -> VLM fail closed
```

所以 E3 timeout 不应再让整集丢失，但一个 30/30 fallback 的 Run **不能作为 E3 质量 PASS**。

## 5. E4 专项验收 — 匿名人物连续性

E4 是当前阻塞项的正式修复。

语义模型：

```text
subject_A / subject_B = Shot-local observation label
anonymous graph node = (ShotRevisionItem, subject label)
LocalSubject = Scene-scoped anonymous continuity cluster
LocalSubject != Character
```

Primary positive edge：`E2 subject_continuity_hint`。

Fallback positive edge：相邻/近邻 Shot 的强稳定外观相似。

动态状态必须从 identity-like continuity key 中剥离：

```text
表情 / 情绪
动作 / 姿态 / 手势
是否说话
screen position
shot framing / camera framing
```

可作为 soft stable cue：

```text
发型 / 发色
服装颜色与款式
长期配饰
性别表现 / 年龄段
```

Hard negative：

```text
同一 Shot 同时出现的任意两个 observations = cannot-link
```

Cannot-link 必须是传递安全的：如果 cluster A 已含 Shot 12 的人物A，则任何包含 Shot 12 人物B 的 cluster 都不能再与 A 合并。

### E4 本轮真实验收重点

必须优先重跑刚刚失败的同一个 Episode：

```text
Scene 04 客厅 / 19 Shots / visible cast = 一女一男
期望：roughly 2 stable LocalSubjects
禁止：人物 A-N 式碎片化
```

同时验证：

```text
1. subject_A/B 在后续 Shot 交换人物不会生成新人
2. 表情惊讶 -> 愤怒、抱臂、低头看手机等变化不会生成新人
3. 同镜两人永远不合并
4. 真正新人物仍要分开
5. 人物暂时出画/插入镜头后再次出现能通过 E2 hints 恢复连续性
6. LocalSubject.appearance_json 可看到 E4 cluster provenance
7. FUSION metadata 可看到 observation/cluster/union/cannot-link stats
```

## 6. E1 Scene / Dialogue 回归检查

Scene：

```text
UNKNOWN / generic closeup -> inherit current Scene
compatible specificity -> same Scene
strong location or INT/EXT contradiction -> new Scene
```

Dialogue：

```text
ASR_SEGMENT = 完整文本真值
Shot DIALOGUE = projection
```

跨镜 projections 必须共享 group + continuation metadata；UI 只在起始镜显示完整对白，后续仅显示“承接上一镜对白”，不能重复整句。

## 7. Provenance / Contract 检查

每条最终 VLM Evidence 必须继续满足：

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen ShotRevisionItem
source_start_us/end_us = exact Shot range
```

payload：

```text
payload.e2_semantic
payload.semantic
payload.episode_window
payload.contextual_refinement
```

Historical Run/sidecar 不重写；只有新 Run 使用新 E4 行为。

## 8. Runtime preflight

API：

```text
GET /api/breakdown/p2/runtime-preflight
```

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
```

基础条件至少确认 main Python / faster-whisper / RapidOCR / OpenCV / FFmpeg / FFprobe / isolated Qwen runtime / checkpoint / CUDA when requested / nvidia-smi。

注意：当前 acceptance preflight 代码仍有历史 VLM probe 路径，不能单独证明 E2/E3/E4 质量。真正的 runtime 证据仍是一次新 Episode 成功跑过当前 production chain。

## 9. Acceptance Contract

API：

```text
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

人工评分继续覆盖：

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

本轮 notes/blocking_issues 必须额外写明：

```text
E4 LocalSubject count / Scene 04 19-Shot continuity
same-Shot cannot-link result
label-swap result
E3 READY vs FALLBACK_E2 / timeout count
cross-Shot dialogue UI behavior
```

PASS 仍要求 required scores >=4.0 且 blocking_issues 为空。机器指标不能自动变成 PASS。

## 10. Identity / Final Asset 禁止事项

E4 LocalSubject graph 绝不能被解释成 Final Character identity。

```text
LocalSubject != Character
subject continuity hint != ReID evidence
ASR speaker != Character
Draft Scene/Prop != Final Scene/Prop
```

Character V10.1 的 Person Evidence / MOT / YoutuReID / same-sample cannot-link / face hard conflict / >=3 independent Shots/images / explicit Shot assignment / Final Gate 全部保持不变。

## 11. 测试 / CI

E4 单元覆盖：

```text
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

覆盖：hint preservation、label swap、动态描述变化、same-Shot cannot-link、stable appearance fallback。

Hosted GitHub Actions 不使用。代码存在不等于本机 pytest/Qwen/CUDA PASS。

## 12. 下一步操作

```text
git pull
→ 对同一个失败 Episode 点“重新拉片本集”
→ 首先只看 LocalSubject/Scene 04 19 镜人物连续性
→ 如果 E4 通过，再单独处理 E3 TimeoutExpired
→ 在真实验收通过前 P2.6 保持 NOT PASSED，P5 保持 PAUSED
```
