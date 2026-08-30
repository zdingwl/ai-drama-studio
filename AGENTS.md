# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

Current Breakdown truth:

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED
G1 Window Context + Exact-Shot Ground = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 anonymous continuity Fusion     = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
legacy text-only per-Shot E3          = RETIRED FROM PRODUCTION / HISTORICAL ONLY
G2 Scene-level text LLM               = PLANNED / NOT IMPLEMENTED
Scene Timeline result UI              = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Latest real run before Fast Grounded V2 was **REJECTED** for two independent reasons:

```text
1. 30 Shots produced 21 LocalSubjects; the 19-Shot living-room Scene produced 14 temporary
   subjects although the visible cast stayed one woman + one man.
2. Exact-Shot visible facts leaked from window context: Shot 0001 visibly showed blue roses in a
   vase, but the result described a surprised young woman's face from a neighboring Shot.
```

That run also had text-only E3 TimeoutExpired fallback and took roughly multi-hour class on a
~1-minute Episode. Never describe P2 as accepted/closed until the new Fast Grounded real run and
human review pass.

Core principles:

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是模型连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

## 1. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
6. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
7. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
8. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
9. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
10. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
11. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
12. current code/tests
13. latest docs/sessions/*.md handoff
```

Truth priority: `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT`.

## 2. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR (faster-whisper)
→ OCR (RapidOCR)
→ G1 Fast Grounded Qwen3-VL, one subprocess/model load
   ├─ low-cost overlapping Episode windows
   │    24s target / 25% overlap / 1 FPS / ~262k pixels
   │    output Scene + subject/prop continuity only
   └─ exact frozen Shot frame grounding
        <1.2s: 1 frame
        1.2..3s: 2 frames
        >3s: 3 frames
        ~5 Shots/batch
        visible people/actions/props/shot prose come only from exact-Shot frames
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
   ├─ Scene continuity
   ├─ ASR_SEGMENT dialogue truth + Shot projections
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator remains:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Production VLM path:

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

The old `breakdown_p2_refinement_v1.py` / `run_breakdown_refinement_qwen3.py` remain for historical
comparison/tests only. They are not production execution truth anymore.

## 3. Visual truth boundary

Window Context may provide only soft continuity/context:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

Exact-Shot grounding owns:

```text
shot.summary visible content
shot.visual_description
shot_type / composition
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Only Scene fields may inherit window context when exact-Shot images cannot show the environment.
Never import neighboring Shot people/actions/props into the current Shot.

Mandatory regression case:

```text
Shot 0001 = blue roses / vase insert
=> subjects=[]
=> props contains blue roses / vase when visible
=> visual description must describe the flowers, not the woman in the next Shot
```

## 4. Scene / Dialogue / anonymous identity

Scene rule:

```text
missing/UNKNOWN/generic environment -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT↔EXT contradiction -> new Scene
```

Dialogue rule:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE TimelineEvent = projection, not sentence truth
```

Cross-Shot projections preserve the full ASR sentence and continuation metadata; UI must not render
continuation projections as duplicate dialogue lines.

Shot-local `subject_A/subject_B` are observation labels only. E4 creates Scene-scoped anonymous
continuity clusters from window hints + conservative stable appearance fallback. Same-Shot people
have a hard cannot-link. Expression/emotion/action/pose/speaking/screen position/framing are not
identity keys.

## 5. Anonymous Draft is not Final identity

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
Breakdown Evidence != Final Asset/Binding truth
```

P4 may use Draft only as a search hypothesis after current-Shot visual verification.

## 6. Shot/history invariants

Keep Reference Video V2:

```text
FFprobe / FFmpeg
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
manual edit / split / merge / rerun / restore
```

Historical Breakdown anchors to the exact frozen ShotRevision/ShotRevisionItem. A new Current
ShotRevision makes incompatible active Runs STALE. No ordinal/timestamp guessing.

## 7. Character V10.1 is protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax same-sample cannot-link, high-quality face conflict, >=3 independent Shots/images for
new identity, ambiguity rules or explicit Shot assignment. Breakdown continuity is only a Draft prior.

## 8. Performance gate

Reference acceptance clip:

```text
60 seconds / ~30 Shots / ~4 Scenes
```

First engineering target:

```text
whole Breakdown < 30 minutes
```

Second target after tuning:

```text
60s video -> 10..20 minute class
```

`60s -> 5..6h` is performance failure, not an acceptable production baseline.

The G1 runner must load Qwen3-VL once per Episode run and must never re-encode the same Episode
window merely to emit different Shot JSON batches. Exact-Shot grounding uses images in small
batches instead of replaying full video clips.

## 9. G2 and result UI

Next planned stage after G1 real acceptance:

```text
Scene
+ exact-Shot grounded visual facts
+ ASR truth
+ OCR truth
+ E4 LocalSubject continuity
→ pure-text LLM, once per Scene
→ Scene Timeline Breakdown
```

The text LLM may organize, summarize and format known facts; it may not invent visual facts or Final
identity. The final user-facing 02 拉片 surface should be Scene Timeline first, with exact Shot as
clickable evidence/location detail rather than the primary reading structure.

Do not implement/accept the pretty Scene Timeline UI as a substitute for G1 visual correctness.

## 10. Acceptance gate

Current truth:

```text
latest real run = REJECTED (pre Fast Grounded)
G1 local-real = PENDING
P2-E4 local-real = PENDING under new grounded input
P2.6 = NOT PASSED
```

Next real run must use the same rejected Episode and verify:

```text
blue-rose Shot 0001 has no leaked woman
Scene continuity and genuine scene changes are correct
19-Shot living-room / actual one woman + one man -> roughly two stable LocalSubjects
subject_A/B swaps do not create new people
same-Shot people never merge
cross-Shot dialogue remains whole without UI duplicate continuation
60-second-class runtime is dramatically lower and stage elapsed times are recorded
Character V10.1 / Final Asset tables remain untouched
```

Only real-video + human review may move P2.6 toward PASS.

## 11. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Repository test files are not proof of
fresh local pytest/Qwen/CUDA PASS.

Fast Grounded coverage includes:

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

## 12. Documentation sync

When status changes keep aligned:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
latest docs/sessions/*.md handoff
```

## 13. Next safe work

```text
A. git pull
B. rerun the same rejected Episode on Windows/CUDA
C. inspect Shot 0001 blue roses first
D. inspect Scene 04 LocalSubject continuity
E. record total and stage runtime
F. fix G1 real regressions before implementing G2 Scene text LLM / Scene Timeline UI
G. do not advance P5 until Breakdown passes real acceptance
```
