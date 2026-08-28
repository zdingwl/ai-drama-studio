# AI Drama Studio — 整集上下文拉片 / Episode-context Breakdown

> **Status:** ACCEPTED TARGET / P2-E1 + P2-E2 + P2-E3 IMPLEMENTED ON MAIN / LOCAL-REAL ACCEPTANCE PENDING  
> **Accepted:** 2026-08-28  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Architecture:** Reference Video V2 / Breakdown-first / Character V10.1

## 1. 核心产品原则

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

旧逐 Shot 语义存在两个结构性问题：一句对白跨切镜会被错误拆句；同一 Scene 中的特写、背影、插入镜头、虚化背景镜头会因为自己看不清环境而被错误换场。

正式目标：

```text
Episode 原视频 / proxy / audio
→ Shot Detection + ShotRevision（时间坐标）
→ Episode ASR / OCR
→ P2-E2 overlapping continuous-window Video Understanding
→ P2-E3 contextual Shot refinement
→ Episode-context Fusion
→ anonymous Breakdown Draft
→ 03 资产专用 Evidence 验证
→ Final Asset / Binding
```

不变边界：LocalSubject != Character，SceneSegmentDraft != Final Scene，DraftPropHint != Final Prop，ASR speaker != Character。VLM 不得输出或绕过 Final Character/Scene/Prop/Binding 真值。

## 2. P2-E1 — Episode-context Fusion

状态：

```text
IMPLEMENTED ON MAIN
local-real acceptance = PENDING
```

正式模块：

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

### Scene continuity

```text
明确地点 → 当前 Scene anchor
UNKNOWN / 特写 / 虚化 / 泛化“室内/房间” → 继承当前 Scene
病房 → 医院病房、客厅 → 家中客厅 → 同一 Scene
明确地点冲突或 INT ↔ EXT 强冲突 → 新 Scene
```

规则：**看不出来 != 换场。**

### Dialogue truth

```text
ASR_SEGMENT = Episode-time 对白文本真值
Shot DIALOGUE TimelineEvent = 该对白在 Shot 上的时间投影
```

跨镜一句话保留完整文本，并共享 `dialogue_group_id/asr_segment_id`，同时记录 `continues_from_previous_shot` / `continues_to_next_shot`。ASR_WORD 仍是 immutable SUPPORT Evidence。

## 3. P2-E2 — overlapping continuous-window Qwen3-VL

状态：

```text
IMPLEMENTED ON MAIN
local-real Qwen/Windows acceptance = PENDING
```

正式模块：

```text
engine/app/breakdown_p2_vlm_episode_v2.py
profile = breakdown-p2-vlm-episode-window-e2-v1
window schema = breakdown-p2-vlm-episode-window-v1

scripts/run_breakdown_vlm_qwen3_episode_windows.py
prompt profile = breakdown-p2-vlm-episode-window-zh-v1
```

### 3.1 窗口策略

默认：

```text
window target = 24 秒
allowed duration = 20..40 秒
window overlap = 25%
allowed overlap = 10..50%
窗口边界对齐 Shot boundary
每个 Shot 必须完整落入至少一个 window
按 Episode 顺序串行推理
```

如果一个 Shot 自身超过 nominal window，宁可让该窗口超过目标时长，也不把一个 Shot 人为切碎后再让模型猜边界。

生产输入优先使用 `READY preprocess proxy`，找不到时才回退 `Episode.source_path`。每个窗口由 FFmpeg 从整集视频临时物化，Qwen runner 只消费临时窗口，不重写原媒体。

### 3.2 Qwen 一次看什么

每个窗口同时拿到：

```text
连续视频窗口
+ 窗口内所有 Shot 的 exact revision_item_id
+ 每个 Shot 在窗口内的开始/结束时间
```

Qwen 先理解整个窗口，再分别输出每个 Shot 的匿名结构化语义。Prompt 明确要求：切镜不是自动换场；特写/虚化可借前后画面判断，但证据不足必须 `UNCERTAIN`。

窗口输出包括：

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
  revision_item_id
  scene_continuity = SAME|NEW_SCENE|UNCERTAIN
  scene_basis = DIRECT|CONTEXT|MIXED|UNCERTAIN
  context_note
  semantic.scene / shot / subjects / events / props
