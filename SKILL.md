---
name: ai-drama-studio-reference-video-v2
version: 3.12.0
description: Reference Video V2 / Episode-context Breakdown / Character V10.1；P2-E4 anonymous subject continuity 已进 production，真实短剧验收仍未通过。
---

# AI Drama Studio — Reference Video V2 / Episode-context Breakdown / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
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
Architecture: Reference Video V2
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2-E1 Scene/Dialogue continuity: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement: IMPLEMENTED / LOCAL-REAL QUALITY NOT ACCEPTED
P2-E4 final Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / real-model acceptance: NOT PASSED
P3 02 拉片 UI: IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

Latest pre-E4 real run was rejected: 30 Shots -> 21 LocalSubjects; Scene 04 / 19 Shots -> 14 temporary people although the scene visually stayed one woman + one man. E3 timed out for the run and fell back to E2.

Core rules:

> **先看懂，再识别，再回填。**

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 2. Current Breakdown production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ P2-E2 overlapping Episode-window Qwen3-VL
→ preserve E2 subject/prop continuity hints
→ P2-E3 contextual Shot refinement
   └─ E3-only failure -> FALLBACK_E2
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
→ E2 breakdown_p2_vlm_episode_v2.py
→ E3 breakdown_p2_refinement_v1.py
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
base = breakdown-p2-fusion-episode-context-e1-v2
```

## 3. Reference Video invariants

Keep:

```text
FFprobe authoritative media facts
FFmpeg preprocess/proxy/audio
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
per-Shot Reference Clip / thumbnail / keyframes
manual edit / split / merge / rerun / restore
```

Shot boundaries are exact timing/edit coordinates, not semantic-context limits. Historical Runs remain anchored to frozen ShotRevision/ShotRevisionItem.

## 4. P1 / identity boundaries

Formal Draft tables stay unchanged. E4 is not a destructive schema migration.

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

## 5. E1 Scene + Dialogue rules retained inside E4

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

## 6. E2 window continuity

Default: 24s target, 20..40s allowed, 25% overlap, 10..50% allowed, Shot-aligned, sequential, proxy-first/source-fallback.

Qwen window output includes:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
  revision_item_id
  scene_continuity
  scene_basis
  context_note
  semantic.scene/shot/subjects/events/props
```

The old E2 normalizer discarded subject/prop continuity hints. Production now preserves them via `breakdown_p2_vlm_continuity_v1.py` in `ProviderResult.metadata.window_summaries`. No frozen sidecar/API migration is introduced.

## 7. E3 contextual Shot refinement

E3 is text-only and consumes:

```text
provisional Scene
+ Previous/Current/Next E2 semantics
+ E2 window context
+ overlapping ASR_SEGMENT
+ overlapping OCR observations
```

Hard rules:

```text
only current Shot may be refined
neighbor-only people/objects cannot be imported
current E2 subject labels are the only allowed labels
ASR/OCR text stays read-only
no speaker identity inference
no Final business IDs
shot type/camera/composition stay E2-grounded
```

E3 is a quality layer, not source truth. Any E3-only runtime/model/subprocess/timeout failure falls back to validated E2 with explicit `FALLBACK_E2`. E2 visual failure still fails closed. An all-fallback run does not count as E3 quality acceptance.

## 8. E4 anonymous Subject Continuity Graph

Old Fusion linked people by exact normalized `appearance_summary`. This was rejected by real-video acceptance because expression/pose/action wording changes fragmented one person into many LocalSubjects.

E4 semantics:

```text
Shot-local subject_A/B = observation labels only
node = exact ShotRevisionItem + subject label
primary edge = E2 subject_continuity_hint
fallback edge = strong stable-appearance similarity across nearby Shots
hard negative = same-Shot cannot-link
cluster = Scene-scoped LocalSubject
LocalSubject != Character
```

Dynamic state must not be an identity key:

```text
exclude expression / emotion / action / pose / speaking / screen position / camera framing
```

Stable fallback may use hair, clothing, persistent accessories and other stable visual cues. It must remain conservative: ambiguous evidence stays separate.

Same-Shot cannot-link is enforced transitively during union, so a bad model hint cannot indirectly merge two people visible together.

E4 provenance is retained in LocalSubject `appearance_json` and Fusion metadata.

## 9. Provider / Contract boundaries

ASR = FasterWhisper large-v3 / Episode audio / word timestamps.  
OCR = RapidOCR PP-OCRv6 small.  
VLM = Qwen3-VL-4B-Instruct / overlapping Episode windows → optional E3 refinement.  
Fusion = deterministic E4 graph + E1 Scene/Dialogue rules.

No P2 stage writes Final Character/Scene/Prop/Binding truth.

## 10. Character V10.1 protected baseline

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax new-identity evidence thresholds, same-sample cannot-link, face hard conflict, ambiguity or explicit Shot assignment. E4 anonymous continuity is only a Draft prior.

## 11. P3 / P4 / P5

P3 remains implemented with `镜头管理 + 拉片结果`. Technical provenance stays backend truth.  
P4 remains Draft-guided Scene/Prop with current-revision visual re-verification.  
P5 Character safe integration remains paused until Episode-context Breakdown passes local-real acceptance.

## 12. P2.6 acceptance

Current:

```text
latest real pre-E4 run = REJECTED
P2-E4 local-real = PENDING
P2.6 = NOT PASSED
```

Required next real run must re-run the same Episode and verify:

```text
19-Shot living room -> actual one woman + one man becomes roughly two LocalSubjects
subject_A/B label swaps do not create new people
expression/action/pose changes do not create new people
same-Shot people never merge
genuine new people remain distinct
Scene continuity / genuine scene changes do not regress
cross-Shot dialogue remains whole with no duplicate UI continuation
E3 TimeoutExpired remains explicit FALLBACK_E2 if it repeats
Character V10.1 / Final Assets remain untouched
```

Only real-video + human review may move P2.6 to PASS.

## 13. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]`. Do not report tests/model quality as passed unless actually executed locally.

E4 unit coverage:

```text
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

## 14. Phase pointer

```text
P0 COMPLETE
P1 CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 IMPLEMENTED / LOCAL-REAL QUALITY NOT ACCEPTED
P2-E4 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 NOT PASSED
P3 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 PLANNED / PAUSED
```

Immediate safe work: `git pull` and re-run the exact rejected Episode so new E2 continuity metadata + E4 Fusion are generated. Inspect LocalSubject continuity before doing any further P5 work or declaring acceptance.
