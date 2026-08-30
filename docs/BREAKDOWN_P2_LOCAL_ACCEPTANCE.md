# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P1/P2 CONDITIONAL PASS / FAST GROUNDED G1 IMPLEMENTED / LOCAL-REAL NOT PASSED**  
> Date: 2026-08-30  
> Production pipeline: `breakdown-p2-full-v1`  
> Production G1 VLM: `breakdown-p2-vlm-fast-grounded-v1`  
> Production E4 Fusion: `breakdown-p2-fusion-episode-context-e4-v1`  
> Legacy text-only E3: **RETIRED FROM PRODUCTION**  
> Acceptance schema: `breakdown-p2-acceptance-v1`

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

最新 Fast Grounded 之前的真实 Run 明确 **REJECTED**：

```text
30 Shots
21 LocalSubjects
Scene 04 客厅 / 19 Shots -> 14 LocalSubjects
实际 visible cast -> 同一女一男
Shot 0001 实际 -> 蓝色玫瑰 / 花瓶特写
旧 VLM 结果 -> 错写为邻镜年轻女性面部特写
legacy E3 -> 30/30 TimeoutExpired / FALLBACK_E2
约 1 分钟视频 -> multi-hour runtime class
```

因此当前不能写 `P2 ACCEPTED`、`P2 CLOSED`、`P2.6 PASS`。

## 2. 当前正式生产链

```text
Episode Current ShotRevision
→ frozen BreakdownRun
→ Episode ASR
→ OCR
→ G1 Fast Grounded Qwen3-VL（同一进程只加载一次模型）
   ├─ Window Context
   │    24s target / 25% overlap / 1 FPS / 262144 max pixels
   │    只负责 Scene + subject/prop continuity
   └─ Exact-Shot frame grounding
        <1.2s: 1 frame
        1.2..3s: 2 frames
        >3s: 3 frames
        default 5 Shots/batch
        当前 Shot 可见事实只来自自己的图片
→ immutable exact-Shot VLM_OUTPUT sidecar
→ E4 Episode-context Fusion
   ├─ conservative Scene continuity
   ├─ ASR dialogue truth + projections
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
→ acceptance report
→ human review
```

正式模块：

```text
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
scripts/run_breakdown_vlm_fast_grounded_qwen3.py
engine/app/breakdown_p2_vlm_runtime_v1.py
engine/app/breakdown_p2_vlm_continuity_v1.py
engine/app/breakdown_p2_fusion_episode_v4.py
engine/app/breakdown_p2_pipeline_v1.py
engine/app/breakdown_p2_acceptance_v1.py
```

旧 `breakdown_p2_refinement_v1.py` / `run_breakdown_refinement_qwen3.py` 只保留历史比较与测试，不是当前生产链。

## 3. G1 Window Context 验收

默认：

```text
window target = 24 秒
overlap = 25%
window edge = Shot boundary
window fps = 1.0
window max pixels = 262144
Episode 顺序推理
READY proxy 优先，Episode source fallback
```

允许输出：

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

硬规则：

```text
cut != scene change
closeup / blur / insert 可借上下文判断 Scene
Window 不负责 current Shot 的最终人物/动作/道具/画面描述
Window 不能把邻 Shot 可见事实写成当前 Shot truth
同一个 window 不得仅为了不同 Shot JSON batch 重复做完整视频编码
no ASR/OCR transcription
no Final asset IDs
```

## 4. G1 Exact-Shot Grounding 验收

抽帧：

```text
<1.2s  -> 50% 位置 1 张
1.2..3s -> 25% + 75% 两张
>3s -> 15% + 50% + 85% 三张
```

Exact-Shot 必须拥有：

```text
shot.summary visible content
shot.visual_description
shot_type / composition
subjects presence / appearance / activity
visible events
visible plot-relevant props
```

只允许 Window Context 补：

```text
scene.location_hint
scene.interior_exterior
scene.time_of_day
scene.environment_description
```

禁止：

```text
neighbor person -> current subjects
neighbor action -> current events
neighbor prop -> current props
neighbor visual -> current visual_description
```

### 必测回归：Shot 0001 蓝玫瑰

当前真实素材中 Shot 0001 是蓝色玫瑰/花瓶特写。

必须满足：

```text
subjects = []
visual description = 蓝色玫瑰 / 花瓶等当前画面事实
props contains visible blue roses / vase when model recognizes them
Scene 可以从连续上下文继承
```

禁止再次输出“年轻女性面部特写 / 表情惊讶”等邻镜事实。

