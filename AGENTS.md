# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

Current Breakdown truth:

```text
P1/P2 implementation acceptance      = CONDITIONAL PASS
P2-E1 Scene/Dialogue continuity       = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window Qwen3-VL      = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement      = IMPLEMENTED / LOCAL-REAL QUALITY NOT ACCEPTED
P2-E4 final Episode-context Fusion    = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 02 拉片 UI                         = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Latest pre-E4 real run was **REJECTED**: 30 Shots produced 21 LocalSubjects; the 19-Shot living-room Scene produced 14 temporary subjects although the visible cast stayed one woman + one man. E3 timed out for the run and explicitly fell back to E2. Never describe P2 as accepted/closed until a new real run receives required human PASS.

Core principles:

> **先看懂，再识别，再回填。**

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 1. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
6. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
7. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
8. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
9. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
10. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
11. current code/tests
12. latest docs/sessions/*.md handoff
```

Truth priority: `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT`.

## 2. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ P2-E2 overlapping Episode-window Qwen3-VL
→ preserve E2 subject/prop continuity hints
→ P2-E3 contextual Shot refinement
   └─ E3-only runtime/model/subprocess/timeout failure -> FALLBACK_E2
→ one immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E4 Episode-context Fusion
   ├─ E1 Scene continuity fallback
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

Production VLM used by the pipeline:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_runtime_v1.py
→ E2 engine/app/breakdown_p2_vlm_episode_v2.py
→ E3 engine/app/breakdown_p2_refinement_v1.py
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
base = breakdown-p2-fusion-episode-context-e1-v2
```

Formal APIs remain unchanged. Batch Breakdown remains sequential by `Episode.sort_order`; heavy jobs remain globally serialized.

## 3. E1 Scene / Dialogue rules retained in E4

Scene:

```text
missing / UNKNOWN / generic environment -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT ↔ EXT contradiction -> new Scene
```

Rule: `看不出来 != 换场`.

Dialogue:

```text
ASR_SEGMENT = Episode-time dialogue text truth
Shot DIALOGUE TimelineEvent = projection, not sentence truth
```

Cross-Shot projections keep full ASR text + `dialogue_group_id/asr_segment_id` + continuation metadata. Raw ASR_WORD stays immutable. UI continuation projections are not rendered as duplicate dialogue lines.

## 4. E2 continuity evidence

Default window: 24s, allowed 20..40s, overlap 25%, allowed 10..50%, Shot-aligned, sequential, READY proxy first then Episode source fallback.

Window output includes:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
```

The old normalizer discarded subject/prop continuity hints. Production now preserves them in `ProviderResult.metadata.window_summaries` through `breakdown_p2_vlm_continuity_v1.py`. Frozen sidecar/API schema does not change.

## 5. E3 rules

E3 is text-only quality refinement after E2. It consumes Scene + Previous/Current/Next E2 semantics + E2 window context + overlapping ASR/OCR. It may not import neighbor-only people/objects, rewrite ASR/OCR truth, create new current-Shot subject labels or generate Final IDs.

E3 is not source truth. E3-only failure returns explicit `FALLBACK_E2`; only E2 visual failure fails VLM closed. A run that falls back for all Shots does not count as E3 quality acceptance.

## 6. E4 anonymous subject continuity

Shot-local `subject_A/subject_B` are observation labels only and may swap between Shots. They are never global identity keys.

E4 builds a Scene-scoped anonymous graph:

```text
node = (ShotRevisionItem, subject_label)
primary positive edge = E2 subject_continuity_hint
fallback positive edge = strong stable-appearance similarity across nearby Shots
hard negative = any two observations from the same Shot
cluster = LocalSubject Draft continuity
```

Stable appearance fallback excludes dynamic state:

```text
expression / emotion / action / pose / speaking / screen position / camera framing
```

It prefers hair, clothing, persistent accessories and other stable cues. Same-Shot cannot-link is hard and checked transitively during union. Ambiguous evidence stays separate instead of forcing a merge.

E4 writes no Character/Final Asset truth. `LocalSubject != Character` remains absolute.

## 7. Anonymous Draft is not identity truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
Breakdown Evidence != Final Asset/Binding truth
```

P4 may use Draft only as a search hypothesis after current-Shot visual verification.

## 8. Shot / history invariants

Keep Reference Video V2:

```text
FFprobe / FFmpeg
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
manual edit / split / merge / rerun / restore
```

Historical Breakdown always anchors to the exact frozen ShotRevision/ShotRevisionItem. New Current ShotRevision makes incompatible active Runs STALE. No ordinal/timestamp guessing.

## 9. Character V10.1 is protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax same-sample cannot-link, high-quality face conflict, >=3 independent Shots/images for new identity, ambiguity rules or explicit Shot assignment. E4 continuity is only a Draft prior.

## 10. Acceptance gate

Current truth:

```text
latest real pre-E4 run = REJECTED
P2-E4 local-real = PENDING
P2.6 = NOT PASSED
```

Next real run must verify the exact rejected Episode first:

```text
19-Shot living-room / actual one woman + one man -> roughly two stable LocalSubjects
subject_A/B swaps do not create new people
expression/action/pose changes do not create new people
same-Shot people never merge
genuine new people remain separate
Scene continuity/genuine scene changes do not regress
cross-Shot dialogue remains whole with no UI duplicate continuation
E3 timeout remains explicit FALLBACK_E2 if it repeats
Character V10.1 / Final Asset tables remain untouched
```

Only after real-video + human review may P2.6 become PASS.

## 11. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Repository test files are not equivalent to fresh local pytest/Qwen/CUDA PASS.

Current E4 unit coverage includes:

```text
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

## 12. Documentation sync

When status changes keep aligned:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
latest docs/sessions/*.md handoff
```

## 13. Next safe work

```text
A. git pull
B. re-run the same rejected Episode so new continuity metadata + E4 Fusion are generated
C. inspect LocalSubject count / 19-Shot living-room first
D. only after E4 continuity is sound, diagnose/optimize E3 TimeoutExpired separately
E. do not advance P5 until Episode-context Breakdown passes real acceptance
```
