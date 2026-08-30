# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 CONDITIONAL PASS / FAST GROUNDED G1 IMPLEMENTED / LOCAL-REAL NOT PASSED**  
> Date: 2026-08-30  
> Production pipeline: `breakdown-p2-full-v1`  
> Production G1 VLM: `breakdown-p2-vlm-fast-grounded-v1`  
> Production E4 Fusion: `breakdown-p2-fusion-episode-context-e4-v1`  
> Legacy text-only E3: **RETIRED FROM PRODUCTION**

## 1. 当前验收结论

```text
P1/P2 实现验收                         = CONDITIONAL PASS
Fast Grounded G1                       = IMPLEMENTED / LOCAL-REAL PENDING
P2-E4 Episode-context Fusion           = IMPLEMENTED / LOCAL-REAL PENDING
legacy text-only per-Shot E3           = RETIRED FROM PRODUCTION
G2 Scene-level text LLM                = PLANNED / NOT IMPLEMENTED
Scene Timeline UI                      = PLANNED / NOT IMPLEMENTED
P2.6 Windows / 真实模型验收             = NOT PASSED
完整真实短剧 PASS report                = 尚不存在
```

历史 pre-Fast-Grounded Run 是失败基线：

```text
30 Shots
21 LocalSubjects
old Scene04 / 19 Shots -> 14 LocalSubjects
visible cast -> mainly one woman + one man
Shot0001 actual -> blue roses / glass vase
old VLM -> neighboring young woman leakage
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute video -> multi-hour runtime class
```

最新 Fast Grounded V2 **已经完成真实重跑**。当前 UI：

```text
30 Shots
4 Scenes
Scene01 5 Shots
Scene02 5 Shots
Scene03 2 Shots
Scene04 18 Shots
```

已人工确认一个正向门：

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage no longer observed
```

因此当前状态不是“等待重新跑”，而是“**对已经完成的 Fast Grounded Run 做剩余真实验收**”。

## 2. 当前正式生产链

```text
Episode Current ShotRevision
→ frozen BreakdownRun
→ Episode ASR
→ OCR
→ G1 Fast Grounded Qwen3-VL（同一进程只加载一次模型）
   ├─ Window Context
   │    24s / 25% overlap / 1 FPS / 262144 max pixels
   │    only Scene + subject/prop continuity
   └─ Exact-Shot frame grounding
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
        current-Shot visible facts only from its own frames
