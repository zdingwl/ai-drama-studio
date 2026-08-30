---
name: ai-drama-studio-reference-video-v2
version: 3.13.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1 已进 production，真实 Windows/Qwen 验收待完成。
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

Latest real run before Fast Grounded was rejected:

```text
30 Shots -> 21 LocalSubjects
Scene 04 / 19 Shots -> 14 temporary people although actual cast stayed one woman + one man
Shot 0001 visible image -> blue roses/vase
old visual result -> leaked neighboring surprised young woman
legacy E3 -> 30/30 TimeoutExpired fallback
~1 minute Episode -> multi-hour runtime class
```

Core rules:

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

## 2. Current Breakdown production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Fast Grounded Qwen3-VL, one model load
   ├─ Window Context
   │    24s target / 25% overlap / 1 FPS / ~262k pixels
   │    Scene + subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s: 1 frame
        1.2..3s: 2 frames
        >3s: 3 frames
        default 5 Shots/batch
        visible people/actions/props/shot prose only from current Shot images
→ one immutable exact-Shot VLM_OUTPUT sidecar
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

Legacy `breakdown_p2_refinement_v1.py` / `run_breakdown_refinement_qwen3.py` remain only for historical artifacts/tests, not production execution.

## 3. Reference Video invariants

Keep:

```text
FFprobe authoritative media facts
FFmpeg preprocess/proxy/audio/frame extraction
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
per-Shot Reference Clip / thumbnail / keyframes
manual edit / split / merge / rerun / restore
```

Shot boundaries are exact timing/edit coordinates, not semantic-context limits. Historical Runs remain anchored to frozen ShotRevision/ShotRevisionItem.

## 4. P1 / identity boundaries

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

Fast Grounded does not introduce a destructive Draft schema migration.

## 5. Window Context rules

Window Context may output:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

It answers continuity questions only: same Scene vs real Scene change, anonymous subject continuity and plot-relevant prop continuity.

It must not own current-Shot visible people/actions/props or final shot prose. The same Episode window must not be repeatedly video-encoded merely to emit different Shot JSON batches.

## 6. Exact-Shot grounding rules

Exact frozen Shot frames own visible truth:

```text
shot.summary visible content
shot.visual_description
shot_type / composition
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Only Scene fields may conservatively borrow Window Context when current Shot frames cannot show enough environment.

Forbidden:

```text
neighbor person -> current Shot subject
neighbor action -> current Shot event
neighbor prop -> current Shot prop
neighbor framing -> current Shot photography fact
```

Mandatory regression:

```text
Shot 0001 blue roses/vase insert
=> subjects=[]
=> description=flowers/vase
=> no leaked woman
```

## 7. Scene + Dialogue rules retained inside E4

Scene:

```text
strong scene evidence establishes current Scene
missing / UNKNOWN / generic / closeup -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT ↔ EXT contradiction -> new Scene
```

Dialogue:

```text
ASR_SEGMENT = Episode-time dialogue text truth
ASR_WORD = SUPPORT timing/confidence evidence
Shot DIALOGUE TimelineEvent = projection
```

Cross-Shot dialogue keeps full text + shared group/projection/continuation metadata. UI continuation rows are suppressed as duplicate text.

## 8. E4 anonymous Subject Continuity Graph

```text
Shot-local subject_A/B = observation labels only
node = exact ShotRevisionItem + subject label
primary edge = Window Context subject_continuity_hint
fallback edge = strong stable-appearance similarity across nearby Shots
hard negative = same-Shot cannot-link
cluster = Scene-scoped LocalSubject
LocalSubject != Character
```

Dynamic state must not be identity key:

```text
exclude expression / emotion / action / pose / speaking / screen position / camera framing
```

Fallback may use hair, clothing, persistent accessories and other stable cues. Ambiguous evidence stays separate. Same-Shot cannot-link is transitive through graph union.

## 9. Legacy E3 status

The old text-only per-Shot E3 is retired from production because it loaded a vision model for text-only work, ran once per Shot, timed out on the real 30-Shot case and could not repair bad E2 visual truth.

Historical compatibility helpers/modules may remain importable. Do not describe legacy E3 as current production quality truth.

## 10. G2 Scene-level text LLM target

G2 is planned only after G1 real acceptance.

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

The text model may organize/summarize existing evidence but may not invent visible facts or Final identity.

Target UI is Scene Timeline first. Exact Shot remains clickable visual evidence/location detail.

## 11. Provider / Contract boundaries

ASR = faster-whisper large-v3 / Episode audio / word timestamps.  
OCR = RapidOCR.  
VLM = Qwen3-VL-4B-Instruct / Fast Grounded Window Context + Exact-Shot frames.  
Fusion = deterministic E4 graph + conservative Scene/Dialogue rules.  
G2 = pure-text LLM, planned, one call per Scene.

No Breakdown stage writes Final Character/Scene/Prop/Binding truth.

## 12. Character V10.1 protected baseline

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax new-identity evidence thresholds, same-sample cannot-link, face hard conflict, ambiguity or explicit Shot assignment. Breakdown anonymous continuity is only a Draft prior.

## 13. Performance gate

Reference material:

```text
60 seconds / ~30 Shots / ~4 Scenes
```

Targets:

```text
first: complete Breakdown < 30 min
later: 60s -> 10..20 minute class
60s -> 5..6h = FAIL
```

The Fast Grounded runner must load Qwen3-VL once per Episode run. Window video is processed once per window; exact Shots use image batches instead of replaying full videos.

Actual performance is only accepted from Windows/CUDA elapsed-time logs, not from code inspection.

## 14. P3 / P4 / P5

P3 current Shot-card result view remains implemented but is not the final result design.  
P4 remains Draft-guided Scene/Prop with current-revision visual re-verification.  
P5 Character safe integration remains paused until Breakdown passes local-real acceptance.

## 15. P2.6 acceptance

Current:

```text
latest real run = REJECTED (pre Fast Grounded)
Fast Grounded G1 local-real = PENDING
P2-E4 under grounded input = PENDING
P2.6 = NOT PASSED
```

Next real run must verify:

```text
Shot 0001 blue roses/vase has no leaked woman
same-scene closeup/insert inherits correct Scene
real Scene changes still split
19-Shot living room -> actual one woman + one man becomes roughly two LocalSubjects
subject_A/B swaps do not create new people
same-Shot people never merge
cross-Shot dialogue remains whole without duplicate UI continuation
runtime is dramatically below old multi-hour class and stage elapsed times are recorded
Character V10.1 / Final Assets remain untouched
```

Only real-video + human review may move P2.6 to PASS.

## 16. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Do not report tests/model quality as passed unless actually executed locally.

Current targeted coverage:

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

## 17. Phase pointer

```text
P0 COMPLETE
P1 CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
Fast Grounded G1 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
legacy E3 RETIRED FROM PRODUCTION
G2 PLANNED / NOT IMPLEMENTED
P2.6 NOT PASSED
P3 current UI IMPLEMENTED / NOT FINAL ACCEPTED
P4 IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 PLANNED / PAUSED
```

Immediate safe work: `git pull`, rerun the exact rejected Episode, inspect Shot 0001 visible truth first,
then inspect Scene 04 LocalSubject continuity and actual runtime. Fix G1 before G2/UI/P5.
