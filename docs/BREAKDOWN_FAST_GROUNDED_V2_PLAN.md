# Breakdown Fast Grounded V2 — 准确率与速度基线

> Status: **APPROVED BASELINE / G1 FAST GROUNDED VLM IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING**  
> Date: 2026-08-30  
> Repository: `zdingwl/ai-drama-studio`  
> Production safety: `LocalSubject != Character`; no Final Asset truth in Breakdown.

## 1. 为什么重构

最近真实短剧验收暴露了三个结构性问题：

```text
1. 1 分钟视频可能运行 5~6 小时，性能不可接受
2. 连续窗口把邻镜人物/动作串进当前 Shot，例如蓝玫瑰特写被写成女性面部特写
3. 结果页更像“逐 Shot 数据卡”，不是真正可连续阅读的 Scene 拉片稿
```

旧生产链：

```text
Episode ASR
→ OCR
→ 24s overlapping Qwen3-VL windows
   └─ 每个 window 同时生成大量逐 Shot 完整 semantic
→ text-only per-Shot E3 (Qwen3-VL 再跑一遍文字精修)
→ E4 Fusion
```

问题在于：

- rapid-cut window 为了输出很多 Shot JSON 会重复对同一段视频推理；
- E3 明明是纯文本任务却继续加载视觉模型，并且逐 Shot 调用；
- window context 与 exact-Shot visible truth 混在同一个模型输出中。

## 2. 新核心原则

> **昂贵的视频大模型只做必须做的连续上下文理解，而且每段视频只编码一次。**

> **Exact Shot 图片是真实可见事实的最高优先级；Window Context 只能补 Scene，不得补人物、动作、道具和画面。**

> **Shot 是最小视觉证据与定位单位；Scene Timeline 是用户阅读拉片结果的主要单位。**

保持：

```text
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / history
integer microseconds
ASR/OCR raw Evidence
E4 anonymous continuity
Character V10.1 Final Gate
```

## 3. 新生产目标链

```text
Original Episode
↓
TransNetV2 Shot Detection + ShotRevision
↓
Episode ASR (faster-whisper)
+
OCR (RapidOCR)
↓
G1 Fast Grounded VLM
├─ A. Window Context
│    24s target / 25% overlap
│    1 FPS / ~262k max pixels
│    only Scene + subject/prop continuity
│
└─ B. Exact-Shot Grounding
     <1.2s  -> 1 frame
     1.2~3s -> 2 frames
     >3s    -> 3 frames
     5 Shots/batch default
     exact Shot frames own visible truth
↓
E4 Anonymous Subject Continuity Graph
↓
Scene segmentation / Episode Fusion
↓
G2 Scene-level pure-text LLM (next phase)
↓
Scene Timeline Breakdown
↓
Result UI
```

G1 Window + Exact-Shot Grounding 在同一个隔离 Qwen3-VL 子进程内完成：

```text
start subprocess once
→ load Qwen3-VL once
→ Window 1
→ Window 2
→ Window 3
→ Exact-Shot batch 1
→ Exact-Shot batch 2
→ ...
→ write JSONL
→ exit
```

禁止旧行为：同一个 24 秒视频为了 Shot 1~6、7~12、13~18 重复进行完整视频编码。

## 4. G1 Window Context 职责

Window Context 只允许输出：

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

不再要求它输出每个 Shot 的完整：

```text
visual_description
subjects
current action
events
props
shot framing
```

Window 的任务是：

```text
切镜是不是换场？
人物是否是跨镜连续的匿名人物？
剧情相关道具是否连续？
特写/虚化镜头属于哪个 Scene？
```

默认参数第一版：

```text
window target = 24s
window overlap = 25%
window fps = 1.0
window max pixels = 262144
window max new tokens = 1600
```

## 5. G1 Exact-Shot Grounding 职责

每个 frozen Shot 从自己的 Reference Clip 抽取少量图片：

```text
shot duration < 1.2s
→ 50% 位置 1 张

1.2s <= duration <= 3s
→ 25% + 75% 位置 2 张

duration > 3s
→ 15% + 50% + 85% 位置 3 张
```

Exact-Shot 负责：

```text
shot.summary 的可见部分
shot.visual_description
shot_type_hint
composition_hint
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Window Context 只能补：

```text
scene.location_hint
scene.interior_exterior
scene.time_of_day
scene.environment_description
```

硬优先级：

```text
Exact-Shot visible fact > Window Context
```

示例：

```text
Window：后续是女性在客厅争执
Exact Shot 0001：只有蓝色玫瑰花束