```

自然语言继续要求简体中文；JSON key 与机器枚举保持英文。ASR/OCR 原始文本不在视觉 E2 中转录或翻译。

### 3.3 多窗口覆盖同一个 Shot

同一 Shot 可能同时出现在多个重叠 window。E2 选择拥有最多前后上下文的候选：

```text
primary rank = min(left_context, right_context)
secondary = Shot center 距 window center 越近越好
final tie = 更早 window
```

选中的窗口写入每条 Shot `VLM_OUTPUT.payload.episode_window`：

```text
window_id
window_start_us / window_end_us
supporting_window_ids
selection_policy
scene_continuity
scene_basis
context_note
```

### 3.4 E2 Contract

E2 本身生成 exact-Shot 匿名 `VLM_OUTPUT`。生产 stable runtime 在 E3 完成后才固化最终 VLM sidecar，因此 E2 视觉结果会被保留为 `payload.e2_semantic`，而不是单独再落一个可变中间 sidecar。

历史 BreakdownRun/sidecar 不重写。只有重新运行 AI 拉片的新 Run 才使用当前 E2/E3。

### 3.5 Runtime

E2 isolated runner：

```text
scripts/run_breakdown_vlm_qwen3_episode_windows.py
```

模型在该进程中加载一次，然后按 window 串行推理。Windows 默认仍可强制 `decord`，并阻止 qwen-vl-utils 在 decord 失败后用 torchvision fallback 掩盖真正的解码错误。

CLI 可选调参：

```text
--vlm-window-seconds 20..40
--vlm-window-overlap-ratio 0.10..0.50
```

## 4. P2-E3 — contextual Shot refinement

状态：

```text
IMPLEMENTED ON MAIN
local-real contextual refinement acceptance = PENDING
```

正式模块：

```text
engine/app/breakdown_p2_refinement_v1.py
profile = breakdown-p2-contextual-shot-refinement-e3-v1
input schema = breakdown-p2-contextual-refinement-input-v1

scripts/run_breakdown_refinement_qwen3.py
prompt profile = breakdown-p2-contextual-shot-refinement-zh-v1

engine/app/breakdown_p2_vlm_runtime_v1.py
= stable production composite E2 → E3 Provider
```

### 4.1 为什么 E3 不做成第四个 P2 Provider

Frozen P2 component contract 仍是：

```text
ASR / OCR / VLM
```

E3 属于 VLM 的“上下文精修”阶段，而不是新的 raw modality。把它放在稳定 VLM runtime 内可以保持：

```text
API 不变
pipeline provider order 不变
P2 sidecar schema 不变
E1 Fusion/P1/P3/P4 reader 不变
```

生产 VLM 一次 `analyze()` 的逻辑现在是：

```text
E2 window visual inference
→ build E3 context from already-registered ASR/OCR + E2
→ E3 text-only Qwen refinement
→ persist one final immutable VLM sidecar
```

### 4.2 每个 Shot 的 E3 输入

E3 对每个 exact frozen Shot 构造：

```text
provisional Scene context
+ previous Shot E2 semantic
+ current Shot E2 semantic
+ next Shot E2 semantic
+ selected/supporting E2 window summaries
+ neighborhood-overlapping ASR_SEGMENT
+ neighborhood-overlapping OCR_OBSERVATION
```

邻域默认使用 Previous → Current → Next 的 Episode-time 范围。ASR/OCR 使用原始 source-us 范围筛选，绝不按 Shot 边界重写原文本。

### 4.3 E3 是 text-only，而不是第二次看视频

E2 已经看过连续视频窗口。E3 的职责是“利用已有视觉理解 + 剧情上下文，把当前 Shot 写准确”，不是再次解码视频发现新物体。

因此 Prompt 明确：

```text
只精修 current_shot
previous/next/window 只能解释上下文
不能把邻 Shot 独有的人/物搬进 current Shot
ASR_SEGMENT = read-only dialogue truth
OCR = read-only text observation
不能猜 speaker identity
current E2 subject labels = 唯一允许的 subject labels
scene UNKNOWN 只有在上下文支持时才能补全
景别/运镜/构图优先 current E2 视觉观察
不生成 Final ID
所有新描述用简体中文
```

### 4.4 输出白名单与保守合并

E3 输出再次经过旧 VLM `_normalize_semantic()` 白名单，因此未知字段、Final business ID、任意 chain-of-thought 字段都会被丢弃。

人物标签还增加一层约束：E3 只允许更新 current E2 已有的 `subject_*`，不允许从邻镜头新增 subject。

如果 E3 某个 Shot 输出失败/无效：

```text
该 Shot → FALLBACK_E2
保留 E2 semantic
记录 warning + contextual_refinement.status
```

如果整个 E3 runtime 缺失或整体 inference 失败：

```text
production VLM Provider = FAILED
pipeline fail closed
```

这避免“系统声称已经跑 E3，但实际静默退回整集 E2”成为新的隐性质量问题。

### 4.5 最终 sidecar 怎么保存

最终仍只有一个 immutable `VLM_OUTPUT` sidecar：

```text
source_type = VLM_OUTPUT
source_id = E2 exact-Shot source id
shot_revision_item_id = exact frozen item
source_start_us/end_us = exact Shot range

