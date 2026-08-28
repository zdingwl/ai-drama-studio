# AI Drama Studio — 整集上下文拉片 / Episode-context Breakdown

> **Status:** ACCEPTED TARGET / P2-E1 IMPLEMENTED / P2-E2 IMPLEMENTED ON MAIN / LOCAL-REAL ACCEPTANCE PENDING  
> **Accepted:** 2026-08-28  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Architecture:** Reference Video V2 / Breakdown-first / Character V10.1

## 1. 核心产品原则

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

旧逐 Shot 语义存在两个结构性问题：一句对白跨切镜会被错误拆句；同一 Scene 中的特写、背影、插入镜头、虚化背景镜头会因为自己看不清环境而被错误换场。

因此正式目标是：

```text
Episode 原视频 / proxy / audio
→ Shot Detection + ShotRevision（时间坐标）
→ Episode ASR / OCR
→ overlapping continuous-window Video Understanding
→ Scene continuity / Episode context
→ contextual Shot refinement
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

engine/app/breakdown_p2_vlm_runtime_v1.py
= stable production import -> E2 provider
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

自然语言继续要求简体中文；JSON key 与机器枚举保持英文。ASR/OCR 原始文本不在 VLM 中转录或翻译。

### 3.3 多窗口覆盖同一个 Shot

同一 Shot 可能同时出现在多个重叠 window。E2 不简单“最后一个覆盖前一个”，而是选择拥有最多前后上下文的候选：

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

因此后续 E3 可以知道“这个场景判断是当前镜头自己看出来的，还是主要借前后镜头得出的”。

### 3.4 Contract 兼容

E2 **不修改 frozen P2 sidecar schema**。最终仍向现有 Fusion 输出：

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen ShotRevisionItem
source_start_us / source_end_us = exact Shot range
payload.semantic = existing P2.4 semantic schema
```

所以 E1 Fusion、P1 validator、P3、P4 不需要因 E2 做破坏性迁移。

窗口级信息属于 VLM Provider provenance；历史 BreakdownRun/sidecar 不重写。只有重新运行 AI 拉片的新 Run 才使用 E2。

### 3.5 Runtime

E2 isolated runner：

```text
scripts/run_breakdown_vlm_qwen3_episode_windows.py
```

模型仍只加载一次，然后按 window 串行推理。Windows 默认仍可强制 `decord`，并阻止 qwen-vl-utils 在 decord 失败后用 torchvision fallback 掩盖真正的解码错误。

CLI 新增可选调参：

```text
--vlm-window-seconds 20..40
--vlm-window-overlap-ratio 0.10..0.50
```

## 4. P2-E3 — contextual Shot refinement

状态：

```text
PLANNED / NEXT AFTER E2 LOCAL-REAL CHECK
```

E2 已经给 Shot 视觉上下文，但还没有把 ASR/OCR/Scene 上下文重新用于一次明确的 Shot refinement。E3 目标输入：

```text
current Scene context
+ previous/current/next Shot
+ selected/supporting E2 windows
+ overlapping Episode ASR
+ overlapping OCR
```

目标输出仍是用户真正需要的镜头级结果：画面、匿名人物 presence、动作、对白投影、关键道具、景别、运镜、叙事作用。

## 5. P2-E4 — final Episode-context Fusion

状态：

```text
PLANNED
```

E4 会让连续窗口 Evidence 成为 Scene/anonymous-subject continuity 的主要证据，E1 的“未知就继承”退为保守 fallback。

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
OCR                               = existing observation provider
VLM                               = P2-E2 overlapping Episode windows
Fusion                            = P2-E1 Episode-context Fusion v2
P2-E3 contextual shot refinement  = NOT IMPLEMENTED
P2-E4 final Episode Fusion        = NOT IMPLEMENTED
P2.6 real-model acceptance        = NOT PASSED
```

因此可以准确说：

> **连续窗口视觉理解 E2 已进入生产代码，但真实 Windows/Qwen 短剧效果尚未验收；E3/E4 仍未完成。**

不能说“整套 Episode-context 拉片已经 PASS/关闭”。

## 7. 测试与验收

新增单元覆盖：

```text
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
```

覆盖目标：窗口按 Shot 对齐并重叠、所有 Shot 有覆盖、多窗口选择最强上下文、最终仍输出 exact-shot `VLM_OUTPUT`、Final Asset ID/未知模型字段被 whitelist 丢弃、无 Episode 视频时 fail closed、稳定 runtime import 已切到 E2。

本 connector 会话无法运行用户本机 pytest/Qwen/CUDA，因此代码存在不等于真实模型质量通过。

真实短剧重测必须至少检查：

```text
1. 大全景 → 特写 → 插入 → 特写仍保持正确 Scene
2. 特写自身看不到背景时 scene_basis 能体现 CONTEXT/MIXED
3. 明确换场仍能被识别，不能因为“连续性”而过度合并
4. 同一人物跨相邻镜头的外观/动作描述更稳定，但不能越过匿名身份边界
5. 关键道具跨镜连续性更稳定
6. 跨镜对白仍保持 E1 的完整 ASR_SEGMENT 真值
7. VLM_OUTPUT 仍 exact Shot bound，P1 validator/lifecycle 不退化
8. Character V10.1 / Final Asset tables 不被 E2 写入
```

E2 本地真实行为稳定后进入 P2-E3；P5 Character safe integration 继续暂停，直到 Episode-context semantic baseline 足够稳定。
