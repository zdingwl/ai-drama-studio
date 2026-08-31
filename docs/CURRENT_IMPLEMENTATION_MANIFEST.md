# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-31 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Window Context: SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: COMPACT-RECONSTRUCTION V3 / PRODUCTION / PERFORMANCE+SHOT QUALITY POSITIVE
P2-E6 Fusion: IMPLEMENTED / TARGETED LOCAL TEST PASS
Fresh production performance: PASS / 14.098 min / <=20min YES
Fresh Scene segmentation: POSITIVE / 2 Scenes
Fresh Shot0001 visible truth: POSITIVE
Fresh anonymous continuity: REGRESSION / Scene1=4 / Scene2=16 LocalSubjects
same-Shot hard safety: PASS / conflicts=0
P2.6 Windows / real-model acceptance: NOT PASS (anonymous continuity regression)
G2 Scene-level text LLM: BLOCKED / NOT IMPLEMENTED
Scene Timeline UI: BLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Performance tuning and Window-v4 are frozen. Character V10.1 is protected. Do not loosen
same-Shot cannot-link or Final identity gates. Current debugging scope is anonymous LocalSubject
continuity only.

## Latest final production Run

```text
Run = BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
whole run = 845.898s = 14.098 min
ASR = 15.884s
OCR = 264.235s
VLM = 564.050s
```

```text
Window Context = 84.910s
Exact-Shot = 459.158s
model load = 6.896s
58 grounding frames
10 generation attempts
0 MAXED
```

Window:

```text
4/4 READY
276, 304, 237, 233 output tokens / 1600
```

Exact-Shot:

```text
batch1 75.501s |  993/4096 | READY | attempts=1
batch2 58.314s |  763/4096 | READY | attempts=1
batch3 78.236s | 1027/4096 | READY | attempts=1
batch4 80.167s | 1055/4096 | READY | attempts=1
batch5 84.011s | 1088/4096 | READY | attempts=1
batch6 81.942s | 1061/4096 | READY | attempts=1
```

Quality:

```text
Shot0001 subjects=0
Shot0001 props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
Scenes=2
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=4
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=16
same_shot_cluster_conflicts=0
```

Performance and Shot/Scene truth pass, but anonymous continuity does not.

## Previous continuity quality baseline

```text
Run = BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
Shot0001 subjects=0
```

This baseline proves the accepted E6/replay-v3 continuity policy can resolve the Episode correctly
when its evidence is sufficiently discriminative. The new final production Run must be diagnosed
against its compact Exact-Shot observations and Window-v4 subject hints before changing policy.

## Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ Qwen3-VL one model load
   ├─ Window Segment-index v4
   │    24s / 25% overlap / 1 FPS / 262144 px / 1600 tokens
   └─ Exact-Shot Compact-Reconstruction v3
        1..3 frames / 524288 px / 4096 tokens / 5 Shots per batch
→ immutable VLM_OUTPUT sidecar
→ P2-E6 Episode-context Fusion
   ├─ Scene corridor-family continuity + DIRECT boundary safeguard
   ├─ ASR_SEGMENT dialogue truth
   └─ anonymous continuity Stage1..4 + hard same-Shot cannot-link
→ P1 validator
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v1
```

## Production modules

```text
P2 sidecar                         engine/app/breakdown_p2_sidecar_v1.py
ASR                                engine/app/breakdown_p2_asr_v1.py
OCR                                engine/app/breakdown_p2_ocr_runtime_v1.py
Fast Grounded semantic base        engine/app/breakdown_p2_vlm_fast_grounded_v1.py
Production timing provider v3      engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
Production continuity wrapper      engine/app/breakdown_p2_vlm_continuity_v1.py
Window production v4               scripts/run_breakdown_vlm_window_segment_index_v4.py
Exact-Shot production v3           scripts/run_breakdown_vlm_exact_shot_compact_v3.py
Timed production entry             scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py
Production E6 Fusion               engine/app/breakdown_p2_fusion_episode_v6.py
Read-only replay v3                engine/app/breakdown_g1_fusion_replay_v3.py
Completed-run replay adapter       engine/app/breakdown_g1_fusion_replay_completed_v3.py
Continuity stage diagnostic        engine/app/breakdown_g1_subject_continuity_stage_diagnostics_v1.py
Continuity stage inspector         scripts/inspect_breakdown_subject_continuity_stages.py
```

## Anonymous continuity invariants

```text
subject_A/B = Shot-local observations only
LocalSubject != Character
same-Shot observations = hard cannot-link
explicit male/female contradiction blocks soft union
explicit long-hair vs short/bald contradiction blocks soft union
missing attribute is not contradiction
expression/emotion/action/pose/speaking/screen position/framing are not identity keys
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## Testing / CI discipline

User-local evidence:

```text
12/12 E6/v3 Fusion targeted tests PASS
3/3 Exact-Shot compact-v3 targeted tests PASS
Window-v4 real diagnostic 4/4 READY
Exact-Shot-v3 selected real batches READY
final full production Run performance 14.098 min
final full production same-shot conflicts=0
```

The final full Run also produced the new LocalSubject fragmentation regression; therefore it is
explicit evidence to reopen only the continuity layer. Do not claim P2.6 PASS.

Hosted GitHub Actions remain unused.

## Next required action

Do **not** rerun the Episode yet.

Run the completed-run, provider-free stage diagnostic:

```powershell
python scripts\inspect_breakdown_subject_continuity_stages.py `
  --run-id BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
```

Use it to determine whether fragmentation originates in:

```text
Stage1 Window hint resolution
Stage2 compact appearance fallback
Stage3 cluster bridge
Stage4 coherent component bridge
```

Then build a read-only replay candidate against the same immutable sidecars. Only promote a fix if
the replay returns approximately 2 anonymous people per Scene, keeps conflicts=0, and does not
weaken Character or same-Shot safety. Only after that should one final production Run be executed.
