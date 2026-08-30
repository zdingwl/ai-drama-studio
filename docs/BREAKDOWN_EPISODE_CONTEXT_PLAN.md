# AI Drama Studio — 整集上下文拉片 / Episode-context Breakdown

> **Status:** TARGET PRINCIPLES RETAINED / EXECUTION SUPERSEDED BY FAST GROUNDED V2  
> **Accepted:** 2026-08-28  
> **Fast Grounded supersession:** 2026-08-30  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Architecture:** Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

当前可执行实现请优先读取：

```text
docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
scripts/run_breakdown_vlm_fast_grounded_qwen3.py
engine/app/breakdown_p2_fusion_episode_v4.py
```

本文件保留 Episode-context 的长期语义原则和 E1/E4 历史背景；旧的“E2 full Shot semantics -> text-only per-Shot E3”不再是 production truth。

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
        visible facts only from current frozen Shot images
→ P2-E4 Episode-context Fusion
→ anonymous Breakdown Draft
→ P1 validator
→ human acceptance
→ 03 资产 Evidence 验证
→ Final Asset / Binding
```

后续 planned：

```text
Scene + grounded visual facts + ASR + OCR + E4 continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

## 3. E1 Scene / Dialogue rules（仍有效）

Scene：

```text
明确地点 -> current Scene anchor
UNKNOWN / 特写 / 虚化 / 泛化“室内/房间” -> 继承 current Scene
兼容具体化 -> same Scene
明确地点冲突或 INT ↔ EXT 强冲突 -> new Scene
```

Rule: `看不出来 != 换场`.

Dialogue：

```text
ASR_SEGMENT = Episode-time 对白文本真值
Shot DIALOGUE TimelineEvent = 对白在 Shot 上的投影
```

跨镜一句话保留完整文本和 shared dialogue group/projection/continuation metadata。UI 不重复显示 continuation projection。

## 4. 为什么旧 E2 full-Shot Window 输出被替换

旧 E2 使用 overlapping continuous-window Qwen3-VL，同时要求一个 window 生成每个 Shot 的：

```text
scene / shot / subjects / events / props
```

真实案例暴露：

```text
Shot 0001 实际只有蓝色玫瑰/花瓶
旧 window semantic 却写成邻镜“年轻女性面部特写，表情惊讶”
```

原因不是“没有连续上下文”，而是连续上下文和 exact-Shot visible truth 没有分层。

Fast Grounded 改为：

```text
Window -> context/continuity only
Exact Shot -> visible fact truth
```

## 5. 为什么旧 E3 被退出 production

旧 E3 是 text-only contextual refinement，但继续加载 Qwen3-VL 并逐 Shot 调用。

真实 30-Shot Run：

```text
30/30 TimeoutExpired
全部 FALLBACK_E2
```

同时 E3 不重新看 exact Shot，因此无法可靠修复 E2 已经串错的视觉事实。

当前决定：

```text
legacy E3 modules = historical comparison/tests only
G1 Exact-Shot Grounding = current visual correction layer
G2 Scene-level pure-text LLM = planned language organization layer
```

## 6. P2-E4 anonymous Subject Continuity Graph（仍有效）

生产模块：

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
```

语义：

```text
Shot-local subject_A/B = current Shot observation label
anonymous graph node = (ShotRevisionItem, subject label)
LocalSubject = Scene-scoped anonymous continuity cluster
LocalSubject != Character
```

Primary positive edge：Window Context `subject_continuity_hint`。

Fallback：相邻/近邻 Shot 的强稳定外观相似。

动态状态不能做身份 key：

```text
表情 / 情绪 / 动作 / 姿态 / 手势 / speaking / screen position / framing
```

同一 Shot 两个 observations = hard cannot-link，且通过 union graph 传递安全。

## 7. Fast Grounded G1 当前参数

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

详细 Contract、速度预算和验收见 `docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md`。

## 8. Performance requirement

Reference：60 秒 / ~30 Shots / ~4 Scenes。

```text
first target < 30 min total
later target = 10..20 minute class
60s -> 5..6h = FAIL
```

这些是工程预算，必须用 Windows/CUDA 实测确认，不能由代码存在自动变成 PASS。

## 9. 当前验收真值

```text
latest real run = REJECTED (pre Fast Grounded)
Fast Grounded G1 = IMPLEMENTED / LOCAL-REAL PENDING
P2-E4 under grounded input = LOCAL-REAL PENDING
G2 Scene text LLM = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
P2.6 = NOT PASSED
```

下一真实 Run 必须先验证：

```text
Shot 0001 蓝玫瑰不串入邻镜女性
closeup/insert Scene continuity 不回退
真实换场仍正确
Scene 04 / 19 Shots / 一女一男 -> roughly 2 LocalSubjects
same-Shot cannot-link 保持
跨镜对白保持完整且 UI 不重复
实际耗时显著下降
Character V10.1 / Final Asset 不被 Breakdown 写入
```

## 10. Next

```text
git pull
→ 同一个失败 Episode 重新拉片
→ 先看 Shot 0001
→ 再看 Scene 04 anonymous continuity
→ 记录时间
→ G1 有问题先修 G1
→ G1 通过后再实现 G2 Scene LLM / Scene Timeline UI
→ P5 继续暂停直到 P2.6 真 PASS
```
