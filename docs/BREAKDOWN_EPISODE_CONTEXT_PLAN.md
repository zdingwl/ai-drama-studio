# AI Drama Studio — 整集上下文拉片 / Episode-context Breakdown

> **Status:** ACCEPTED TARGET / P2-E1 + E2 + E3 + E4 IMPLEMENTED ON MAIN / LOCAL-REAL ACCEPTANCE NOT PASSED  
> **Accepted:** 2026-08-28  
> **E4 implemented:** 2026-08-29  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Architecture:** Reference Video V2 / Breakdown-first / Character V10.1

## 1. 核心产品原则

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

正式流程：

```text
Episode 原视频 / proxy / audio
→ Shot Detection + ShotRevision（时间坐标）
→ Episode ASR / OCR
→ overlapping continuous-window Video Understanding
→ contextual Shot refinement
→ Episode-context Fusion
→ anonymous Breakdown Draft
→ 03 资产专用 Evidence 验证
→ Final Asset / Binding
```

硬边界：

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
VLM/Draft != Final business truth
```

## 2. P2-E1 — Scene / Dialogue continuity

状态：`IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING`。

正式模块：

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

E1 规则保留在当前 E4 中。

Scene：

```text
明确地点 -> current Scene anchor
UNKNOWN / 特写 / 虚化 / 泛化“室内/房间” -> 继承当前 Scene
兼容具体化（病房 -> 医院病房） -> 同一 Scene
明确地点冲突或 INT ↔ EXT 强冲突 -> 新 Scene
```

Dialogue：

```text
ASR_SEGMENT = Episode-time 对白文本真值
Shot DIALOGUE TimelineEvent = 对白在 Shot 上的投影
```

跨镜一句话保留完整文本并共享 `dialogue_group_id/asr_segment_id`、source/projection range、continuation flags。UI 不重复显示 continuation projection。

## 3. P2-E2 — overlapping continuous-window Qwen3-VL

状态：`IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING`。

正式模块：

```text
engine/app/breakdown_p2_vlm_episode_v2.py
scripts/run_breakdown_vlm_qwen3_episode_windows.py
profile = breakdown-p2-vlm-episode-window-e2-v1
```

默认窗口：24 秒；允许 20..40 秒；25% overlap；允许 10..50%；Shot-aligned；按 Episode 顺序串行。

Qwen 同时看到连续视频窗口 + 窗口内所有 exact Shot 边界。输出：

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
  revision_item_id
  scene_continuity
  scene_basis
  context_note
  semantic.scene / shot / subjects / events / props
```

### 3.1 E2 continuity evidence 修正

真实验收发现：Prompt 虽已要求 `subject_continuity_hints / prop_continuity_hints`，旧 normalizer 却只保存 `window_summary + scene_change_candidates`，导致连续性信息在 Fusion 前丢失。

生产现在增加：

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
profile = breakdown-p2-vlm-window-continuity-preservation-e4-v1
```

它保留并规范化 window-level subject/prop continuity hints 到 `ProviderResult.metadata.window_summaries`，同时保持 frozen per-Shot `VLM_OUTPUT` sidecar schema 不变。

## 4. P2-E3 — contextual Shot refinement

状态：`IMPLEMENTED / LOCAL-REAL QUALITY NOT ACCEPTED`。

正式模块：

```text
engine/app/breakdown_p2_refinement_v1.py
scripts/run_breakdown_refinement_qwen3.py
engine/app/breakdown_p2_vlm_runtime_v1.py
```

E3 是 text-only refinement：

```text
provisional Scene
+ Previous/Current/Next E2 semantics
+ E2 window summaries
+ overlapping ASR_SEGMENT
+ overlapping OCR
```

E3 不允许把邻镜头独有的人/物搬入当前镜头，不改 ASR/OCR 文本，不猜 speaker identity，不创建 Final IDs。

当前生产 failure policy：

```text
E3-only malformed/runtime/model/subprocess/TimeoutExpired
→ explicit FALLBACK_E2
→ keep validated E2 semantics

E2 visual failure
→ VLM fail closed
```

最新真实 30-Shot Run 的 E3 全部 TimeoutExpired，因此该 Run 只能证明 fail-soft 生效，不能作为 E3 质量 PASS。

## 5. P2-E4 — final Episode-context Fusion

状态：`IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING`。

正式生产模块：

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
base = breakdown-p2-fusion-episode-context-e1-v2
```

