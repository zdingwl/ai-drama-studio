---
name: ai-drama-studio-reference-video-v2
version: 3.14.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；Fast Grounded 已完成真实重跑，Shot0001 正向验证，G1/P2.6 仍待 Scene04/Scene/耗时验收。
---

# AI Drama Studio — Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
→ docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
→ current code/tests
→ latest docs/sessions/*.md handoff
```

Executable CURRENT = `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests`.

## 1. Current baseline

```text
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
legacy text-only per-Shot E3: RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level pure-text LLM: PLANNED / NOT IMPLEMENTED
Scene Timeline UI: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT PASSED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

## 2. Current real-run truth

Historical pre-Fast-Grounded failure baseline:

```text
30 Shots -> 21 LocalSubjects
old Scene04 / 19 Shots -> 14 temporary people
actual visible cast -> mainly one woman + one man
Shot0001 actual -> blue roses / glass vase
old result -> neighboring woman leakage
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute Episode -> multi-hour runtime class
```

Latest Fast Grounded V2 real rerun has already completed. Current UI:

```text
30 Shots
4 Scenes
Scene01 5 Shots
Scene02 5 Shots
Scene03 2 Shots
Scene04 18 Shots
```

Confirmed positive gate:

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage no longer observed
```

Still pending:

```text
Scene04 anonymous continuity
same-Shot hard cannot-link real result
4 Scene boundary correctness
whole-run elapsed
ASR/OCR/VLM timings
OCR short-noise recording only
```

Do not describe G1/P2.6 as PASS until those core gates receive real-data + human review.

## 3. Current Breakdown production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Fast Grounded Qwen3-VL, one model load
   ├─ Window Context
   │    24s / 25% overlap / 1 FPS / ~262k pixels
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        default 5 Shots/batch
        visible people/actions/props/shot prose only from current Shot images
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator remains `engine/app/breakdown_p2_pipeline_v1.py`, profile `breakdown-p2-full-v1`, provider order `ASR → OCR → VLM`.

Production VLM:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_runtime_v1.py
→ engine/app/breakdown_p2_vlm_fast_grounded_v1.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3.py
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
```

Legacy E2/E3 modules remain historical only.

## 4. Core semantic boundaries

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

Window Context only provides continuity/context:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

Exact-Shot owns visible truth:

```text
shot summary / visual_description
shot type / composition
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Forbidden:

```text
neighbor person -> current Shot subject
neighbor action -> current Shot event
neighbor prop -> current Shot prop
neighbor framing -> current Shot photography fact
```

## 5. Scene / Dialogue / E4 rules

Scene:

```text
strong scene evidence establishes current Scene
missing / UNKNOWN / generic / closeup -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT↔EXT contradiction -> new Scene
看不出来 != 换场
```

Dialogue:

```text
ASR_SEGMENT = Episode-time dialogue truth
ASR_WORD = support timing/confidence evidence
Shot DIALOGUE TimelineEvent = projection
```

Anonymous continuity:

```text
subject_A/B = Shot-local observation labels only
node = exact ShotRevisionItem + subject label
primary edge = Window Context continuity hint
fallback edge = conservative stable appearance
same-Shot observations = hard cannot-link
cluster = Scene-scoped LocalSubject
```

Dynamic expression/emotion/action/pose/speaking/screen position/framing are not identity keys.

## 6. G1 real-acceptance tooling

Read-only diagnostics:

```text
engine/app/breakdown_g1_acceptance_diagnostics_v1.py
engine/app/breakdown_g1_run_selector_v1.py
engine/app/breakdown_g1_acceptance_summary_v1.py
scripts/inspect_breakdown_g1_run.py
```

Recommended local command for the already-completed real rerun:

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

`--latest` only accepts completed Fast Grounded Runs. `--summary` changes terminal presentation only; the full JSON artifact is still written by default.

Do not rerun the Episode just to inspect the existing result. Rerun only after a concrete G1 fix.

Review:

```text
Shot0001 subject_count/props/visual truth
Scene count + boundaries
Scene04 LocalSubject count and source_members
subject_A/B swaps inside each LocalSubject
same_shot_cluster_conflicts
whole-run elapsed
provider timings
short OCR noise samples
```

Human review remains mandatory; counters do not auto-PASS P2.6.

## 7. Performance gate

```text
reference: ~60s / ~30 Shots / ~4 Scenes
first target: whole Breakdown <30 min
second target: 10..20 min class
5..6h = FAIL
```

Authoritative whole-run elapsed is `BreakdownRun.started_at -> completed_at`. Provider timings currently persist ASR/OCR/VLM only.

## 8. Character V10.1 protected baseline

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax identity safety because of Breakdown anonymous continuity.

## 9. G2 / Scene Timeline target

Only after G1 real acceptance:

```text
Scene
+ Exact-Shot grounded visual facts
+ ASR truth
+ OCR truth
+ E4 LocalSubject continuity
+ prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

G2 may organize known evidence but may not invent visible facts or Final identity. UI prettification cannot substitute for G1 correctness.

## 10. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Do not report repository tests/model quality as locally passed unless actually executed.

## 11. Immediate safe work

```text
git pull
→ python scripts/inspect_breakdown_g1_run.py --latest --summary
→ inspect Scene04 anonymous continuity
→ require same_shot_cluster_conflicts=[]
→ review current 4 Scene boundaries
→ record whole-run + provider timings
→ record OCR noise only
→ G1 failure: fix that G1 layer and rerun
→ G1 acceptable: begin G2 Scene-level text LLM
→ P5 remains paused until P2.6 genuinely passes
```
