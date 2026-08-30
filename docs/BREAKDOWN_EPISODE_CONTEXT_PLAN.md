# AI Drama Studio — 整集上下文拉片 / Episode-context Breakdown

> **Status:** TARGET PRINCIPLES RETAINED / EXECUTION SUPERSEDED BY FAST GROUNDED V2  
> **Accepted:** 2026-08-28  
> **Fast Grounded supersession:** 2026-08-30  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Architecture:** Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

当前可执行实现优先读取：

```text
docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
engine/app/breakdown_p2_fusion_episode_v4.py
scripts/inspect_breakdown_g1_run.py
```

本文件保留 Episode-context 长期语义原则；旧的 `E2 full Shot semantics -> text-only per-Shot E3` 已退出 production。

## 1. 长期核心原则

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是 AI 连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

硬边界：

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
VLM/Draft != Final business truth
```

## 2. 当前正式流程

```text
Episode 原视频 / proxy / audio
→ Shot Detection + frozen ShotRevision
→ Episode ASR / OCR
→ Fast Grounded VLM
   ├─ overlapping Window Context
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        current-Shot visible facts only from exact frozen Shot images
→ P2-E4 Episode-context Fusion
→ anonymous Breakdown Draft
→ P1 validator
→ human acceptance
→ later asset Evidence verification
→ Final Asset / Binding
```

后续 planned：

```text
Scene + grounded visual facts + ASR + OCR + E4 continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

## 3. Scene / Dialogue rules

Scene：

```text
明确地点 -> current Scene anchor
UNKNOWN / 特写 / 虚化 / 泛化室内 -> inherit current Scene
兼容具体化 -> same Scene
明确地点冲突或 INT↔EXT 强冲突 -> new Scene
看不出来 != 换场
```

Dialogue：

```text
ASR_SEGMENT = Episode-time 对白文本真值
Shot DIALOGUE TimelineEvent = 对白在 Shot 上的投影
```

跨镜一句话保留完整文本与 shared group/projection/continuation metadata；UI 不重复显示 continuation projection。

## 4. 为什么旧 E2/E3 被替换

旧 E2 把连续 window context 与 current-Shot visible truth 混在一起，真实案例中：

```text
Shot0001 实际 = 蓝色玫瑰 / 花瓶
旧 semantic = 邻镜年轻女性面部特写
```

Fast Grounded 改为：

```text
Window -> continuity/context only
Exact Shot -> current visible fact truth
```

旧 E3 是 text-only refinement，却逐 Shot 加载/调用视觉模型；历史 30-Shot Run 中 `30/30 TimeoutExpired`，且无法可靠修正已串错的视觉事实，因此已退出 production。

## 5. P2-E4 anonymous Subject Continuity Graph

生产模块：

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
```

语义：

```text
subject_A/B = Shot-local observation label
anonymous graph node = (ShotRevisionItem, subject label)
LocalSubject = Scene-scoped anonymous continuity cluster
LocalSubject != Character
```

Primary positive edge：Window Context `subject_continuity_hint`。  
Fallback：近邻 Shot 的强稳定外观相似。  
同一 Shot 两个 observations = hard cannot-link。

动态状态不能做 identity key：

```text
表情 / 情绪 / 动作 / 姿态 / 手势 / speaking / screen position / framing
```

## 6. Fast Grounded G1 当前参数

```text
Window target = 24s
Window overlap = 25%
Window FPS = 1.0
Window max pixels = 262144
Exact-Shot frames:
  <1.2s -> 1
  1.2..3s -> 2
  >3s -> 3
Grounding batch = 5 Shots default
Model load = one subprocess / one Qwen3-VL load per Episode run
```

## 7. 当前真实重跑状态

历史 pre-Fast-Grounded Run 仍作为失败基线：

```text
30 Shots
21 LocalSubjects
old Scene04 / 19 Shots -> 14 LocalSubjects
actual cast -> mainly one woman + one man
Shot0001 blue roses/vase -> neighboring woman leakage
multi-hour runtime class
```

Fast Grounded V2 已完成真实重跑。当前 UI：

```text
30 Shots
4 Scenes
Scene01 5 Shots
Scene02 5 Shots
Scene03 2 Shots
Scene04 18 Shots
```

已确认：

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage no longer observed
```

尚未完成：

```text
Scene04 anonymous continuity review
same-Shot cannot-link real review
4 Scene boundary review
whole-run elapsed review
ASR/OCR/VLM timings review
```

所以当前仍是：

```text
Fast Grounded G1 = IMPLEMENTED / LOCAL-REAL PENDING
P2-E4 under grounded input = LOCAL-REAL PENDING
G2 Scene text LLM = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
P2.6 = NOT PASSED
```

## 8. 当前正确的验收动作

不要再次重跑模型来“获取验收信息”。先读取已经完成的 Run：

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

该工具会自动选择 completed Fast Grounded Run，并展示：

```text
Shot0001 final Draft
Scene boundaries
Scene04 LocalSubjects + source_members
same_shot_cluster_conflicts
whole-run elapsed
ASR/OCR/VLM timings
OCR short-noise samples
```

只有当发现具体 G1 问题并修改了 G1 后，才需要重新跑 Episode。

## 9. Performance requirement

Reference：~60 秒 / ~30 Shots / ~4 Scenes。

```text
first target < 30 min total
later target = 10..20 minute class
60s -> 5..6h = FAIL
```

权威整链时间：`BreakdownRun.started_at -> completed_at`。Provider timings 当前只保存 ASR/OCR/VLM。

## 10. Next

```text
inspect existing Fast Grounded Run
→ judge Scene04 anonymous continuity
→ require same_shot_cluster_conflicts=[]
→ judge whether 4 Scene boundaries are real
→ record whole-run + provider timings
→ record OCR noise only
→ if G1 fails: fix G1 and rerun
→ if G1 acceptable: begin G2 Scene-level pure-text LLM
→ P5 stays paused until P2.6 genuinely passes
```
