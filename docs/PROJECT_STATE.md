# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-30 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2 + Breakdown Fast Grounded V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

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

Latest real run before Fast Grounded V2 was **REJECTED**:

```text
30 Shots
21 LocalSubjects total
Scene 04 / 客厅 / 19 Shots -> 14 LocalSubjects
actual visible continuity -> same one woman + one man
legacy E3 -> 30/30 TimeoutExpired -> FALLBACK_E2
Shot 0001 visible truth -> blue roses / vase
old result -> incorrectly described a surprised young woman from a neighboring Shot
runtime class -> multi-hour for ~1 minute video
```

This is evidence for the new G1 visual-grounding and performance blockers. It is not a PASS.

## 2. Product principles

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

> **Exact-Shot visible fact > Window Context.**

Hard semantic boundaries remain:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

## 3. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR observations
→ G1 Fast Grounded Qwen3-VL
   ├─ overlapping Episode Window Context
   │    default 24s / 25% overlap / 1 FPS / 262144 max pixels
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot frame grounding
        <1.2s: 1 frame
        1.2..3s: 2 frames
        >3s: 3 frames
        default 5 Shots/batch
        visible facts only from the exact frozen Shot frames
   both stages run inside one Qwen3-VL subprocess/model load
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
   ├─ conservative Scene continuity
   ├─ ASR_SEGMENT cross-Shot dialogue truth/projection
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal pipeline remains:

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

Formal APIs stay unchanged. Batch remains sequential by `Episode.sort_order`; heavy work remains globally serialized.

## 4. G1 Window Context

Window Context no longer writes the final per-Shot visual facts. It only provides:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

Its purpose is to decide continuity across cuts: same Scene, actual Scene change, anonymous person continuity and important prop continuity. It may not create current-Shot people/actions/props.

The expensive video window is analyzed once. Rapid-cut output batching must not replay the same 24-second video merely to emit different Shot JSON groups.

## 5. G1 Exact-Shot Grounding

Each frozen Shot is grounded from its own Reference Clip frames:

```text
< 1.2s  -> 50% frame
1.2..3s -> 25% + 75%
> 3s    -> 15% + 50% + 85%
```

Exact-Shot owns:

```text
shot.summary visible content
shot.visual_description
shot_type / composition
subjects presence / appearance / current activity
visible events
visible plot-relevant props
```

Window Context may only conservatively fill Scene fields when the exact Shot cannot show enough environment.

Mandatory regression:

```text
Shot 0001 blue-rose/vase insert
=> subjects=[]
=> description is flowers/vase
=> neighbor woman must never leak into this Shot
```

## 6. Scene + Dialogue rules

Scene:

```text
UNKNOWN / missing / generic / background-poor closeup -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT ↔ EXT contradiction -> new Scene
```

Rule: `看不出来 != 换场`.

Dialogue:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE TimelineEvent = projection, not sentence truth
```

Cross-Shot projections keep full ASR segment text and continuation metadata. Raw ASR_WORD remains immutable. The result UI suppresses duplicate continuation projections.

## 7. P2-E4 anonymous subject continuity

E4 stays production and consumes grounded exact-Shot subjects plus Window Context continuity hints.

```text
Shot-local subject_A / subject_B = observation labels only
anonymous Subject Continuity Graph = cross-Shot Draft continuity
LocalSubject = Scene-scoped anonymous cluster
LocalSubject != Character
```

Primary positive edges come from Window Context `subject_continuity_hints`; conservative fallback uses stable appearance only. Dynamic expression/emotion/action/pose/speaking/screen position/framing do not define identity.

Any two observations in the same Shot have a hard cannot-link, enforced transitively. Ambiguous evidence remains separate instead of forcing a false merge.

## 8. Legacy E3 status

`breakdown_p2_refinement_v1.py` and `scripts/run_breakdown_refinement_qwen3.py` remain for historical comparison/tests, but **text-only per-Shot E3 is retired from production**.

Reason:

```text
it loaded a vision model for a text-only task
it ran per Shot
latest real run timed out on all 30 Shots
it added cost without protecting exact-Shot visible truth
```

Its future product responsibility is replaced by:

```text
Exact-Shot visual grounding (G1)
+
Scene-level pure-text LLM organization (G2, planned)
```

## 9. G2 Scene-level text LLM / Scene Timeline

Planned after G1 real acceptance:

```text
Scene
+ exact-Shot grounded visual facts
+ ASR truth
+ OCR truth
+ E4 LocalSubject continuity
+ prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
```

The text model may organize/condense known evidence but may never invent visual facts or Final identities.

Target result surface is Scene-first readable script/timeline. Exact Shot remains clickable evidence/location detail rather than the primary reading structure.

## 10. Reference Video / history invariants

```text
FFprobe / FFmpeg preprocess
TransNetV2 Shot boundaries
integer microseconds
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
manual boundary edit / split / merge / rerun / restore
```

Historical Breakdown remains anchored to exact frozen ShotRevision/ShotRevisionItem and is never silently rebound.

## 11. Character protection

Character V10.1 remains protected:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Breakdown anonymous continuity cannot override same-sample cannot-link, face conflict, >=3 independent Shot/image gates, explicit assignment or Final Character truth.

## 12. Performance gate

Reference target:

```text
60 seconds / ~30 Shots / ~4 Scenes
```

First engineering target:

```text
complete Breakdown < 30 minutes
```

Second target after tuning:

```text
60s -> 10..20 minute class
```

`60s -> 5..6h` is a performance failure.

Current budget is documented in `docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md`. It is a target, not a measured PASS until the Windows/CUDA machine records real timings.

## 13. Validation reality / next acceptance

Fast Grounded code added:

```text
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
scripts/run_breakdown_vlm_fast_grounded_qwen3.py
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
```

Stable production runtime has been switched to Fast Grounded VLM. Remote code presence is not fresh local pytest/Qwen/CUDA PASS. Hosted GitHub Actions remain intentionally unused.

Next real run must rerun the same rejected Episode and verify:

```text
1. Shot 0001 blue roses/vase: no leaked woman
2. same-scene closeup/insert still inherits correct Scene
3. genuine Scene changes remain separate
4. Scene 04 / 19 Shots / one woman + one man -> roughly two stable LocalSubjects
5. subject_A/B swaps do not create new people
6. same-Shot people never merge
7. cross-Shot dialogue remains whole without UI duplicate continuation
8. total/stage runtime is recorded and dramatically lower than the old multi-hour run
9. Character V10.1 / Final Asset tables remain untouched
```

Only after real run + human review may P2.6 move toward PASS. Current truth remains **NOT PASSED**.

## 14. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Code/test files in the repository are not equivalent to local execution.

## 15. Next safe work

```text
A. git pull
B. rerun the exact rejected Episode
C. inspect Shot 0001 first
D. inspect 19-Shot living-room anonymous continuity
E. record elapsed time
F. fix G1 regressions before G2 Scene LLM or Scene Timeline UI
G. do not advance P5 until Breakdown passes real acceptance
```