### 5.1 为什么 E4 成为阻塞项

E4 前真实 Run：

```text
30 Shots -> 21 LocalSubjects
Scene 04 客厅 / 19 Shots -> 14 LocalSubjects
实际画面 -> 始终同一女一男
```

旧 Fusion 使用完整 normalized `appearance_summary` 作为跨镜 key。`表情惊讶 / 表情愤怒 / 双臂交叉 / 低头看手机` 等动态词一变化，就会生成新 LocalSubject。Shot-local `subject_A/B` 也会在后续镜头交换人物，因此不能直接串联。

### 5.2 E4 anonymous Subject Continuity Graph

长期语义：

```text
Shot-local subject_A/B = 当前 Shot observation label
anonymous graph node = (ShotRevisionItem, subject label)
LocalSubject = Scene-scoped anonymous continuity cluster
LocalSubject != Character
```

Primary positive edge：

```text
E2 window subject_continuity_hint
```

Conservative fallback：强稳定外观相似，仅用于相邻/近邻 Shot。

稳定特征倾向：

```text
发型 / 发色
服装颜色与款式
长期配饰
性别表现 / 年龄段等软视觉特征
```

动态状态从 continuity key 剥离：

```text
表情 / 情绪
动作 / 姿态 / 手势
是否说话
屏幕左/中/右
景别 / camera framing
```

### 5.3 cannot-link

任意两个在同一 Shot 同时出现的 observation 都是 hard cannot-link。

E4 union-find 每次合并前检查两个 cluster 的 Shot 集合是否相交，因此 cannot-link 也能阻止“通过第三个镜头间接把同镜两个人合并”的传递错误。

模型 hint 冲突、stable appearance 不足或候选不唯一时，默认保持 unresolved/separate，不强行合并。

### 5.4 E4 如何兼容 P1

E4 不新增 Final/identity 表，也不做 destructive schema migration。它在进入成熟 P1 writer 前生成 `(shot_revision_item_id, subject_label) -> continuity cluster key`，然后复用现有 `LocalSubject / ShotLocalSubject / TimelineEventSubject` 写入流程。

E4 provenance 写入：

```text
LocalSubject.appearance_json
Run.component_status.FUSION.subject_continuity
Run.provider_metadata.p2_fusion
```

包括 observation_count / cluster_count / hint_count / explicit_union_count / fallback_union_count / rejected_cannot_link_count。

## 6. 当前生产真值

```text
Shot Detection                    = Reference Video V2
ASR                               = Episode-level
OCR                               = observation provider
VLM E2                            = overlapping Episode windows
VLM continuity preservation       = implemented
VLM E3                            = contextual refinement / fail-soft to E2
Fusion                            = P2-E4 Episode-context Fusion
P2.6 real-model acceptance        = NOT PASSED
```

准确说法：

> **Episode-context 生产链已经实现到 E4，但真实短剧验收仍未通过；E4 需要用刚刚失败的真实案例重跑验证。**

## 7. 真实验收标准

下一次必须优先重跑同一个失败 Episode，至少检查：

```text
1. Scene 04 / 客厅 / 19 Shots，实际一女一男 -> roughly 2 stable LocalSubjects
2. subject_A/B label swap 不生成新人
3. 表情/动作/姿态变化不生成新人
4. 同镜两个人绝不能合并
5. 真正新人物仍必须分离
6. Scene wide/closeup/blur/inserts continuity 不退化
7. 真换场仍能正确切 Scene
8. 跨镜对白保持完整 ASR truth，UI 不重复 continuation
9. E3 若继续 timeout，必须显式 FALLBACK_E2
10. Character V10.1 / Final Asset tables 不被 E4 写入
```

只有真实模型 + 人工 review 达到要求后，P2.6 才能变为 PASS。

## 8. 测试 / CI

新增 E4 单元覆盖：

```text
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

覆盖 continuity hint 合并、Shot-local label swap、动态描述变化、hard same-Shot cannot-link、stable appearance fallback、E2 hint preservation。

GitHub hosted Actions 继续不使用。仓库中存在测试文件不等于本机 pytest/Qwen/CUDA 已通过。

## 9. 下一步

```text
git pull
→ 重新拉片同一失败 Episode
→ 先核对 LocalSubject 数量和 Scene 04 19 镜人物连续性
→ 通过后再单独优化 E3 TimeoutExpired
→ P5 继续暂停直到 P2.6 真正 PASS
```