→ immutable exact-Shot VLM_OUTPUT sidecar
→ E4 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
→ human acceptance
```

## 3. 当前验收入口

不要为了看验收数据再次跑模型。先执行：

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

该命令会：

```text
1. 自动寻找本地最近完成的 Fast Grounded BreakdownRun
2. 校验 production_vlm_profile = breakdown-p2-vlm-fast-grounded-v1
3. 拒绝旧 E2/E3 / unfinished Run
4. 读取现有 Draft，不重新运行 ASR/OCR/VLM
5. 默认写完整 JSON acceptance artifact
6. 在终端输出一屏 summary
```

可选：

```powershell
python scripts/inspect_breakdown_g1_run.py --episode-id <EPISODE_ID> --summary
python scripts/inspect_breakdown_g1_run.py --run-id <RUN_ID> --summary
```

## 4. Shot0001 Exact-Shot 回归

当前真实素材 Shot0001 是蓝色玫瑰 / 玻璃花瓶特写。

本轮已看到：

```text
subjects=[]
visual truth = flowers/vase
neighbor woman leakage = not observed
```

这项可记为正向结果，但不能据此自动 PASS 整个 G1。

## 5. Scene04 匿名人物连续性

当前 Fast Grounded UI 的 Scene04 是 **18 Shots**，不要再把历史 19-Shot 数量当作本轮硬事实。

真实主要人物仍是：

```text
one woman + one man
```

重点读取 summary/JSON：

```text
scene_04_focus.local_subject_count
scenes[Scene04].local_subjects[].shot_ordinals
scenes[Scene04].local_subjects[].source_members
scenes[Scene04].local_subjects[].source_members[].source_label
same_shot_cluster_conflicts
```

判断原则：

```text
roughly 2 stable LocalSubjects = expected direction
subject_A/B label swap must not create new people
action/emotion/pose/speaking change must not create new people
same-Shot two people must never merge
real new person must remain separate
```

`roughly 2` 是人类验收方向，不是把机器硬编码成“必须等于 2”。

任何 `same_shot_cluster_conflicts != []` 都是 hard safety regression，应先修 G1/E4。

## 6. Scene 连续性验收

当前 UI 显示：

```text
Scene01 = 5 Shots
Scene02 = 5 Shots
Scene03 = 2 Shots
Scene04 = 18 Shots
```

这只是当前机器分段结果，不等于四个 Scene 已人工接受。

逐个检查：

```text
location_hint
interior_exterior
time_of_day
shot_ordinals
source_start_us / source_end_us
```

规则：

```text
UNKNOWN / generic / closeup / background-poor -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction -> new Scene
explicit INT ↔ EXT contradiction -> new Scene
看不出来 != 换场
```

特别检查“公寓走廊 / 公寓楼道 / hallway / corridor”是否因文字同义词被重复拆场。若语义上是同一连续空间但被拆成多个 Scene，这是 G1 Scene continuity 问题，不能交给 G2/UI 掩盖。

## 7. Dialogue 回归

```text
ASR_SEGMENT = Episode-time dialogue truth
Shot DIALOGUE TimelineEvent = projection
```

跨镜一句对白应保留完整 ASR truth 和 projection/continuation metadata。UI 不应把 continuation 当成新的重复台词。

## 8. Runtime / 性能验收

参考素材：

```text
~60 秒 / ~30 Shots / ~4 Scenes
```

标准：

```text
first target: whole Breakdown < 30 min
second target: 10..20 min class
5..6h = FAIL
```

权威整链时间：

```text
BreakdownRun.started_at -> BreakdownRun.completed_at
```

诊断输出：

```text
runtime.total_elapsed_seconds
runtime.total_elapsed_minutes
runtime.targets.under_30_minutes
runtime.targets.at_or_below_20_minutes
runtime.provider_timings_seconds
```

注意：`provider_timings_seconds` 当前只保存 ASR/OCR/VLM。`total_elapsed` 还包含 Fusion / validator / IO，所以不能把 provider 三项相加当作整链时间，也不能把 residual 简单命名成“Fusion 精确耗时”。

## 9. OCR 本轮只记录

记录：

```text
ocr_record_only.ocr_event_count
ocr_record_only.short_text_samples
```

例如：

```text
人
人民
副
V
```

本轮不优先做 OCR 去噪，除非 OCR 已经直接污染核心 Scene/subject truth。后续再单独做去重、单字噪声、字幕/环境文字分类。

## 10. Identity / Final Asset 禁止事项

```text
LocalSubject != Character
subject continuity hint != ReID evidence
ASR speaker != Character
Draft Scene/Prop != Final Scene/Prop
```

Character V10.1 的 Person Evidence / MOT / YoutuReID / same-sample cannot-link / face hard conflict / >=3 independent Shots/images / explicit Shot assignment / Final Gate 全部保持不变。

## 11. G1 决策门

必须至少完成三项人工判断：

```text
A. Scene04 anonymous continuity acceptable
B. Scene continuity / boundaries acceptable
C. real whole-run runtime acceptable
```

并要求：

```text
Shot0001 remains correct
same_shot_cluster_conflicts=[]
```

如果任一核心门失败：

```text
fix that G1 layer
→ then rerun the Episode to produce new inference evidence
→ inspect again
```

如果核心门基本通过：

```text
G1 can move toward accepted
→ then begin G2 Scene-level pure-text LLM
→ then Scene Timeline result surface
```

机器统计不会自动把 `P2.6` 改成 PASS，最终仍需要 human acceptance report。

## 12. G2 当前不验收

```text
Scene
+ Exact-Shot grounded visual facts
+ ASR
+ OCR
+ E4 LocalSubjects
+ prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

G2 不负责看视频，也不能创造新的视觉事实或 Final identity。

## 13. 测试 / CI

当前相关 repository coverage：

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
engine/tests/v2/test_breakdown_g1_acceptance_diagnostics_v1.py
engine/tests/v2/test_breakdown_g1_run_selector_v1.py
engine/tests/v2/test_breakdown_g1_acceptance_summary_v1.py
```

Hosted GitHub Actions 不使用。代码/测试文件存在不等于本机 pytest/Qwen/CUDA PASS。

## 14. 现在应该做什么

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

然后只做判断：

```text
Scene04 人物是否收敛
same-Shot 是否安全
4 Scenes 是否合理
整链耗时是否达标
OCR 噪声记录
```

**没有修改 G1 就不要无意义再次重跑模型。**