## 5. E4 匿名人物连续性验收

语义模型：

```text
subject_A / subject_B = Shot-local observation label
anonymous graph node = (ShotRevisionItem, subject label)
LocalSubject = Scene-scoped anonymous continuity cluster
LocalSubject != Character
```

Primary positive edge：Window Context `subject_continuity_hint`。  
Fallback：相邻/近邻 Shot 的强稳定外观相似。

动态状态必须从 identity-like continuity key 中剥离：

```text
表情 / 情绪
动作 / 姿态 / 手势
是否说话
screen position
shot/camera framing
```

可作为 soft stable cue：发型、发色、服装、长期配饰、性别表现、年龄段。

Hard negative：同一 Shot 同时出现的任意两个 observations = cannot-link，且必须传递安全。

### 本轮真实验收重点

```text
Scene 04 客厅 / 19 Shots / visible cast = 一女一男
期望：roughly 2 stable LocalSubjects
禁止：人物 A-N 式碎片化
```

同时验证 label swap 不造新人、动作/情绪改变不造新人、同镜两人绝不合并、真正新人物仍分开。

## 6. Scene / Dialogue 回归

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

跨镜 projections 必须共享 group + continuation metadata；UI 不得重复显示完整 continuation 文本。

## 7. Provenance / Contract

每条最终 VLM Evidence：

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen ShotRevisionItem
source_start_us/end_us = exact Shot range
```

Fast Grounded payload：

```text
payload.semantic = grounded semantic consumed by Fusion
payload.exact_shot_semantic = exact frame result before Scene inheritance
payload.episode_window = selected Scene context provenance
payload.exact_shot_grounding = sampling + visual truth policy
```

Provider metadata：

```text
production_vlm_profile = breakdown-p2-vlm-fast-grounded-v1
model_load_policy = one-run-one-vlm-process-one-model-load
window_summaries = continuity context for E4
```

Historical Run/sidecar 不重写；只有新 Run 使用新 G1 行为。

## 8. Runtime / 性能验收

API：

```text
GET /api/breakdown/p2/runtime-preflight
```

CLI：

```text
python scripts/run_breakdown_p2.py preflight --strict
```

基础条件至少确认 main Python / faster-whisper / RapidOCR / OpenCV / FFmpeg / FFprobe / isolated Qwen runtime / checkpoint / CUDA when requested / nvidia-smi。

性能参考素材：

```text
60 秒 / ~30 Shots / ~4 Scenes
```

第一目标：

```text
完整 Breakdown < 30 min
```

第二目标：

```text
60s -> 10..20 minute class
```

`60s -> 5..6h` 一律 FAIL。必须记录至少 ASR/OCR/VLM/Fusion 总体 elapsed；后续再细化 Window 与 Grounding 分项 profiler。

Preflight 只能证明环境存在，不等于真实速度/质量 PASS。

## 9. G2 / Scene Timeline（当前不验收）

G2 仍是 planned：

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

G2 不负责看视频，也不能创造视觉事实。Scene Timeline UI 也不能在 G1 错误时用更漂亮的排版掩盖错误。

## 10. Acceptance Contract

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
Shot 0001 blue-rose grounding
neighbor visual leakage = yes/no
Scene 04 LocalSubject count
same-Shot cannot-link result
label-swap result
cross-Shot dialogue UI behavior
actual total runtime
```

PASS 仍要求 required scores >=4.0 且 blocking_issues 为空。机器指标不能自动变成 PASS。

## 11. Identity / Final Asset 禁止事项

```text
LocalSubject != Character
subject continuity hint != ReID evidence
ASR speaker != Character
Draft Scene/Prop != Final Scene/Prop
```

Character V10.1 的 Person Evidence / MOT / YoutuReID / same-sample cannot-link / face hard conflict / >=3 independent Shots/images / explicit Shot assignment / Final Gate 全部保持不变。

## 12. 测试 / CI

专项覆盖：

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

Hosted GitHub Actions 不使用。代码存在不等于本机 pytest/Qwen/CUDA PASS。

## 13. 下一步操作

```text
git pull
→ 同一个失败 Episode “重新拉片本集”
→ 第一眼检查 Shot 0001 蓝玫瑰，不要先看别的
→ 再检查 Scene 04 / 19 镜人物连续性
→ 记录实际总耗时
→ 有 G1 错误先修 G1
→ G1 通过后再做 G2 Scene LLM / Scene Timeline UI
→ P2.6 未真实 PASS 前 P5 继续 PAUSED
```