正确：
subjects=[]
props=[蓝色玫瑰]
visual_description=蓝色玫瑰插在玻璃花瓶中
scene=客厅（允许从上下文继承）

错误：
年轻女性面部特写，表情惊讶
```

## 6. 当前 G1 实现

新增：

```text
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
scripts/run_breakdown_vlm_fast_grounded_qwen3.py
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
```

稳定生产入口 `engine/app/breakdown_p2_vlm_runtime_v1.py` 已切到 Fast Grounded Provider。

为了保持现有 P2 Contract / E4 / API：

```text
one exact Shot -> one VLM_OUTPUT
shot_revision_item_id = exact frozen item
source_start_us/end_us = exact Shot range
payload.semantic = grounded semantic consumed by Fusion
metadata.window_summaries = continuity context consumed by E4
```

旧 E2/E3 文件暂时保留用于历史比较与测试，但 **text-only per-Shot E3 不再是生产执行步骤**。

## 7. G2 纯语言模型（下一阶段）

G2 不负责看视频，不负责创造视觉事实。

输入：

```text
Scene
+ exact-Shot grounded visual facts
+ ASR_SEGMENT truth
+ OCR truth
+ E4 LocalSubject continuity
+ prop continuity
```

输出：

```text
Scene Timeline Breakdown
```

目标展示：

```text
场景 01 · 内 · 日 · 走廊                     00:00–00:22
人物：人物A、人物B
道具：蓝玫瑰

[00:00] 镜头特写——玻璃花瓶中插着一束蓝色玫瑰。
[00:01] 镜头切到走廊，人物A拎着黑色塑料袋站在人物B面前。

人物A（质问）[00:01]
我刚到的花怎么又在你家花瓶里？

人物B（理直气壮）[00:04]
这花就在走廊，怎么就是你的了？

[00:16] 人物A伸手要钱。
```

推荐第一版使用本地纯文本 Qwen3 4B 级模型；若单 GPU 显存紧张，可用量化模型在 CPU/llama.cpp 运行。Scene-level 调用，不逐 Shot 调用。

## 8. 性能预算

标准验收素材：

```text
60 秒
约 30 Shots
约 4 Scenes
```

第一目标：

```text
Shot/media preparation   < 2 min
ASR                       < 3 min
OCR                       < 2 min
Window Context VLM        < 8 min
Exact-Shot Grounding      < 8 min
E4/Fusion                 < 1 min
Scene LLM (G2)            < 3 min
other IO                  < 2 min
--------------------------------
total first target        < 30 min
```

第二目标：

```text
60s video -> 10~20 min class
```

`60s -> 5~6h` 一律视为性能不合格，不能作为正常生产状态接受。

具体耗时必须由 Windows + CUDA + 本机 checkpoint 真实日志确认，文档预算不是 PASS 证明。

## 9. 缓存策略

每层独立 fingerprint，避免改一个 Prompt 重跑全部模型：

```text
Shot cache
= video hash + detector/model params

ASR cache
= audio hash + ASR model/params

OCR cache
= frame hash + OCR model/params

Window Context cache
= source video hash + window range + VLM + context prompt + fps/pixels

Exact-Shot cache
= ShotRevisionItem + sampled frame hashes + VLM + grounding prompt

E4 cache
= grounded semantics + continuity hints + graph policy

Scene Timeline cache (G2)
= Scene input hash + text LLM + prompt
```

前端排版变化不得触发任何模型重跑。

## 10. 验收顺序

G1 真实验收必须先检查：

```text
1. Shot 0001 蓝玫瑰特写：subjects 必须为空，不能串入下一镜女性
2. Scene continuity：特写/虚化背景仍能继承正确 Scene
3. 真正换场仍能正确切开
4. 19-Shot 客厅：匿名人物连续性仍收敛到真实一女一男附近
5. same-Shot cannot-link 不回退
6. ASR 跨镜完整对白不回退
7. 60 秒真实运行耗时显著下降，并记录各阶段 elapsed time
```

在 G1 未通过前，不实施 P5 Final Character 绑定，也不把 G2/UI 的漂亮排版误认为拉片质量 PASS。

## 11. 状态边界

当前：

```text
Fast Grounded baseline = APPROVED
G1 code = IMPLEMENTED
G1 local-real = PENDING
G2 Scene LLM = PLANNED / NOT IMPLEMENTED
Scene Timeline UI = PLANNED / NOT IMPLEMENTED
P2.6 = NOT PASSED
```

Hosted GitHub Actions 继续不使用；提交使用 `[skip ci]`。本地 pytest/Qwen/CUDA 未实际运行时不得声称 PASS。