payload.semantic = E3 refined semantic        # existing Fusion consumes this
payload.e2_semantic = original E2 semantic    # visual baseline preserved
payload.episode_window = E2 selected/supporting window provenance
payload.contextual_refinement = E3 provenance
```

Provider metadata 同时记录：

```text
contextual_refinement_profile
contextual_refinement_prompt_profile
contextual_refinement_status
contextual_refinement_provider
contextual_refinement_version
e2_semantic_preservation
fusion_semantic_source
```

这样 E3 没有破坏 immutable Evidence 原则：**新 Run 一次生成并一次固化最终 sidecar；历史 Run 永不改写。**

## 5. P2-E4 — final Episode-context Fusion

状态：

```text
PLANNED / NEXT
```

目前 E1 Fusion 会直接消费 `payload.semantic`，因此已经自动获得 E3 refined Shot semantics；但 Scene / anonymous-subject continuity 的融合规则仍主要是 E1 的保守启发式。

E4 目标：

```text
E2 explicit scene_continuity / scene_basis / window summaries
+ E3 refined Shot semantic
+ Episode ASR/OCR
→ primary Episode-time Scene continuity
→ stronger anonymous-subject continuity hints
→ final Shot projections
```

E1 的“UNKNOWN 就继承”退为 fallback，而不是主判断。

长期语义模型：

```text
Scene = Episode-time range spanning multiple Shots
Dialogue = Episode-time range spanning one or more Shots
LocalSubject = Scene/window scoped anonymous continuity
Shot = 上述信息在切镜区间内的展示/检索投影
```

长期原则：

```text
看不出来 != 换场
切镜 != 对白断句
人物暂时出画 != 从剧情上下文消失
Shot boundary != semantic context boundary
```

## 6. 当前生产真值

```text
Shot Detection                    = Reference Video V2
ASR                               = Episode-level
OCR                               = observation provider
VLM E2                            = overlapping Episode windows
VLM E3                            = contextual per-Shot refinement
Production VLM sidecar            = E2 preserved + E3 semantic
Fusion                            = P2-E1 Episode-context Fusion v2
P2-E4 final Episode Fusion        = NOT IMPLEMENTED
P2.6 real-model acceptance        = NOT PASSED
```

因此准确说法是：

> **连续窗口视觉理解 E2 与上下文镜头精修 E3 已进入生产代码，但真实 Windows/Qwen 短剧效果尚未验收；最终 E4 Episode-context Fusion 仍未完成。**

不能说“整套 Episode-context 拉片已经 PASS/关闭”。

## 7. 测试与验收

当前单元覆盖：

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
engine/tests/v2/test_breakdown_p2_refinement_v1.py
```

E3 测试覆盖：

```text
Previous/Current/Next + Scene + window + ASR/OCR context construction
Final ID / unknown-field whitelist
禁止 E3 新增 current Shot 不存在的 subject label
保留 payload.e2_semantic
保留 ASR/OCR provenance ids
单 Shot E3 失败 → explicit FALLBACK_E2
E2→E3 adapter 保持原 VLM source ids/exact Shot anchors
stable runtime = E2 subclass + E3 composite
```

本 connector 会话在远程提交前对 E3 新文件做过 Python syntax compile，但无法运行用户本机完整 pytest/Qwen/CUDA，因此代码存在不等于真实模型质量通过。

真实短剧重测必须至少检查：

```text
1. 大全景 → 特写 → 插入 → 特写仍保持正确 Scene
2. 特写自身看不到背景时 E2 scene_basis 能体现 CONTEXT/MIXED
3. 明确换场仍能被识别，不能因为“连续性”而过度合并
4. E3 当前 Shot 描述是否更符合前后剧情，但不能出现邻镜头独有的人/物
5. 同一匿名人物的当前镜头动作/外观描述是否更稳定
6. 关键道具叙事作用是否更准确，但不能由对白凭空生成视觉存在
7. 跨镜对白仍保持 E1 的完整 ASR_SEGMENT 真值，E3 不改 ASR 文本
8. VLM_OUTPUT exact Shot anchor / P1 validator / lifecycle 不退化
9. Character V10.1 / Final Asset tables 不被 E2/E3 写入
```

E2/E3 本地真实行为稳定后进入 P2-E4；P5 Character safe integration 继续暂停，直到 Episode-context semantic baseline 足够稳定。
