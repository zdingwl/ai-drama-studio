# Breakdown Fast Grounded V2 — 准确率与速度基线

> Status: **APPROVED BASELINE / G1 IMPLEMENTED / REAL RERUN COMPLETED / LOCAL-REAL ACCEPTANCE PENDING**  
> Date: 2026-08-30  
> Repository: `zdingwl/ai-drama-studio`  
> Production safety: `LocalSubject != Character`; no Final Asset truth in Breakdown.

## 1. 为什么重构

历史真实短剧 Run 暴露三个结构问题：

```text
1. ~1 分钟视频可能运行 5~6 小时，性能不可接受
2. 连续 window 把邻镜人物/动作串进当前 Shot，例如蓝玫瑰特写被写成女性面部特写
3. 结果页更像逐 Shot 数据卡，不是真正可连续阅读的 Scene 拉片稿
```

旧生产链：

```text
Episode ASR
→ OCR
→ overlapping Qwen3-VL windows 输出完整逐 Shot semantics
→ text-only per-Shot E3 再加载视觉模型逐 Shot 精修
→ E4 Fusion
```

Fast Grounded V2 的结构修正：

```text
Window Context -> 连续理解
Exact-Shot frames -> 当前镜头可见事实
E4 -> 匿名人物/Scene/对白 Fusion
G2 later -> Scene-level pure-text organization
```

## 2. 核心原则

> **昂贵的视频大模型只做必须做的连续上下文理解，而且每段 window 只编码一次。**

> **Exact Shot 图片是真实可见事实的最高优先级；Window Context 只能补 Scene/continuity，不得创造当前镜人物、动作、道具和画面事实。**

> **Shot 是最小视觉证据与定位单位；Scene Timeline 是最终用户阅读拉片结果的主要单位。**

保持：

```text
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / history
integer microseconds
ASR/OCR raw Evidence
E4 anonymous continuity
Character V10.1 Final Gate
```

## 3. 当前生产链

```text
Original Episode
→ TransNetV2 Shot Detection + frozen ShotRevision
→ Episode ASR (faster-whisper)
→ OCR (RapidOCR)
→ G1 Fast Grounded VLM
   ├─ Window Context
   │    24s target / 25% overlap
   │    1 FPS / 262144 max pixels
   │    Scene + subject/prop continuity only
   └─ Exact-Shot Grounding
        <1.2s  -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        5 Shots/batch default
        exact Shot frames own visible truth
→ P2-E4 anonymous Subject Continuity Graph + Scene/Dialogue Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Window + Exact-Shot Grounding 在同一个隔离 Qwen3-VL 子进程内完成：

```text
start subprocess once
→ load Qwen3-VL once
→ Window 1..N
→ Exact-Shot batch 1..N
→ write JSONL
→ exit
```

禁止为了输出不同 Shot JSON batch 重复编码同一个 24 秒 window。

## 4. Window Context 职责

只允许输出：

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

它回答：

```text
cut 是不是实际换场？
人物是否跨镜连续？
关键道具是否连续？
特写/虚化 Shot 属于哪个 Scene？
```

它不负责 current-Shot final visual truth。

## 5. Exact-Shot Grounding 职责

抽帧：

```text
<1.2s -> 50% 位置 1 张
1.2..3s -> 25% + 75% 两张
>3s -> 15% + 50% + 85% 三张
```

Exact-Shot 负责：

```text
shot.summary visible content
shot.visual_description
shot_type_hint / composition_hint
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Window 只可保守补 Scene：

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

## 6. 当前真实重跑结果

历史失败基线：

```text
30 Shots
old Scene04 / 19 Shots -> 14 LocalSubjects
actual cast -> mainly one woman + one man
Shot0001 blue roses/vase -> old result leaked neighboring woman
legacy E3 -> 30/30 TimeoutExpired
runtime -> multi-hour class
```

Fast Grounded V2 已完成同一类真实素材重跑。当前 UI：

```text
30 Shots
4 Scenes
5 / 5 / 2 / 18 Shots
```

已确认：

```text
Shot0001 blue roses / glass vase = correct
subjects=[]
neighbor woman leakage = not observed
```

这证明 Exact-Shot 可见事实边界至少在该回归镜头上明显改善，但**不能自动宣布 G1 PASS**。

仍需读取同一个完成 Run 的：

```text
Scene04 LocalSubjects + source_members
same_shot_cluster_conflicts
Scene boundaries + location hints
whole-run elapsed
ASR/OCR/VLM timings
OCR short-noise samples
```

## 7. 当前验收工具

```text
engine/app/breakdown_g1_acceptance_diagnostics_v1.py
engine/app/breakdown_g1_run_selector_v1.py
engine/app/breakdown_g1_acceptance_summary_v1.py
scripts/inspect_breakdown_g1_run.py
```

本机推荐：

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

`--latest` 只会选择 completed Fast Grounded Run。该工具只读，不会重新运行模型或修改 Draft/Final assets。

**没有 G1 修改时，不要为了验收重复跑模型。**

## 8. G1 真实验收顺序

```text
1. Shot0001 保持 subjects=[]、蓝玫瑰/花瓶可见事实正确。
2. Scene04 当前 18 Shots：主要一女一男应收敛到 roughly 2 stable LocalSubjects。
3. subject_A/B label swap 不得制造新人物。
4. same_shot_cluster_conflicts 必须为空。
5. 检查当前 4 Scene 是否是真换场，尤其 corridor / hallway / living-room 同义地点。
6. 记录 whole-run elapsed 与 ASR/OCR/VLM timings。
7. OCR 噪声只记录，不在本轮抢优先级。
```

`roughly 2` 是 human acceptance direction，不是把 E4 硬编码成必须等于 2。

## 9. 性能预算

参考素材：

```text
~60 秒 / ~30 Shots / ~4 Scenes
```

第一工程目标：

```text
whole Breakdown < 30 min
```

第二目标：

```text
10..20 minute class
```

`5..6h` 一律 FAIL。

权威总耗时：

```text
BreakdownRun.started_at -> completed_at
```

`provider_metadata_json.p2_pipeline.timings_seconds` 当前只保存 ASR/OCR/VLM，不等于整链总时长。

## 10. 缓存方向

每层独立 fingerprint，避免一个 Prompt 改动触发整链无意义重跑：

```text
Shot cache
ASR cache
OCR cache
Window Context cache
Exact-Shot cache
E4 cache
Scene Timeline cache (G2 later)
```

前端排版变化不得触发模型重跑。

## 11. G2（下一阶段，尚未实现）

只有 G1 real acceptance 基本通过后：

```text
Scene
+ exact-Shot grounded visual facts
+ ASR_SEGMENT truth
+ OCR truth
+ E4 LocalSubject continuity
+ prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

G2 不负责看视频，也不能创造视觉事实或 Final identity。

## 12. 状态边界

```text
Fast Grounded baseline = APPROVED
G1 code = IMPLEMENTED
Fast Grounded real rerun = COMPLETED / PARTIAL HUMAN REVIEW
Shot0001 regression gate = POSITIVE
G1 local-real = PENDING
P2-E4 local-real = PENDING
G2 Scene LLM = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
P2.6 = NOT PASSED
```

Hosted GitHub Actions 继续不使用；提交使用 `[skip ci]`。Repository tests 不等于本机 pytest/Qwen/CUDA PASS。
